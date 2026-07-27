#!/usr/bin/env python3
"""Notion 摘要快照 — 供 Gemini 網頁瀏覽用"""
import json, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
TODAY = datetime.date.today().isoformat()

# ── Asset Summary ──
cash = SNAP.get("cash_total", 0)
sec = SNAP.get("securities_total_market_value", 0)
ins = SNAP.get("insurance_current_value", 0)
fund = SNAP.get("fund_market_value", 0)
total = cash + sec + ins + fund
pen = SNAP.get("penetration", {})
apct = pen.get("actual_pct", {})
tgt = pen.get("targets", {})

# ── Holdings ──
holdings = SNAP.get("securities", {}).get("holdings", [])

html = f"""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="utf-8">
<title>龍九控股 Notion 快照 {TODAY}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:-apple-system,sans-serif;background:#fff;color:#1d1d1f;max-width:720px;margin:20px auto;padding:0 16px;line-height:1.6}}
h1{{font-size:22px;font-weight:700;border-bottom:2px solid #0071e3;padding-bottom:8px}}
h2{{font-size:17px;font-weight:600;margin-top:20px}}
table{{width:100%;border-collapse:collapse;font-size:14px;margin:8px 0}}
th{{background:#f5f5f7;padding:6px 8px;text-align:left;font-weight:600;border:1px solid #d2d2d7}}
td{{padding:6px 8px;border:1px solid #d2d2d7}}
.num{{text-align:right}}
.summary{{background:#f5f5f7;padding:12px;border-radius:8px;font-size:14px;margin:12px 0}}
.footer{{color:#86868b;font-size:12px;text-align:center;margin-top:24px;border-top:1px solid #d2d2d7;padding-top:12px}}
</style></head><body>
<h1>📊 龍九控股 Notion 即時快照</h1>
<p style="color:#86868b;font-size:14px">{TODAY} · 供 Gemini 讀取用</p>

<div class="summary">
<b>總資產：{total:,} TWD</b><br>
證券 {sec:,} · 保險 {ins:,} · 基金 {fund:,} · 現金 {cash:,}
</div>

<h2>🎯 穿透配置</h2>
<table><thead><tr><th>類別</th><th class="num">實際</th><th class="num">目標</th></tr></thead><tbody>
<tr><td>台股</td><td class="num">{apct.get("台股市值型成長",0):.1f}%</td><td class="num">{tgt.get("台股市值型目標",0)}%</td></tr>
<tr><td>美股</td><td class="num">{apct.get("美股市值型成長",0):.1f}%</td><td class="num">{tgt.get("美股市值型目標",0)}%</td></tr>
<tr><td>防守型</td><td class="num">{apct.get("防守型配息",0):.1f}%</td><td class="num">{tgt.get("配息型目標",0)}%</td></tr>
<tr><td>債券</td><td class="num">{apct.get("債券",0):.1f}%</td><td class="num">{tgt.get("債券型目標",0)}%</td></tr>
<tr><td>現金</td><td class="num">{apct.get("現金/安全網",0):.1f}%</td><td class="num">{tgt.get("現金目標",0)}%</td></tr>
</tbody></table>

<h2>📋 持股明細</h2>
<table><thead><tr><th>代碼</th><th>股數</th><th class="num">現價</th><th class="num">市值</th><th class="num">損益</th></tr></thead><tbody>
"""
for h in sorted(holdings, key=lambda x: x["value"], reverse=True):
    pnl_cls = "" if h["pnl"] >= 0 else "color:red"
    html += f"<tr><td><b>{h['ticker']}</b></td><td>{h['shares']:,}</td><td class='num'>{h['price']:.2f}</td><td class='num'>{h['value']:,}</td><td class='num' style='{pnl_cls}'>{h['pnl']:+,}</td></tr>"

html += """</tbody></table>
<h2>📋 決策追蹤</h2>
<p style="font-size:14px;color:#86868b">以下為執行中決策，可直接提問 Gemini：</p>
<ul style="font-size:14px">
"""

# Read pending decisions
try:
    dec = json.loads((BASE / "pending_decisions.json").read_text(encoding="utf-8"))
    for d in dec:
        html += f"<li><b>{d['title']}</b> — {d['status']}</li>"
except:
    html += "<li>無</li>"

html += """</ul>
<div class="footer">龍九控股 Notion Bridge · 數據源: snapshot.json · 自動更新</div>
</body></html>"""

out = BASE / "notion_gemini_bridge.html"
out.write_text(html, encoding="utf-8")
print(f"✅ {out.name} ({len(html):,} bytes)")
