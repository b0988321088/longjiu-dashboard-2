#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""唯讀沙箱自測：self_publish.commit_own（自身產出就地提交）— 不碰真 repo、不連網、不碰遠端。

覆蓋：
  A 正向：本輪寫出的產物 → commit 只含該檔＋呼叫 auto_push（--script 正確）＋rc 原樣帶回
  B 誘餌：清單外的 dirty 檔不得被帶進 commit，且跑完仍為 dirty
  C 無變更：產物與 HEAD 相同 → 不 commit、不呼叫 auto_push
  D 窗口外：mtime 早於本輪起跑（本輪沒寫它）→ 不認領
  E 清單安全檢查：空清單／絕對路徑／`*` 開頭／`*` 前綴過短／程式副檔名 → 一律拒絕（rc=2）
  F staged 超出認領清單（他檔已被 stage）→ fail-closed：不 commit、不 push
  G 樣式展開：`notion_bridge/*.md` 只展開該目錄的 .md，不掃其他目錄
"""
import datetime as dt
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(r"C:/Users/bot/Desktop/longjiu_system")
ROOT = (pathlib.Path(os.environ["LOCALAPPDATA"]) / "Temp" /
        f"self_publish_selftest_{dt.datetime.now():%Y%m%d_%H%M%S}")
STUB_PUSH = """import json, os, sys
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "AUTO_PUSH_CALLS.jsonl"), "a",
          encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:], ensure_ascii=False) + "\\n")
