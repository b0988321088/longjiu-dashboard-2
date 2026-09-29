#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIO 審查 af7af243 必修2/必修3：統一 590 萬質押利率註解為 2.65% + 移除 run_daily 硬編碼。"""
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")

# --- 必修2：註解/文件字串統一為 2.65% ---
FIXES = {
    "asset_sync.py": [
        ("# 2026-09-29：國泰基金質押借款（590萬@2.77%，9/29 10:57 入帳）",
         "# 2026-09-29：國泰基金質押借款（590萬@2.65%，9/29 10:57 入帳）"),
        ('"2026-09-29 起「基金質押」（fund_pledge_loan，國泰 590萬@2.77%）與「券商質押」"',
         '"2026-09-29 起「基金質押」（fund_pledge_loan，國泰 590萬@2.65%）與「券商質押」"'),
    ],
    "pledge_status.py": [
        ("# 2026-09-29：國泰基金質押 590萬@2.77%（撥款入帳）→ 現況質押總額須含此筆",
         "# 2026-09-29：國泰基金質押 590萬@2.65%（撥款入帳）→ 現況質押總額須含此筆"),
    ],
    "build_investment_performance.py": [
        ("# 2026-09-29：國泰基金質押撥款 590萬@2.77%（質押基金池 1,178.6 萬×約5成）",
         "# 2026-09-29：國泰基金質押撥款 590萬@2.65%（質押基金池 1,178.6 萬×約5成）"),
    ],
    "build_penetration_report.py": [
        ("# 2026-09-29：國泰基金質押 590萬@2.6%（9/29 10:57 撥款入帳；表定 540 萬，實撥 590 萬）",
         "# 2026-09-29：國泰基金質押 590萬@2.65%（9/29 10:57 撥款入帳；表定 540 萬，實撥 590 萬）"),
    ],
}
for fn, subs in FIXES.items():
    p = BASE / fn
    t = p.read_text(encoding="utf-8")
    for old, new in subs:
        assert old in t, f"{fn} 找不到：{old[:40]}"
        t = t.replace(old, new)
    p.write_text(t, encoding="utf-8")
    print(f"✅ {fn}：{len(subs)} 處註解統一為 2.65%")

# --- 必修3：run_daily 負債表改讀真值（利率＋基金池），移除硬編碼 ---
p = BASE / "run_daily.py"
t = p.read_text(encoding="utf-8")
old_row = '''    if tv.get('fund_pledge_loan', 0) > 0:
        # 2026-09-29：國泰質押撥款 590萬@2.77%（9/29 10:57 入帳）→ 負債表需列示，否則總負債對不上
        loans_rows_html += f"""          <tr><td>國泰世華</td><td>基金質押（質押基金池 1,178.6 萬）</td><td class="num">2.65%</td><td class="num">{tv['fund_pledge_loan']:,}</td><td>9/29 撥款入帳</td></tr>\\n"""'''
new_row = '''    if tv.get('fund_pledge_loan', 0) > 0:
        # 2026-09-29：國泰質押撥款 590萬@2.65%（9/29 10:57 入帳）→ 負債表需列示，否則總負債對不上。
        # CIO 審查 af7af243 必修3：利率與基金池市值一律讀真值，禁硬編碼（利率 tv.fund_pledge_rate／
        # 池市值讀 snapshot.cathay_pledge_0911.擔保池.合計）。
        _fpr = float(tv.get('fund_pledge_rate') or 0.0265) * 100
        _fpool = float((((snap.get('cathay_pledge_0911') or {}).get('擔保池') or {}).get('合計')) or 0)
        _fpool_txt = f"（質押基金池 {_fpool/10000:,.1f} 萬）" if _fpool else ""
        loans_rows_html += f"""          <tr><td>國泰世華</td><td>基金質押{_fpool_txt}</td><td class="num">{_fpr:.2f}%</td><td class="num">{tv['fund_pledge_loan']:,}</td><td>9/29 撥款入帳</td></tr>\\n"""'''
assert old_row in t, "run_daily 基金質押列找不到"
t = t.replace(old_row, new_row)
p.write_text(t, encoding="utf-8")
print("✅ run_daily.py：基金質押列改讀真值（利率／池市值）")

# tv dict 補 fund_pledge_rate
p = BASE / "run_daily.py"
t = p.read_text(encoding="utf-8")
old_kv = '''        "fund_pledge_loan": snap.get("fund_pledge_loan", 0),'''
new_kv = '''        "fund_pledge_loan": snap.get("fund_pledge_loan", 0),
        "fund_pledge_rate": snap.get("fund_pledge_rate", 0),'''
assert old_kv in t
t = t.replace(old_kv, new_kv)
p.write_text(t, encoding="utf-8")
print("✅ run_daily.py：tv 新增 fund_pledge_rate 真值鍵")
