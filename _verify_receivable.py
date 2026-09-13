import json
import sqlite3

s = json.load(open("snapshot.json", encoding="utf-8"))
h = json.load(open("asset_diff_history.json", encoding="utf-8"))
c = sqlite3.connect("dragon_assets.db")
db13 = c.execute("select total_liabilities from assets where date='2026-09-13'").fetchone()[0]
db12 = c.execute("select total_liabilities from assets where date='2026-09-12'").fetchone()[0]
l13 = c.execute("select total_liabilities, credit_card from liabilities where date='2026-09-13'").fetchone()
html = open("daily_report_v2_2026-09-13.html", encoding="utf-8").read()
print(f"  snapshot: 負債 {s['total_liabilities']:,} | 淨值 {s['net_worth']:,} | 應收 {s['receivables_total']:,}")
print(f"  DB 9/13 assets {db13:,.0f} | liab {l13[0]:,.0f} cc {l13[1]:,} | DB 9/12(歷史) {db12:,.0f}")
print(f"  asset_diff_history 9/13 淨值 {h['2026-09-13']['net_worth']:,.0f}")
print(f"  週拆解 net_worth_change {s['net_worth_weekly_breakdown']['net_worth_change']:,}")
print(f"  日報 30,116,569 出現 {html.count('30,116,569')} 次｜應收備忘 {html.count('288,000')} 次")
