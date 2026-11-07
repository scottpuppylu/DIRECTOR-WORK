"""Local ledger for choice-page replies (docs/12 第四、六節; 2.2.0, shadow mode). The Director records every reply in one
SQLite file before acting on it, so a crash, a second Director or a resent reply never starts the same work twice.

Ledger: <DIRECTOR>/choice_inbox.sqlite3 (--db). Tables: revisions (immutable question snapshots), questions (the revision
the page shows now: the "current" pointer, kept apart from the snapshots), inbox (every reply seen, one row per source
key), quarantine (export rows that could not be read; retried on every ingest), decisions (at most one adopted reply per
question revision), effects (the fixed WO-ID and effect ID of a decision, its holder and generation) and events (every
step, who did it). Python standard library only. A 2.1.0 ledger is upgraded in place on first use (a copy is kept as
<db>.v210.bak first).

  choice_reconcile.py register --db D --snapshot SNAP.json     snapshot of one question revision; prints its snapshotHash
  choice_reconcile.py publish  --db D --question CH-01 (--revision 2 | --close)   the page now shows r2 / the question closed
  choice_reconcile.py ingest   --db D --export EXPORT.json     replies read from the page db (ArtifactData), see below
  choice_reconcile.py plan     --db D --question CH-01 --revision 1 [--wo WO-012] [--orders DIR]
  choice_reconcile.py advance  --db D --question CH-01 --revision 1 --from QUEUED --to CLAIMED --session S [--generation N] [--result T]
  choice_reconcile.py settle   --db D --key <source key> --to NOTED|SUPERSEDED|CLOSED [--result T]
  choice_reconcile.py rescan   --db D                          re-check every reply that waited for a snapshot or a revision
  choice_reconcile.py status   --db D [--now ISO] [--late-min 10] [--stuck-min 30] [--json]

EXPORT.json: {"source": "<artifact id>", "decisions": [...], "choiceReplies": [...], "notes": [...]}, each item the doc
fields plus "id". Replies of 2.1 questions come from choiceReplies; legacy questions (no revision) from decisions with
status answered (revision 0); notes become kind note rows. A decisions doc with a revision moves the current pointer of
that question forward (status closed closes it). Each row is read on its own: a row that cannot be read goes to
quarantine (QUARANTINED <key> reason=<code>) and never stops the good rows.

Reply identity: questionId + revision + snapshotHash + submissionId. Idempotency key: <source>|<kind>|<submissionId>; the
same key with the same content is a duplicate, with other content conflict-same-submission (both rows kept).

States: RAW -> RECORDED -> PLANNED -> QUEUED -> CLAIMED -> RECEIPT_PENDING -> CLOSED; PLANNED | QUEUED | CLAIMED -> RECONCILE ->
CLAIMED | QUEUED; RECORDED -> RECEIPT_PENDING for a duplicate, stale, conflicting or invalid reply. plan and every claim
re-check that the revision is still the one the page shows, that its hash matches and that the question is open. A claim
raises the generation and names the holder (--session); only the holder may move CLAIMED -> RECEIPT_PENDING; anyone may
move CLAIMED -> RECONCILE (a takeover, logged; anyone but the holder must give --generation), then claim it again. All moves are compare-and-set on state (and on
--generation when given) inside BEGIN IMMEDIATE, so of two Directors only one wins (the other gets exit 1 and LOST).

settle closes an inbox row no decision adopts: a read note (NOTED), a reply a newer one replaced (SUPERSEDED), or a
duplicate / conflicting / invalid reply answered back to the user (CLOSED); CLOSED on a quarantine key dismisses it.
status counts every state; clear=yes only when nothing is waiting, in flight, without a receipt or in quarantine.
--json prints exactly one JSON document.

Shadow mode: nothing here blocks other tools or the old flow. A broken export, a bad --now, a broken ledger or a missing
folder print one line "CHOICE_RECONCILE: SHADOW_ERROR <reason>" (status --json: one JSON document with "error") and exit
0 (register: exit 2, the page needs its hash). A ledger another Director holds longer than --busy-timeout prints
"CHOICE_RECONCILE: BUSY ..." (plan / advance: "BUSY <key>") and exits 1 for every command: nothing ran, retry. Exit 2
for a usage error (and for a takeover without --generation); plan / advance / settle / publish exit 1 when
the change did not happen (only MOVED / PLANNED / SETTLED / PUBLISHED mean it did).
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import sys

SCHEMA_VERSION = 2
STATES = ("RAW", "RECORDED", "PLANNED", "QUEUED", "CLAIMED", "RECONCILE", "RECEIPT_PENDING", "CLOSED", "NOTED", "SUPERSEDED")
SETTLE = {"RECORDED": {"NOTED", "SUPERSEDED", "CLOSED"}, "RECEIPT_PENDING": {"CLOSED", "SUPERSEDED"}}  # inbox rows no decision adopts
WAITING = ("ok", "legacy")  # verdicts of a reply the Director still has to act on
RETRYABLE = ("unknown-revision",)  # verdicts that a later snapshot or revision can change
MOVES = {"RAW": {"RECORDED"}, "RECORDED": {"PLANNED", "RECEIPT_PENDING"}, "PLANNED": {"QUEUED", "RECONCILE"},
         "QUEUED": {"CLAIMED", "RECONCILE"}, "RECONCILE": {"CLAIMED", "QUEUED"}, "CLAIMED": {"RECEIPT_PENDING", "RECONCILE"},
         "RECEIPT_PENDING": {"CLOSED"}, "CLOSED": set()}
SEEN = ("PLANNED", "QUEUED", "CLAIMED", "RECONCILE")  # the Director has the reply but has not handed it over
TABLES = (
    "CREATE TABLE IF NOT EXISTS revisions (question_id TEXT, revision INTEGER, snapshot_hash TEXT, snapshot TEXT, "
    "registered_at TEXT, withdrawn INTEGER DEFAULT 0, PRIMARY KEY (question_id, revision))",
    "CREATE TABLE IF NOT EXISTS questions (question_id TEXT PRIMARY KEY, revision INTEGER, snapshot_hash TEXT, "
    "open INTEGER, source TEXT, updated_at TEXT)",
    "CREATE TABLE IF NOT EXISTS inbox (source_key TEXT PRIMARY KEY, kind TEXT, question_id TEXT, revision INTEGER, "
    "submission_id TEXT, payload TEXT, received_at TEXT, state TEXT, verdict TEXT, idem_key TEXT, snapshot_hash TEXT)",
    "CREATE TABLE IF NOT EXISTS quarantine (source_key TEXT PRIMARY KEY, collection TEXT, reason TEXT, payload TEXT, "
    "first_seen TEXT, last_seen TEXT, attempts INTEGER, resolved_at TEXT)",
    "CREATE TABLE IF NOT EXISTS decisions (decision_key TEXT PRIMARY KEY, question_id TEXT, revision INTEGER, "
    "source_key TEXT, choice TEXT, state TEXT, created_at TEXT, updated_at TEXT)",
    "CREATE TABLE IF NOT EXISTS effects (effect_key TEXT PRIMARY KEY, decision_key TEXT UNIQUE, wo_id TEXT UNIQUE, "
    "claimed_by TEXT, claimed_at TEXT, result TEXT, generation INTEGER DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, decision_key TEXT, at TEXT, "
    "from_state TEXT, to_state TEXT, session TEXT, generation INTEGER, note TEXT)",
    "CREATE INDEX IF NOT EXISTS inbox_idem ON inbox (idem_key)",
    "CREATE INDEX IF NOT EXISTS inbox_question ON inbox (question_id, revision)",
)
ADDED = (("revisions", "withdrawn", "INTEGER DEFAULT 0"), ("inbox", "idem_key", "TEXT"), ("inbox", "snapshot_hash", "TEXT"),
         ("effects", "generation", "INTEGER DEFAULT 0"))  # columns a 2.1.0 ledger does not have
KEY_SOURCE = re.compile(r"^(.*)/(choiceReplies|decisions|notes)/")


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def snapshot_hash(snapshot):
    """sha256 of the snapshot without its own hash, keys sorted, UTF-8; the page and the ledger compare this value."""
    body = {k: v for k, v in snapshot.items() if k not in ("snapshotHash", "id")}
    text = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def idem_key(source, kind, submission):
    return f"{source}|{kind}|{submission}" if submission else None


def migrate(con, path):
    """Create the 2.2 tables; upgrade a 2.1.0 ledger in place (copy kept first, no row dropped, WO-IDs kept)."""
    if con.execute("PRAGMA user_version").fetchone()[0] >= SCHEMA_VERSION:
        return
    con.execute("BEGIN IMMEDIATE")  # the backup and the upgrade happen under one lock
    try:
        if con.execute("PRAGMA user_version").fetchone()[0] >= SCHEMA_VERSION:  # another Director upgraded it meanwhile
            con.execute("ROLLBACK")
            return
        old = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inbox'").fetchone()
        if old:
            backup_v210(path)
        upgrade(con, old)
        con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise


def backup_v210(path):
    """Copy the 2.1 ledger before the upgrade: to a temp file, checked, then linked to a name nobody holds yet.
    Called with BEGIN IMMEDIATE held, so no one writes meanwhile; any failure stops the upgrade."""
    final = pathlib.Path(str(path) + ".v210.bak")
    temp = final.with_name(f"{final.name}.{os.getpid()}.tmp")
    try:
        source, target = sqlite3.connect(str(path), timeout=5.0), sqlite3.connect(str(temp))
        try:
            source.backup(target)
            check = target.execute("PRAGMA quick_check").fetchone()[0]
            tables = target.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='inbox'").fetchone()[0]
            version = target.execute("PRAGMA user_version").fetchone()[0]
        finally:
            source.close()
            target.close()
        if check != "ok" or tables != 1 or version >= SCHEMA_VERSION:
            raise ValueError(f"backup check failed (quick_check={check}, inbox={tables}, user_version={version}); not upgraded")
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        for name in (final, final.with_name(f"{final.name}.{stamp}")):
            try:
                os.link(str(temp), str(name))
                return name
            except FileExistsError:
                continue
        raise ValueError(f"cannot claim a backup name next to {final}; not upgraded")
    finally:
        if temp.exists():
            temp.unlink()


def upgrade(con, old):
    """The 2.1 -> 2.2 schema change itself; runs inside migrate's transaction."""
    for statement in TABLES:
        if not statement.startswith("CREATE INDEX"):
            con.execute(statement)
    for table, column, decl in ADDED:
        if column not in [r[1] for r in con.execute(f"PRAGMA table_info({table})")]:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    for statement in TABLES:
        if statement.startswith("CREATE INDEX"):
            con.execute(statement)
    if old:
        stamp = now_iso()
        for qid, rev in con.execute("SELECT question_id, MAX(revision) FROM revisions GROUP BY question_id").fetchall():
            digest = con.execute("SELECT snapshot_hash FROM revisions WHERE question_id=? AND revision=?", (qid, rev)).fetchone()[0]
            con.execute("INSERT OR IGNORE INTO questions VALUES (?,?,?,?,?,?)", (qid, rev, digest, 1, "backfill-2.1", stamp))
        for skey, kind, sub, payload in con.execute(
                "SELECT source_key, kind, submission_id, payload FROM inbox WHERE idem_key IS NULL").fetchall():
            m = KEY_SOURCE.match(skey or "")
            body = json.loads(payload or "{}")
            con.execute("UPDATE inbox SET idem_key=?, snapshot_hash=? WHERE source_key=?",
                        (idem_key(m.group(1) if m else "", kind, sub), body.get("snapshotHash") or "", skey))
        con.execute("UPDATE effects SET generation=1 WHERE claimed_at IS NOT NULL AND (generation IS NULL OR generation=0)")
        con.execute("UPDATE effects SET generation=0 WHERE generation IS NULL")


