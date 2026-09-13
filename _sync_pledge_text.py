# -*- coding: utf-8 -*-
"""把其餘生成腳本的「貼死質押敘述」改為呼叫 pledge_status（2026-09-13）

每個 (檔案, 舊字串, 新字串) 都要求舊字串在檔內唯一出現，否則整批不寫入。
新字串一律以 {_pf.pledge_status_line(...)} 動態插值（檔內會自動補 import）。
"""
import ast
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

IMPORT_LINE = "import pledge_status as _pf  # 2026-09-13 質押文字唯一來源（動態）\n"

EDITS = [
    # ── build_rebalance_dashboard.py ──
    ("build_rebalance_dashboard.py",
     '_plan_lines.append("🔍 質押：9/11 先申購貝萊德B11 500萬（未質押）→ B11 過戶(~9/16) 後整池 1,200萬×4.5成=540萬@2.77% 質押（撥款~9/25）→ 還安聯300萬@4.2%＋餘240萬標案押標金（元大50萬待確認）")',
     '_plan_lines.append(_pf.pledge_status_line())'),
    ("build_rebalance_dashboard.py",
     '("9/11", "先申購貝萊德B11 500萬（未質押）→ 過戶後整池 1,200萬×4.5成=540萬@2.77%質押", "high"),',
     '("9/11", f"整池質押 {_pf.pledge_status_line(style=\'short\')}", "high"),'),
    ("build_rebalance_dashboard.py",
     '"最大等待：9/11 申購貝萊德B11 500萬 → 過戶(~9/16) 後整池質押 540萬@2.77% → 撥款 ~9/25 → 還債（4.2%→2.77%）。", ""]',
     'f"最大等待：整池質押 {_pf.pledge_status_line(style=\'short\')} → 撥款到位即清償高息負債（月息 {_pf.pledge_facts()[\'月息_舊\']:,.0f} → {_pf.pledge_facts()[\'月息_新\']:,.0f}）。", ""]'),
    ("build_rebalance_dashboard.py",
     'ltv_txt = "未質押（9/11 先申購B11 500萬；整池質押 540萬@2.77%，撥款~9/25）"',
     'ltv_txt = f"未質押（{_pf.pledge_status_line(style=\'card\')}）"'),
    # ── build_rebalance_report.py ──
    ("build_rebalance_report.py",
     '_plan_items.append("🔍 質押：9/11 先申購貝萊德B11 500萬（未質押）→ B11 過戶(~9/16) 後整池 1,200萬×4.5成=540萬@2.77% 質押（撥款~9/25）→ 還安聯300萬@4.2%＋餘240萬標案押標金（元大50萬待確認）")',
     '_plan_items.append(_pf.pledge_status_line())'),
    ("build_rebalance_report.py",
     '｜9/11 定案：500萬MMF 贖回轉申購貝萊德B11 500萬（未質押）→ 整池1,200萬×4.5成=質押540萬@2.77%→還安聯300萬@4.2%＋餘240萬標案押標金（撥款~9/25；元大50萬待確認）</div>',
     '｜質押（動態）：{_pf.pledge_status_line()}</div>'),
    # ── build_penetration_report.py ──
    ("build_penetration_report.py",
     "PI 質押 540萬@2.77% 尚未撥款（9/11 先申購貝萊德B11 500萬、未質押；整池 1,200萬×4.5成 質押待 B11 過戶後送件、撥款約 2 週 ≈9/25）；",
     "{_pf.pledge_status_line()}；"),
    # ── build_weekly_report.py ──
    ("build_weekly_report.py",
     "<tr><td>2026-09-16 後</td><td>貝萊德 B11 500萬 過戶 → 整池 1,200萬×4.5成 = 540萬@2.77% 質押（撥款 ~9/25）</td><td>⏳</td></tr>",
     "<tr><td>{_pf.pledge_facts()['撥款預估日']}</td><td>{_pf.pledge_status_line(style='card')}</td><td>⏳</td></tr>"),
    ("build_weekly_report.py",
     "→ 整池1,200萬×4.5成 = 質押540萬@2.77% → 還安聯300萬@4.2%＋餘240萬標案押標金</li>",
     "→ {_pf.pledge_status_line()}</li>"),
    ("build_weekly_report.py",
     "<li><b>9/11 定案</b>：先申購貝萊德B11 500萬（未質押）→ B11 過戶後整池質押 540萬@2.77%（1,200萬池×4.5成）；還債優先序：安聯 300萬@4.2% 第一</li>",
     "<li><b>質押現況</b>：{_pf.pledge_status_line()}</li>"),
    # ── build_audit_dashboard.py ──
    ("build_audit_dashboard.py",
     "<li><b>9/11 未質押</b>：先把 MMF 500萬贖回款投入<b>貝萊德B11 500萬</b>（申購中、待過戶）→ 之後整池（富達600+聯博100+B11 500）1,200萬×4.5成 = <b>540萬@2.77%</b> 質押（撥款 ~9/25）→ 還安聯 300萬@4.2% + 餘 240萬標案押標金；避險衛星 00635U 黃金 ~105萬 延後（華許放鷹+金價偏高，等回檔）</li>",
     "<li><b>質押（動態）</b>：{_pf.pledge_status_line()}</li>"),
    # ── build_retirement_plan.py ──
    ("build_retirement_plan.py",
     "整池質押 540萬@2.77% 還安聯300@4.2%＋240萬押標金（年省 ~4.3萬）；洲際W轉貸 ≤2.5%；築巢 2.185% 生效 → 負債成本逐階下探</td></tr>",
     "{_pf.pledge_status_line()}；洲際W轉貸 ≤2.5%；築巢 2.185% 生效 → 負債成本逐階下探</td></tr>"),
    ("build_retirement_plan.py",
     "<li>① 債務優化（高息清零）— 執行中（9/11 先申購B11；整池質押 540萬@2.77% 還安聯）</li>",
     "<li>① 債務優化（高息清零）— 執行中（{_pf.pledge_status_line(style='short')}）</li>"),
    # ── build_final.py ──
    ("build_final.py",
     "'📅 9/11：申購貝萊德B11 500萬（未質押）→ 過戶後整池質押 540 萬@2.77%（撥款 ~9/25）還安聯 300 + 餘240萬押標金',",
     "'📅 質押：' + _pf.pledge_status_line(),"),
    ("build_final.py",
     "'1️⃣ 【您】9/11 申購貝萊德B11 500萬（未質押）→ 過戶後整池質押 540 萬@2.77%',",
     "'1️⃣ 【您】' + _pf.pledge_status_line(style='card'),"),
    # ── entry_monitor.py ──
    ("entry_monitor.py",
     'alerts.append("🎯 PI 已認列 → 執行鏈啟動：\\n├ 台股慢慢買 0050/006208（每週 1.5-2萬）\\n├ 質押富達 350萬@2.77% 還安聯300+元大50\\n└ 黃金衛星 00635U 第一批 ≤20萬")',
     'alerts.append("🎯 PI 已認列 → 執行鏈啟動：\\n├ 台股分批 0050/006208（單筆 ≤5萬）\\n├ " + _pf.pledge_status_line(style="short") + "\\n└ 黃金衛星 00635U 分批 ≤20萬")'),
]

by_file = {}
for fname, old, new in EDITS:
    by_file.setdefault(fname, []).append((old, new))

changed = []
for fname, pairs in by_file.items():
    p = BASE / fname
    src = p.read_text(encoding="utf-8")
    for old, new in pairs:
        n = src.count(old)
        if n != 1:
            print(f"✗ {fname}: 舊字串出現 {n} 次（需 1）→ 跳過整檔：{old[:40]}…")
            break
        src = src.replace(old, new)
    else:
        if "import pledge_status as _pf" not in src:
            m = re.search(r"^(import |from ).*$", src, flags=re.M)
            idx = src.find("\n", m.end()) + 1 if m else 0
            src = src[:idx] + IMPORT_LINE + src[idx:]
        ast.parse(src)
        p.write_text(src, encoding="utf-8")
        changed.append(fname)

print("✅ 已更新：", ", ".join(changed) or "（無）")
