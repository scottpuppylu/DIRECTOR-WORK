#!/usr/bin/env python3
"""browser_check.py - behaviour checks for templates/choice_page.html in headless Chrome (DW 2.2.0, F04 F05 F07 page side).

Usage: python -I -X utf8 tools/browser_check.py [--chrome PATH] [--page PATH]
Browser lookup: --chrome, env DW_CHROME, google-chrome / chromium / chrome on PATH, Windows Chrome and Edge install paths.
No browser found: prints "SKIP browser_check: <reason>" and exits 0; with env DW_REQUIRE_BROWSER=1 it exits 1 instead (CI).
Prints one line per check "name=True/False" and the browser version at the end; exit 1 if any check fails.
Uses a fake Artifact SDK, no network, no real data. Standard library only (Python 3.9+)."""
import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

STUB = """
window.fixture = {callbacks: {}, writes: [], failNext: 0, emit(name, docs) {
  this.callbacks[name]({docs: docs.map(({id, ...f}) => ({id, exists: true, data: () => f}))});
}};
window.claude = {async use(name) {
  if (name === "db") return {
    collection(name) {return {
      onSnapshot(cb) {fixture.callbacks[name] = cb},
      async add(value) {fixture.writes.push([name, value]); if (fixture.failNext > 0) {fixture.failNext--; throw new Error("net")}}
    }},
    doc() {return {onSnapshot() {}}}
  };
  if (name === "user") return {can() {return true}};
  return null;
}};
"""
PROBE = """
setTimeout(async () => {
  const R = {};
  const tick = async () => {for (let i = 0; i < 6; i++) await Promise.resolve(); await new Promise(r => setTimeout(r, 20));};
  try {
    const emit = (n, d) => fixture.emit(n, d);
    const H = "sha256:good";
    const q = {id: "CH-01", revision: 1, status: "open", snapshotHash: H};
    const rev = (hash) => ({id: "rev", questionId: "CH-01", revision: 1, title: "T", snapshotHash: hash,
      options: [{key: "A", label: "Alpha", desc: "da"}, {key: "B", label: "Beta", desc: "db"}]});
    const rep = (id, sub, choice, hash, at, extra) => ({id, kind: "choice", questionId: "CH-01", revision: 1, choice,
      submissionId: sub, snapshotHash: hash, clientAt: at, selectedOptionSnapshot: {key: choice, label: choice === "A" ? "Alpha" : "Beta"}, ...(extra || {})});
    emit("decisions", [q]); emit("choiceRevisions", [rev(H)]); await tick();
    // F04a wrong-hash reply keeps the question open
    emit("choiceReplies", [rep("R0", "s0", "B", "sha256:wrong", "2026-11-08T00:00:00Z")]); await tick();
    R.invalid_reply_keeps_open = !!document.querySelector("#open article") && !document.querySelector("#answered article")
      && document.querySelector("#open article").textContent.includes("指紋");
    // F04a' legacy reply (no hash / no submissionId) is not a valid answer
    emit("choiceReplies", [{id: "L1", kind: "choice", questionId: "CH-01", revision: 1, choice: "B", snapshotHash: H, clientAt: "2026-11-08T00:00:00Z"}]); await tick();
    R.legacy_reply_not_valid = !!document.querySelector("#open article") && !document.querySelector("#answered article")
      && document.querySelector("#open article").textContent.includes("舊格式");
    // F04b receipt only for the adopted submission
    emit("choiceReplies", [rep("R1", "first", "B", H, "2026-11-08T00:00:00Z"), rep("R2", "second", "A", H, "2026-11-08T00:00:01Z")]);
    emit("choiceReceipts", [{questionId: "CH-01", revision: 1, submissionId: "second", stage: "handed", at: "2026-11-08T00:00:02Z", wo: "WO-019"}]); await tick();
    let text = document.querySelector("#answered article").textContent;
    R.receipt_goes_to_adopted = text.includes("Alpha") && text.includes("WO-019") && !text.includes("Beta");
    // receipt that matches no valid reply is history only
    emit("choiceReplies", [rep("R1", "first", "B", H, "2026-11-08T00:00:00Z")]);
    emit("choiceReceipts", [{questionId: "CH-01", revision: 1, submissionId: "ghost", stage: "handed", at: "2026-11-08T00:00:02Z", wo: "WO-777"}]); await tick();
    text = document.querySelector("#answered article").textContent;
    R.unmatched_receipt_not_shown_as_done = !text.includes("WO-777") && text.includes("等總監讀取") && text.includes("只當歷史");
    // F05 revision doc hash differs from registered: no options, send blocked
    emit("choiceReplies", []); emit("choiceReceipts", []); emit("choiceRevisions", [rev("sha256:other")]); await tick();
    R.mismatch_blocks = !document.querySelector('#open [data-opt="B"]') && document.querySelector("#open .send").disabled
      && document.querySelector("#open article").textContent.includes("對不上");
    // F05 good hash: send, option snapshot rebuilt from registered snapshot, ids present
    emit("choiceRevisions", [rev(H)]); await tick();
    document.querySelector('#open [data-opt="B"]').click();
    document.querySelector("#open .send").click(); await tick();
    const w = fixture.writes.filter(x => x[0] === "choiceReplies").map(x => x[1]);
    R.good_send = w.length === 1 && w[0].snapshotHash === H && w[0].choice === "B" && w[0].revision === 1
      && w[0].selectedOptionSnapshot.label === "Beta" && w[0].selectedOptionSnapshot.desc === "db"
      && !!w[0].submissionId && !!w[0].pageSource && w[0].kind === "choice";
    // retry after failure keeps the submissionId only while content is the same (second question CH-02)
    const q2 = {id: "CH-02", revision: 1, status: "open", snapshotHash: "sha256:g2"};
    const rev2 = {id: "rev2", questionId: "CH-02", revision: 1, title: "T2", snapshotHash: "sha256:g2",
      options: [{key: "A", label: "Alpha"}, {key: "B", label: "Beta"}]};
    emit("decisions", [q, q2]); emit("choiceRevisions", [rev(H), rev2]); await tick();
    fixture.writes.length = 0; fixture.failNext = 2;
    const c2 = () => document.querySelector('#open article[data-id="CH-02"]');
    c2().querySelector('[data-opt="B"]').click(); c2().querySelector(".send").click(); await tick();
    c2().querySelector(".send").click(); await tick();
    c2().querySelector('[data-opt="A"]').click(); c2().querySelector(".send").click(); await tick();
    const ids = fixture.writes.map(x => x[1].submissionId + ":" + x[1].choice);
    R.retry_same_id_changed_content_new_id = ids.length === 3 && ids[0].split(":")[0] === ids[1].split(":")[0]
      && ids[2].split(":")[0] !== ids[0].split(":")[0];
    // F07 note retry: same text -> same submissionId, carries pageSource
    fixture.writes.length = 0; fixture.failNext = 1;
    document.getElementById("note-text").value = "hello"; document.getElementById("note-send").click(); await tick();
    document.getElementById("note-send").click(); await tick();
    const n = fixture.writes.filter(x => x[0] === "notes").map(x => x[1]);
    R.note_retry_same_id = n.length === 2 && n[0].submissionId === n[1].submissionId && !!n[0].pageSource && n[0].kind === "note";
    // 2.2 follow-up: nohash keeps the answered state; another revision's reply is prior, not legacy; a blocked card does not say "choose again"
    const q3 = {id: "CH-03", revision: 1, status: "open"};
    const rev3 = {id: "rev3", questionId: "CH-03", revision: 1, title: "T3", snapshotHash: "sha256:g3", options: [{key: "A", label: "Alpha"}]};
    const q4 = {id: "CH-04", revision: 2, status: "open", snapshotHash: "sha256:g4"};
    const rev4 = {id: "rev4", questionId: "CH-04", revision: 2, title: "T4", snapshotHash: "sha256:other4", options: [{key: "A", label: "Alpha"}]};
    emit("decisions", [q, q2, q3, q4]); emit("choiceRevisions", [rev(H), rev2, rev3, rev4]);
    emit("choiceReplies", [
      {id: "N1", kind: "choice", questionId: "CH-03", revision: 1, choice: "A", submissionId: "n1", clientAt: "2026-11-08T00:00:00Z", selectedOptionSnapshot: {key: "A", label: "Alpha"}},
      {id: "P1", kind: "choice", questionId: "CH-04", revision: 1, choice: "A", submissionId: "p1", snapshotHash: "sha256:old", clientAt: "2026-11-08T00:00:00Z", selectedOptionSnapshot: {key: "A", label: "Alpha"}},
      {id: "B1", kind: "choice", questionId: "CH-04", revision: 2, choice: "A", submissionId: "b1", snapshotHash: "sha256:bad", clientAt: "2026-11-08T00:00:01Z"}]);
    emit("choiceReceipts", [{questionId: "CH-03", revision: 1, submissionId: "n1", stage: "handed", at: "2026-11-08T00:00:02Z", wo: "WO-030"}]); await tick();
    const ans3 = [...document.querySelectorAll("#answered article")].map(a => a.textContent).find(x => x.includes("WO-030")) || "";
    R.nohash_keeps_answered = ans3.includes("重新登記") && !document.querySelector('#open article[data-id="CH-03"]');
    const open4 = (document.querySelector('#open article[data-id="CH-04"]') || {textContent: ""}).textContent;
    R.other_revision_is_prior_not_legacy = open4.includes("第 1 版選過") && !open4.includes("舊格式");
    R.blocked_card_does_not_say_choose_again = open4.includes("對不上") && !open4.includes("請再選一次") && !open4.includes("請照現在的選項");
  } catch (e) { R.error = String(e && e.stack || e); }
  const m = document.createElement("pre"); m.id = "w3-result"; m.textContent = JSON.stringify(R); document.body.append(m);
}, 100);
"""