def connect(path, timeout=5.0):
    con = sqlite3.connect(str(path), timeout=timeout, isolation_level=None)
    migrate(con, path)
    return con


def load_json(path):
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read {path}: {error}")
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def log(con, key, before, after, session=None, generation=None, note=None):
    con.execute("INSERT INTO events (decision_key, at, from_state, to_state, session, generation, note) VALUES (?,?,?,?,?,?,?)",
                (key, now_iso(), before, after, session, generation, note))


def current(con, qid):
    """(revision, snapshot_hash, open, source) the page shows now, or None for a question never registered."""
    row = con.execute("SELECT revision, snapshot_hash, open, source FROM questions WHERE question_id=?", (qid,)).fetchone()
    if row:
        return row
    top = con.execute("SELECT revision, snapshot_hash FROM revisions WHERE question_id=? ORDER BY revision DESC LIMIT 1", (qid,)).fetchone()
    return (top[0], top[1], 1, "registered") if top else None


def registered(con, qid, rev):
    row = con.execute("SELECT snapshot_hash FROM revisions WHERE question_id=? AND revision=?", (qid, rev)).fetchone()
    return row[0] if row else None


def set_pointer(con, qid, rev, digest, is_open, source):
    con.execute("INSERT INTO questions VALUES (?,?,?,?,?,?) ON CONFLICT(question_id) DO UPDATE SET revision=excluded.revision, "
                "snapshot_hash=excluded.snapshot_hash, open=excluded.open, source=excluded.source, updated_at=excluded.updated_at",
                (qid, rev, digest, 1 if is_open else 0, source, now_iso()))


