#!/usr/bin/env python3
"""從日報 HTML 截取關鍵數字，產出靜態儀表板（無注入邏輯）"""
import re
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent
TODAY = date.today().isoformat()
REPORT = BASE / f"daily_report_v2_{TODAY}.html"
OUTPUT = BASE / "index.html"

def extract(report_html):
    data = {}
    # 鎖定穿透表格區塊
    start = report_html.find("Asset Penetration")
    if start < 0:
        start = report_html.find("資產結構")
    if start < 0:
        return data
    sec = report_html[start:start+1500]
    nums = re.findall(r'<td[^>]*class="num"[^>]*>([0-9,.]+)', sec)
    if len(nums) >= 15:
        data["tw_val"] = nums[0].replace(",","").replace(" TWD","")
        data["tw_pct"] = nums[1].replace("%","")
        data["us_val"] = nums[3].replace(",","").replace(" TWD","")
        data["us_pct"] = nums[4].replace("%","")
        data["def_val"] = nums[6].replace(",","").replace(" TWD","")
        data["def_pct"] = nums[7].replace("%","")
        data["bond_val"] = nums[9].replace(",","").replace(" TWD","")
        data["bond_pct"] = nums[10].replace("%","")
        data["cash_val"] = nums[12].replace(",","").replace(" TWD","")
        data["cash_pct"] = nums[13].replace("%","")
    # 總資產
    m = re.search(r'([0-9,]+)\s*TWD\s*</div>\s*<div[^>]*>\s*總資產', report_html)
    if m: data["total_assets"] = m.group(1)
    m2 = re.search(r'([0-9,]+)\s*TWD\s*</div>\s*<div[^>]*>\s*淨資產', report_html)
    if m2: data["net_worth"] = m2.group(1)
    # 證券
    m3 = re.search(r'總市值[：:]\s*<strong>([0-9,]+)', report_html)
    if m3: data["sec_total"] = m3.group(1)
    m4 = re.search(r'前三大[：:](.*?)<', report_html)
    if m4: data["sec_top3"] = m4.group(1).strip()
    return data

def build_html(d):
    tw_v = d.get("tw_val", "—")
    us_v = d.get("us_val", "—")
    def_v = d.get("def_val", "—")
    bond_v = d.get("bond_val", "—")
    cash_v = d.get("cash_val", "—")
    tw_pct = d.get("tw_pct", "0")
    us_pct = d.get("us_pct", "0")
    def_pct = d.get("def_pct", "0")
    bond_pct = d.get("bond_pct", "0")
    cash_pct = d.get("cash_pct", "0")
    sec_total = d.get("sec_total", "—")
    sec_top3 = d.get("sec_top3", "")
    total = d.get("total_assets", "—")
    net = d.get("net_worth", "—")
    return f"""<!DOCTYPE html>
<html lang="zh-TW"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>龍九資產管理系統</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,sans-serif}}
body{{background:#f5f5f7;padding:16px;color:#1d1d1f}}
.card{{background:#fff;border-radius:14px;padding:16px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.card-title{{font-size:15px;font-weight:600;margin-bottom:10px;color:#1d1d1f}}
.row{{display:flex;justify-content:space-between;padding:6px 0;font-size:14px;border-bottom:1px solid #f0f0f0}}
.row:last-child{{border:none}}
.label{{color:#6e6e73}}
.value{{font-weight:600}}
.header{{text-align:center;padding:20px 0 12px}}
.header h1{{font-size:20px;font-weight:700}}
.header .date{{font-size:13px;color:#6e6e73;margin-top:4px}}
.bar-wrap{{background:#f0f0f0;border-radius:6px;height:8px;margin:4px 0 8px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:6px;min-width:2%}}
</style></head><body>
<div class="header"><h1>📊 龍九資產管理系統</h1>
<div class="date">{TODAY} | 資料來源：日報</div></div>
<div class="card"><div class="card-title">💰 總覽</div>
<div class="row"><span class="label">總資產</span><span class="value">{total}</span></div>
<div class="row"><span class="label">淨資產</span><span class="value">{net}</span></div></div>
<div class="card"><div class="card-title">📈 穿透分析 (35/30/25/5/5)</div>
<div class="row"><span class="label">🇹🇼 台股</span><span class="value">{tw_v}</span></div>
<div class="bar-wrap"><div class="bar-fill" style="width:{tw_pct}%;background:#2563eb"></div></div>
<div class="row"><span class="label">🇺🇸 美股</span><span class="value">{us_v}</span></div>
<div class="bar-wrap"><div class="bar-fill" style="width:{us_pct}%;background:#059669"></div></div>
<div class="row"><span class="label">🛡️ 防守</span><span class="value">{def_v}</span></div>
<div class="bar-wrap"><div class="bar-fill" style="width:{def_pct}%;background:#d97706"></div></div>
<div class="row"><span class="label">💵 債券</span><span class="value">{bond_v}</span></div>
<div class="bar-wrap"><div class="bar-fill" style="width:{bond_pct}%;background:#7c3aed"></div></div>
<div class="row"><span class="label">💰 現金</span><span class="value">{cash_v}</span></div>
<div class="bar-wrap"><div class="bar-fill" style="width:{cash_pct}%;background:#0891b2"></div></div></div>
<div class="card"><div class="card-title">📋 證券部位</div>
<div class="row"><span class="label">總市值</span><span class="value">{sec_total}</span></div>
<div style="font-size:13px;color:#6e6e73;margin-top:6px">前三大：{sec_top3}</div></div>
<div style="text-align:center;font-size:12px;color:#6e6e73;padding:12px 0">龍九控股 · 靜態儀表板 · {TODAY}</div>
</body></html>"""

def main():
    if not REPORT.exists():
        print(f"❌ 日報不存在：{REPORT}")
        return 1
    html = REPORT.read_text(encoding="utf-8", errors="ignore")
    data = extract(html)
    output = build_html(data)
    OUTPUT.write_text(output, encoding="utf-8")
    print(f"✅ 儀表板已產出 ({len(OUTPUT.read_text())} bytes)")
    return 0

if __name__ == "__main__":
    exit(main())
