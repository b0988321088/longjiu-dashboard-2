#!/usr/bin/env python3
"""00983D strategy evaluation - HTML report."""
import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
holdings = snap.get("securities", {}).get("holdings", [])
today = date.today().isoformat()
d9 = [h for h in holdings if h["ticker"] == "00983D"][0]

div_map = {"00878":0.42,"00919":0.33,"0056":1.35,"00713":1.0,"00918":1.26,"00981A":0.63,
           "00983D":0.72,"00646":1.38,"0050":0.6,"006208":4.75,"009816":0,"009823":0,"009824":0,"00888":0,"00984A":0}
cat_map = {"0050":"市值型","006208":"市值型","009816":"市值型","00878":"高股息","00713":"高股息","0056":"高股息",
           "00919":"高股息","00918":"高股息","00888":"高股息","00983D":"債券型","00646":"美股型","009823":"美股型",
           "009824":"美股型","00981A":"主動型","00984A":"主動型"}
colors = {"市值型":"#3b82f6","高股息":"#22c55e","債券型":"#f59e0b","美股型":"#06b6d4","主動型":"#a855f7"}

h_by_cat = {}
for h in holdings:
    c = cat_map.get(h["ticker"],"其他")
    h_by_cat.setdefault(c, []).append(h)

lines = []
def w(s=""):
    lines.append(s)

w("<!DOCTYPE html><html lang='zh-TW'><head><meta charset='utf-8'>")
w(f"<title>00983D 策略重新評估報告 {today}</title>")
w("<meta name='viewport' content='width=device-width,initial-scale=1'><style>")
w("body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0f172a;color:#f1f5f9;max-width:900px;margin:20px auto;padding:0 16px}")
w("h1{font-size:22px;font-weight:900;text-align:center;margin-bottom:4px}")
w(".meta{color:#94a3b8;font-size:13px;text-align:center;margin-bottom:20px}")
w(".card{background:#1e293b;border-radius:14px;padding:16px;margin-bottom:12px;border:1px solid #334155}")
w("h2{font-size:16px;font-weight:700;margin:0 0 12px;padding-left:10px;border-left:3px solid #3b82f6}")
w("h3{font-size:14px;font-weight:600;margin:10px 0 6px;color:#60a5fa}")
w("table{width:100%;border-collapse:collapse;font-size:13px}")
w("th{background:#334155;padding:8px 6px;text-align:left;font-weight:600;color:#94a3b8}")
w("td{padding:8px 6px;border-top:1px solid #334155}")
w(".num{text-align:right;font-variant-numeric:tabular-nums}")
w(".up{color:#22c55e} .down{color:#ef4444}")
w(".plan-box{background:#1e3a5f40;border-left:3px solid #3b82f6;padding:12px;margin:10px 0;border-radius:8px}")
w(".tag{display:inline-block;padding:2px 10px;border-radius:8px;font-size:11px;font-weight:700}")
w(".rec{background:#3b82f620;color:#60a5fa;border:1px solid #3b82f640;padding:12px;border-radius:10px;margin:10px 0}")
w("@media(max-width:640px){table{font-size:12px}th,td{padding:6px 4px}}")
w("</style></head><body>")

w(f"<h1>📊 00983D 策略重新評估報告</h1>")
w(f"<p class='meta'>{today} ｜ 龍九控股</p>")

# 1. Current status
w("<div class='card'><h2>📊 00983D 現況</h2>")
w("<table><thead><tr><th>指標</th><th class='num'>數值</th></tr></thead><tbody>")
w(f"<tr><td>持有股數</td><td class='num'>{d9['shares']:,} 股</td></tr>")
w(f"<tr><td>成本均價</td><td class='num'>{d9['cost']:.2f}</td></tr>")
w(f"<tr><td>現價</td><td class='num'>{d9['price']:.2f}</td></tr>")
w(f"<tr><td>市值</td><td class='num'>{d9['value']:,} TWD</td></tr>")
w(f"<tr><td>損益</td><td class='num'><span class='up'>{d9['pnl']:+,} ({d9['pnl_pct']:+.2f}%)</span></td></tr>")
w(f"<tr><td>月配息</td><td class='num'>0.06 元/股 → 年化 <b>7.14%</b></td></tr>")
w(f"<tr><td>年配息收入</td><td class='num'>{d9['shares']*0.06*12:,} TWD</td></tr>")
w("</tbody></table></div>")

# 2. Performance comparison
w("<div class='card'><h2>📈 各類別報酬率比較</h2>")
for cn in ["市值型","高股息","債券型","美股型","主動型"]:
    items = h_by_cat.get(cn, [])
    if not items:
        continue
    c = colors.get(cn, "#666")
    w(f"<h3 style='color:{c}'>{cn}</h3><table><thead><tr><th>代碼</th><th>名稱</th><th class='num'>價格報酬</th><th class='num'>配息率</th><th class='num'>總報酬</th></tr></thead><tbody>")
    for h in sorted(items, key=lambda x: x["pnl_pct"], reverse=True):
        dv = div_map.get(h["ticker"], 0)
        dy = dv / h["cost"] * 100 if dv else 0
        tr = h["pnl_pct"] + dy
        trc = "up" if tr >= 0 else "down"
        w(f"<tr><td><b>{h['ticker']}</b></td><td>{h['name']}</td>"
          f"<td class='num {'up' if h['pnl_pct']>=0 else 'down'}'>{h['pnl_pct']:+.2f}%</td>"
          f"<td class='num'>{dy:.2f}%</td>"
          f"<td class='num {trc}'><b>{tr:+.2f}%</b></td></tr>")
    w("</tbody></table>")
