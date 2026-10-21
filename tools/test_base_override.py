#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/test_base_override.py — risk_factor_penetration 的資料根可覆寫測試（零網路）

驗的是「整支程式的讀寫根都被 LONGJIU_BASE 控制」，不是只驗輸出檔名：
  ① 不設環境變數 → BASE ＝正式路徑（預設行為不變，正式執行不受影響）
  ② 設 LONGJIU_BASE → BASE 跟著換
  ③ 讀取根也換：load() 必須讀到覆寫目錄裡的 snapshot.json（不是正式那份）
  ④ 寫入點在原始碼中是 BASE 組合（AST 檢查），且全檔只有一個硬編路徑字面（env 預設值）

背景：2026-10-21 沙盒測試時本檔讀正式 snapshot.json、把 PNG 寫回正式目錄，
      導致 clone 隔離失效。修法只用一個環境變數覆寫，不動計算邏輯。
"""
from __future__ import annotations

import ast
import importlib
import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

PROD = r"C:\Users\bot\Desktop\longjiu_system"
ok = fail = 0


def check(name: str, cond: bool) -> None:
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✅ {name}")
    else:
        fail += 1
        print(f"  ❌ {name}")


print("=== risk_factor_penetration 資料根覆寫測試 ===")

import risk_factor_penetration as rfp  # noqa: E402

# ① 預設（無環境變數）
os.environ.pop("LONGJIU_BASE", None)
rfp = importlib.reload(rfp)
check("不設 LONGJIU_BASE → BASE 為正式路徑", str(rfp.BASE) == PROD)

# ② 環境變數覆寫
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    os.environ["LONGJIU_BASE"] = str(tmp)
    rfp = importlib.reload(rfp)
    check("設定 LONGJIU_BASE → BASE 跟著換", Path(rfp.BASE) == tmp)

    # ③ 讀取根：覆寫目錄內的檔案才是它讀到的
    (tmp / "snapshot.json").write_text('{"marker": "sandbox-only"}', encoding="utf-8")
    check("load() 讀到覆寫目錄（非正式 snapshot）",
          rfp.load("snapshot.json").get("marker") == "sandbox-only")

# ④ 靜態：寫入點由 BASE 組合；全檔僅一個硬編路徑字面（且為 env 預設）
src = (BASE / "risk_factor_penetration.py").read_text(encoding="utf-8")
tree = ast.parse(src)
write_ok = False
literals = []
for node in ast.walk(tree):
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and PROD in node.value:
        literals.append(node.value)
    # out = BASE / f"risk_factor_penetration_{TODAY}.png"
    if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "out":
        v = node.value
        if isinstance(v, ast.BinOp) and getattr(v.left, "id", "") == "BASE":
            write_ok = True
check("PNG 寫入點由 BASE 組合（非字面路徑）", write_ok)
check("全檔只有一個硬編路徑字面，且為 env 預設值",
      len(literals) == 1 and "os.environ.get" in src)

os.environ.pop("LONGJIU_BASE", None)
print(f"\n=== 覆寫測試：PASS {ok} / FAIL {fail} ===")
sys.exit(0 if fail == 0 else 1)
