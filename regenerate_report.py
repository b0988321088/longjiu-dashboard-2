"""日報重新產生腳本 — 從 schedule_events.json 統一讀取排程

用法：python regenerate_report.py
自動產出：daily_report_v2_YYYY-MM-DD.html + asset_diff_YYYY-MM-DD.html

依賴：
- snapshot.json（資產數據）
- schedule_events.json（排程事件，修改此檔即可更新日報排程）
- daily_analysis.json（市場情報、巴菲特/CTO分析）
- data/emergency_llm_analysis.json（緊急應變報告）

流程：
1. calibrate_sources() → 三源校驗
2. 讀取 schedule_events.json → 排程表(P0+本週)
3. 讀取 daily_analysis.json → 市場情報
4. render_daily_report() → HTML（含緊急應變）
5. _inject_market_intel() → 巴菲特/CTO/CIO
6. 穿透 __DR_*__ 取代
7. 章節 1/6→6/6
8. subprocess asset_diff_monitor.py → 差異分析
"""
import json, sqlite3, re, sys
from pathlib import Path
from datetime import date as dt

BASE = Path(__file__).resolve().parent
TODAY = dt.today().isoformat()
OUT = BASE / f"daily_report_v2_{TODAY}.html"

sys.path.insert(0, str(BASE))
from run_daily import calibrate_sources, render_daily_report, _inject_market_intel

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

# 3. 載入市場情報
daily_analysis = {}
da_path = BASE / "daily_analysis.json"
if da_path.exists():
    try:
        daily_analysis = json.loads(da_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] daily_analysis.json: {e}")
briefing = daily_analysis.get("briefing", "")
_market_html = f"<pre style='font-size:14px;line-height:1.6;white-space:pre-wrap'>{briefing}</pre>"

# 3b. 載入緊急應變分析
_emergency_html = ""
_ej = BASE / "data" / "emergency_llm_analysis.json"
if _ej.exists():
    _d = json.loads(_ej.read_text(encoding="utf-8"))
    _r = _d.get("full_report", _d.get("analysis", ""))
    _emergency_html = f'<div class="callout callout-warn">{_r.replace(chr(10), "<br>" + chr(10))}</div>'
    # 加入緊急應變連結
    _emergency_html += '<br><a href=\"https://longjiu-dashboard-2-production.up.railway.app/emergency_report_2026-07-24.html\" target=\"_blank\" style=\"display:inline-block;margin-top:10px;color:#34D399;font-weight:bold\">📄 檢視完整緊急應變報告 →</a>'

# 4. 從 schedule_events.json 統一讀取排程
_events = json.loads((BASE / "schedule_events.json").read_text(encoding="utf-8"))

# 排程表（7-8月 + 待處理）
_schedule_rows = []
for e in _events:
    d = e.get("date","")
    if d == "待處理" or (d >= "2026-07-26" and d <= "2026-08-31"):
        _schedule_rows.append(f'<tr><td>{d}</td><td>{e.get("item","")}</td><td class="num">{e.get("amount","")}</td><td>{e.get("status","")}</td></tr>')
_schedule = "\n".join(_schedule_rows[:15])

# P0 任務（只顯示重要/待處理事件）
_p0_core = [
    '<li>7/17（五）— 國泰轉貸面簽/對保（✅ 已執行，待後續流程）</li>',
    '<li>7/22（三）— 玉山信用卡繳款截止 3,176</li>',
    '<li>⚠️ <strong>7/23（四）</strong>— 安聯 AI 收益 T+4 轉換截止 ← ⏰ 已過期</li>',
]
# 篩選重要事件（只顯示 7-8 月，排除遠期每月重複）
_important = ['🔴','🔄','⚠️','⏸️','📋 重要']
_p0_dynamic = []
for e in _events:
    d = e.get("date","")
    st = e.get("status","") or ""
    if any(s in st for s in _important):
        # 只保留 7-8 月 + 待處理
        if d == "待處理" or ("2026-07" <= d <= "2026-08"):
            _p0_dynamic.append(f'<li>{d} — {e.get("item","")} {e.get("amount","")} {st}</li>')
_p0_html = '\n'.join(_p0_core + _p0_dynamic)

html = render_daily_report(tv, market_intel_text=_market_html, schedule_rows_html=_schedule, p0_tasks_html=_p0_html, llm_emergency_analysis=_emergency_html)

# 5. 注入市場情報 + 緊急應變（雙保險）
html = _inject_market_intel(html, tv, daily_analysis, _emergency_html)

