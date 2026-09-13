"""Verify the Notion decision page exists (read-only; never prints the token)."""
import os
import requests
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENV = BASE / ".env"


def _load(key, default=""):
    v = os.environ.get(key, "")
    if v:
        return v
    try:
        for line in open(ENV, encoding="utf-8", errors="ignore"):
            if key in line and "=" in line and "YOUR" not in line:
                return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return default


TOKEN = _load("NOTION_TOKEN")
DB = _load("NOTION_ANALYSIS_DB_ID")
print(f"  token={bool(TOKEN)}(len {len(TOKEN)}) db={bool(DB)}(len {len(DB)})")
H = {"Authorization": f"Bearer {TOKEN}", "Notion-Version": "2022-06-28",
     "Content-Type": "application/json"}
try:
    r = requests.post(f"https://api.notion.com/v1/databases/{DB}/query", headers=H,
                      json={"page_size": 3, "sorts": [{"timestamp": "created_time",
                                                       "direction": "descending"}]}, timeout=20)
    print("  query status:", r.status_code)
    if r.status_code == 200:
        for p in r.json().get("results", []):
            t = "".join(x["plain_text"] for x in p["properties"].get("名稱", {}).get("title", []))
            print("   →", t[:75], "|", p["created_time"][:19])
    else:
        print("  ", r.text[:200])
except Exception as e:
    print("  ❌", e)
