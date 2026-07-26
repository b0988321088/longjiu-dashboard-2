"""日報重新產生腳本 — 直接呼叫 render_daily_report() + _inject_market_intel()"""
import json, sqlite3, re, sys
from pathlib import Path
from datetime import date as dt

BASE = Path(__file__).resolve().parent
TODAY = dt.today().isoformat()
OUT = BASE / f"daily_report_v2_{TODAY}.html"

sys.path.insert(0, str(BASE))
from run_daily import calibrate_sources, render_daily_report, _inject_market_intel, _generate_schedule_html

# 1. 載入資料
tv = calibrate_sources()

# 2. 補 holdings_top3 + count
db = sqlite3.connect(str(BASE / "dragon_assets.db"))
rows = db.execute("SELECT ticker, shares FROM holdings WHERE shares > 0 ORDER BY shares DESC").fetchall()
db.close()
total = sum(v for _, v in rows) or 1
pcts = [round(v / total * 100, 1) for _, v in rows]
tv["holdings_top3"] = [(r[0], pcts[i]) for i, r in enumerate(rows[:3])]
tv["holdings_count"] = len(rows)

# 3. 產出 HTML + 動態排程
from calendar_sync import parse_events
today = dt.today().isoformat()
_events = parse_events("")
_future = [e for e in _events if e.get("start","") >= today] # Filter for future events
_schedule = _generate_schedule_html(_future) # Use the function from run_daily
html = render_daily_report(tv, schedule_rows_html=_schedule)

# 4. 注入市場情報 + 穿透值
html = _inject_market_intel(html, tv, {})

# 4b. 穿透 __DR_*__ 取代（main() 有做但 _inject_market_intel 沒有）
import json as _j
_snap = _j.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
_pen = _snap.get("penetration", {})
_atwd = _pen.get("actual_twd", {})
_apct = _pen.get("actual_pct", {})
_tgt = _pen.get("targets", {})
for k, v in [("__DR_TW_V__",f"{_atwd.get('台股市值型成長',0):,.0f}"),("__DR_US_V__",f"{_atwd.get('美股市值型成長',0):,.0f}"),("__DR_DEF_V__",f"{_atwd.get('防守型配息',0):,.0f}"),("__DR_BOND_V__",f"{_atwd.get('債券',0):,.0f}"),("__DR_CASH_V__",f"{_atwd.get('現金/安全網',0):,.0f}")]: html = html.replace(k, v)
for k, v in [("__DR_TW_PCT__",f"{_apct.get('台股市值型成長',0):.1f}%"),("__DR_US_PCT__",f"{_apct.get('美股市值型成長',0):.1f}%"),("__DR_DEF_PCT__",f"{_apct.get('防守型配息',0):.1f}%"),("__DR_BOND_PCT__",f"{_apct.get('債券',0):.1f}%"),("__DR_CASH_PCT__",f"{_apct.get('現金/安全網',0):.1f}%")]: html = html.replace(k, v)
for k, v in [("__DR_TW_TGT__",f"{_tgt.get('台股市值型目標',35):.0f}%"),("__DR_US_TGT__",f"{_tgt.get('美股市值型目標',30):.0f}%"),("__DR_DEF_TGT__",f"{_tgt.get('配息型目標',25):.0f}%"),("__DR_BOND_TGT__",f"{_tgt.get('債券型目標',5):.0f}%"),("__DR_CASH_TGT__",f"{_tgt.get('現金目標',5):.0f}%")]: html = html.replace(k, v)
for k, t, g in [("__DR_TW_GAP__",_apct.get('台股市值型成長',0),_tgt.get('台股市值型目標',35)),("__DR_US_GAP__",_apct.get('美股市值型成長',0),_tgt.get('美股市值型目標',30)),("__DR_DEF_GAP__",_apct.get('防守型配息',0),_tgt.get('配息型目標',25)),("__DR_BOND_GAP__",_apct.get('債券',0),_tgt.get('債券型目標',5)),("__DR_CASH_GAP__",_apct.get('現金/安全網',0),_tgt.get('現金目標',5))]:
    html = html.replace(k, f"{t - g:+.1f}pp")

# 5. 注入緊急應變分析
emergency_json = BASE / "data" / "emergency_llm_analysis.json"
if emergency_json.exists():
    d = json.loads(emergency_json.read_text(encoding="utf-8"))
    report = d.get("full_report", d.get("analysis", ""))
    callout = f'<div class="callout callout-warn">{report.replace(chr(10), "<br>" + chr(10))}</div>'
    html = html.replace("{llm_emergency_analysis}", callout)

# 6. 章節重新編號 5→6
for i in range(1, 7):
    html = html.replace(f"{i}/5｜", f"{i}/6｜")
html = html.replace("5/6｜投資決策框架", "6/6｜投資決策框架")

# 7. 寫入
OUT.write_text(html, encoding="utf-8")
h = OUT.read_text(encoding="utf-8")
print(f"✅ {OUT.name} — {len(h):,} bytes")

# 8. 驗證
drs = h.count("__DR_")
checks = {
    "__DR_殘留": drs == 0,
    "配息118,296": "118,296" in h,
    "安聯7,843,892": "7,843,892" in h,
    "證券2,479,320": "2,479,320" in h,
    "章節6/6": "6/6｜" in h,
}
ok = all(checks.values())
for k, v in checks.items():
    print(f"  {'✅' if v else '❌'} {k}")
sys.exit(0 if ok else 1)
