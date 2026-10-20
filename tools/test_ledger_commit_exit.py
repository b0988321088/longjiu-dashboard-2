# -*- coding: utf-8 -*-
"""test_ledger_commit_exit.py — TD-20261013-01 事件帳本提交出口回歸測試（2026-10-21）

測什麼：nightly_dashboard_sync.py 把 error_register.md／inc_events.jsonl 納入 22:15
提交集之後，四種情境的行為是否正確：

  L1 正常追加         → 兩檔被提交、推送一次、rc=0
  L2 重複執行（無變更）→ 不產生空 commit、rc=0
  L3 只有儀表板檔變更  → 行為與舊版相同（不因新增帳本而改變）
  L4 審查失敗         → 撤回 commit、內容留在工作區、不推送、rc=1（可重試）
  L5 未授權變更       → 不被納入 commit、仍留 dirty（收工檢查會攔）
  L6 推送失敗         → commit 保留（不撤回）、rc=1（可重試）、內容不丟

做法：把真腳本複製到臨時 git repo，只把 REPO 常數換成該目錄，並在該目錄放
      三個樁（publish_gate／cio_lane／auto_push.py），用環境變數控制它們的回應。
      全程不動正式 repo。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "nightly_dashboard_sync.py"
DASH = ["radar_state.json", "schedule_events.json", "work_log.json", "snapshot.json",
        "pending_decisions.json", "dashboard_decisions.json", "us30y_state.json"]
LEDGERS = ["error_register.md", "inc_events.jsonl"]

STUB_GATE = '''# -*- coding: utf-8 -*-
import os
def classify_paths(root, changed, ref="HEAD"):
    must = os.environ.get("LJ_STUB_GATE_CIO", "1") == "1"
    return {"must_cio": must, "mode": "CIO" if must else "AUTO", "changed": list(changed)}
'''

STUB_LANE = '''# -*- coding: utf-8 -*-
import os
def review_and_record(tag=""):
    ok = os.environ.get("LJ_STUB_CIO_OK", "1") == "1"
    open(os.path.join(os.path.dirname(__file__), "CIO_CALLED"), "a").write(tag + "\\n")
    return ok, ("APPROVE（stub）" if ok else "REJECT（stub）")
'''

STUB_PUSH = '''# -*- coding: utf-8 -*-
import os, sys
rc = int(os.environ.get("LJ_STUB_PUSH_RC", "0"))
with open(os.path.join(os.path.dirname(__file__), "PUSH_CALLED"), "a") as f:
    f.write(str(rc) + "\\n")
print("stub auto_push rc=%d" % rc)
sys.exit(rc)
'''

PASS = FAIL = 0
def ck(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}｜{detail}")
    else:
        FAIL += 1
        print(f"  FAIL {name}｜{detail}")


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def make_repo() -> Path:
    d = Path(tempfile.mkdtemp(prefix="ledger_exit_"))
    git(d, "init", "-q")
    git(d, "config", "user.email", "t@example.com")
    git(d, "config", "user.name", "t")
    for f in DASH + LEDGERS + ["other.txt"]:
        (d / f).write_text("v0\n", encoding="utf-8")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "init")

    # 樁
    (d / "publish_gate.py").write_text(STUB_GATE, encoding="utf-8")
    (d / "cio_lane.py").write_text(STUB_LANE, encoding="utf-8")
    (d / "auto_push.py").write_text(STUB_PUSH, encoding="utf-8")

    # 真腳本（只換 REPO 常數）
    src = SRC.read_text(encoding="utf-8")
    src2, n = re.subn(r'REPO = r"[^"]*"', f'REPO = r"{d.as_posix()}"', src, count=1)
    assert n == 1, "找不到 REPO 常數"
    (d / "nightly_dashboard_sync.py").write_text(src2, encoding="utf-8")
    return d


def run(repo: Path, **env_extra) -> subprocess.CompletedProcess:
    env = dict(os.environ, **env_extra)
    return subprocess.run([sys.executable, "nightly_dashboard_sync.py"], cwd=str(repo),
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=env)


def commits(repo: Path) -> int:
    return int(git(repo, "rev-list", "--count", "HEAD").stdout.strip() or 0)


def head_files(repo: Path) -> list[str]:
    out = git(repo, "show", "--name-only", "--format=", "HEAD").stdout
    return sorted(x for x in out.splitlines() if x.strip())


def porcelain(repo: Path) -> str:
    return git(repo, "status", "--porcelain").stdout


def cleanup(d: Path) -> None:
    shutil.rmtree(d, ignore_errors=True)


print("=== L1 正常追加：只有兩份帳本有變更 → 應提交並推送 ===")
d = make_repo()
try:
    (d / "error_register.md").write_text("v0\n## INCIDENT abcd1234\n", encoding="utf-8")
    (d / "inc_events.jsonl").write_text('v0\n{"id":"x"}\n', encoding="utf-8")
    r = run(d)
    n = commits(d)
    files = head_files(d)
    ck("rc=0", r.returncode == 0, f"rc={r.returncode}")
    ck("產生 1 顆新 commit", n == 2, f"commits={n}")
    ck("commit 只含兩份帳本", files == sorted(LEDGERS), f"{files}")
    ck("推送被呼叫一次且成功", (d / "PUSH_CALLED").exists() and (d / "PUSH_CALLED").read_text().strip() == "0")
    ck("帳本已無未提交變更", not [x for x in porcelain(d).splitlines() if "error_register" in x or "inc_events" in x],
       porcelain(d).strip()[:80])

    print("=== L2 重複執行（無變更）→ 不得產生空 commit ===")
    before = commits(d)
    r2 = run(d)
    ck("rc=0", r2.returncode == 0, f"rc={r2.returncode}")
    ck("commit 數不變", commits(d) == before, f"{before}→{commits(d)}")
    ck("未再次推送", (d / "PUSH_CALLED").read_text().count("\n") == 1,
       (d / "PUSH_CALLED").read_text().strip())
finally:
    cleanup(d)

print("=== L3 只有儀表板檔變更 → 舊行為不變 ===")
d = make_repo()
try:
    (d / "snapshot.json").write_text("v1\n", encoding="utf-8")
    r = run(d)
    ck("rc=0", r.returncode == 0, f"rc={r.returncode}")
    ck("commit 只含該儀表板檔", head_files(d) == ["snapshot.json"], f"{head_files(d)}")
finally:
    cleanup(d)

print("=== L4 審查失敗 → 撤回 commit、內容保留、不推送、rc=1 ===")
d = make_repo()
try:
    (d / "error_register.md").write_text("v0\n## INCIDENT ffff0000\n", encoding="utf-8")
    (d / "inc_events.jsonl").write_text('v0\n{"id":"y"}\n', encoding="utf-8")
    r = run(d, LJ_STUB_CIO_OK="0")
    ck("rc=1", r.returncode == 1, f"rc={r.returncode}")
    ck("commit 已撤回（HEAD 未前進）", commits(d) == 1, f"commits={commits(d)}")
    ck("未呼叫推送", not (d / "PUSH_CALLED").exists())
    dirty = porcelain(d)
    ck("兩份帳本內容仍留在工作區",
       "error_register.md" in dirty and "inc_events.jsonl" in dirty, dirty.replace("\n", " ")[:90])
    ck("內容未被覆蓋", "ffff0000" in (d / "error_register.md").read_text(encoding="utf-8"))

    print("=== L4b 同一天的第二次執行：審查恢復後可重試成功 ===")
    r2 = run(d)
    ck("rc=0", r2.returncode == 0, f"rc={r2.returncode}")
    ck("重試後成功產生 commit", commits(d) == 2, f"commits={commits(d)}")
finally:
    cleanup(d)

print("=== L5 未授權變更不得被納入 commit、且仍被攔下 ===")
d = make_repo()
try:
    (d / "error_register.md").write_text("v0\n## INCIDENT 1234abcd\n", encoding="utf-8")
    (d / "other.txt").write_text("unauthorized\n", encoding="utf-8")
    r = run(d)
    files = head_files(d)
    ck("rc=0", r.returncode == 0, f"rc={r.returncode}")
    ck("commit 不含未授權檔", "other.txt" not in files, f"{files}")
    ck("未授權檔仍留 dirty（收工檢查會攔）", "other.txt" in porcelain(d))
finally:
    cleanup(d)

print("=== L6 推送失敗 → commit 保留可重試、內容不丟 ===")
d = make_repo()
try:
    (d / "inc_events.jsonl").write_text('v0\n{"id":"z"}\n', encoding="utf-8")
    r = run(d, LJ_STUB_PUSH_RC="2")
    ck("rc=1", r.returncode == 1, f"rc={r.returncode}")
    ck("commit 保留（未被撤回）", commits(d) == 2, f"commits={commits(d)}")
    ck("推送確實嘗試過", (d / "PUSH_CALLED").exists())
    ck("帳本內容完整", '{"id":"z"}' in (d / "inc_events.jsonl").read_text(encoding="utf-8"))
finally:
    cleanup(d)

print("=" * 60)
print(f"合計 {PASS} PASS / {FAIL} FAIL")
sys.exit(0 if FAIL == 0 else 1)
