"""產出差異摘要 md 檔供 Gemini 審查"""
import json
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent
today = date.today().isoformat()
hist_path = BASE / "asset_diff_history.json"
diff_path = BASE / f"diff_{today}.md"

if not hist_path.exists():
    print("⚠️ asset_diff_history.json 不存在")
    diff_path.write_text("", encoding="utf-8")
    exit(0)

hist = json.loads(hist_path.read_text("utf-8"))
today_data = hist.get(today, {})

lines = []
for k, v in sorted(today_data.items()):
    if isinstance(v, (int, float)):
        lines.append(f"{k}: {v:,.0f}")
    elif isinstance(v, dict):
        for k2, v2 in v.items():
            if isinstance(v2, (int, float)):
                lines.append(f"{k2}: {v2:,.0f}")
            else:
                lines.append(f"{k2}: {v2}")
    elif isinstance(v, str):
        lines.append(f"{k}: {v[:100]}")

diff_path.write_text("\n".join(lines), encoding="utf-8")
print(f"✅ diff_{today}.md 已產出 ({len(lines)} 行)")
