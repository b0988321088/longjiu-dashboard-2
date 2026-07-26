"""Railway 動態日報伺服器 — 每次請求重新產出（含章節 1/6→6/6）"""
import os, json, sqlite3, sys
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

BASE = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", 8080))
sys.path.insert(0, str(BASE))

def generate_report():
    import run_daily as rd
    tv = rd.calibrate_sources()
    db = sqlite3.connect(str(BASE / "dragon_assets.db"))
    rows = db.execute("SELECT ticker, shares FROM holdings WHERE shares > 0 ORDER BY shares DESC").fetchall()
    db.close()
    total = sum(v for _, v in rows) or 1
    pcts = [round(v / total * 100, 1) for _, v in rows]
    tv["holdings_top3"] = [(r[0], pcts[i]) for i, r in enumerate(rows[:3])]
    tv["holdings_count"] = len(rows)
    
    html = rd.render_daily_report(tv)
    html = rd._inject_market_intel(html, tv, {})
    
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
