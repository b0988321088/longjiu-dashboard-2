#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""唯讀沙箱自測：22:40 收工稽核「未提交」修復（不改真 repo、不連網、不碰遠端）。

覆蓋：
  A. wrappers/cost_watch_close.py（22:30 close 班）：自身產出就地提交＋推送唯一出口
     A1 有變更 → commit 只含自身檔案、呼叫 auto_push
     A2 誘餌髒檔（.scratch）不得被掃進 commit、跑完仍為髒
     A3 無變更 → 不 commit、不呼叫 auto_push
     A4 close 本體失敗（rc≠0）→ 帳本照提交推送，但 rc 仍非 0（不靜默）
  B. append_dashboard_decisions.py（決策入庫唯一入口）：入庫寫入集就地提交
     B1 唯一待推 commit → 提交＋推送；commit 只含 2 檔；JSON 合法、收據 +1
     B2 另有待推 commit → 只提交、不代推
     B3 讀不到 origin/clean-main → 只提交、不代推
     B4 --dry-run → 不寫入、不提交
"""
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(r"C:/Users/bot/Desktop/longjiu_system")
ROOT = (pathlib.Path(os.environ["LOCALAPPDATA"]) / "Temp" /
        f"closeout_fix_selftest_{dt.datetime.now():%Y%m%d_%H%M%S}")
OWN_W = ("cost.html", "cost_data.json", "data/ai_cost_daily.jsonl")
OWN_A = ("dashboard_decisions.json", "data/decision_intake_receipts.jsonl")
FAILS = []


def g(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def run_py(script, cwd, *args):
    return subprocess.run([sys.executable, str(script), *args], cwd=str(cwd),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   | " + detail) if detail else ""))


def commit_files(cwd):
    out = g(cwd, "show", "--name-only", "--format=", "HEAD").stdout.split()
    return sorted(out)


def head_count(cwd):
    return int((g(cwd, "rev-list", "--count", "HEAD").stdout or "0").strip())


def fresh(name):
    d = ROOT / name
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    g(d, "init", "-q")
    g(d, "config", "core.autocrlf", "true")
    g(d, "config", "user.name", "selftest")
    g(d, "config", "user.email", "selftest@localhost")
    return d


def write_wrapper(d):
    src = (REPO / "wrappers" / "cost_watch_close.py").read_text(encoding="utf-8")
    assert 'REPO = r"C:/Users/bot/Desktop/longjiu_system"' in src, "wrapper REPO 常數樣式改變，自測需同步"
    (d / "w_close.py").write_text(
        src.replace('REPO = r"C:/Users/bot/Desktop/longjiu_system"', f'REPO = r"{d.as_posix()}"'),
        encoding="utf-8", newline="")
    # stub 真身：寫一行帳本
    (d / "cost_watch.py").write_text(
        "import pathlib,sys\n"
        "if '--fail' in sys.argv: sys.exit(3)\n"
        "p=pathlib.Path('data/ai_cost_daily.jsonl'); p.parent.mkdir(exist_ok=True)\n"
        "n=len(p.read_text(encoding='utf-8').splitlines()) if p.exists() else 0\n"
        "with p.open('a',encoding='utf-8',newline='') as f: f.write('{\"row\": %d}\\r\\n' % (n+1))\n",
        encoding="utf-8", newline="")
    # stub auto_push：記錄呼叫
    (d / "auto_push.py").write_text(
        "import pathlib,sys\n"
        "with pathlib.Path('push_calls.log').open('a',encoding='utf-8') as f: f.write(' '.join(sys.argv[1:])+'\\n')\n",
        encoding="utf-8", newline="")
    (d / "cost.html").write_text("v1", encoding="utf-8", newline="")
    (d / "cost_data.json").write_text('{"v":1}', encoding="utf-8", newline="")
    (d / "data").mkdir(exist_ok=True)
    (d / "data" / "ai_cost_daily.jsonl").write_text('{"row": 0}\r\n', encoding="utf-8", newline="")
    g(d, "add", "-A")
    g(d, "commit", "-qm", "seed")


def write_append_env(d):
    src = (REPO / "append_dashboard_decisions.py").read_text(encoding="utf-8")
    assert "REPO = Path(__file__).resolve().parent" in src, "append REPO 推導樣式改變，自測需同步"
    (d / "append_dashboard_decisions.py").write_text(src, encoding="utf-8", newline="")
    dec = ("{\r\n  \"decisions\": [\r\n  {\r\n    \"id\": \"mem-seed-1\",\r\n    \"task\": \"seed\"\r\n  }\r\n"
           "  ],\r\n  \"meta\": {\"count\": 1}\r\n}\r\n")
    (d / "dashboard_decisions.json").write_text(dec, encoding="utf-8", newline="")
    (d / "data").mkdir(exist_ok=True)
    (d / "auto_push.py").write_text(
        "import pathlib,sys\n"
        "with pathlib.Path('push_calls.log').open('a',encoding='utf-8') as f: f.write(' '.join(sys.argv[1:])+'\\n')\n",
        encoding="utf-8", newline="")
    g(d, "add", "-A")
    g(d, "commit", "-qm", "seed")
    g(d, "update-ref", "refs/remotes/origin/clean-main", "HEAD")


def main():
    if ROOT.exists():
        shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True, exist_ok=True)

    print("=== A) wrappers/cost_watch_close.py ===")
    d = fresh("A")
    write_wrapper(d)
    n0 = head_count(d)
    p = run_py(d / "w_close.py", d)
    check("A1 有變更：exit 0", p.returncode == 0, f"rc={p.returncode} out={p.stdout.strip()[-120:]}")
    check("A1 commit +1", head_count(d) == n0 + 1)
    check("A1 commit 只含自身檔案", set(commit_files(d)) <= set(OWN_W) and "data/ai_cost_daily.jsonl" in commit_files(d), str(commit_files(d)))
    check("A1 呼叫 auto_push 唯一出口", "cost_watch_close.py" in (d / "push_calls.log").read_text(encoding="utf-8"))
    check("A1 帳本已被提交（工作區乾淨）",
          not [x for x in g(d, "status", "--porcelain").stdout.splitlines()
               if "push_calls.log" not in x],
          repr(g(d, "status", "--porcelain").stdout))

    (d / ".scratch").write_text("decoy", encoding="utf-8")
    (d / "cost.html").write_text("v2", encoding="utf-8", newline="")
    p = run_py(d / "w_close.py", d)
    check("A2 誘餌髒檔不入 commit", ".scratch" not in commit_files(d) and "cost.html" in commit_files(d), str(commit_files(d)))
    check("A2 誘餌跑完仍為髒", ".scratch" in g(d, "status", "--porcelain").stdout)
    check("A2 帳本仍被提交", "data/ai_cost_daily.jsonl" not in g(d, "status", "--porcelain").stdout)

    # A3：真身不再改檔（模擬「當日帳本已是最新值」）
    (d / "cost_watch.py").write_text("# no-op 真身\n", encoding="utf-8", newline="")
    calls0 = (d / "push_calls.log").read_text(encoding="utf-8")
    n1 = head_count(d)
    p = run_py(d / "w_close.py", d)
    check("A3 無變更：不 commit", head_count(d) == n1)
    check("A3 無變更：不呼叫 auto_push",
          (d / "push_calls.log").read_text(encoding="utf-8") == calls0)
    check("A3 無變更：訊息說明略過", "無變更" in p.stdout, p.stdout.strip()[-80:])

    (d / "cost_watch.py").write_text(
        "import pathlib\n"
        "p=pathlib.Path('data/ai_cost_daily.jsonl')\n"
        "with p.open('a',encoding='utf-8',newline='') as f: f.write('{\"row\": 99}\\r\\n')\n"
        "import sys\nsys.exit(3)\n",
        encoding="utf-8", newline="")
    (d / "cost.html").write_text("v3", encoding="utf-8", newline="")
    n2 = head_count(d)
    p = run_py(d / "w_close.py", d)
    check("A4 close 失敗仍提交帳本", head_count(d) == n2 + 1)
    check("A4 close 失敗仍推送", "cost_watch_close.py" in (d / "push_calls.log").read_text(encoding="utf-8")[-200:])
    check("A4 close 失敗 rc≠0（不靜默）", p.returncode != 0, f"rc={p.returncode}")

    print("=== B) append_dashboard_decisions.py ===")
    d = fresh("B1")
    write_append_env(d)
    (d / ".scratch").write_text("decoy", encoding="utf-8")
    n0 = head_count(d)
    p = run_py(d / "append_dashboard_decisions.py", d,
               "--task", "自測入庫", "--summary", "沙箱", "--quiet")
    check("B1 exit 0", p.returncode == 0, f"rc={p.returncode} {p.stdout.strip()[-120:]} {p.stderr.strip()[-120:]}")
    check("B1 commit +1", head_count(d) == n0 + 1)
    check("B1 commit 只含自身兩檔", commit_files(d) == sorted(OWN_A), str(commit_files(d)))
    check("B1 唯一待推 → 有推送", "append_dashboard_decisions.py" in (d / "push_calls.log").read_text(encoding="utf-8"))
    check("B1 stdout 標示已提交並推送", "已提交並推送" in p.stdout, p.stdout.strip()[-80:])
    dec = json.loads((d / "dashboard_decisions.json").read_text(encoding="utf-8"))
    check("B1 決策 +1", len(dec["decisions"]) == 2)
    check("B1 收據 +1", len((d / "data" / "decision_intake_receipts.jsonl").read_text(encoding="utf-8").splitlines()) == 1)
    check("B1 誘餌不受影響", ".scratch" in g(d, "status", "--porcelain").stdout)
    src = (d / "dashboard_decisions.json").read_text(encoding="utf-8")
    check("B1 未整檔重排（seed 段逐字保留）", '"id": "mem-seed-1"' in src and src.count('"decisions"') == 1)

    d = fresh("B2")
    write_append_env(d)
    (d / "other.txt").write_text("x", encoding="utf-8")
    g(d, "add", "other.txt")
    g(d, "commit", "-qm", "別班待推 commit")
    p = run_py(d / "append_dashboard_decisions.py", d,
               "--task", "自測入庫2", "--summary", "沙箱", "--quiet")
    check("B2 只提交不代推", "待推 2 顆" in p.stdout and not (d / "push_calls.log").exists(),
          p.stdout.strip()[-90:])

    d = fresh("B3")
    write_append_env(d)
    g(d, "update-ref", "-d", "refs/remotes/origin/clean-main")
    p = run_py(d / "append_dashboard_decisions.py", d,
               "--task", "自測入庫3", "--summary", "沙箱", "--quiet")
    check("B3 讀不到基準 → 只提交不代推",
          "讀不到 origin/clean-main" in p.stdout and not (d / "push_calls.log").exists(),
          p.stdout.strip()[-90:])

    d = fresh("B4")
    write_append_env(d)
    n0 = head_count(d)
    p = run_py(d / "append_dashboard_decisions.py", d,
               "--task", "自測入庫4", "--summary", "沙箱", "--quiet", "--dry-run")
    check("B4 dry-run 不提交", head_count(d) == n0)
    check("B4 dry-run 不寫收據", not (d / "data" / "decision_intake_receipts.jsonl").exists())
    check("B4 dry-run 無推送", not (d / "push_calls.log").exists())

    print()
    print(f"結果：{'ALL PASS' if not FAILS else 'FAIL ' + str(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
