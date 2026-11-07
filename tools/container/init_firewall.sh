#!/bin/bash
# Outbound allowlist for the DW worker container, in two phases (entrypoint.sh
# starts the DNS resolver between them):
#   init_firewall.sh dns    policy DROP; loopback and replies allowed; only user
#                           dwdns (dns_allow.py) may reach DW_DNS_UPSTREAM on
#                           port 53; port 53 on 127.0.0.1 (resolv.conf, set by
#                           run_worker --dns) goes to dns_allow.py on port 5353;
#                           port 53 anywhere else is rejected. IPv6 dropped.
#   init_firewall.sh https  TCP 443 to the IPv4 addresses the names in
#                           DW_ALLOW_DOMAINS resolve to now ("*." names are
#                           skipped), then REJECT everything else.
#   DW_ALLOW_DOMAINS  space-separated host names (run_worker.sh sets it)
#   DW_DNS_UPSTREAM   space-separated IPv4 resolvers (run_worker.sh sets it)
# With --network none there is nothing to filter, so it only reports that.
set -euo pipefail
export PATH="/usr/sbin:/sbin:$PATH"   # iptables lives in /usr/sbin on Debian

ALLOW="${DW_ALLOW_DOMAINS:-api.anthropic.com}"
UPSTREAM="${DW_DNS_UPSTREAM:-}"
PHASE="${1:-}"

die() { echo "firewall: $*" >&2; exit 1; }

if [ -z "$(ls /sys/class/net 2>/dev/null | grep -v '^lo$' || true)" ]; then
  echo "firewall: no network interface besides lo; nothing to filter"
  exit 0
fi

case "$PHASE" in
  dns)
    [ -n "$UPSTREAM" ] || die "DW_DNS_UPSTREAM is empty; start the container with run_worker.sh"
    for ns in $UPSTREAM; do
      [[ "$ns" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || die "DW_DNS_UPSTREAM: not an IPv4 address: $ns"
    done
    iptables -F OUTPUT
    iptables -P OUTPUT DROP
    iptables -A OUTPUT -o lo -j ACCEPT
    iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    for ns in $UPSTREAM; do
      iptables -A OUTPUT -p udp -d "$ns" --dport 53 -m owner --uid-owner dwdns -j ACCEPT
      iptables -A OUTPUT -p tcp -d "$ns" --dport 53 -m owner --uid-owner dwdns -j ACCEPT
    done
    iptables -t nat -F OUTPUT
    iptables -t nat -A OUTPUT -d 127.0.0.1 -p udp --dport 53 -j REDIRECT --to-ports 5353
    iptables -t nat -A OUTPUT -d 127.0.0.1 -p tcp --dport 53 -j REDIRECT --to-ports 5353
    if command -v ip6tables >/dev/null 2>&1; then
      ip6tables -P OUTPUT DROP 2>/dev/null || true
      ip6tables -A OUTPUT -o lo -j ACCEPT 2>/dev/null || true
    fi
    echo "firewall: DNS only through dns_allow.py (upstream ${UPSTREAM})"
    ;;
  https)
    count=0
    for name in $ALLOW; do
      case "$name" in
        "*."*) continue ;;
      esac
      for addr in $(getent ahostsv4 "$name" | awk '{print $1}' | sort -u); do
        iptables -A OUTPUT -p tcp -d "$addr" --dport 443 -j ACCEPT
        count=$((count + 1))
      done
    done
    iptables -A OUTPUT -j REJECT --reject-with icmp-port-unreachable
    echo "firewall: allow 443 to ${count} address(es) of: ${ALLOW}"
    ;;
  *) die "usage: init_firewall.sh dns|https" ;;
esac
