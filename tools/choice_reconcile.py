"""Local ledger for choice-page replies (docs/12 第四、六節; 2.1.0, shadow mode). The Director records every reply in one
SQLite file before acting on it, so a crash, a second Director or a resent reply never starts the same work twice.

Ledger: <DIRECTOR>/choice_inbox.sqlite3 (--db). Tables: revisions (immutable question snapshots), inbox (every reply
seen, one row per source key), decisions (at most one adopted reply per question revision, with its state) and effects
(the fixed WO-ID of a decision, who claimed it, the result). Python standard library only.

  choice_reconcile.py register --db D --snapshot SNAP.json     snapshot of one question revision; prints its snapshotHash
  choice_reconcile.py ingest   --db D --export EXPORT.json     replies read from the page db (ArtifactData), see below
  choice_reconcile.py plan     --db D --question CH-01 --revision 1 [--wo WO-012] [--orders DIR]
  choice_reconcile.py advance  --db D --question CH-01 --revision 1 --from QUEUED --to CLAIMED [--session S] [--result T]
  choice_reconcile.py status   --db D [--now ISO] [--late-min 10] [--stuck-min 30] [--json]

EXPORT.json: {"source": "<artifact id>", "decisions": [...], "choiceReplies": [...], "notes": [...]}, each item the doc
fields plus "id". Replies of 2.1 questions come from choiceReplies; legacy questions (no revision) from decisions with
status answered (revision 0); notes become kind note rows.

States: RAW -> RECORDED -> PLANNED -> QUEUED -> CLAIMED | RECONCILE -> RECEIPT_PENDING -> CLOSED; RECONCILE -> CLAIMED |
QUEUED; RECORDED -> RECEIPT_PENDING for a duplicate, stale, conflicting or invalid reply. plan runs inside BEGIN
IMMEDIATE: the same question revision always gets the same WO-ID. advance changes a state only when it still is --from,
so of two Directors only one wins (the other gets exit 1 and the current state).

Shadow mode: status and ingest only print hints and always exit 0; nothing here blocks other tools or the old flow.
Exit 2 for a usage error or an unreadable file; plan / advance exit 1 when the state change did not happen.
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import re
import sqlite3
import sys

STATES = ("RAW", "RECORDED", "PLANNED", "QUEUED", "CLAIMED", "RECONCILE", "RECEIPT_PENDING", "CLOSED")
MOVES = {"RAW": {"RECORDED"}, "RECORDED": {"PLANNED", "RECEIPT_PENDING"}, "PLANNED": {"QUEUED"},
         "QUEUED": {"CLAIMED", "RECONCILE"}, "RECONCILE": {"CLAIMED", "QUEUED"}, "CLAIMED": {"RECEIPT_PENDING"},
         "RECEIPT_PENDING": {"CLOSED"}, "CLOSED": set()}
SEEN = ("PLANNED", "QUEUED", "CLAIMED", "RECONCILE")  # the Director has the reply but has not handed it over
SCHEMA = """
CREATE TABLE IF NOT EXISTS revisions (question_id TEXT, revision INTEGER, snapshot_hash TEXT, snapshot TEXT,
  registered_at TEXT, PRIMARY KEY (question_id, revision));
CREATE TABLE IF NOT EXISTS inbox (source_key TEXT PRIMARY KEY, kind TEXT, question_id TEXT, revision INTEGER,
  submission_id TEXT, payload TEXT, received_at TEXT, state TEXT, verdict TEXT);