def live(con, qid, rev, reply_hash=None):
    """None when replies of this revision may be acted on now; otherwise why not (plan and claim re-check this)."""
    if rev == 0:
        return None
    cur = current(con, qid)
    if not cur:
        return "unknown-question: no snapshot registered"
    if not cur[2]:
        return "question-closed: the question is closed on the page"
    if rev != cur[0]:
        return f"stale: the page shows r{cur[0]}, not r{rev}"
    pending = con.execute("SELECT MIN(revision) FROM revisions WHERE question_id=? AND revision>? AND COALESCE(withdrawn,0)=0",
                          (qid, rev)).fetchone()[0]
    if pending is not None:
        return (f"held: r{pending} is registered but not on the page yet; publish --revision {pending} once the page shows it, "
                f"or publish --revision {rev} to keep r{rev}")
    digest = registered(con, qid, rev)
    if cur[1] and digest and cur[1] != digest:
        return f"bad-hash: the page hash {cur[1]} is not the registered {digest}"
    if reply_hash is not None and reply_hash != digest:
        return "bad-hash: the adopted reply carries another snapshotHash"
    return None


def classify(con, kind, qid, rev, payload, decisions):
    """The verdict of one reply: ok, legacy, or why it is only kept (unknown-revision, stale, question-closed, bad-hash, bad-choice)."""
    if kind == "note":
        return "note"
    if rev == 0:
        d = decisions.get(qid) or {}
        keys = [o.get("key") for o in d.get("options") or [] if isinstance(o, dict)]
        return "legacy" if (not keys and payload.get("choice") == "done") or payload.get("choice") in keys else "bad-choice"
    snap = con.execute("SELECT snapshot_hash, snapshot FROM revisions WHERE question_id=? AND revision=?", (qid, rev)).fetchone()
    if not snap:
        return "unknown-revision"
    cur = current(con, qid)
    if rev < cur[0]:
        return "stale"
    if not cur[2]:
        return "question-closed"
    if payload.get("snapshotHash") != snap[0]:
        return "bad-hash"
    keys = [o.get("key") for o in json.loads(snap[1]).get("options") or [] if isinstance(o, dict)]
    if keys and payload.get("choice") not in keys or not keys and payload.get("choice") != "done":
        return "bad-choice"
    return "ok"


def judge(con, kind, qid, rev, payload, decisions, idem, skey=None, before=None):
    """(verdict, state) of a reply against what the ledger already holds; before = rowid of the row being re-checked."""
    verdict = classify(con, kind, qid, rev, payload, decisions)
    order = " AND rowid<?" if before is not None else ""
    extra = (before,) if before is not None else ()
    if idem and verdict in ("ok", "legacy", "note"):
        twin = con.execute("SELECT payload FROM inbox WHERE idem_key=? AND source_key!=?" + order + " ORDER BY rowid LIMIT 1",
                           (idem, skey or "") + extra).fetchone()
        if twin:
            fields = ("text",) if kind == "note" else ("choice", "note")
            mine, theirs = json.loads(twin[0]), payload
            same = all(mine.get(k) == theirs.get(k) for k in fields)
            verdict = "duplicate" if same else "conflict-same-submission"
    if verdict in ("ok", "legacy"):
        adopted = con.execute("SELECT choice FROM decisions WHERE question_id=? AND revision=?", (qid, rev)).fetchone()
        if adopted:  # a late reply: compare with the decision already taken, whatever its state
            verdict = "duplicate" if adopted[0] == payload.get("choice") else "conflict-late"
        else:
            other = con.execute("SELECT payload FROM inbox WHERE question_id=? AND revision=? AND state='RECORDED' AND kind='choice' "
                                "AND verdict IN ('ok','legacy') AND source_key!=?" + order + " ORDER BY rowid LIMIT 1",
                                (qid, rev, skey or "") + extra).fetchone()
            if other:
                verdict = "conflict" if json.loads(other[0]).get("choice") != payload.get("choice") else "duplicate"
    if kind == "note":
        state = "CLOSED" if verdict == "duplicate" else "RECORDED"  # a resent note is read once; a changed one is read too
    else:
        state = "RECORDED" if verdict in ("ok", "legacy") else "RECEIPT_PENDING"
    if verdict == "legacy" and (decisions.get(qid) or {}).get("status") == "closed":
        verdict, state = "legacy-closed", "CLOSED"  # a 2.0 answer the Director already closed
    return verdict, state