def find_chrome(explicit):
    if explicit:
        return explicit if pathlib.Path(explicit).is_file() else None
    env = os.environ.get("DW_CHROME")
    if env and pathlib.Path(env).is_file():
        return env
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    bases = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    for base in filter(None, bases):
        for rel in ("Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe"):
            candidate = pathlib.Path(base) / rel
            if candidate.is_file():
                return str(candidate)
    return None


def skip(reason):
    print("SKIP browser_check: " + reason)
    return 1 if os.environ.get("DW_REQUIRE_BROWSER") == "1" else 0


def version(chrome):
    try:
        out = subprocess.run([chrome, "--version"], capture_output=True, timeout=20).stdout or b""
        text = out.decode("utf-8", "replace").strip()
        if re.search(r"\d+\.\d+\.\d+", text):
            return text
        # Windows Chrome/Edge do not print --version; the install folder has a version-named subfolder.
        dirs = [x.name for x in pathlib.Path(chrome).parent.iterdir() if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", x.name)]
        return (pathlib.Path(chrome).name + " " + max(dirs, key=lambda s: [int(n) for n in s.split(".")])) if dirs else "(version not reported by this browser)"
    except Exception as exc:  # noqa: BLE001 - version is informational
        return "(version unknown: %s)" % exc


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chrome")
    ap.add_argument("--page", default=str(ROOT / "templates" / "choice_page.html"))
    a = ap.parse_args()
    chrome = find_chrome(a.chrome)
    if not chrome:
        return skip("no Chrome/Chromium/Edge found (use --chrome or DW_CHROME)")
    tpl = pathlib.Path(a.page).read_text(encoding="utf-8")
    html = tpl.replace("<script>", "<script>" + STUB + "</script>\n<script>", 1) + "\n<script>" + PROBE + "</script>"
    flags = ["--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
             "--host-resolver-rules=MAP * ~NOTFOUND", "--no-proxy-server", "--virtual-time-budget=6000", "--dump-dom"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        flags.append("--no-sandbox")
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "p.html"
        f.write_text(html, encoding="utf-8")
        try:
            r = subprocess.run([chrome] + flags + ["--user-data-dir=" + str(pathlib.Path(d) / "prof"), f.as_uri()],
                               capture_output=True, text=True, encoding="utf-8", timeout=120)
        except subprocess.TimeoutExpired:
            print("browser_check: Chrome timed out")
            print("browser: " + version(chrome))
            return 1
    m = re.search(r'<pre id="w3-result">([^<]+)</pre>', r.stdout)
    if not m:
        print("browser_check: no result from the page (exit %s) %s" % (r.returncode, r.stderr[-400:]))
        print("browser: " + version(chrome))
        return 1
    vals = json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    for k, v in vals.items():
        print("%s=%s" % (k, v))
    print("browser: " + version(chrome))
    return 0 if "error" not in vals and vals and all(v is True for v in vals.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
