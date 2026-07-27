#!/usr/bin/env python3
"""Generate detailed penetration report."""
import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
from update_all import calc_penetration

cash = snap.get("cash_total", 3119158)
ins = snap.get("insurance_current_value", 9802872)
sec = snap.get("securities_total_market_value", 2597360)
funds = snap.get("fund_market_value", 793434)
p = calc_penetration(cash, ins, sec, funds, snap=snap)
tw_v, us_v, def_v, bond_v, cash_pv = p["台股市值型成長"], p["美股市值型成長"], p["防守型配息"], p["債券"], p["現金/安全網"]
total = tw_v + us_v + def_v + bond_v + cash_pv

# 自動校正 snapshot 穿透數據（供日報第2章使用）
targets_map = {"台股市值型": 35, "美股市值型": 30, "配息型": 25, "債券型": 5, "現金": 5}
actual_map = {"台股市值型成長": tw_v, "美股市值型成長": us_v, "防守型配息": def_v, "債券": bond_v, "現金/安全網": cash_pv}
actual_pct = {k: round(v / total * 100, 1) for k, v in actual_map.items()}
gaps = {
    "台股市值型成長": round(actual_pct["台股市值型成長"] - targets_map["台股市值型"], 1),
    "美股市值型成長": round(actual_pct["美股市值型成長"] - targets_map["美股市值型"], 1),
    "防守型配息": round(actual_pct["防守型配息"] - targets_map["配息型"], 1),
    "債券及安全現金": round(actual_pct["債券"] + actual_pct["現金/安全網"] - targets_map["債券型"] - targets_map["現金"], 1),
}
snap["penetration"] = {
    "updated_at": date.today().isoformat(),
    "source": "calc_penetration (auto-calibrated)",
    "targets": {f"{k}目標": v for k, v in targets_map.items()},
    "actual_pct": actual_pct,
    "gaps": gaps,
    "actual_twd": actual_map,
    "alert": f"台股不足{abs(round(actual_pct['台股市值型成長']-targets_map['台股市值型'],1))}pp；現金+債券超標{abs(round(actual_pct['債券']+actual_pct['現金/安全網']-targets_map['債券型']-targets_map['現金'],1))}pp",
}
(BASE / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"  穿透數據已自動校正並寫入 snapshot.json")

holdings = snap.get("securities", {}).get("holdings", [])
today = date.today().isoformat()

# Classify holdings
def cat_ticker(t):
    if t in ("0050","006208","009816"): return "tw"
    if t in ("00646","009823","009824"): return "us"
    if t in ("00713","00878","0056","00919","00918","00888"): return "def"
    if t in ("00981A","00984A"): return "active"
    if t in ("00983D",): return "bond"
    return "other"
cats_data = [
    ("tw", "台股市值型", tw_v, 35, "#3b82f6","0050/006208/009816"),
    ("us", "美股市值型", us_v, 30, "#06b6d4","00646/009823/009824"),
    ("def","防守型配息", def_v, 25, "#22c55e","00878/00713/00919等"),
    ("bond","債券", bond_v, 5, "#f59e0b","00983D"),
    ("cash","安全現金", cash_pv, 5, "#a855f7","銀行活存"),
]

lines = []
def w(s=""):
    lines.append(s)

w("<!DOCTYPE html><html lang='zh-TW'><head><meta charset='utf-8'>")
w(f"<title>龍九控股 穿透分析報告（詳細版）{today}</title>")
w("<meta name='viewport' content='width=device-width,initial-scale=1'><style>")
w("body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0f172a;color:#f1f5f9;max-width:900px;margin:20px auto;padding:0 16px}")
w("h1{font-size:24px;font-weight:900;text-align:center;background:linear-gradient(135deg,#3b82f6,#a855f7);-webkit-background-clip:text;-webkit-text-fill-color:transparent}")
w(".meta{color:#94a3b8;font-size:13px;text-align:center;margin-bottom:20px}")
w(".card{background:#1e293b;border-radius:14px;padding:16px;margin-bottom:12px;border:1px solid #334155}")
w("h2{font-size:16px;font-weight:700;margin:0 0 12px;padding-left:10px;border-left:3px solid #3b82f6}")
w("h3{font-size:14px;font-weight:600;margin:12px 0 6px;color:#60a5fa}")
w("table{width:100%;border-collapse:collapse;font-size:13px}")
w("th{background:#334155;padding:8px 6px;text-align:left;font-weight:600;color:#94a3b8}")
w("td{padding:8px 6px;border-top:1px solid #334155}")
w(".num{text-align:right;font-variant-numeric:tabular-nums}")
w(".up{color:#22c55e} .down{color:#ef4444}")
w(".bar-wrap{background:#334155;border-radius:8px;height:10px;margin:4px 0 10px;overflow:hidden}")
w(".bar-fill{height:10px;border-radius:8px}")
w(".tag{display:inline-block;padding:2px 10px;border-radius:8px;font-size:11px;font-weight:700}")
w(".over{background:#ef444420;color:#ef4444} .under{background:#f59e0b20;color:#f59e0b} .good{background:#22c55e20;color:#22c55e}")
w(".callout{background:#1e3a5f40;border-left:3px solid #3b82f6;padding:10px 14px;margin:10px 0;border-radius:6px;font-size:13px;line-height:1.7}")
w("@media(max-width:640px){table{font-size:12px}th,td{padding:6px 4px}}")
w("</style></head><body>")

