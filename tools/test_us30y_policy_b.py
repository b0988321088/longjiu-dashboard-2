#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/test_us30y_policy_b.py — B 案（5.20 純顯示／行動綁 5.30＋連續5日）驗收測試

用途
----
1. 無參數：跑契約測試（預設必須與舊制逐位元相同；切到 B 案後的判定必須符合規格）。
2. `--sim`：抓 Yahoo ^TYX 近 6 個月的日線，印出「舊制 vs B 案各自會觸發幾次／幾日」
   —— 給 12/01 裁決用的實證，不改任何檔案、不寫 state。

設計原則
--------
門檻變更屬決策層：預設（APPROVED=False）行為不得有任何變化，否則測試直接 fail。
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import us30y_policy as pol            # noqa: E402
import us30y_monitor as mon           # noqa: E402

FAIL = []


def ok(cond, name, extra=""):
    print(("  ✅ " if cond else "  ❌ ") + name + (f"｜{extra}" if extra else ""))
    if not cond:
        FAIL.append(name)


def _rows(vals):
    """[(date, rate)] 由新到舊（與 monitor 的 rows 同序）。"""
    return [(f"2026-11-{30 - i:02d}", v) for i, v in enumerate(vals)]


def test_default_legacy():
    print("\n① 舊制基準（強制 APPROVED=False 時）必須與 2026-11-04 前逐位元相同")
    _saved = pol.APPROVED
    pol.APPROVED = False
    try:
        ok(pol.is_active() is False, "is_active() False")
        ok(pol.action_consecutive_days() == 2, "行動連續日數＝2（舊制）")
        ok("舊制" in pol.describe(), "describe() 顯示舊制")
        # 舊制：連 2 日 ≥5.30 即觸發
        ok(mon.red_line_hit(_rows([5.31, 5.32])) is True, "舊制 2 日 ≥5.30 → 觸發")
        ok(mon.red_line_hit(_rows([5.31, 5.20])) is False, "舊制 1 日 ≥5.30 → 不觸發")
    finally:
        pol.APPROVED = _saved


def test_shipped_state():
    print("\n①b 上線狀態（APPROVED=True，2026-11-04 使用者裁決）")
    ok(pol.APPROVED is True, "APPROVED=True（已上線）")
    ok(pol.is_active("2026-11-30") is False, "11/30 尚未生效（凍結期內不放行）")
    ok(pol.is_active("2026-12-01") is True, "12/01 起生效")
    # 今日（< 生效日）→ 模組層常數仍為舊制，產線行為不變
    ok(mon.RED_CONSECUTIVE_DAYS == 2, "今日 RED_CONSECUTIVE_DAYS＝2（生效日未到）")


def test_active_gate():
    print("\n② 生效閘門：核准＋日期雙條件")
    pol.APPROVED = True
    try:
        ok(pol.is_active("2026-11-30") is False, "核准但 11/30 → 仍未生效")
        ok(pol.is_active("2026-12-01") is True, "核准且 12/01 → 生效")
        ok(pol.action_consecutive_days("2026-12-01") == 5, "生效後連續日數＝5")
        ok(pol.action_consecutive_days("2026-11-30") == 2, "生效前仍為 2")
        ok(pol.is_active("bad-date") is False, "日期解析失敗 → fail-closed 未生效")
    finally:
        pol.APPROVED = False


def test_b_rules():
    print("\n③ B 案判定（5.20 不觸發行動、5.30 需連 5 日）")
    mon.RED_CONSECUTIVE_DAYS = 5
    try:
        ok(mon.red_line_hit(_rows([5.45, 5.45, 5.45, 5.45])) is False, "4 日 ≥5.30 → 不觸發")
        ok(mon.red_line_hit(_rows([5.45, 5.45, 5.45, 5.45, 5.45])) is True, "5 日 ≥5.30 → 觸發")
        ok(mon.red_line_hit(_rows([5.45, 5.45, 5.45, 5.45, 5.29])) is False, "第5日跌破 5.30 → 不觸發")
        ok(mon.red_line_hit(_rows([5.29, 5.25, 5.21])) is False, "5.20-5.30 區間 → 完全不觸發行動")
    finally:
        mon.RED_CONSECUTIVE_DAYS = 2


