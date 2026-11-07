#!/usr/bin/env python3
"""Allowlist DNS resolver for the DW worker container (1.2.0). Standard library only.

    python3 -I -B dns_allow.py [--port 5353]

Reads two environment variables (run_worker.sh sets both):
    DW_ALLOW_DOMAINS  space-separated names; "*.example.com" also allows every
                      name under example.com (not example.com itself)
    DW_DNS_UPSTREAM   space-separated IPv4 resolvers to ask

Listens on 127.0.0.1, UDP and TCP. entrypoint.sh runs it as user dwdns with no
capabilities, and the firewall lets only dwdns reach the upstream resolvers on
port 53. Port 53 on 127.0.0.1 is redirected here; port 53 anywhere else is
rejected.

For each query:
    not one plain question, or a malformed one     FORMERR
    the name is not on the list                    NXDOMAIN, nothing is sent upstream
    on the list, but not class IN type A or AAAA   REFUSED, nothing is sent upstream
    on the list, IN A or IN AAAA                   asked upstream
The upstream query is built from scratch: a random ID, the name in lower case,
the type, RD, and nothing else. No bit the worker chose (ID, letter case, extra
records, EDNS options) leaves the container; the reply gets the worker's ID and
question back. What still leaks: which listed name and type, and when (timing).
"""
import os
import random
import re
import socket
import socketserver
import struct
import sys
import threading

A, AAAA, IN = 1, 28, 1
NOERROR, FORMERR, SERVFAIL, NXDOMAIN, REFUSED = 0, 1, 2, 3, 5
LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
UPSTREAM_TIMEOUT = 3.0
MAX_ACTIVE = 64


def parse_list(text):
    """Allowlist text (one name per line or space-separated, # comments) -> sorted unique lower-case names.
    Raises ValueError naming the first bad entry."""
    names = set()
    for number, line in enumerate(text.splitlines(), 1):
        for word in line.split("#", 1)[0].split():
            name = word.lower().rstrip(".")
            labels = name[2:].split(".") if name.startswith("*.") else name.split(".")
            if not name or len(name) > 253 or not all(LABEL.match(label) for label in labels):
                raise ValueError(f"line {number}: not a host name: {word[:80]!r}")
            names.add(name)
    return sorted(names)


def allowed(name, names):
    """name: lower-case, no trailing dot. Exact match, or under a "*." entry."""
    if name in names:
        return True
    parts = name.split(".")
    return any("*." + ".".join(parts[i:]) in names for i in range(1, len(parts)))


def parse_query(packet):
    """-> dict(id, flags, qname_wire, name, qtype, qclass, end) for a one-question query. Raises ValueError."""
    if len(packet) < 12:
        raise ValueError("short header")
    qid, flags, qd, an, ns, ar = struct.unpack("!6H", packet[:12])
    if qd != 1:
        raise ValueError("not one question")
    pos, labels = 12, []
    while True:
        if pos >= len(packet):
            raise ValueError("name runs past the packet")
        size = packet[pos]
        if size == 0:
            pos += 1
            break
        if size > 63:
            raise ValueError("compressed or extended label")
        labels.append(packet[pos + 1:pos + 1 + size])
        pos += 1 + size
        if pos - 12 > 255:
            raise ValueError("name longer than 255 bytes")
    if pos + 4 > len(packet):
        raise ValueError("question runs past the packet")
    qtype, qclass = struct.unpack("!2H", packet[pos:pos + 4])
    name = ".".join(label.decode("latin-1") for label in labels).lower()
    return {"id": qid, "flags": flags, "qname_wire": packet[12:pos], "name": name,
            "qtype": qtype, "qclass": qclass, "end": pos + 4}


def reply(packet, rcode, q=None):
    """A header-only answer to packet (with its question when it parsed), or None when there is no header."""
    if len(packet) < 12:
        return None
    qid, flags = struct.unpack("!2H", packet[:4])
    flags = 0x8000 | (flags & 0x7900) | 0x0080 | rcode  # QR, opcode and RD kept, RA, rcode
    if q is None:
        return struct.pack("!6H", qid, flags, 0, 0, 0, 0)
    return struct.pack("!6H", qid, flags, 1, 0, 0, 0) + packet[12:q["end"]]


def upstream_query(q, qid):
    """The query asked upstream: nothing from the worker but the listed name and the type."""
    wire = b"".join(bytes([len(label)]) + label.encode("ascii") for label in q["name"].split(".")) + b"\0"
    return struct.pack("!6H", qid, 0x0100, 1, 0, 0, 0) + wire + struct.pack("!2H", q["qtype"], IN)


def decide(packet, names):
    """-> ("drop", None) | ("reply", bytes) | ("forward", q)."""
    if len(packet) < 12 or packet[2] & 0x80:  # no header, or a response
        return "drop", None
    try:
        q = parse_query(packet)
    except ValueError:
        return "reply", reply(packet, FORMERR)
    if (q["flags"] >> 11) & 0xF != 0:
        return "reply", reply(packet, REFUSED, q)
    if not allowed(q["name"], names):
        return "reply", reply(packet, NXDOMAIN, q)
    if q["qclass"] != IN or q["qtype"] not in (A, AAAA):
        return "reply", reply(packet, REFUSED, q)
    return "forward", q