# 6. 穿透 __DR_*__ 取代
_snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
_pen = _snap.get("penetration", {})
_atwd, _apct, _tgt = _pen.get("actual_twd", {}), _pen.get("actual_pct", {}), _pen.get("targets", {})
for k, v in [("__DR_TW_V__",f"{_atwd.get('台股市值型成長',0):,.0f}"),("__DR_US_V__",f"{_atwd.get('美股市值型成長',0):,.0f}"),("__DR_DEF_V__",f"{_atwd.get('防守型配息',0):,.0f}"),("__DR_BOND_V__",f"{_atwd.get('債券',0):,.0f}"),("__DR_CASH_V__",f"{_atwd.get('現金/安全網',0):,.0f}")]: html = html.replace(k, v)
for k, v in [("__DR_TW_PCT__",f"{_apct.get('台股市值型成長',0):.1f}%"),("__DR_US_PCT__",f"{_apct.get('美股市值型成長',0):.1f}%"),("__DR_DEF_PCT__",f"{_apct.get('防守型配息',0):.1f}%"),("__DR_BOND_PCT__",f"{_apct.get('債券',0):.1f}%"),("__DR_CASH_PCT__",f"{_apct.get('現金/安全網',0):.1f}%")]: html = html.replace(k, v)
for k, v in [("__DR_TW_TGT__",f"{_tgt.get('台股市值型目標',35):.0f}%"),("__DR_US_TGT__",f"{_tgt.get('美股市值型目標',30):.0f}%"),("__DR_DEF_TGT__",f"{_tgt.get('配息型目標',25):.0f}%"),("__DR_BOND_TGT__",f"{_tgt.get('債券型目標',5):.0f}%"),("__DR_CASH_TGT__",f"{_tgt.get('現金目標',5):.0f}%")]: html = html.replace(k, v)
for k, t, g in [("__DR_TW_GAP__",_apct.get('台股市值型成長',0),_tgt.get('台股市值型目標',35)),("__DR_US_GAP__",_apct.get('美股市值型成長',0),_tgt.get('美股市值型目標',30)),("__DR_DEF_GAP__",_apct.get('防守型配息',0),_tgt.get('配息型目標',25)),("__DR_BOND_GAP__",_apct.get('債券',0),_tgt.get('債券型目標',5)),("__DR_CASH_GAP__",_apct.get('現金/安全網',0),_tgt.get('現金目標',5))]:
    html = html.replace(k, f"{t - g:+.1f}pp")

# 8. 章節 5→6
for i in range(1, 7):
    html = html.replace(f"{i}/5｜", f"{i}/6｜")
html = html.replace("5/6｜投資決策框架", "6/6｜投資決策框架")

# 9. 寫入
OUT.write_text(html, encoding="utf-8")

# 9b. 自動產出差異分析
import subprocess
_diff_ok = subprocess.run(["python", str(BASE / "asset_diff_monitor.py")], capture_output=True, text=True, timeout=60)
print(_diff_ok.stdout.split(chr(10))[-2] if _diff_ok.stdout else f"差異分析 exit={_diff_ok.returncode}")

# 9c. 自動更新儀表板
from run_daily import _inject_dashboard
_index_tpl = BASE / "index_template.html"
if _index_tpl.exists():
    _index_html = _index_tpl.read_text(encoding="utf-8")
    _index_html = _inject_dashboard(_index_html, tv, daily_analysis)
    # 動態取代 placeholder
    _cash_v = tv.get("cash_total", tv.get("cash", 3614169))
    _mortgage_v = tv.get("mortgage_monthly_total", tv.get("mortgage_balance", 0))
    _salary_v = tv.get("salary", 43144)
    for ph, val in [("__DBS_BALANCE__", f"{_cash_v:,.0f}"), ("__SINOPAC_BALANCE__", f"{_cash_v:,.0f}"),
                    ("__SINOPAC_MORTGAGE__", f"{_mortgage_v:,.0f}"), ("__RESERVE_POOL__", f"{tv.get('financial_mortgage',2000000):,.0f}"),
                    ("__SALARY__", f"{_salary_v:,.0f}")]:
        _index_html = _index_html.replace(ph, val)
    (BASE / "index.html").write_text(_index_html, encoding="utf-8")
    print(f"✅ index.html ({len(_index_html):,} bytes)")

h = OUT.read_text(encoding="utf-8")
print(f"✅ {OUT.name} — {len(h):,} bytes")

# 10. 驗證
drs = h.count("__DR_")
checks = {
    "__DR_殘留": drs == 0,
    "市場情報": len(briefing) > 0,
    "排程7/27": "台新信用卡" in h,
    "排程體檢": "體檢" in h,
    "配息118,296": "118,296" in h,
    "章節6/6": "6/6｜" in h,
}
ok = all(checks.values())
for k, v in checks.items():
    print(f"  {'✅' if v else '❌'} {k}")
import sys
sys.exit(0 if ok else 1)