w(f"<h1>📊 龍九控股 穿透分析報告（詳細版）</h1>")
w(f"<p class='meta'>{today} ｜ 穿透分母 = {total:,} TWD</p>")

# 1. Overview table
w("<div class='card'><h2>🎯 配置總覽</h2>")
w("<table><thead><tr><th>類別</th><th class='num'>金額</th><th class='num'>佔比</th><th class='num'>目標</th><th class='num'>缺口</th><th>狀態</th></tr></thead><tbody>")
for key, name, val, target, color, desc in cats_data:
    pct = val / total * 100
    gap = pct - target
    if gap > 5: st = "<span class='tag over'>⚠️ 超標</span>"
    elif gap < -5: st = "<span class='tag under'>🔴 不足</span>"
    else: st = "<span class='tag good'>✅ 正常</span>"
    gc = "down" if gap < 0 else "up"
    w(f"<tr><td>{name}</td><td class='num'>{val:,}</td><td class='num'>{pct:.1f}%</td><td class='num'>{target}%</td><td class='num {gc}'>{gap:+.1f}pp</td><td>{st}</td></tr>")
w("</tbody></table></div>")

# 2. Bar chart
w("<div class='card'><h2>📈 配置比例 vs 目標</h2>")
for key, name, val, target, color, desc in cats_data:
    pct = val / total * 100
    w(f"<div style='font-size:13px;font-weight:600;margin-top:12px'>{name}</div>")
    w(f"<div style='display:flex;justify-content:space-between;font-size:12px;color:#94a3b8'>")
    w(f"<span>實際 {pct:.1f}%</span><span>目標 {target}%</span></div>")
    w(f"<div class='bar-wrap'><div class='bar-fill' style='width:{pct:.1f}%;background:{color}'></div></div>")
    w(f"<div style='font-size:11px;color:#64748b'>{desc}</div>")
w("</div>")

# 3. Holdings detail
w("<div class='card'><h2>📋 各類別明細</h2>")
for key, name, val, target, color, desc in cats_data:
    if key == "cash":
        w(f"<h3 style='color:{color}'>{name} — {val:,} TWD</h3>")
        w("<p style='font-size:13px;color:#64748b'>銀行活存 + 定存，無個別證券</p>")
        continue
    items = [h for h in holdings if cat_ticker(h["ticker"]) == key]
    w(f"<h3 style='color:{color}'>{name} — {val:,} TWD（{val/total*100:.1f}%）</h3>")
    if items:
        w("<table><thead><tr><th>代碼</th><th>名稱</th><th class='num'>股數</th><th class='num'>現價</th>")
        w("<th class='num'>市值</th><th class='num'>佔比</th><th class='num'>損益</th></tr></thead><tbody>")
        for h in sorted(items, key=lambda x: x["value"], reverse=True):
            wp = h["value"] / val * 100 if val else 0
            pc = "up" if h["pnl"] >= 0 else "down"
            w(f"<tr><td><b>{h['ticker']}</b></td><td>{h['name']}</td>")
            w(f"<td class='num'>{h['shares']:,}</td><td class='num'>{h['price']:.2f}</td>")
            w(f"<td class='num'>{h['value']:,}</td><td class='num'>{wp:.1f}%</td>")
            w(f"<td class='num {pc}'>{h['pnl']:+,} ({h['pnl_pct']:+.1f}%)</td></tr>")
        w("</tbody></table>")
w("</div>")