def reevaluate(con, qid, quiet=False):
    """Re-check the replies of one question that a new snapshot or revision can change; returns how many changed."""
    changed = 0
    rows = con.execute(
        "SELECT rowid, source_key, revision, payload, state, verdict, idem_key FROM inbox WHERE question_id=? AND kind='choice' "
        "AND revision>0 AND ((state='RECORDED' AND verdict='ok') OR (state='RECEIPT_PENDING' AND verdict IN (%s))) "
        "AND source_key NOT IN (SELECT source_key FROM decisions) ORDER BY rowid" % ",".join("?" * len(RETRYABLE)),
        (qid,) + RETRYABLE).fetchall()
    for rowid, skey, rev, payload, state, verdict, idem in rows:
        new, new_state = judge(con, "choice", qid, rev, json.loads(payload), {}, idem, skey, rowid)
        if (new, new_state) != (verdict, state):
            con.execute("UPDATE inbox SET verdict=?, state=? WHERE source_key=?", (new, new_state, skey))
            changed += 1
            if not quiet:
                print(f"REEVALUATED {skey} {verdict} -> {new} {new_state}")
    return changed


def cmd_register(args):
    snap = load_json(args.snapshot)
    qid, rev = snap.get("questionId"), snap.get("revision")
    if not qid or not isinstance(rev, int) or isinstance(rev, bool) or rev < 1:
        print("CHOICE_RECONCILE: a snapshot needs questionId and an integer revision >= 1")
        return 2
    digest = snapshot_hash(snap)
    con = connect(args.db, timeout=args.busy_timeout)
    con.execute("BEGIN IMMEDIATE")
    old = con.execute("SELECT snapshot_hash FROM revisions WHERE question_id=? AND revision=?", (qid, rev)).fetchone()
    if old and old[0] != digest:
        con.execute("ROLLBACK")
        print(f"REFUSED {qid} r{rev}: this revision is already registered with {old[0]}; a changed question is a new revision")
        return 1
    if old:
        con.execute("UPDATE revisions SET withdrawn=0 WHERE question_id=? AND revision=?", (qid, rev))
    else:
        con.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?)",
                    (qid, rev, digest, json.dumps(snap, ensure_ascii=False, sort_keys=True), now_iso(), 0))
    if not con.execute("SELECT 1 FROM questions WHERE question_id=?", (qid,)).fetchone():
        set_pointer(con, qid, rev, digest, True, "register-first")  # the first revision: no page can show an older one
    reevaluate(con, qid)
    con.execute("COMMIT")
    print(f"REGISTERED {qid} r{rev} snapshotHash={digest}")
    return 0


def cmd_publish(args):
    con = connect(args.db, timeout=args.busy_timeout)
    con.execute("BEGIN IMMEDIATE")
    cur = current(con, args.question)
    if args.close:
        if not cur:
            con.execute("ROLLBACK")
            print(f"REFUSED {args.question}: no snapshot registered")
            return 1
        set_pointer(con, args.question, cur[0], cur[1], False, "publish")
        reevaluate(con, args.question)
        con.execute("COMMIT")
        print(f"PUBLISHED {args.question} closed (was r{cur[0]})")
        return 0
    digest = registered(con, args.question, args.revision)
    why = ("not registered; register it first" if not digest else
           f"the page already showed r{cur[0]}; a published revision never goes back" if cur and args.revision < cur[0] else "")
    if why:
        con.execute("ROLLBACK")
        print(f"REFUSED {args.question} r{args.revision}: {why}")
        return 1
    set_pointer(con, args.question, args.revision, digest, True, "publish")
    con.execute("UPDATE revisions SET withdrawn=1 WHERE question_id=? AND revision>?", (args.question, args.revision))
    reevaluate(con, args.question)
    con.execute("COMMIT")
    print(f"PUBLISHED {args.question} r{args.revision} snapshotHash={digest}")
    return 0


def sync_pointer(con, d):
    """A 2.1 decisions doc tells which revision the page shows; move the pointer forward only. Returns True when it moved."""
    qid, rev = d.get("id"), d.get("revision")
    if not isinstance(rev, int) or isinstance(rev, bool) or rev < 1:
        return False
    cur = current(con, qid)
    closed = d.get("status") == "closed"
    page_hash = d.get("snapshotHash") or ""
    if cur and rev < cur[0]:
        return False  # an older export: the pointer never goes back
    if cur and rev == cur[0] and (not cur[2] or not closed and (not page_hash or page_hash == cur[1])):
        return False  # nothing new; a closed question is never reopened by an export
    digest = registered(con, qid, rev)
    set_pointer(con, qid, rev, page_hash or digest or "", not closed, "page")
    con.execute("UPDATE revisions SET withdrawn=0 WHERE question_id=? AND revision=?", (qid, rev))
    return True


def quarantine(con, skey, collection, reason, raw):
    if con.execute("SELECT 1 FROM quarantine WHERE source_key=? AND reason='dismissed'", (skey,)).fetchone():
        return  # settled --to CLOSED once: never raised again
    stamp = now_iso()
    con.execute("INSERT INTO quarantine VALUES (?,?,?,?,?,?,?,NULL) ON CONFLICT(source_key) DO UPDATE SET reason=excluded.reason, "
                "payload=excluded.payload, last_seen=excluded.last_seen, attempts=quarantine.attempts+1, resolved_at=NULL",
                (skey, collection, reason, raw, stamp, stamp, 1))
    print(f"QUARANTINED {skey} reason={reason} retry=yes")


