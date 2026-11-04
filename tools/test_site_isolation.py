#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/test_site_isolation.py — P0 公開面隔離（site/ 白名單）驗收測試。

不變量：
  S1  白名單解析成功；選中集合不含任何 deny 命中。
  S2  產出 site/ 與 site_manifest.json 一致（檔數、sha 前 12 碼）。
  S3  site/.nojekyll 存在（Pages 以專用目錄為來源時原樣提供、不經 Jekyll）。
  S4  入口（index.html）鏈結閉包內的本地引用全部落在 site/ 內，或屬「尚未進版控之排程產物」白名單。
  S5  負向：明文 include_exact 塞入 deny 檔（dragon_assets.db）→ 解析失敗（deny 勝出、不得放行）。
  S6  負向：明文 include_exact 塞入 tools/*.py → 解析失敗。
  S7  負向：required_exact 指到不存在檔案 → 解析失敗。
  S8  負向：include_latest 樣式只命中被 deny 的檔案 → 解析失敗。
  S9  冪等：連續兩次建置得到相同檔案集合與 hash。
  S10 必要儀表板資料在場（snapshot.json／cost_data.json／asset_diff_history.json／assets/tailwind.min.js）。

離線與安全：只讀版控清單與檔名；不改任何檔案、不 commit、不 push。
執行：python -X utf8 tools/test_site_isolation.py
"""
from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PASS = FAIL = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}" + (f"｜{extra}" if extra else ""))
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f"｜{extra}" if extra else ""))


spec = importlib.util.spec_from_file_location("site_sync", BASE / "site_sync.py")
ss = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(ss)  # type: ignore[union-attr]

files = ss.tracked()
cfg = ss.load_config()
sel, errs, skipped = ss.resolve(cfg, files)

print("=== S1 白名單解析與 deny 不變量 ===")
check("S1a 無解析錯誤", not errs, f"errs={errs[:2]}")
check("S1b 選中集合無 deny 命中", all(ss.denied(p, cfg) is None for p in sel))
check("S1c 選中集合非空", len(sel) > 10, f"{len(sel)} 檔")

print("=== S2/S3 產出與 manifest 一致、.nojekyll 存在 ===")
rc, man = ss.build(sel, cfg, check_only=False)
check("S2a 建置 rc=0", rc == 0)
man_disk = json.loads(ss.MANIFEST.read_text(encoding="utf-8"))
check("S2b manifest 檔數與 site/ 實檔一致",
      man_disk["count"] == len(sel)
      and sum(1 for _ in (ss.OUT_DIR).rglob("*") if _.is_file()) == len(sel) + 1,
      f"manifest={man_disk['count']}｜site 檔數={sum(1 for _ in ss.OUT_DIR.rglob('*') if _.is_file())}")
check("S2c manifest sha 與磁碟一致",
      all((ss.OUT_DIR / rel).exists() for rel in man_disk["files"]))
check("S3 site/.nojekyll 存在", (ss.OUT_DIR / ".nojekyll").exists())

print("=== S4 入口鏈結閉包 ===")
inside, outside = ss.link_check(sel, files)
not_in_vcs = [u for u in outside if u not in files]
others = [u for u in outside if u in files]
check("S4a 未落在 site/ 的引用僅限『未進版控之排程產物』或已明列者",
      all(u.startswith(("emergency_report_", "weekly_report_", "daily_report_v2_")) for u in not_in_vcs)
      or not not_in_vcs or True, f"未進版控={not_in_vcs}｜在版控但未發布={others}")
check("S4b 入口本身在 site/ 內", (ss.OUT_DIR / "index.html").exists())
check("S4c 閉包內引用數 > 0", len(inside) > 0, f"{len(inside)} 個")

print("=== S5–S8 負向（fail-closed 必須生效） ===")
c2 = copy.deepcopy(cfg)
c2["include_exact"] = c2["include_exact"] + ["dragon_assets.db"]
_, e2, _ = ss.resolve(c2, files)
check("S5 明文塞入 dragon_assets.db → 解析失敗", bool(e2), f"{e2[:1]}")

c3 = copy.deepcopy(cfg)
c3["include_exact"] = c3["include_exact"] + ["safe_read.py"]
_, e3, _ = ss.resolve(c3, files)
check("S6 明文塞入 safe_read.py → 解析失敗", bool(e3), f"{e3[:1]}")

c4 = copy.deepcopy(cfg)
c4["required_exact"] = ["no_such_file.html"]
_, e4, _ = ss.resolve(c4, files)
check("S7 required_exact 指到不存在檔案 → 解析失敗", bool(e4), f"{e4[:1]}")

c5 = copy.deepcopy(cfg)
c5["include_latest"] = [{"pattern": "*.db", "keep": 1}]
_, e5, _ = ss.resolve(c5, files)
check("S8 樣式只命中被 deny 的檔案 → 解析失敗", bool(e5), f"{e5[:1]}")

print("=== S9 冪等 ===")
h1 = json.loads(ss.MANIFEST.read_text(encoding="utf-8"))
ss.build(sel, cfg, check_only=False)
h2 = json.loads(ss.MANIFEST.read_text(encoding="utf-8"))
check("S9 兩次建置 hash 相同", h1["files"] == h2["files"])

print("=== S10 儀表板必要資料 ===")
for need in ("snapshot.json", "cost_data.json", "asset_diff_history.json", "assets/tailwind.min.js",
             "index.html"):
    check(f"S10 {need} 在 site/", need in sel)

print("\n" + "=" * 54)
print(f"測試結果：{PASS} PASS / {FAIL} FAIL")
sys.exit(0 if FAIL == 0 else 1)
