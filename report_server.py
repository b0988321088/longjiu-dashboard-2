"""Railway 動態日報伺服器 — 每次請求重新產出（含章節 1/6→6/6）"""
import os, json, sqlite3, sys
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

BASE = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", 8080))
sys.path.insert(0, str(BASE))

def generate_report():
    from datetime import date # Import date for dynamic scheduling
    import calendar_sync as cs # Import calendar_sync
    import run_daily as rd # Import run_daily, already present but good for clarity
    tv = rd.calibrate_sources()
    db = sqlite3.connect(str(BASE / "dragon_assets.db"))
    rows = db.execute("SELECT ticker, shares FROM holdings WHERE shares > 0 ORDER BY shares DESC").fetchall()
    db.close()
    total = sum(v for _, v in rows) or 1
    pcts = [round(v / total * 100, 1) for _, v in rows]
    tv["holdings_top3"] = [(r[0], pcts[i]) for i, r in enumerate(rows[:3])]
    tv["holdings_count"] = len(rows)

    # Dynamic schedule from calendar_sync
    today = date.today().isoformat()
    _events = cs.parse_events("")
    _future = [e for e in _events if e.get("start","") >= today] # Filter for future events
    _schedule = rd._generate_schedule_html(_future) # Use the function from run_daily

    # --- 動態市場情報 ---
    _mi_html_rows = []
    try:
        import sqlite3
        _db_mi = sqlite3.connect(str(BASE / "dragon_assets.db"))
        _r_mi = _db_mi.execute("SELECT summary, signals FROM market_intel WHERE date=? ORDER BY timestamp DESC LIMIT 1", (today,)).fetchone()
        _db_mi.close()
        if _r_mi and _r_mi[0]:
            _mi_html_rows.append(f"<p><strong>【情報摘要】</strong>{_r_mi[0]}</p>")
            try:
                _j_mi = json.loads(_r_mi[1]) if _r_mi[1] else {}
                if _j_mi.get("buy"):
                    _mi_html_rows.append("<p><strong>【買進訊號】</strong></p>")
                    for _s_mi in (_j_mi.get("buy", []) or [])[:2]:
                        _mi_html_rows.append(f"<p style=\"margin-left:12px\">• {_s_mi}</p>")
                if _j_mi.get("sell"):
                    _mi_html_rows.append("<p><strong>【賣出訊號】</strong></p>")
                    for _s_mi in (_j_mi.get("sell", []) or [])[:2]:
                        _mi_html_rows.append(f"<p style=\"margin-left:12px\">• {_s_mi}</p>")
            except: pass
    except Exception as _ex_mi:
        print(f"[WARN] Failed to load market_intel from DB in report_server: {_ex_mi}")

    # 從 daily_analysis.json 補充市場數據
    _da_mi = {}
    _da_path = BASE / "daily_analysis.json"
    if _da_path.exists():
        try:
            _da_mi = json.loads(_da_path.read_text(encoding='utf-8')).get("market", {})
        except Exception as _ex_da:
            print(f"[WARN] Failed to load market data from daily_analysis.json in report_server: {_ex_da}")

    _mi_map = [
        ("twii", "台股加權"), ("tsm", "台積電"), ("sox", "費半"), ("us", "美股"), ("cpi", "美國 CPI")
    ]
    for _k_mi, _l_mi in _mi_map:
        _v_mi = _da_mi.get(_k_mi)
        if _v_mi and _v_mi != "—":
            _mi_html_rows.append(f"<p><strong>【{_l_mi}】</strong>{_v_mi}</p>")
    
    if not _mi_html_rows:
        _mi_html_rows.append("<p>本日市場情報待補齊</p>")

    _market_intel_html = "\n".join(_mi_html_rows)
    # --- END 動態市場情報 ---

    html = rd.render_daily_report(tv, schedule_rows_html=_schedule, market_intel_text=_market_intel_html)
    html = rd._inject_market_intel(html, tv, {}) # This still populates __MARKET_ROWS__ etc. if needed

    # Penetration replacement
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    pen = snap.get("penetration", {})
    atwd, apct, tgt = pen.get("actual_twd", {}), pen.get("actual_pct", {}), pen.get("targets", {})
    for k, v in [("__DR_TW_V__",f"{atwd.get('台股市值型成長',0):,.0f}"),("__DR_US_V__",f"{atwd.get('美股市值型成長',0):,.0f}"),("__DR_DEF_V__",f"{atwd.get('防守型配息',0):,.0f}"),("__DR_BOND_V__",f"{atwd.get('債券',0):,.0f}"),("__DR_CASH_V__",f"{atwd.get('現金/安全網',0):,.0f}")]: html = html.replace(k, v)
    for k, v in [("__DR_TW_PCT__",f"{apct.get('台股市值型成長',0):.1f}%"),("__DR_US_PCT__",f"{apct.get('美股市值型成長',0):.1f}%"),("__DR_DEF_PCT__",f"{apct.get('防守型配息',0):.1f}%"),("__DR_BOND_PCT__",f"{apct.get('債券',0):.1f}%"),("__DR_CASH_PCT__",f"{apct.get('現金/安全網',0):.1f}%")]: html = html.replace(k, v)
    for k, v in [("__DR_TW_TGT__",f"{tgt.get('台股市值型目標',35):.0f}%"),("__DR_US_TGT__",f"{tgt.get('美股市值型目標',30):.0f}%"),("__DR_DEF_TGT__",f"{tgt.get('配息型目標',25):.0f}%"),("__DR_BOND_TGT__",f"{tgt.get('債券型目標',5):.0f}%"),("__DR_CASH_TGT__",f"{tgt.get('現金目標',5):.0f}%")]: html = html.replace(k, v)
    for k, t, g in [("__DR_TW_GAP__",apct.get('台股市值型成長',0),tgt.get('台股市值型目標',35)),("__DR_US_GAP__",apct.get('美股市值型成長',0),tgt.get('美股市值型目標',30)),("__DR_DEF_GAP__",apct.get('防守型配息',0),tgt.get('配息型目標',25)),("__DR_BOND_GAP__",apct.get('債券',0),tgt.get('債券型目標',5)),("__DR_CASH_GAP__",apct.get('現金/安全網',0),tgt.get('現金目標',5))]: html = html.replace(k, f"{t - g:+.1f}pp")

    # Emergency analysis
    ej = BASE / "data" / "emergency_llm_analysis.json"
    if ej.exists():
        d = json.loads(ej.read_text(encoding="utf-8"))
        r = d.get("full_report", d.get("analysis", ""))
        html = html.replace("{llm_emergency_analysis}", f'<div class="callout callout-warn">{r.replace(chr(10), "<br>" + chr(10))}</div>')

    # Chapter renumbering 5→6
    for i in range(1, 7):
        html = html.replace(f"{i}/5｜", f"{i}/6｜")
    html = html.replace("5/6｜投資決策框架", "6/6｜投資決策框架")

    return html

class DynamicReportHandler(SimpleHTTPRequestHandler):
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
    HTTPServer(("0.0.0.0", PORT), DynamicReportHandler).serve_forever()
