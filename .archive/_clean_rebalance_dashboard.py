# -*- coding: utf-8 -*-
"""清理 build_rebalance_dashboard.py 中的亂碼與舊邏輯"""
import re
from pathlib import Path

P = Path("build_rebalance_dashboard.py")
text = P.read_text(encoding="utf-8")

# 1. 找到所有 ── 本週投資計劃 開頭到下個章節的範圍
start = text.find("# ── 本週投資計劃")
end = text.find("# ── 動作建議")
assert start != -1 and end != -1
new_block = """    # ── 本週投資計劃（2026-09-13 v3：動態全資產面結論）──
    try:
        _plan_html = ""
        _rs = json.loads((Path(__file__).resolve().parent / "radar_state.json").read_text(encoding="utf-8"))
        _rows = (_rs.get("weekly_plan", {}) or {}).get("rows") or []
        for r in _rows:
            _plan_html += f"<div style='margin-bottom:6px;font-size:11px;color:#d1fae5'>{r.get('動作','')} <b>{r.get('類別','')}</b>：{r.get('內容','')}</div>"
        
        html = html.replace('<h2>📋 本週投資計劃（8/29 全資產面結論）</h2>', f'<h2>📋 本週投資計劃（{TODAY} 全資產面結論）</h2>')
        html = html.replace('{_plan_html}', _plan_html)
    except Exception as _e2:
        _plan_html = f"<div class='card'><h2>📋 本週投資計劃</h2><div style='color:#999'>產生失敗: {_e2}</div></div>"
        html = html.replace('{_plan_html}', _plan_html)
"""
text = text[:start] + new_block + text[end:]
P.write_text(text, encoding="utf-8")
print("✅ 清理完成")
