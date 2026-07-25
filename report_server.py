"""Railway 靜態檔案伺服器 — 取代 GitHub Pages"""
import os, json
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from datetime import date

BASE = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", 8080))

class ReportHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE), **kwargs)
    
    def log_message(self, format, *args):
        pass  # 不輸出 request log

    def do_GET(self):
        path = self.path.lstrip("/")
        today_str = date.today().isoformat()
        if not path:
            # 自動找最新的日報
            _candidates = sorted(BASE.glob("daily_report_v2_*.html"), reverse=True)
            path = _candidates[0].name if _candidates else f"daily_report_v2_{today_str}.html"
        if path == "emergency":
            _ec = sorted(BASE.glob("emergency_report_*.html"), reverse=True)
            path = _ec[0].name if _ec else "emergency_report_2026-07-24.html"
        if path == "diff":
            _dc = sorted(BASE.glob("asset_diff_*.html"), reverse=True)
            path = _dc[0].name if _dc else f"asset_diff_{today_str}.html"
        self.path = "/" + path
        return super().do_GET()

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), ReportHandler)
    print(f"✅ Report server running on port {PORT}")
    print(f"   http://localhost:{PORT}/")
    server.serve_forever()
