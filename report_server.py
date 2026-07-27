"""Railway 動態日報伺服器 — 從 schedule_events.json 讀取，不含 Google Calendar 相依"""
import os, json, sqlite3, sys
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

BASE = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", 8080))
sys.path.insert(0, str(BASE))

def generate_report():
    from run_daily import calibrate_sources, render_daily_report, _inject_market_intel
    tv = calibrate_sources()

    # 補 holdings 資料
    db = sqlite3.connect(str(BASE / "dragon_assets.db"))
    rows = db.execute("SELECT ticker, shares FROM holdings WHERE shares > 0 ORDER BY shares DESC").fetchall()
    db.close()
    total = sum(v for _, v in rows) or 1
    pcts = [round(v / total * 100, 1) for _, v in rows]
    tv["holdings_top3"] = [(r[0], pcts[i]) for i, r in enumerate(rows[:3])]
    tv["holdings_count"] = len(rows)

    # 排程
    events = json.loads((BASE / "schedule_events.json").read_text(encoding="utf-8"))
    sched = []
    for e in events:
        d = e.get("date","")
        if d == "待處理" or ("2026-07" <= d <= "2026-08"):
            sched.append(f'<tr><td>{d}</td><td>{e.get("item","")}</td><td class="num">{e.get("amount","")}</td><td>{e.get("status","")}</td></tr>')
    _sched = "\n".join(sched[:15])
    imp = ['🔴','🔄','⚠️','⏸️','📋 重要']
    p0d = [f'<li>{e.get("date","")} — {e.get("item","")} {e.get("amount","")} {e.get("status","")}</li>' for e in events if any(s in (e.get("status","") or "") for s in imp) and (e.get("date","")=="待處理" or "2026-07" <= e.get("date","") <= "2026-08")]
    _p0 = '\n'.join([
        '<li>7/17（五）— 國泰轉貸面簽/對保（✅ 已執行，待後續流程）</li>',
        '<li>7/22（三）— 玉山信用卡繳款截止 3,176</li>',
    ] + p0d)

    # 市場情報
    da = {}
    da_p = BASE / "daily_analysis.json"
    if da_p.exists():
        da = json.loads(da_p.read_text(encoding="utf-8"))
    mk = f"<pre style='font-size:14px;line-height:1.6;white-space:pre-wrap'>{da.get('briefing','')}</pre>"

    # 緊急應變
    em = ""
    ej = BASE / "data" / "emergency_llm_analysis.json"
    if ej.exists():
        d = json.loads(ej.read_text(encoding="utf-8"))
        r = d.get("full_report", d.get("analysis", ""))
        em = f'<div class="callout callout-warn">{r.replace(chr(10), "<br>" + chr(10))}</div>'
    em += f'<br><a href=\"https://longjiu-dashboard-2-production.up.railway.app/emergency_report_{today}.html\" target=\"_blank\" style=\"display:inline-block;margin-top:10px;color:#34D399;font-weight:bold\">📄 檢視完整 LLM 緊急應變報告 →</a>'

    html = render_daily_report(tv, market_intel_text=mk, schedule_rows_html=_sched, p0_tasks_html=_p0, llm_emergency_analysis=em)
    html = _inject_market_intel(html, tv, da, em)

    # 章節
    for i in range(1, 7):
        html = html.replace(f"{i}/5｜", f"{i}/6｜")
    html = html.replace("5/6｜投資決策框架", "6/6｜投資決策框架")

    # 穿透 __DR_*__ 取代
    _snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    _pen = _snap.get("penetration", {})
    _atwd, _apct, _tgt = _pen.get("actual_twd", {}), _pen.get("actual_pct", {}), _pen.get("targets", {})
    for k, v in [("__DR_TW_V__",f"{_atwd.get('台股市值型成長',0):,.0f}"),("__DR_US_V__",f"{_atwd.get('美股市值型成長',0):,.0f}"),("__DR_DEF_V__",f"{_atwd.get('防守型配息',0):,.0f}"),("__DR_BOND_V__",f"{_atwd.get('債券',0):,.0f}"),("__DR_CASH_V__",f"{_atwd.get('現金/安全網',0):,.0f}")]: html = html.replace(k, v)
    for k, v in [("__DR_TW_PCT__",f"{_apct.get('台股市值型成長',0):.1f}%"),("__DR_US_PCT__",f"{_apct.get('美股市值型成長',0):.1f}%"),("__DR_DEF_PCT__",f"{_apct.get('防守型配息',0):.1f}%"),("__DR_BOND_PCT__",f"{_apct.get('債券',0):.1f}%"),("__DR_CASH_PCT__",f"{_apct.get('現金/安全網',0):.1f}%")]: html = html.replace(k, v)
    for k, v in [("__DR_TW_TGT__",f"{_tgt.get('台股市值型目標',35):.0f}%"),("__DR_US_TGT__",f"{_tgt.get('美股市值型目標',30):.0f}%"),("__DR_DEF_TGT__",f"{_tgt.get('配息型目標',25):.0f}%"),("__DR_BOND_TGT__",f"{_tgt.get('債券型目標',5):.0f}%"),("__DR_CASH_TGT__",f"{_tgt.get('現金目標',5):.0f}%")]: html = html.replace(k, v)
    for k, t, g in [("__DR_TW_GAP__",_apct.get('台股市值型成長',0),_tgt.get('台股市值型目標',35)),("__DR_US_GAP__",_apct.get('美股市值型成長',0),_tgt.get('美股市值型目標',30)),("__DR_DEF_GAP__",_apct.get('防守型配息',0),_tgt.get('配息型目標',25)),("__DR_BOND_GAP__",_apct.get('債券',0),_tgt.get('債券型目標',5)),("__DR_CASH_GAP__",_apct.get('現金/安全網',0),_tgt.get('現金目標',5))]:
        html = html.replace(k, f"{t - g:+.1f}pp")

    return html

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/daily_report", "/index.html"):
            html = generate_report()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        else:
            super().do_GET()

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Serving on port {PORT}")
    server.serve_forever()
