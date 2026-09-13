# -*- coding: utf-8 -*-
"""補完 build_rebalance_dashboard.py（該檔有一組字串重複出現 2 次）"""
import ast
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
P = BASE / "build_rebalance_dashboard.py"
src = P.read_text(encoding="utf-8")
IMPORT_LINE = "import pledge_status as _pf  # 2026-09-13 質押文字唯一來源（動態）\n"

EDITS = [
    ('_plan_lines.append("🔍 質押：9/11 先申購貝萊德B11 500萬（未質押）→ B11 過戶(~9/16) 後整池 1,200萬×4.5成=540萬@2.77% 質押（撥款~9/25）→ 還安聯300萬@4.2%＋餘240萬標案押標金（元大50萬待確認）")',
     '_plan_lines.append(_pf.pledge_status_line())', 1),
    ('("9/11", "先申購貝萊德B11 500萬（未質押）→ 過戶後整池 1,200萬×4.5成=540萬@2.77%質押", "high"),',
     '("9/11", f"整池質押 {_pf.pledge_status_line(style=\'short\')}", "high"),', 2),
    ('"最大等待：9/11 申購貝萊德B11 500萬 → 過戶(~9/16) 後整池質押 540萬@2.77% → 撥款 ~9/25 → 還債（4.2%→2.77%）。", ""]',
     'f"最大等待：整池質押 {_pf.pledge_status_line(style=\'short\')} → 撥款到位即清償高息負債。", ""]', 1),
    ('ltv_txt = "未質押（9/11 先申購B11 500萬；整池質押 540萬@2.77%，撥款~9/25）"',
     'ltv_txt = f"未質押（{_pf.pledge_status_line(style=\'card\')}）"', 1),
]

for old, new, want in EDITS:
    n = src.count(old)
    assert n == want, f"出現 {n} 次（預期 {want}）：{old[:40]}"
    src = src.replace(old, new)

if "import pledge_status as _pf" not in src:
    m = re.search(r"^(import |from ).*$", src, flags=re.M)
    idx = src.find("\n", m.end()) + 1 if m else 0
    src = src[:idx] + IMPORT_LINE + src[idx:]

ast.parse(src)
P.write_text(src, encoding="utf-8")
print("✅ build_rebalance_dashboard.py 已更新；殘留檢查：",
      re.findall(r"還安聯300萬@4\.2%＋餘240萬|9/11 先申購貝萊德B11", src))
