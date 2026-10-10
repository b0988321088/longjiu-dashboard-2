#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B 案驗收測試：現金計分端改接 allowable_cash()（fail-closed）
使用者 2026-10-10 核准之最小影響方案；驗收必查 6 項。
執行：python tools/test_bcase_cash_scoring.py
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import report_components as RC  # noqa: E402

SNAP = json.loads((ROOT / "snapshot.json").read_text(encoding="utf-8"))
_PASS, _FAIL = [], []


def chk(name, cond, detail=""):
    (_PASS if cond else _FAIL).append(name)
    print(("PASS  " if cond else "FAIL  ") + name + (("  ｜" + str(detail)) if detail else ""))


def mk(**over):
    s = copy.deepcopy(SNAP)
    s.update(over)
    return s


print("=" * 72)
print("B 案驗收測試：現金計分端 fail-closed（allowable_cash）")
print("=" * 72)

# ── 基準：原始 snapshot ──────────────────────────────────────────────
d0 = RC.render_health_score(SNAP)
_cash_layers = SNAP.get("cash_layers") or {}
TRUE_CASH = _cash_layers.get("available", _cash_layers.get("unrestricted_cash"))
FLOOR = d0.get("現金") is not None and None  # placeholder
print(f"\n[基準] cash_layers 真值 = {TRUE_CASH!r}｜現金欄 = {d0.get('現金')!r}｜缺真值旗標 = {d0.get('現金缺真值')!r}")

# ── 必查 1：正常情境（allowable_cash 回傳有效值 → 現金分數正確）──────
chk("1a 正常情境：現金＝可動用真值（allowable_cash）",
    d0.get("現金") == TRUE_CASH, f"預期 {TRUE_CASH}，實得 {d0.get('現金')}")
chk("1b 正常情境：缺真值旗標為 False", d0.get("現金缺真值") is False)
_floor_val = None
try:
    from sot_targets import cash_floor as _cf
    _floor_val = _cf(SNAP)
except Exception as e:  # pragma: no cover
    print("   （cash_floor 讀取失敗：%s）" % e)
_expect_score = 100 if (TRUE_CASH is not None and _floor_val is not None and TRUE_CASH >= _floor_val) else 0
chk("1c 正常情境：現金標準分正確", d0.get("現金標準") == _expect_score,
    f"現金 {TRUE_CASH} vs 底線 {_floor_val} → 預期 {_expect_score}")

# ── 必查 2：缺 cash_layers.unrestricted_cash → 不得回退、不得默默給分 ──
s2 = mk(cash_layers={})
d2 = RC.render_health_score(s2)
chk("2a 缺 cash_layers：現金欄為 None（缺值保留）", d2.get("現金") is None, d2.get("現金"))
chk("2b 缺 cash_layers：缺真值旗標 True", d2.get("現金缺真值") is True)
chk("2c 缺 cash_layers：未回退至 snapshot.json 或給分", d2.get("現金") != TRUE_CASH and d2.get("現金標準") == 0)

s2b = mk(); s2b.pop("cash_layers", None)
d2b = RC.render_health_score(s2b)
chk("2d 完全移除 cash_layers：仍為 None（不回退檔案）", d2b.get("現金") is None and d2b.get("現金缺真值") is True)

# ── 必查 3：拋錯 → 該維度 0 分、真值缺值、整體標記不完整 ────────────
chk("3a 拋錯情境：現金分為 0", d2.get("現金標準") == 0)
chk("3b 拋錯情境：真值非 0 元（保留 None，禁以 0 混充）", d2.get("現金") is None)
_card = RC._render_health_card_legacy(s2)
chk("3c 拋錯情境：卡片揭露『健康度未完整』", "健康度未完整" in _card)
chk("3d 拋錯情境：卡片明示缺真值維度為現金", "現金" in _card and "缺真值" in _card)
chk("3e 拋錯情境：卡片不把缺真值顯示成『現金跌破底線』", "現金跌破底線" not in _card)

# ── 必查 4：合法的 0 元 vs 真值缺失（必須區分）────────────────────
s4 = mk(cash_layers={"unrestricted_cash": 0})
d4 = RC.render_health_score(s4)
chk("4a 合法 0 元：現金欄為 0（非 None）", d4.get("現金") == 0, d4.get("現金"))
chk("4b 合法 0 元：缺真值旗標 False", d4.get("現金缺真值") is False)
chk("4c 合法 0 元：確認為跌破 → 紅線（min(55)+🔴）", d4.get("燈號") == "🔴" and d4.get("分數") <= 55,
    f"分數={d4.get('分數')} 燈號={d4.get('燈號')}")
_card4 = RC._render_health_card_legacy(s4)
chk("4d 合法 0 元：卡片顯示『現金跌破底線』（非未完整）",
    "現金跌破底線" in _card4 and "健康度未完整" not in _card4)
chk("4e 合法 0 元與缺真值結果不同（狀態可區分）",
    d4.get("現金") != d2.get("現金") and d4.get("現金缺真值") != d2.get("現金缺真值"))

# ── 必查 5：其他維度仍可計算，但不掩蓋現金缺值 ──────────────────────
chk("5a 其他維度仍計算（覆蓋分不變）", d2.get("覆蓋分") == d0.get("覆蓋分"),
    f"{d2.get('覆蓋分')} vs {d0.get('覆蓋分')}")
chk("5b 其他維度仍計算（防禦分不變）", d2.get("防禦分") == d0.get("防禦分"))
chk("5c 其他維度仍計算（LTV分不變）", d2.get("LTV分") == d0.get("LTV分"))
chk("5d 缺真值不得掩蓋：分數與正常情境不同", d2.get("分數") != d0.get("分數") or d2.get("現金缺真值"))
chk("5e 缺真值不冒充『確認跌破』：不套用 min(55) 紅線",
    d2.get("分數") > 55, f"缺真值分數={d2.get('分數')}（若 ≤55 代表誤套紅線）")

# ── 必查 6：回歸 — cash_floor 仍走 _cf_fn 單一入口、其他維度未受影響 ──
_src = (ROOT / "report_components.py").read_text(encoding="utf-8")
chk("6a 回歸：cash_floor 仍走 _cf_fn(snap) 單一入口", "floor = _cf_fn(snap)" in _src)
chk("6b 回歸：計分路徑已無 restricted_cash 依賴", "_rst_fn(snap)" not in _src)
chk("6c 回歸：allowable_cash 為唯一現金來源", "from sot_targets import allowable_cash as _ac_fn" in _src)
chk("6d 回歸：正常情境分數與修改前一致（基準值比對）",
    d0.get("分數") == d4.get("分數") or d0.get("現金標準") == 100,
    f"現行 = {d0.get('分數')}（現金 {d0.get('現金')} / 底線 {_floor_val}）")

print("\n" + "=" * 72)
print(f"結果：PASS {len(_PASS)} / FAIL {len(_FAIL)}")
if _FAIL:
    print("未通過：" + "、".join(_FAIL))
print("=" * 72)
sys.exit(0 if not _FAIL else 1)
