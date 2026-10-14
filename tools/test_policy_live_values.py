#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""TD-20261014-01 契約測試：政策面「當日市場對照」＋政策文字回歸檢查。

測項：
 A. 真值注入：輸出值必須等於當日 data 真值（證明非寫死）
 B. 真值缺失：明確標示「真值暫缺」，不得退回任何靜態舊值
 C. 邊界：空 dict／None／net=0／momentum 非數值／缺 key 皆不得拋例外
 D. 回歸檢查（tools/check_policy_notes.py）：能抓到違規文字、且不誤判政策事件數值
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

PASS = FAIL = 0


def check(desc: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {desc}")
    else:
        FAIL += 1
        print(f"  ❌ {desc} {extra}")


def load_fn(path: Path, name: str):
    """只取目標函式的 AST 後 exec —— 不執行模組層，避免觸發產線（抓網路／寫 state）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    ns: dict = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
    return ns[name]


render_policy_live = load_fn(BASE / "institutional_flow.py", "render_policy_live")

DATA = {
    "tnx": {"date": "2026-10-14", "last": 5.217, "momentum": 5.16},
    "twd": {"date": "2026-10-14", "last": 32.147, "週變化": 0.00938},
    "cot": {"contracts": {"黃金": {"net": 210335, "date": "2026-10-06"},
                          "原油": {"net": -12446, "date": "2026-10-06"}}},
}
SIG = {"美債10年": {"color": "🔴", "note": "10Y殖利率月動能 +5.2%（急升，債券承壓）"},
       "台幣": {"color": "⚪", "note": "USD/TWD 32.15 週變化 +0.94%"},
       "黃金": {"color": "🟡", "note": "淨多單 210,335 週減 -3.8% — 觀望"},
       "原油": {"color": "🔴", "note": "淨多單 -12,446 週減 -116.8% — 聰明錢撤離"},
       "台股": {"color": "🟢", "note": "外資淨買超 7.0億（連1日）— 台股慢慢買順勢"},
       "Fed流動性": {"color": "⚪", "note": "基準建立中"}}

print("=== A. 真值注入（非寫死）===")
out = render_policy_live(SIG, DATA)
joined = "\n".join(out)
check("含 10Y 殖利率當日值 5.22%", "5.22%" in joined)
check("含 10Y 月動能 +5.2%", "+5.2%" in joined)
check("含 USD/TWD 當日值 32.15", "32.15" in joined)
check("含台幣週變化 +0.94%", "+0.94%" in joined)
check("含黃金 COT 淨多單 210,335", "210,335" in joined)
check("含原油 COT 淨多單 -12,446", "-12,446" in joined)
check("COT 行附資料日期", "2026-10-06" in joined)
check("燈號行逐項輸出（6 項）", sum(1 for k in SIG if f"{k}：" in joined) == 6)

print("=== B. 真值缺失 → 暫缺，不得退回舊值 ===")
out2 = render_policy_live({}, {})
j2 = "\n".join(out2)
check("缺 tnx → 標示真值暫缺", "美債10年殖利率：（真值暫缺）" in j2)
check("缺 twd → 標示真值暫缺", "美元／台幣：（真值暫缺）" in j2)
check("缺 cot → 標示真值暫缺", "黃金 COT：（真值暫缺）" in j2)
check("缺 sig → 燈號標示真值暫缺", "美債10年：（真值暫缺）" in j2)
check("不殘留任何舊值 5.22／32.15／210,335", not any(x in j2 for x in ("5.22", "32.15", "210,335")))

print("=== C. 邊界 ===")
try:
    check("None 輸入不拋例外", isinstance(render_policy_live(None, None), list))
except Exception as e:
    check("None 輸入不拋例外", False, f"→ {e.__class__.__name__}")
try:
    check("空 dict 不拋例外", isinstance(render_policy_live({}, {}), list))
except Exception as e:
    check("空 dict 不拋例外", False, f"→ {e.__class__.__name__}")
d_zero = {"cot": {"contracts": {"黃金": {"net": 0, "date": "d"}, "原油": {"net": 0, "date": "d"}}}}
check("net=0 仍視為有效值（顯示 0）", "淨多單 0" in "\n".join(render_policy_live({}, d_zero)))
d_bad = dict(DATA, tnx={"date": "x", "last": 5.2, "momentum": "NaN"})
check("momentum 非數值不炸且不輸出月動能", "月動能" not in "\n".join(render_policy_live({}, d_bad)))
d_partial = {"cot": {"contracts": {"黃金": {"net": None, "date": "d"}}}}
check("COT net=None → 暫缺", "黃金 COT：（真值暫缺）" in "\n".join(render_policy_live({}, d_partial)))

print("=== D. 回歸檢查 check_policy_notes.py ===")
CHK = BASE / "tools" / "check_policy_notes.py"
check("檢查腳本存在", CHK.exists())


def run_chk(policy_notes: dict):
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "radar_state.json"
        f.write_text(json.dumps({"policy_notes": policy_notes}, ensure_ascii=False), encoding="utf-8")
        return subprocess.run([sys.executable, str(CHK), "--state", str(f)],
                              capture_output=True, text=True, encoding="utf-8")


r_clean = run_chk({"新聞1": {"內容": "FOMC 升息 1 碼，利率區間 3.75-4.00%（政策事實，允許）"},
                   "記錄時間": "2026-09-20 13:30"})
check("政策事件數值 → PASS（不誤判）", r_clean.returncode == 0, f"rc={r_clean.returncode} {r_clean.stdout[:120]}")

r_bad1 = run_chk({"新聞2": {"市場反應": "10Y 月動能 +6.2% 急升"}})
check("抓到『10Y 月動能 +6.2%』", r_bad1.returncode == 1, f"rc={r_bad1.returncode}")
r_bad2 = run_chk({"新聞2": {"市場反應": "USD/TWD 31.76（週 +0.27%）"}})
check("抓到『USD/TWD 31.76』", r_bad2.returncode == 1, f"rc={r_bad2.returncode}")
r_bad3 = run_chk({"原油綜合判斷": "COT 淨多單 -17,845（週增 28%）"})
check("抓到『淨多單 -17,845』", r_bad3.returncode == 1, f"rc={r_bad3.returncode}")
r_bad4 = run_chk({"債券升息敏感度": "債券桶 28.8%（7,507,641，目標 25% 超配）"})
check("抓到『債券桶 28.8%』", r_bad4.returncode == 1, f"rc={r_bad4.returncode}")
r_bad5 = run_chk({"新聞2": {"市場反應": "美債10年殖利率 5.22%（當日）"}})
check("抓到『美債10年殖利率 5.22%』", r_bad5.returncode == 1, f"rc={r_bad5.returncode}")

# 歷史事件數據（已發生、附日期）不得誤判為違規
r_hist = run_chk({"新聞1": {
    "內容": "9/15-16 FOMC 升息 1 碼：3.50-3.75% → 3.75-4.00%（政策事實）",
    "市場反應": "9/18 台股開 46,449.56、盤中站上 47,000（台積電 +35 元、觸及 2,460）；US30Y 5.34→9/17 收 5.29"}})
check("歷史事件數據（附日期）→ PASS（不誤判）", r_hist.returncode == 0,
      f"rc={r_hist.returncode} {r_hist.stdout.strip()[:120]}")

print("=== E. 實際 radar_state.json 現況 ===")
live = subprocess.run([sys.executable, str(CHK)], cwd=str(BASE),
                      capture_output=True, text=True, encoding="utf-8")
check("現有 radar_state.json → PASS（已無機敏殘留）", live.returncode == 0,
      f"rc={live.returncode} {live.stdout.strip()[:160]}")

print()
print("=" * 46)
print(f"PASS {PASS} / FAIL {FAIL}")
sys.exit(1 if FAIL else 0)