def read_rows(con, data, source):
    """Every export row as (kind, source_key, question, revision, payload, idem); unreadable rows go to quarantine."""
    rows, decisions, bad = [], {}, 0

    def items(name):
        value = data.get(name)
        if value is None:
            return []
        if isinstance(value, list):
            return value
        quarantine(con, f"{source}/{name}", name, "not-a-list", json.dumps(value, ensure_ascii=False, default=str)[:2000])
        return None

    def keyed(name, item, index):
        raw = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        ident = item.get("id") if isinstance(item, dict) else None
        if isinstance(ident, (str, int)) and not isinstance(ident, bool) and str(ident):
            return f"{source}/{name}/{ident}", raw
        return f"{source}/{name}/?{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}", raw

    lists = {name: items(name) for name in ("decisions", "choiceReplies", "notes")}
    bad += sum(1 for v in lists.values() if v is None)
    for i, d in enumerate(lists["decisions"] or []):
        if isinstance(d, dict) and isinstance(d.get("id"), str) and d.get("id"):
            decisions[d["id"]] = d
        else:
            skey, raw = keyed("decisions", d, i)
            quarantine(con, skey, "decisions", "missing-id" if isinstance(d, dict) else "not-an-object", raw)
            bad += 1
    for i, r in enumerate(lists["choiceReplies"] or []):
        skey, raw = keyed("choiceReplies", r, i)
        reason = None
        if not isinstance(r, dict):
            reason = "not-an-object"
        elif skey.split("/")[-1].startswith("?"):
            reason = "missing-id"
        elif not isinstance(r.get("questionId"), str) or not r.get("questionId"):
            reason = "missing-question"
        else:
            rev = r.get("revision")
            if rev in (None, "", 0):
                rev = 0
            elif isinstance(rev, int) and not isinstance(rev, bool) and rev > 0:
                pass
            elif isinstance(rev, str) and rev.isdigit():
                rev = int(rev)
            else:
                reason = "bad-revision"
        if reason:
            quarantine(con, skey, "choiceReplies", reason, raw)
            bad += 1
            continue
        rows.append(("choice", skey, r["questionId"], rev, r, idem_key(source, "choice", r.get("submissionId"))))
    for d in decisions.values():
        if d.get("revision") is None and d.get("status") in ("answered", "closed") and d.get("answer"):
            if not isinstance(d["answer"], dict):
                quarantine(con, f"{source}/decisions/{d['id']}/answer", "decisions", "bad-answer",
                           json.dumps(d["answer"], ensure_ascii=False, default=str))
                bad += 1
                continue
            a = dict(d["answer"])
            key = a.get("submissionId") or a.get("at") or ""
            rows.append(("choice", f"{source}/decisions/{d['id']}/{key}", d["id"], 0, a, idem_key(source, "choice", a.get("submissionId"))))
    for i, n in enumerate(lists["notes"] or []):
        skey, raw = keyed("notes", n, i)
        if not isinstance(n, dict) or skey.split("/")[-1].startswith("?"):
            quarantine(con, skey, "notes", "not-an-object" if not isinstance(n, dict) else "missing-id", raw)
            bad += 1
            continue
        rows.append(("note", skey, None, 0, n, idem_key(source, "note", n.get("submissionId"))))
    return rows, decisions, bad


def cmd_ingest(args):
    data = load_json(args.export)
    given = str(data.get("source") or "")
    if given and args.source and given != args.source:
        print(f"WARNING the export says source={given}, --source says {args.source}; using the export's")
    if not given and not args.source:
        print('WARNING the export has no top-level "source" and no --source was given; using "artifact". '
              "Give --source <artifact id> every time, or the same reply in another export counts twice")
    source = given or args.source or "artifact"
    con = connect(args.db, timeout=args.busy_timeout)
    counts = {}
    con.execute("BEGIN IMMEDIATE")
    rows, decisions, bad = read_rows(con, data, source)
    if bad:
        counts["quarantined"] = bad
    moved = [qid for qid, d in decisions.items() if sync_pointer(con, d)]
    for qid in moved:
        n = reevaluate(con, qid)
        if n:
            counts["reevaluated"] = counts.get("reevaluated", 0) + n
    for kind, skey, qid, rev, payload, idem in rows:
        con.execute("UPDATE quarantine SET resolved_at=? WHERE source_key=? AND resolved_at IS NULL", (now_iso(), skey))
        known = con.execute("SELECT verdict, state FROM inbox WHERE source_key=?", (skey,)).fetchone()
        if known:
            if known[0] in RETRYABLE and known[1] == "RECEIPT_PENDING" and reevaluate(con, qid):
                counts["reevaluated"] = counts.get("reevaluated", 0) + 1
            else:
                counts["already"] = counts.get("already", 0) + 1
            continue
        if kind == "choice" and rev > 0:  # a valid reply for a newer registered revision proves the page shows it
            cur, digest = current(con, qid), registered(con, qid, rev)
            if cur and digest and rev > cur[0] and cur[2] and payload.get("snapshotHash") == digest:
                set_pointer(con, qid, rev, digest, True, "reply")
                reevaluate(con, qid)
        verdict, state = judge(con, kind, qid, rev, payload, decisions, idem, skey)
        con.execute("INSERT INTO inbox VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (skey, kind, qid, rev, payload.get("submissionId"), json.dumps(payload, ensure_ascii=False, sort_keys=True),
                     now_iso(), state, verdict, idem, payload.get("snapshotHash") or ""))
        counts[verdict] = counts.get(verdict, 0) + 1
        print(f"{state} {skey} {qid or ''} r{rev} {verdict}")
    con.execute("COMMIT")
    summary = " ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
    print(f"CHOICE_INGEST: {summary} (shadow: only recorded, nothing blocked)")
    return 0


def cmd_rescan(args):
    con = connect(args.db, timeout=args.busy_timeout)
    con.execute("BEGIN IMMEDIATE")
    qids = [q for (q,) in con.execute("SELECT DISTINCT question_id FROM inbox WHERE kind='choice' AND revision>0")]
    total = sum(reevaluate(con, qid) for qid in qids)
    con.execute("COMMIT")
    print(f"CHOICE_RESCAN: questions={len(qids)} reevaluated={total}")
    return 0