sys.exit(int(os.environ.get("STUB_PUSH_RC", "0")))
"""
FAILS = []


def check(name, cond, detail=""):
    if not cond:
        FAILS.append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   | " + detail) if detail else ""))


def g(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def new_sandbox(tag):
    d = ROOT / tag
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    g(d, "init", "-q")
    g(d, "config", "user.email", "selftest@local")
    g(d, "config", "user.name", "selftest")
    g(d, "config", "core.autocrlf", "false")
    shutil.copy2(REPO / "self_publish.py", d / "self_publish.py")
    (d / "auto_push.py").write_text(STUB_PUSH, encoding="utf-8", newline="\n")
    return d


def load(d, tag):
    """在沙箱目錄載入 self_publish（REPO 由 __file__ 決定 → 指向沙箱）。"""
    name = f"self_publish_{tag}_{dt.datetime.now():%H%M%S%f}"
    spec = importlib.util.spec_from_file_location(name, d / "self_publish.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def baseline(d, files):
    for rel, content in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
    g(d, "add", "-A")
    g(d, "commit", "-q", "-m", "baseline")
    return g(d, "rev-parse", "HEAD").stdout.strip()


def head(d):
    return g(d, "rev-parse", "HEAD").stdout.strip()


def changed_in_head(d):
    return sorted(x for x in g(d, "show", "--name-only", "--format=", "HEAD").stdout.splitlines() if x)


def push_calls(d):
    f = d / "AUTO_PUSH_CALLS.jsonl"
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


def dirty(d, rel):
    return bool(g(d, "status", "--porcelain", "--", rel).stdout.strip())


# ---- A：正向 ----------------------------------------------------------------
def case_a():
    d = new_sandbox("A")
    baseline(d, {"cost_data.json": "old", "keep.txt": "x"})
    h0 = head(d)
    mod = load(d, "A")
    (d / "cost_data.json").write_text("new", encoding="utf-8", newline="\n")   # 本輪寫出
    rc = mod.commit_own("probe_a.py", ["cost_data.json"])
    check("A1 commit 內容只含自家產物", changed_in_head(d) == ["cost_data.json"])
    check("A2 走 auto_push 唯一出口且帶 --script", push_calls(d) == [["--script", "probe_a.py"]])
    check("A3 rc 原樣帶回（0）", rc == 0, f"rc={rc}")
    check("A4 HEAD 前進", head(d) != h0)
    check("A5 提交訊息署名 producer", "probe_a.py" in g(d, "log", "-1", "--format=%B").stdout)


# ---- B：誘餌 ----------------------------------------------------------------
def case_b():
    d = new_sandbox("B")
    baseline(d, {"cost_data.json": "old", "decoy.md": "old"})
    mod = load(d, "B")
    (d / "cost_data.json").write_text("new", encoding="utf-8", newline="\n")
    (d / "decoy.md").write_text("他班改的", encoding="utf-8", newline="\n")
    mod.commit_own("probe_b.py", ["cost_data.json"])
    check("B1 誘餌未被帶進 commit", changed_in_head(d) == ["cost_data.json"])
    check("B2 誘餌跑完仍 dirty（保留原狀）", dirty(d, "decoy.md"))


# ---- C：無變更 --------------------------------------------------------------
def case_c():
    d = new_sandbox("C")
    baseline(d, {"cost_data.json": "same"})
    h0 = head(d)
    mod = load(d, "C")
    (d / "cost_data.json").write_text("same", encoding="utf-8", newline="\n")   # 同內容重寫
    rc = mod.commit_own("probe_c.py", ["cost_data.json"])
    check("C1 無變更不 commit", head(d) == h0)
    check("C2 無變更不呼叫 auto_push", push_calls(d) == [])
    check("C3 rc = producer rc", rc == 0)


# ---- D：窗口外 --------------------------------------------------------------
def case_d():
    d = new_sandbox("D")
    baseline(d, {"cost_data.json": "old"})
    h0 = head(d)
    f = d / "cost_data.json"
    f.write_text("他班稍早改的", encoding="utf-8", newline="\n")
    old = dt.datetime.now().timestamp() - 600
    os.utime(f, (old, old))                                    # mtime 早於本輪起跑
    mod = load(d, "D")
    rc = mod.commit_own("probe_d.py", ["cost_data.json"])
    check("D1 窗口外（mtime < T0）不認領", head(d) == h0)
    check("D2 不呼叫 auto_push", push_calls(d) == [])
    check("D3 rc = producer rc", rc == 0)


# ---- E：清單安全檢查 --------------------------------------------------------
def case_e():
    d = new_sandbox("E")
    baseline(d, {"cost_data.json": "old"})
    mod = load(d, "E")
    bad = {
        "空清單": [],
        "絕對路徑": ["C:/Windows/win.ini"],
        "`*` 開頭": ["*.json"],
        "前綴過短（ab*）": ["ab*.json"],
        "程式副檔名": ["build_dashboard.py"],
        "含 ..": ["../outside.json"],
        "指向 .git": [".git/CIO_APPROVED"],
    }
    for label, allow in bad.items():
        try:
            rc = mod.commit_own("probe_e.py", allow)
        except SystemExit as exc:                             # 條目檢查走 SystemExit(2)
            rc = exc.code
        check(f"E 拒絕：{label}", rc == 2, f"rc={rc}")


# ---- F：staged 超出認領清單 -------------------------------------------------
def case_f():
    d = new_sandbox("F")
    baseline(d, {"cost_data.json": "old", "other.json": "old"})
    h0 = head(d)
    mod = load(d, "F")
    (d / "cost_data.json").write_text("new", encoding="utf-8", newline="\n")
    (d / "other.json").write_text("他檔", encoding="utf-8", newline="\n")
    g(d, "add", "--", "other.json")                           # 模擬他班已 stage
    rc = mod.commit_own("probe_f.py", ["cost_data.json"])
    check("F1 staged 超出 → fail-closed 不 commit", head(d) == h0, f"rc={rc}")
    check("F2 不呼叫 auto_push", push_calls(d) == [])
    check("F3 rc 非 0", rc != 0, f"rc={rc}")


# ---- G：樣式展開 ------------------------------------------------------------
def case_g():
    d = new_sandbox("G")
    baseline(d, {"notion_bridge/2026-10-12_strategy_handbook.md": "old",
                 "other/2026-10-12_thing.md": "old"})
    mod = load(d, "G")
    (d / "notion_bridge/2026-10-12_strategy_handbook.md").write_text("new", encoding="utf-8", newline="\n")
    (d / "other/2026-10-12_thing.md").write_text("new", encoding="utf-8", newline="\n")
    mod.commit_own("probe_g.py", ["notion_bridge/*.md"])
    check("G1 樣式只展開自身目錄", changed_in_head(d) == ["notion_bridge/2026-10-12_strategy_handbook.md"])
    check("G2 其他目錄同名樣式不受影響", dirty(d, "other/2026-10-12_thing.md"))


# ---- H：起跑時刻契約（since= 覆寫）----------------------------------------
def case_h():
    d = new_sandbox("H")
    baseline(d, {"cost_data.json": "old"})
    f = d / "cost_data.json"
    f.write_text("本輪寫的", encoding="utf-8", newline="\n")      # 先寫檔（mtime=now）
    mod = load(d, "H")                                          # 之後才載入 → T0 晚於 mtime
    h0 = head(d)
    rc = mod.commit_own("probe_h.py", ["cost_data.json"])
    check("H1 模組晚於產物載入 → 不認領（契約）", head(d) == h0 and push_calls(d) == [], f"rc={rc}")
    rc = mod.commit_own("probe_h.py", ["cost_data.json"], since=f.stat().st_mtime - 1)
    check("H2 明確傳入 since= → 可認領", changed_in_head(d) == ["cost_data.json"], f"rc={rc}")


if __name__ == "__main__":
    print(f"self_publish 沙箱自測（{ROOT}）")
    for fn in (case_a, case_b, case_c, case_d, case_e, case_f, case_g, case_h):
        fn()
    print(f"\n結果：{'✅ 全部通過' if not FAILS else '❌ 失敗 ' + str(FAILS)}")
    sys.exit(1 if FAILS else 0)