def answer_for_worker(answer, sent, q, packet):
    """Upstream answer -> the answer for the worker (its ID and question back), or None when it does not match."""
    sent_question = sent[12:]
    if len(answer) < 12 + len(sent_question) or answer[:2] != sent[:2] or not answer[2] & 0x80:
        return None
    if struct.unpack("!H", answer[4:6])[0] != 1 or answer[12:12 + len(sent_question)] != sent_question:
        return None
    flags = struct.unpack("!H", answer[2:4])[0]
    flags = (flags & ~0x0100) | (q["flags"] & 0x0100)  # the worker's RD bit
    return packet[:2] + struct.pack("!H", flags) + answer[4:12] + packet[12:q["end"]] + answer[12 + len(sent_question):]


def ask_upstream(q, packet, upstream, tcp=False, port=53):
    for server in upstream:
        sent = upstream_query(q, random.SystemRandom().randrange(65536))
        try:
            if tcp:
                with socket.create_connection((server, port), timeout=UPSTREAM_TIMEOUT) as s:
                    s.sendall(struct.pack("!H", len(sent)) + sent)
                    answer = read_tcp_message(s)
            else:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.settimeout(UPSTREAM_TIMEOUT)
                    s.connect((server, port))
                    s.send(sent)
                    answer = s.recv(65535)
        except OSError:
            continue
        result = answer_for_worker(answer or b"", sent, q, packet)
        if result is not None:
            return result
    return reply(packet, SERVFAIL, q)


def read_exact(s, size):
    data = b""
    while len(data) < size:
        chunk = s.recv(size - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def read_tcp_message(s):
    head = read_exact(s, 2)
    return read_exact(s, struct.unpack("!H", head)[0]) if head else None


class Resolver:
    def __init__(self, names, upstream, log=sys.stderr, upstream_port=53):
        self.names, self.upstream, self.log, self.port = set(names), list(upstream), log, upstream_port
        self.active = threading.BoundedSemaphore(MAX_ACTIVE)
        self.denied, self.lock = set(), threading.Lock()

    def handle(self, packet, tcp=False):
        if not self.active.acquire(blocking=False):
            return None
        try:
            kind, value = decide(packet, self.names)
            if kind == "forward":
                return ask_upstream(value, packet, self.upstream, tcp, self.port)
            if kind == "reply" and value[3] & 0xF in (NXDOMAIN, REFUSED):
                self.note_denied(packet)
            return value
        finally:
            self.active.release()

    def note_denied(self, packet):
        try:
            q = parse_query(packet)
        except ValueError:
            return
        shown = "".join(c if c.isascii() and (c.isalnum() or c in ".-_*") else "?" for c in q["name"][:120])
        with self.lock:
            if shown in self.denied or len(self.denied) >= 100:
                return
            self.denied.add(shown)
        print(f"dns_allow: refused {shown or '.'} type {q['qtype']}", file=self.log, flush=True)


def serve(resolver, port, ready=None):
    """UDP and TCP on 127.0.0.1:port until the process ends. ready: threading.Event set once both listen."""
    class UDP(socketserver.BaseRequestHandler):
        def handle(self):
            data, sock = self.request
            out = resolver.handle(data)
            if out:
                sock.sendto(out, self.client_address)

    class TCP(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(10)
            try:
                while True:
                    data = read_tcp_message(self.request)
                    if not data:
                        return
                    out = resolver.handle(data, tcp=True)
                    if not out:
                        return
                    self.request.sendall(struct.pack("!H", len(out)) + out)
            except OSError:
                return

    class UDPServer(socketserver.ThreadingMixIn, socketserver.UDPServer):
        daemon_threads = True

    class TCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        daemon_threads = True
        allow_reuse_address = True

    servers = [UDPServer(("127.0.0.1", port), UDP), TCPServer(("127.0.0.1", port), TCP)]
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    for t in threads:
        t.start()
    if ready is not None:
        ready.set()
    return servers


def main(argv):
    port = 5353
    if argv[:1] == ["--port"] and len(argv) == 2 and argv[1].isdigit():
        port = int(argv[1])
    elif argv:
        print("usage: dns_allow.py [--port N]", file=sys.stderr)
        return 2
    try:
        names = parse_list(os.environ.get("DW_ALLOW_DOMAINS", ""))
    except ValueError as err:
        print(f"dns_allow: DW_ALLOW_DOMAINS {err}", file=sys.stderr)
        return 2
    upstream = os.environ.get("DW_DNS_UPSTREAM", "").split()
    if not names or not upstream or not all(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", u) for u in upstream):
        print("dns_allow: needs DW_ALLOW_DOMAINS and DW_DNS_UPSTREAM (IPv4 addresses)", file=sys.stderr)
        return 2
    serve(Resolver(names, upstream), port)
    print(f"dns_allow: 127.0.0.1:{port}, {len(names)} name(s), upstream {' '.join(upstream)}", flush=True)
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