def next_wo(con, orders):
    numbers = [int(m.group(1)) for (wo,) in con.execute("SELECT wo_id FROM effects") for m in [re.match(r"WO-(\d+)$", wo or "")] if m]
    if orders and pathlib.Path(orders).is_dir():
        numbers += [int(m.group(1)) for p in pathlib.Path(orders).iterdir() for m in [re.match(r"WO-(\d+)", p.name)] if m]
    return f"WO-{max(numbers, default=0) + 1:03d}"


def identity(qid, rev, payload):
    """questionId + revision + snapshotHash + submissionId: the one identity the page, receipts and ledger share."""
    return {"questionId": qid, "revision": rev, "snapshotHash": payload.get("snapshotHash") or "",
            "submissionId": payload.get("submissionId") or ""}


def begin(con, key):
    try:
        con.execute("BEGIN IMMEDIATE")
        return True
    except sqlite3.OperationalError as error:
        print(f"BUSY {key}: {error}; another Director holds the ledger, try again")
        return False


def cmd_plan(args):
    key = f"{args.question}:r{args.revision}"
    con = connect(args.db, timeout=args.busy_timeout)
    if not begin(con, key):
        return 1
    old = con.execute("SELECT e.wo_id, d.state FROM decisions d JOIN effects e ON e.decision_key=d.decision_key WHERE d.decision_key=?",
                      (key,)).fetchone()
    if old:
        con.execute("ROLLBACK")
        note = f" (asked for {args.wo}; kept the first one)" if args.wo and args.wo != old[0] else ""
        why = live(con, args.question, args.revision)
        warn = (f" WARNING {why}; advance --from {old[1]} --to RECONCILE --session <you> to look into it"
                if why and "RECONCILE" in MOVES.get(old[1], set()) else "")
        print(f"PLANNED {key} {old[0]} state={old[1]} already{note}{warn}")
        return 0
    pick = con.execute("SELECT source_key, payload FROM inbox WHERE question_id=? AND revision=? AND state='RECORDED' AND kind='choice' "
                       "AND verdict IN ('ok','legacy') ORDER BY received_at, rowid LIMIT 1", (args.question, args.revision)).fetchone()
    if not pick:
        con.execute("ROLLBACK")
        print(f"NOTHING {key}: no recorded reply to adopt; run ingest first")
        return 1
    payload = json.loads(pick[1])
    why = live(con, args.question, args.revision, payload.get("snapshotHash") if args.revision else None)
    if why:
        con.execute("ROLLBACK")
        print(f"{'HOLD' if why.startswith('held') else 'REFUSED'} {key}: {why}")
        return 1
    wo = args.wo or next_wo(con, args.orders)
    if con.execute("SELECT 1 FROM effects WHERE wo_id=?", (wo,)).fetchone():
        con.execute("ROLLBACK")
        print(f"REFUSED {key}: {wo} already belongs to another decision")
        return 1
    stamp = now_iso()
    con.execute("INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?)",
                (key, args.question, args.revision, pick[0], payload.get("choice"), "PLANNED", stamp, stamp))
    con.execute("INSERT INTO effects VALUES (?,?,?,?,?,?,?)", (key + ":effect", key, wo, None, None, None, 0))
    con.execute("UPDATE inbox SET state='PLANNED' WHERE source_key=?", (pick[0],))
    log(con, key, "RECORDED", "PLANNED", note=wo)
    con.execute("COMMIT")
    ident = identity(args.question, args.revision, payload)
    print(f"PLANNED {key} {wo} from {pick[0]} effect={key}:effect identity={json.dumps(ident, ensure_ascii=False)}")
    return 0


def cmd_advance(args):
    key = f"{args.question}:r{args.revision}"
    if args.to not in MOVES.get(args.from_, set()):
        print(f"REFUSED {key}: {args.from_} -> {args.to} is not a step (allowed: {sorted(MOVES.get(args.from_, set()))})")
        return 2
    con = connect(args.db, timeout=args.busy_timeout)
    if "CLAIMED" in (args.from_, args.to) or "RECONCILE" in (args.from_, args.to):
        if not args.session:
            print(f"REFUSED {key}: {args.from_} -> {args.to} needs --session <your name> (the holder is checked)")
            return 2
    if not begin(con, key):
        return 1
    row = con.execute("SELECT d.state, d.source_key, e.claimed_by, COALESCE(e.generation,0), e.wo_id, e.effect_key FROM decisions d "
                      "JOIN effects e ON e.decision_key=d.decision_key WHERE d.decision_key=?", (key,)).fetchone()
    if not row or row[0] != args.from_:
        con.execute("ROLLBACK")
        print(f"LOST {key}: state is {row[0] if row else 'unknown'}, not {args.from_}; someone else moved it")
        return 1
    state, source_key, holder, generation, wo, effect = row
    if args.from_ == "CLAIMED" and args.to == "RECONCILE" and holder != args.session and args.generation is None:
        con.execute("ROLLBACK")
        print(f"REFUSED {key}: held by {holder or 'nobody (2.1 claim)'} at generation {generation}; a takeover needs "
              f"--generation {generation} (the one you saw), so a newer claim is never taken by mistake")
        return 2
    if args.generation is not None and args.generation != generation:
        con.execute("ROLLBACK")
        print(f"LOST {key}: generation is {generation}, not {args.generation}; someone took it over")
        return 1
    if args.from_ == "CLAIMED" and args.to == "RECEIPT_PENDING" and holder != args.session:
        con.execute("ROLLBACK")
        who = f"held by {holder} (generation {generation})" if holder else "a 2.1 claim with no holder"
        print(f"REFUSED {key}: {who}; only the holder hands it over. Check the effect first, then advance --from CLAIMED --to RECONCILE")
        return 1
    if args.to == "CLAIMED" and args.revision:
        payload = json.loads(con.execute("SELECT payload FROM inbox WHERE source_key=?", (source_key,)).fetchone()[0])
        why = live(con, args.question, args.revision, payload.get("snapshotHash"))
        if why:
            con.execute("ROLLBACK")
            print(f"REFUSED {key}: {why}; do not start this work order (QUEUED -> RECONCILE to look into it)")
            return 1
    new_gen = generation + 1 if args.to == "CLAIMED" else generation
    done = con.execute("UPDATE decisions SET state=?, updated_at=? WHERE decision_key=? AND state=?",
                       (args.to, now_iso(), key, args.from_)).rowcount
    done = done and con.execute("UPDATE effects SET generation=? WHERE decision_key=? AND COALESCE(generation,0)=?",
                                (new_gen, key, generation)).rowcount
    if not done:
        con.execute("ROLLBACK")
        print(f"LOST {key}: changed while moving; someone else moved it")
        return 1
    if args.to == "CLAIMED":
        con.execute("UPDATE effects SET claimed_by=?, claimed_at=? WHERE decision_key=?", (args.session, now_iso(), key))
    if args.result:
        con.execute("UPDATE effects SET result=? WHERE decision_key=?", (args.result, key))
    con.execute("UPDATE inbox SET state=? WHERE source_key=?", (args.to, source_key))
    takeover = args.from_ == "CLAIMED" and args.to == "RECONCILE" and holder != args.session
    log(con, key, args.from_, args.to, args.session, new_gen, f"takeover from {holder}" if takeover else args.result)
    con.execute("COMMIT")
    extra = f" generation={new_gen} holder={args.session}" if args.to == "CLAIMED" else f" generation={new_gen}"
    print(f"MOVED {key} {args.from_} -> {args.to}{extra} effect={effect} wo={wo}")
    if takeover or args.to == "RECONCILE":
        print(f"RECONCILE {key}: before doing anything again, look up {wo} / effect {effect} (work order, task, landed decision); "
              f"redo only what did not happen")
    return 0