CREATE TABLE IF NOT EXISTS decisions (decision_key TEXT PRIMARY KEY, question_id TEXT, revision INTEGER,
  source_key TEXT, choice TEXT, state TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS effects (effect_key TEXT PRIMARY KEY, decision_key TEXT UNIQUE, wo_id TEXT UNIQUE,
  claimed_by TEXT, claimed_at TEXT, result TEXT);
"""


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def snapshot_hash(snapshot):
    """sha256 of the snapshot without its own hash, keys sorted, UTF-8; the page and the ledger compare this value."""
    body = {k: v for k, v in snapshot.items() if k not in ("snapshotHash", "id")}
    text = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def connect(path, timeout=5.0):
    con = sqlite3.connect(str(path), timeout=timeout, isolation_level=None)
    con.executescript(SCHEMA)
    return con


def load_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"CHOICE_RECONCILE: cannot read {path}: {error}")
        sys.exit(2)


def cmd_register(args):
    snap = load_json(args.snapshot)
    qid, rev = snap.get("questionId"), snap.get("revision")
    if not qid or not isinstance(rev, int) or rev < 1:
        print("CHOICE_RECONCILE: a snapshot needs questionId and an integer revision >= 1")
        return 2
    digest = snapshot_hash(snap)
    con = connect(args.db)
    con.execute("BEGIN IMMEDIATE")
    old = con.execute("SELECT snapshot_hash FROM revisions WHERE question_id=? AND revision=?", (qid, rev)).fetchone()
    if old and old[0] != digest:
        con.execute("ROLLBACK")
        print(f"REFUSED {qid} r{rev}: this revision is already registered with {old[0]}; a changed question is a new revision")
        return 1
    if not old:
        con.execute("INSERT INTO revisions VALUES (?,?,?,?,?)",
                    (qid, rev, digest, json.dumps(snap, ensure_ascii=False, sort_keys=True), now_iso()))
    con.execute("COMMIT")
    print(f"REGISTERED {qid} r{rev} snapshotHash={digest}")
    return 0


def classify(con, kind, qid, rev, sub, payload, decisions):
    """The verdict of one new reply: ok, legacy, or why it is only kept (unknown, stale, bad-hash, bad-choice)."""
    if kind == "note":
        return "note"
    if rev == 0:
        d = decisions.get(qid) or {}
        keys = [o.get("key") for o in d.get("options") or []]
        return "legacy" if (not keys and payload.get("choice") == "done") or payload.get("choice") in keys else "bad-choice"
    snap = con.execute("SELECT snapshot_hash, snapshot FROM revisions WHERE question_id=? AND revision=?", (qid, rev)).fetchone()
    if not snap:
        return "unknown-revision"
    latest = con.execute("SELECT MAX(revision) FROM revisions WHERE question_id=?", (qid,)).fetchone()[0]
    if rev < latest:
        return "stale"
    if payload.get("snapshotHash") != snap[0]:
        return "bad-hash"
    keys = [o.get("key") for o in json.loads(snap[1]).get("options") or []]
    if keys and payload.get("choice") not in keys or not keys and payload.get("choice") != "done":
        return "bad-choice"
    return "ok"


def cmd_ingest(args):
    data = load_json(args.export)
    source = data.get("source") or "artifact"
    decisions = {d.get("id"): d for d in data.get("decisions") or []}
    rows = []
    for r in data.get("choiceReplies") or []:
        rows.append(("choice", f"{source}/choiceReplies/{r.get('id')}", r.get("questionId"), int(r.get("revision") or 0), r))
    for d in decisions.values():
        if d.get("revision") is None and d.get("status") in ("answered", "closed") and d.get("answer"):
            a = dict(d["answer"])
            key = a.get("submissionId") or a.get("at") or ""
            rows.append(("choice", f"{source}/decisions/{d.get('id')}/{key}", d.get("id"), 0, a))
    for n in data.get("notes") or []:
        rows.append(("note", f"{source}/notes/{n.get('id')}", None, 0, n))
    con = connect(args.db)
    counts = {}
    con.execute("BEGIN IMMEDIATE")
    for kind, skey, qid, rev, payload in rows:
        if con.execute("SELECT 1 FROM inbox WHERE source_key=?", (skey,)).fetchone():
            counts["already"] = counts.get("already", 0) + 1
            continue
        sub = payload.get("submissionId")
        verdict = classify(con, kind, qid, rev, sub, payload, decisions)
        if verdict in ("ok", "legacy") and sub:
            twin = con.execute("SELECT payload FROM inbox WHERE submission_id=? AND kind='choice'", (sub,)).fetchone()
            if twin:
                same = {k: json.loads(twin[0]).get(k) for k in ("choice", "note")} == {k: payload.get(k) for k in ("choice", "note")}
                verdict = "duplicate" if same else "conflict-same-submission"
        if verdict in ("ok", "legacy"):
            other = con.execute("SELECT payload FROM inbox WHERE question_id=? AND revision=? AND state='RECORDED' AND kind='choice'",
                                (qid, rev)).fetchone()
            if other and json.loads(other[0]).get("choice") != payload.get("choice"):
                verdict = "conflict"
            elif other:
                verdict = "duplicate"
        state = "RECORDED" if verdict in ("ok", "legacy", "note") else "RECEIPT_PENDING"
        con.execute("INSERT INTO inbox VALUES (?,?,?,?,?,?,?,?,?)",
                    (skey, kind, qid, rev, sub, json.dumps(payload, ensure_ascii=False, sort_keys=True), now_iso(), state, verdict))
        counts[verdict] = counts.get(verdict, 0) + 1
        print(f"{state} {skey} {qid or ''} r{rev} {verdict}")
    con.execute("COMMIT")
    summary = " ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
    print(f"CHOICE_INGEST: {summary} (shadow: only recorded, nothing blocked)")
    return 0


def next_wo(con, orders):
    numbers = [int(m.group(1)) for (wo,) in con.execute("SELECT wo_id FROM effects") for m in [re.match(r"WO-(\d+)$", wo or "")] if m]
    if orders and pathlib.Path(orders).is_dir():
        numbers += [int(m.group(1)) for p in pathlib.Path(orders).iterdir() for m in [re.match(r"WO-(\d+)", p.name)] if m]
    return f"WO-{max(numbers, default=0) + 1:03d}"


def cmd_plan(args):
    key = f"{args.question}:r{args.revision}"
    con = connect(args.db, timeout=args.busy_timeout)
    try:
        con.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError as error:
        print(f"BUSY {key}: {error}; another Director holds the ledger, try again")
        return 1
    old = con.execute("SELECT e.wo_id, d.state FROM decisions d JOIN effects e ON e.decision_key=d.decision_key WHERE d.decision_key=?",
                      (key,)).fetchone()
    if old:
        con.execute("ROLLBACK")
        note = f" (asked for {args.wo}; kept the first one)" if args.wo and args.wo != old[0] else ""
        print(f"PLANNED {key} {old[0]} state={old[1]} already{note}")
        return 0
    pick = con.execute("SELECT source_key, payload FROM inbox WHERE question_id=? AND revision=? AND state='RECORDED' AND kind='choice' "
                       "ORDER BY received_at, source_key LIMIT 1", (args.question, args.revision)).fetchone()
    if not pick:
        con.execute("ROLLBACK")
        print(f"NOTHING {key}: no recorded reply to adopt; run ingest first")
        return 1
    wo = args.wo or next_wo(con, args.orders)
    if con.execute("SELECT 1 FROM effects WHERE wo_id=?", (wo,)).fetchone():
        con.execute("ROLLBACK")
        print(f"REFUSED {key}: {wo} already belongs to another decision")
        return 1
    stamp = now_iso()
    con.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?)",
                (key, args.question, args.revision, pick[0], json.loads(pick[1]).get("choice"), "PLANNED", stamp, stamp))
    con.execute("INSERT INTO effects VALUES (?,?,?,?,?,?)", (key + ":effect", key, wo, None, None, None))
    con.execute("UPDATE inbox SET state='PLANNED' WHERE source_key=?", (pick[0],))
    con.execute("COMMIT")
    print(f"PLANNED {key} {wo} from {pick[0]}")
    return 0


def cmd_advance(args):
    key = f"{args.question}:r{args.revision}"
    if args.to not in MOVES.get(args.from_, set()):
        print(f"REFUSED {key}: {args.from_} -> {args.to} is not a step (allowed: {sorted(MOVES.get(args.from_, set()))})")
        return 2
    con = connect(args.db, timeout=args.busy_timeout)
    con.execute("BEGIN IMMEDIATE")
    done = con.execute("UPDATE decisions SET state=?, updated_at=? WHERE decision_key=? AND state=?",
                       (args.to, now_iso(), key, args.from_)).rowcount
    if not done:
        row = con.execute("SELECT state FROM decisions WHERE decision_key=?", (key,)).fetchone()
        con.execute("ROLLBACK")
        print(f"LOST {key}: state is {row[0] if row else 'unknown'}, not {args.from_}; someone else moved it")
        return 1
    if args.to == "CLAIMED":
        con.execute("UPDATE effects SET claimed_by=?, claimed_at=? WHERE decision_key=?", (args.session, now_iso(), key))
    if args.result:
        con.execute("UPDATE effects SET result=? WHERE decision_key=?", (args.result, key))
    con.execute("UPDATE inbox SET state=? WHERE source_key=(SELECT source_key FROM decisions WHERE decision_key=?)", (args.to, key))
    con.execute("COMMIT")
    print(f"MOVED {key} {args.from_} -> {args.to}")
    return 0


def minutes(since, now):
    try:
        then = datetime.datetime.fromisoformat(since.replace("Z", "+00:00"))
        return int((now - then).total_seconds() // 60)
    except (AttributeError, ValueError):
        return None


def cmd_status(args):
    if not pathlib.Path(args.db).exists():
        print(f"CHOICE_RECONCILE: open=0 not_received=0 stuck=0 receipts_pending=0 (no ledger at {args.db})")
        return 0
    now = datetime.datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.datetime.now(datetime.timezone.utc)
    con = connect(args.db)
    items = []
    for skey, qid, rev, state, verdict, received in con.execute(
            "SELECT source_key, question_id, revision, state, verdict, received_at FROM inbox WHERE state='RECORDED' ORDER BY received_at"):
        m = minutes(received, now)
        items.append({"key": skey, "question": qid, "revision": rev, "state": state, "verdict": verdict, "minutes": m,
                      "hint": "沒交出去" if m is not None and m >= args.late_min else ""})
    for key, state, updated, wo, claimed in con.execute(
            "SELECT d.decision_key, d.state, d.updated_at, e.wo_id, e.claimed_by FROM decisions d JOIN effects e ON e.decision_key=d.decision_key "
            "WHERE d.state != 'CLOSED' ORDER BY d.updated_at"):
        m = minutes(updated, now)
        hint = ""
        if state in SEEN and m is not None and m >= args.stuck_min:
            hint = "收到但卡住"
        if state == "RECONCILE":
            hint = "結果不明，先查證再決定"
        items.append({"key": key, "state": state, "wo": wo, "claimed_by": claimed, "minutes": m, "hint": hint})
    pending = con.execute("SELECT COUNT(*) FROM inbox WHERE state='RECEIPT_PENDING'").fetchone()[0]
    stuck = sum(1 for i in items if i["hint"] == "收到但卡住")
    late = sum(1 for i in items if i["hint"] == "沒交出去")
    if args.json:
        print(json.dumps({"items": items, "receipts_pending": pending}, ensure_ascii=False))
    else:
        for i in items:
            print(f"- {i['key']} {i['state']} {i.get('wo') or ''} {i['minutes']} 分 {i['hint']}".rstrip())
    print(f"CHOICE_RECONCILE: open={len(items)} not_handed={late} stuck={stuck} receipts_pending={pending} (shadow: hints only)")
    return 0


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="local ledger for choice-page replies (shadow)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("register", "ingest", "plan", "advance", "status"):
        p = sub.add_parser(name)
        p.add_argument("--db", required=True, type=pathlib.Path)
        p.add_argument("--busy-timeout", type=float, default=5.0)
    sub.choices["register"].add_argument("--snapshot", required=True)
    sub.choices["ingest"].add_argument("--export", required=True)
    for name in ("plan", "advance"):
        sub.choices[name].add_argument("--question", required=True)
        sub.choices[name].add_argument("--revision", required=True, type=int)
    sub.choices["plan"].add_argument("--wo")
    sub.choices["plan"].add_argument("--orders")
    adv = sub.choices["advance"]
    adv.add_argument("--from", dest="from_", required=True, choices=STATES)
    adv.add_argument("--to", required=True, choices=STATES)
    adv.add_argument("--session")
    adv.add_argument("--result")
    st = sub.choices["status"]
    st.add_argument("--now")
    st.add_argument("--late-min", type=int, default=10)
    st.add_argument("--stuck-min", type=int, default=30)
    st.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    return {"register": cmd_register, "ingest": cmd_ingest, "plan": cmd_plan, "advance": cmd_advance, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