def test_display_helpers():
    print()
    print("⑤ 顯示層文案（8 個報表共用；今日舊制／12-01 後 B 案）")
    _saved = pol.is_active
    try:
        pol.is_active = lambda *a, **k: False
        ok(pol.band_text() == "5.20-5.30%", "舊制 band_text")
        ok("美股停購" in pol.band_action(), "舊制 band_action 含美股停購")
        ok("連續2日" in pol.red_text(), "舊制 red_text 連續2日")
        ok("連3日" not in pol.entry_text() and "連續2日" in pol.entry_text(), "舊制 entry_text 連續2日")
        ok("警戒區" in pol.us30y_state_text(5.29), "舊制 state(5.29) 警戒區")
        _g = pol.gate_rows()
        ok(len(_g) == 3 and "美股停購" in _g[1][2], "舊制 gate_rows 3 列且含停購")
    finally:
        pol.is_active = _saved
    _saved2 = pol.is_active
    try:
        pol.is_active = lambda *a, **k: True
        ok("5.30" in pol.band_text() and "連續5日" in pol.band_text(), "B 案 band_text")
        ok("不凍結" in pol.band_action(), "B 案 band_action 明確不凍結")
        ok("連續5日" in pol.red_text(), "B 案 red_text 連續5日")
        ok("連續5日" in pol.entry_text(), "B 案 entry_text 連續5日")
        ok("僅顯示" in pol.us30y_state_text(5.29), "B 案 state(5.29) 僅顯示")
        ok("才凍結" in pol.us30y_state_text(5.35), "B 案 state(5.35) 才凍結")
        _g2 = pol.gate_rows()
        ok("不凍結" in _g2[0][2] and "顯示用" in _g2[1][2], "B 案 gate_rows 語意正確")
    finally:
        pol.is_active = _saved2


def test_label():
    print("\n④ 文案口徑")
    ok("防禦" in mon.MODE_LABELS["A"] or "警戒" in mon.MODE_LABELS["A"], "模式A 標籤可讀")
    ok("5.30" in pol.describe() or "舊制" in pol.describe(), "describe() 有明確門檻敘述")


def sim():
    print("\n⑤ 實證：近 6 個月舊制 vs B 案（不改檔、不寫 state）")
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETYX?range=6mo&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    res = json.load(urllib.request.urlopen(req, timeout=30))["chart"]["result"][0]
    ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
    import time as _t
    pts = [(_t.strftime("%Y-%m-%d", _t.gmtime(t)), v) for t, v in zip(ts, cl) if v is not None]
    pts.reverse()  # 由新到舊

    def count(need_red, need_a):
        red_days = a_days = 0
        red_runs = a_runs = 0
        for i in range(len(pts)):
            row = pts[i:i + need_red]
            if len(row) == need_red and all(v >= 5.30 for _, v in row):
                red_days += 1
                if i == 0 or not (len(pts[i - 1:i - 1 + need_red]) == need_red
                                  and all(v >= 5.30 for _, v in pts[i - 1:i - 1 + need_red])):
                    red_runs += 1
            row_a = pts[i:i + need_a]
            if len(row_a) == need_a and all(v >= 5.20 for _, v in row_a):
                a_days += 1
                if i == 0 or not (len(pts[i - 1:i - 1 + need_a]) == need_a
                                  and all(v >= 5.20 for _, v in pts[i - 1:i - 1 + need_a])):
                    a_runs += 1
        return red_days, red_runs, a_days, a_runs

    for label, (nr, na) in (("舊制（紅線2日／模式A 2日）", (2, 2)), ("B 案（紅線5日）", (5, 2))):
        rd, rr, ad, ar = count(nr, na)
        print(f"  {label}：紅線觸發 {rr} 段／{rd} 個判定日；模式A(顯示) 觸發 {ar} 段／{ad} 日")
    print(f"  樣本：{pts[0][0]} {pts[0][1]:.3f}%（最新）｜{pts[-1][0]} {pts[-1][1]:.3f}%（最舊）")


def main():
    print("═══ B 案驗收（us30y_policy）═══")
    test_default_legacy()
    test_shipped_state()
    test_active_gate()
    test_b_rules()
    test_display_helpers()
    test_label()
    if "--sim" in sys.argv:
        sim()
    print(f"\n[RESULT] {'PASS' if not FAIL else 'FAIL ' + str(len(FAIL)) + ' 項：' + '／'.join(FAIL)}")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
