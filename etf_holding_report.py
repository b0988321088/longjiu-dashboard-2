#!/usr/bin/env python3
"""ETF Holdings Report — 每週一自動產出持股ETF報告"""
import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
TODAY = date.today()

def load_snapshot():
    p = BASE / "snapshot.json"
    if not p.exists():
        print("❌ snapshot.json not found")
        return None
    return json.loads(p.read_text(encoding="utf-8"))

def categorize(ticker, name):
    """分類 ETF 類型"""
    t = ticker.upper()
    n = name.lower()
    if t in ("0050", "006208", "009816"):
        return "📈 台股市值型"
    if t in ("00646", "009823"):
        return "🌎 美股/全球型"
    if t == "009824":
        return "🌎 美股/全球型"
    if t in ("00878", "00919", "0056", "00918", "00888", "00713"):
        return "💰 台股高股息"
    if "主動" in n or t in ("00981A", "00984A"):
        return "🎯 主動型ETF"
    if t == "00983D":
        return "🏦 債券型"
    return "📦 其他"

def build_report(holdings):
    if not holdings:
        return "❌ 無持股資料"

    total_value = sum(h["value"] for h in holdings)
    total_cost = sum(h["shares"] * h["cost"] for h in holdings)
    total_pnl = sum(h["pnl"] for h in holdings)
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0

    # 分類彙總
    categories = {}
    for h in holdings:
        cat = categorize(h["ticker"], h["name"])
        categories.setdefault(cat, []).append(h)

    # 分類統計
    cat_stats = {}
    for cat, items in categories.items():
        val = sum(h["value"] for h in items)
        pnl = sum(h["pnl"] for h in items)
        cost = sum(h["shares"] * h["cost"] for h in items)
        cat_stats[cat] = {
            "value": val,
            "pct": val / total_value * 100 if total_value else 0,
            "pnl": pnl,
            "pnl_pct": (pnl / cost * 100) if cost else 0,
            "count": len(items),
        }

    # 排序 holdings 由市值大到小
    holdings_sorted = sorted(holdings, key=lambda h: h["value"], reverse=True)
    cat_order = sorted(cat_stats.keys(), key=lambda c: cat_stats[c]["value"], reverse=True)

    # ── Build HTML ──
    lines = []
    def w(s=""):
        lines.append(s)

    w("<!DOCTYPE html><html><head><meta charset='utf-8'>")
    w(f"<title>龍九持股ETF報告 {TODAY}</title>")
    w("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    w("<style>")
    w("body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#f5f5f7;margin:0;padding:16px;color:#1d1d1f}")
    w(".card{background:#fff;border-radius:14px;padding:16px;margin-bottom:12px;box-shadow:0 1px 4px rgba(0,0,0,.06)}")
    w("h2{font-size:17px;font-weight:700;margin:0 0 10px 0;padding-left:10px;border-left:3px solid #2563eb}")
    w("h3{font-size:14px;font-weight:600;margin:12px 0 6px;color:#2563eb}")
    w("table{width:100%;border-collapse:collapse;font-size:13px}")
    w("th{background:#f0f0f5;padding:7px 5px;text-align:left;font-weight:600;font-size:12px;color:#6e6e73}")
    w("td{padding:7px 5px;border-top:1px solid #e5e5ea;white-space:nowrap}")
    w(".num{text-align:right;font-variant-numeric:tabular-nums}")
    w(".up{color:#16a34a} .down{color:#dc2626}")
    w(".tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;font-weight:600}")
    w(".bonds{background:#dbeafe;color:#1e40af} .growth{background:#dcfce7;color:#166534}")
    w(".dividend{background:#fef9c3;color:#854d0e} .active{background:#f3e8ff;color:#6b21a8}")
    w(".global{background:#e0f2fe;color:#075985} .other{background:#f0f0f5;color:#444}")
    w(".summary-row{display:flex;justify-content:space-between;padding:6px 0}")
    w(".summary-label{color:#6e6e73;font-size:13px}")
    w(".summary-value{font-weight:700;font-size:15px}")
    w(".bar-wrap{background:#e5e5ea;border-radius:10px;height:6px;margin:4px 0 8px;overflow:hidden}")
    w(".bar-fill{height:6px;border-radius:10px;background:#2563eb}")
    w("@media(prefers-color-scheme:dark){body{background:#1c1c1e;color:#f5f5f7}.card{background:#2c2c2e;box-shadow:none}th{background:#3a3a3c;color:#a1a1a6}td{border-top-color:#3a3a3c}.tag{opacity:.9}}")
    w("</style></head><body>")

    # Header
    w(f"<h1 style='font-size:20px;font-weight:800;margin:4px 0 12px'>📊 龍九持股ETF報告</h1>")
    w(f"<p style='font-size:13px;color:#6e6e73;margin:-8px 0 12px'>{TODAY}</p>")

    # ── 總覽卡片 ──
    w("<div class='card'>")
    w("<h2>📈 總覽</h2>")
    w(f"<div class='summary-row'><span class='summary-label'>總市值</span><span class='summary-value'>{total_value:,.0f}</span></div>")
    w(f"<div class='summary-row'><span class='summary-label'>總損益</span><span class='summary-value {'up' if total_pnl>=0 else 'down'}'>{total_pnl:+,.0f} ({total_pnl_pct:+.1f}%)</span></div>")
    w(f"<div class='summary-row'><span class='summary-label'>ETF檔數</span><span class='summary-value'>{len(holdings)} 檔</span></div>")
    w("</div>")

    # ── 分類配置卡片 ──
    w("<div class='card'>")
    w("<h2>🎯 配置比例</h2>")
    for cat in cat_order:
        s = cat_stats[cat]
        pct = s["pct"]
        color = "#2563eb"
        if "高股息" in cat: color = "#eab308"
        elif "市值型" in cat: color = "#16a34a"
        elif "債券" in cat: color = "#3b82f6"
        elif "美股" in cat: color = "#06b6d4"
        elif "主動" in cat: color = "#a855f7"
        w(f"<div style='font-size:13px;font-weight:600;margin-top:8px'>{cat} <span style='float:right;color:#6e6e73'>{pct:.1f}%</span></div>")
        w(f"<div class='bar-wrap'><div class='bar-fill' style='width:{pct:.1f}%;background:{color}'></div></div>")
        w(f"<div style='font-size:12px;color:#6e6e73;margin:-2px 0 4px'>{s['value']:,.0f} 元 · {s['count']}檔 · 損益 {s['pnl']:+,.0f} ({s['pnl_pct']:+.1f}%)</div>")
    w("</div>")

    # ── 各分類明細 ──
    w("<div class='card'>")
    w("<h2>📋 持股明細</h2>")
    for cat in cat_order:
        items = categories[cat]
        s = cat_stats[cat]
        w(f"<h3>{cat} <span style='font-weight:400;color:#6e6e73;font-size:12px'>{s['value']:,.0f} 元 ({s['pct']:.1f}%)</span></h3>")
        w("<table><thead><tr>"
          "<th>名稱</th><th>代碼</th><th class='num'>股數</th><th class='num'>現價</th>"
          "<th class='num'>市值</th><th class='num'>佔比</th><th class='num'>損益</th>"
          "</tr></thead><tbody>")
        for h in sorted(items, key=lambda x: x["value"], reverse=True):
            pct = h["value"] / total_value * 100
            pnl_cls = "up" if h["pnl"] >= 0 else "down"
            w(f"<tr>"
              f"<td style='max-width:100px;overflow:hidden;text-overflow:ellipsis'>{h['name']}</td>"
              f"<td><b>{h['ticker']}</b></td>"
              f"<td class='num'>{h['shares']:,}</td>"
              f"<td class='num'>{h['price']:.2f}</td>"
              f"<td class='num'>{h['value']:,}</td>"
              f"<td class='num'>{pct:.1f}%</td>"
              f"<td class='num {pnl_cls}'>{h['pnl']:+,} ({h['pnl_pct']:+.1f}%)</td>"
              f"</tr>")
        w("</tbody></table>")
    w("</div>")

    # ── Footer ──
    w("<p style='font-size:11px;color:#8e8e93;text-align:center;margin-top:16px'>")
    w("龍九控股 · ETF持股報告 · 自動產出")
    w("</p>")
    w("</body></html>")

    html = "\n".join(lines)

    # 寫入檔案
    out_name = f"etf_report_{TODAY.isoformat()}.html"
    out_path = BASE / out_name
    out_path.write_text(html, encoding="utf-8")
    print(f"✅ {out_name}")
    print(f"📍 {total_value:,.0f} 元 | {len(holdings)} 檔 ETF | 損益 {total_pnl:+,.0f} ({total_pnl_pct:+.1f}%)")
    return str(out_path)

def main():
    snap = load_snapshot()
    if not snap:
        return
    holdings = snap.get("securities", {}).get("holdings", [])
    # 過濾掉非 ETF 個股（若有）
    stocks = [h for h in holdings if h["ticker"] not in ("",)]
    build_report(stocks)

if __name__ == "__main__":
    main()