def minutes(since, now):
    try:
        then = datetime.datetime.fromisoformat(since.replace("Z", "+00:00"))
        return int((now - then).total_seconds() // 60)
    except (AttributeError, ValueError, TypeError):
        return None


def status_report(con, now, late_min, stuck_min):
    items, notes, overdue = [], 0, {}
    for skey, qid, rev, state, verdict, received, payload in con.execute(
            "SELECT source_key, question_id, revision, state, verdict, received_at, payload FROM inbox WHERE state='RECORDED' ORDER BY received_at"):
        if verdict not in WAITING:  # a note: read it, then settle --to NOTED
            notes += 1
            continue
        m = minutes(received, now)
        late = m is not None and m >= late_min
        overdue["RECORDED"] = overdue.get("RECORDED", 0) + late
        items.append({"key": skey, "question": qid, "revision": rev, "state": state, "verdict": verdict, "minutes": m,
                      "hint": "沒交出去" if late else "", "identity": identity(qid, rev, json.loads(payload or "{}"))})
    for key, qid, rev, state, updated, wo, claimed, gen, payload in con.execute(
            "SELECT d.decision_key, d.question_id, d.revision, d.state, d.updated_at, e.wo_id, e.claimed_by, COALESCE(e.generation,0), "
            "i.payload FROM decisions d JOIN effects e ON e.decision_key=d.decision_key LEFT JOIN inbox i ON i.source_key=d.source_key "
            "WHERE d.state != 'CLOSED' ORDER BY d.updated_at"):
        m = minutes(updated, now)
        hint = ""
        if state in SEEN + ("RECEIPT_PENDING",) and m is not None and m >= stuck_min:
            hint = "收到但卡住"
            overdue[state] = overdue.get(state, 0) + 1
        why = live(con, qid, rev) if state in ("PLANNED", "QUEUED", "CLAIMED") else None
        if why:
            hint = "題目已改版或已關，先 RECONCILE 查證：" + why
        if state == "CLAIMED" and not claimed:
            hint = "2.1 舊領取，沒有持有者：先 RECONCILE 查證"
        if state == "RECONCILE":
            hint = "結果不明，先查證再決定"
        items.append({"key": key, "state": state, "wo": wo, "claimed_by": claimed, "generation": gen, "minutes": m, "hint": hint,
                      "identity": identity(qid, rev, json.loads(payload or "{}"))})
    pending = con.execute("SELECT COUNT(*) FROM inbox WHERE state='RECEIPT_PENDING'").fetchone()[0]
    for (received,) in con.execute("SELECT received_at FROM inbox WHERE state='RECEIPT_PENDING' AND source_key NOT IN "
                                   "(SELECT source_key FROM decisions)"):
        m = minutes(received, now)
        if m is not None and m >= stuck_min:
            overdue["RECEIPT_PENDING"] = overdue.get("RECEIPT_PENDING", 0) + 1
    states = {"inbox": dict(con.execute("SELECT state, COUNT(*) FROM inbox GROUP BY state ORDER BY state").fetchall()),
              "decisions": dict(con.execute("SELECT state, COUNT(*) FROM decisions GROUP BY state ORDER BY state").fetchall())}
    quarantined = con.execute("SELECT COUNT(*) FROM quarantine WHERE resolved_at IS NULL").fetchone()[0]
    reconcile = states["decisions"].get("RECONCILE", 0)
    stuck = sum(1 for i in items if i["hint"] == "收到但卡住")
    late = sum(1 for i in items if i["hint"] == "沒交出去")
    clear = not items and not notes and not pending and not quarantined
    shown = ",".join(f"{k}:{v}" for k, v in sorted(states["inbox"].items()) if k not in ("CLOSED", "NOTED", "SUPERSEDED"))
    summary = (f"CHOICE_RECONCILE: open={len(items)} not_handed={late} stuck={stuck} receipts_pending={pending} notes={notes} "
               f"reconcile={reconcile} quarantined={quarantined} clear={'yes' if clear else 'no'} states={shown or '-'} (shadow: hints only)")
    return {"schema": "dw-choice-status/2", "summary": summary, "clear": clear, "open": len(items), "not_handed": late,
            "stuck": stuck, "receipts_pending": pending, "notes": notes, "reconcile": reconcile, "quarantined": quarantined,
            "states": states, "overdue": {k: v for k, v in overdue.items() if v}, "items": items}


def cmd_status(args):
    if not pathlib.Path(args.db).exists():
        line = f"CHOICE_RECONCILE: open=0 not_handed=0 stuck=0 receipts_pending=0 notes=0 clear=yes (no ledger at {args.db})"
        if args.json:
            print(json.dumps({"schema": "dw-choice-status/2", "summary": line, "clear": True, "ledger": False, "items": [],
                              "receipts_pending": 0, "notes": 0}, ensure_ascii=False))
        else:
            print(line)
        return 0
    now = datetime.datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    report = status_report(connect(args.db, timeout=args.busy_timeout), now, args.late_min, args.stuck_min)
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
        return 0
    for i in report["items"]:
        print(f"- {i['key']} {i['state']} {i.get('wo') or ''} {i['minutes']} 分 {i['hint']}".rstrip())
    print(report["summary"])
    return 0


def cmd_settle(args):
    """Close an inbox row no decision adopts: a note read (NOTED), a reply a newer one replaced (SUPERSEDED), or one
    answered back to the user (CLOSED); CLOSED on a quarantine key dismisses that unreadable row."""
    con = connect(args.db, timeout=args.busy_timeout)
    con.execute("BEGIN IMMEDIATE")
    row = con.execute("SELECT state FROM inbox WHERE source_key=?", (args.key,)).fetchone()
    held = con.execute("SELECT 1 FROM quarantine WHERE source_key=? AND resolved_at IS NULL", (args.key,)).fetchone()
    if not row and held and args.to == "CLOSED":
        con.execute("UPDATE quarantine SET resolved_at=?, reason='dismissed' WHERE source_key=?", (now_iso(), args.key))
        con.execute("COMMIT")
        print(f"SETTLED {args.key} QUARANTINED -> CLOSED")
        return 0
    adopted = con.execute("SELECT 1 FROM decisions WHERE source_key=?", (args.key,)).fetchone()
    if not row or adopted or args.to not in SETTLE.get(row[0], set()):
        con.execute("ROLLBACK")
        why = "unknown key" if not row else "adopted by a decision; use advance" if adopted else f"{row[0]} -> {args.to} is not allowed"
        print(f"REFUSED {args.key}: {why}")
        return 1
    note = f" ({args.result})" if args.result else ""
    con.execute("UPDATE inbox SET state=?, verdict=verdict || ? WHERE source_key=? AND state=?", (args.to, note, args.key, row[0]))
    con.execute("COMMIT")
    print(f"SETTLED {args.key} {row[0]} -> {args.to}")
    return 0


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="local ledger for choice-page replies (shadow)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("register", "publish", "ingest", "plan", "advance", "settle", "rescan", "status"):
        p = sub.add_parser(name)
        p.add_argument("--db", required=True, type=pathlib.Path)
        p.add_argument("--busy-timeout", type=float, default=5.0)
    sub.choices["register"].add_argument("--snapshot", required=True)
    pub = sub.choices["publish"]
    pub.add_argument("--question", required=True)
    group = pub.add_mutually_exclusive_group(required=True)
    group.add_argument("--revision", type=int)
    group.add_argument("--close", action="store_true")
    sub.choices["ingest"].add_argument("--export", required=True)
    sub.choices["ingest"].add_argument("--source", help="the page's artifact id when the export has no top-level source")
    for name in ("plan", "advance"):
        sub.choices[name].add_argument("--question", required=True)
        sub.choices[name].add_argument("--revision", required=True, type=int)
    sub.choices["plan"].add_argument("--wo")
    sub.choices["plan"].add_argument("--orders")
    adv = sub.choices["advance"]
    adv.add_argument("--from", dest="from_", required=True, choices=STATES)
    adv.add_argument("--to", required=True, choices=STATES)
    adv.add_argument("--session")
    adv.add_argument("--generation", type=int)
    adv.add_argument("--result")
    stl = sub.choices["settle"]
    stl.add_argument("--key", required=True)
    stl.add_argument("--to", required=True, choices=("NOTED", "SUPERSEDED", "CLOSED"))
    stl.add_argument("--result")
    st = sub.choices["status"]
    st.add_argument("--now")
    st.add_argument("--late-min", type=int, default=10)
    st.add_argument("--stuck-min", type=int, default=30)
    st.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    run = {"register": cmd_register, "publish": cmd_publish, "ingest": cmd_ingest, "plan": cmd_plan, "advance": cmd_advance,
           "settle": cmd_settle, "rescan": cmd_rescan, "status": cmd_status}[args.cmd]
    try:
        return run(args)
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        reason = f"{type(error).__name__}: {error}".replace("\n", " ")[:300]
        if isinstance(error, sqlite3.OperationalError) and any(w in str(error).lower() for w in ("locked", "busy")):
            if args.cmd == "status" and args.json:
                print(json.dumps({"schema": "dw-choice-status/2", "error": reason, "busy": True, "clear": False,
                                  "summary": f"CHOICE_RECONCILE: BUSY {reason}"}, ensure_ascii=False))
            else:
                print(f"CHOICE_RECONCILE: BUSY {reason}; another Director holds the ledger, nothing changed, try again")
            return 1  # not shadow: the command did not run, the caller must retry
        if args.cmd == "register":  # registering a snapshot is not shadow: the page needs its hash
            print(f"CHOICE_RECONCILE: cannot register: {reason}")
            return 2
        if args.cmd == "status" and args.json:  # --json always prints exactly one JSON document
            print(json.dumps({"schema": "dw-choice-status/2", "error": reason, "clear": False,
                              "summary": f"CHOICE_RECONCILE: SHADOW_ERROR {reason}"}, ensure_ascii=False))
            return 0
        print(f"CHOICE_RECONCILE: SHADOW_ERROR {reason}")  # shadow: a hint, never a failed command
        return 0


if __name__ == "__main__":
    sys.exit(main())