# 3b. 基金明細（鉅亨基金）
_fb = snap.get("funds_breakdown", {})
if _fb:
    w("<div class='card'><h2>📦 基金穿透（鉅亨基金帳戶）</h2>")
    w("<table><thead><tr><th>基金名稱</th><th class='num'>市值</th><th>穿透分類</th></tr></thead><tbody>")
    _fund_tw = _fund_us = _fund_def = 0
    for _fn, _fv2 in sorted(_fb.items(), key=lambda x: x[1], reverse=True):
        if "路博邁5G" in _fn or "台新美日台" in _fn:
            _cat = "🌎 美股"; _fund_us += _fv2
        elif "0050連結" in _fn or "統一奔騰" in _fn:
            _cat = "🇹🇼 台股"; _fund_tw += _fv2
        elif "台中銀台灣優息" in _fn:
            _cat = "🛡️ 防守型"; _fund_def += _fv2
        else:
            _cat = "🇹🇼 台股"; _fund_tw += _fv2
        w(f"<tr><td style='max-width:180px'>{_fn}</td><td class='num'>{_fv2:,}</td><td>{_cat}</td></tr>")
    w(f"<tr style='border-top:2px solid #3b82f6;font-weight:700'><td>合計</td><td class='num'>{sum(_fb.values()):,}</td>")
    w(f"<td>🇹🇼 台股 {_fund_tw:,} + 🌎 美股 {_fund_us:,} + 🛡️ 防守型 {_fund_def:,}</td></tr>")
    w("</tbody></table></div>")

# 4. Insurance
w("<div class='card'><h2>🏦 保險穿透</h2>")
w("<table><thead><tr><th>項目</th><th class='num'>金額</th></tr></thead><tbody>")
w(f"<tr><td>安聯保單A</td><td class='num'>5,103,668</td></tr>")
w(f"<tr><td>安聯保單B</td><td class='num'>2,740,224</td></tr>")
w(f"<tr><td>第一金FL65</td><td class='num'>1,958,980</td></tr>")
w(f"<tr style='border-top:2px solid #3b82f6;font-weight:700'><td>保險合計</td><td class='num'>{ins:,}</td></tr>")
w("</tbody></table>")
w("<p style='font-size:12px;color:#64748b;margin-top:8px'>保險成分已透過 fund_ratios 穿透至美股/債券</p>")
w("</div>")

# 5. Calculation methodology
w("<div class='card'><h2>🧮 計算方式說明</h2>")
w("<div class='callout'>")
w("<b>📐 穿透公式</b><br><br>")
w("<b>Step 1：分類證券</b><br>")
w("台股 = 0050 + 006208 + 009816（國內市值型 ETF）<br>")
w("美股 = 00646 + 009823 + 009824（美股/全球型 ETF）<br>")
w("防守型 = 00878 + 00713 + 0056 + 00919 + 00918 + 00888（高股息低波動）<br>")
w("債券 = 00983D（主動式投等債）<br>")
w("現金 = Moneybook 銀行帳戶總和（排除信用卡）<br><br>")
w("<b>Step 2：穿透保險基金</b><br>")
w("安聯A+B 共10檔子基金，依各基金債券權重拆解：<br>")
w("• 安聯收益成長 → 35% 債券 / 65% 美股<br>")
w("• M&G 入息 → 55% 債券 / 45% 美股<br>")
w("• 安聯AI收益 → 50% 債券 / 50% 美股<br>")
w("• 貝萊德A10 / 聯博美國成長 → 100% 美股<br>")
w("• 第一金FL65 → 全數列防守型配息<br><br>")
w("<b>Step 3：匯總</b><br>")
w("台股 = 證券台股（保險無台股部位）<br>")
w("美股 = 證券美股 + 保險美股穿透<br>")
w("防守型 = 證券防守型 + 第一金FL65<br>")
w("債券 = 證券債券 + 保險債券穿透<br>")
w("現金 = Moneybook 銀行現金<br><br>")
w(f"<b>📌 穿透分母 = {total:,} TWD</b><br>")
w("（不計入不動產，因不參與流動性配置）")
w("</div></div>")

# 6. Strategy
w("<div class='card'><h2>🧓 再平衡策略建議</h2>")
w("<table><thead><tr><th>優先</th><th>動作</th><th>理由</th></tr></thead><tbody>")
w("<tr><td><span class='tag under'>P0</span></td><td>台股補碼 +15.9pp</td><td>逢低分批買 0050/006208</td></tr>")
w("<tr><td><span class='tag under'>P1</span></td><td>防守型補碼 +13.0pp</td><td>加 00878/00713 抗波動</td></tr>")
w("<tr><td><span class='tag over'>P2</span></td><td>現金減碼 -14.1pp</td><td>閒置資金投入成長型</td></tr>")
w("<tr><td><span class='tag over'>P3</span></td><td>債券減碼 -14.3pp</td><td>降息後轉至成長型</td></tr>")
w("</tbody></table></div>")

w(f"<p class='meta'>龍九控股 ｜ 穿透分析 v2.1<br>數據源: snapshot.json + calc_penetration</p>")
w("</body></html>")

out_path = BASE / f"penetration_report_{today}.html"
out_path.write_text("\n".join(lines), encoding="utf-8")
print(f"✅ {out_path.name} ({len(''.join(lines)):,} bytes)")