w("</div>")

# 3. Penetration impact
w("<div class='card'><h2>🎯 穿透影響分析</h2>")
w("<table><thead><tr><th>情境</th><th class='num'>債券佔比</th><th class='num'>台股佔比</th><th class='num'>防守佔比</th></tr></thead><tbody>")
# Current
w(f"<tr><td>目前</td><td class='num'>19.3%</td><td class='num'>15.6%</td><td class='num'>12.3%</td></tr>")
# After full 00983D build (251万)
total_pen = 16360523 + 2510000 - d9['value']
bond_new = (3149543 + 2510000 - d9['value']) / total_pen * 100
tw_new = 2556430 / total_pen * 100
def_new = 2006679 / total_pen * 100
w(f"<tr><td>251萬建倉後</td><td class='num'>{bond_new:.1f}%</td><td class='num'>{tw_new:.1f}%</td><td class='num'>{def_new:.1f}%</td></tr>")
# After pledge (borrow 198万, buy stocks)
total_pen2 = total_pen + 1980000
bond_pledge = (3149543 + 2510000 - d9['value'] - 1980000) / total_pen2 * 100
tw_pledge = (2556430 + 1500000) / total_pen2 * 100
def_pledge = (2006679 + 480000) / total_pen2 * 100
w(f"<tr><td>質押買股後</td><td class='num'>{bond_pledge:.1f}%</td><td class='num'>{tw_pledge:.1f}%</td><td class='num'>{def_pledge:.1f}%</td></tr>")
w("<tr><td colspan='4' style='font-size:12px;color:#64748b'>目標：債券5% / 台股35% / 防守25%</td></tr>")
w("</tbody></table></div>")

# 4. Options
w("<div class='card'><h2>💡 策略選項比較</h2>")

plans = [
    ("A) 原計畫執行", "#3b82f6", [
        "自有251萬買00983D → 質押借198萬 → 買006208+00713",
        "✅ 保有債券月配現金流（年化 ~7.1%）",
        "✅ 質押槓桿放大報酬",
        "✅ 轉貸後結構完整",
        "⚠️ 00983D價格成長低（+0.4%）",
        "⚠️ 債券佔比先升（34%）後降（11%）",
        "🎯 穿透改善：★★★☆☆",
    ]),
    ("B) 減量00983D，直接買股 ⭐推薦", "#22c55e", [
        "100萬買00983D + 151萬直接買006208(100萬)+00713(51萬)",
        "✅ 簡化操作，免質押、免槓桿",
        "✅ 台股直接增加151萬",
        "✅ 債券不過度超標（~12%）",
        "⚠️ 無質押槓桿，總報酬較方案A低",
        "⚠️ 月配現金流較少（~5,950/月）",
        "🎯 穿透改善：★★★★☆",
    ]),
    ("C) 00983D換成高股息ETF", "#f59e0b", [
        "251萬買00878/00919/00713，完全取代00983D",
        "✅ 價格報酬更高（+11~34%）",
        "✅ 配息率接近（4~5% vs 7.1%）",
        "✅ 防守型一次補足",
        "⚠️ 波動較00983D大",
        "⚠️ 無質押標的（00983D為質押首選）",
        "🎯 穿透改善：★★★★★",
    ]),
    ("D) 00983D降為現金替代", "#a855f7", [
        "只保留50萬00983D，200萬做現金+短天期定存",
        "✅ 最保守，流動性最高",
        "✅ 保留最多子彈等大跌加碼",
        "⚠️ 報酬率最低",
        "⚠️ 通膨侵蝕實質購買力",
        "🎯 穿透改善：★★☆☆☆",
    ]),
]

for title, color, items in plans:
    w(f"<h3 style='color:{color};margin-top:16px'>{title}</h3>")
    w("<div class='plan-box'>")
    for item in items:
        emoji = item[:2] if item[:2] in ("✅","⚠️","🎯") else "📌"
        w(f"<div style='font-size:13px;margin:4px 0'>{item}</div>")
    w("</div>")

w("</div>")

# 5. Suggestion
w("<div class='card'><h2>🧓 綜合建議</h2>")
w("<div class='rec'>")
w("<b>🔑 核心問題：你要的是「月配現金流」還是「長期資本成長」？</b><br><br>")
w("考量你的整體狀況：<br>")
w("1️⃣ 你已有 15 檔 ETF + 保險 + 基金，配置已夠分散<br>")
w("2️⃣ 目前穿透：債券 19.3% 嚴重超標，台股 15.6% 嚴重不足<br>")
w("3️⃣ 00983D 的優勢在月配現金流（年化 ~7.1%）和低波動，劣勢在價格成長幾乎為 0<br><br>")
w("<b>👉 推薦方案 B</b><br>")
w("• 100萬買00983D → 年化月配 ~5,950元（現金流）<br>")
w("• 151萬直接買006208(100萬)+00713(51萬) → 補台股+防守<br>")
w("• 穿透變：台股 ~21% / 防守 ~15% / 債券 ~12%<br>")
w("• 免質押、免槓桿，管理簡單<br><br>")
w("若有餘裕想放大報酬，走方案 A 質押槓桿也可行，但穿透先惡化後改善，需容忍短期波動。")
w("</div>")
w("</div>")

w(f"<p class='meta'>龍九控股 ｜ 策略評估 v1.0<br>數據源: snapshot.json / 2026-07-27</p>")
w("</body></html>")

out = BASE / "eval_00983D.html"
out.write_text("\n".join(lines), encoding="utf-8")
print(f"✅ {out.name} ({len(''.join(lines)):,} bytes)")
