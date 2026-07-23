#!/usr/bin/env python3
"""memory_archiver.py — 記憶歸檔檢查 + 技能摘要更新
由 cron 06:45 觸發，產出結果供 Hermes 在 session 中使用"""

import json, re
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
CACHE = BASE / "memory_archive_today.json"
SKILL_SUMMARY = BASE / "skill_summary_cache.txt"

today = date.today().isoformat()
result = {"date": today, "memory_pct": "?", "skills_count": 0, "actions": []}

# 1. 技能摘要更新
if Path(__file__).parent.parent.parent / "skills":
    try:
        skills_dir = Path.home() / "AppData/Local/hermes/skills"
        entries = []
        for skill_dir in sorted(skills_dir.iterdir()):
            md = skill_dir / "SKILL.md"
            if md.exists():
                text = md.read_text(encoding="utf-8")
                m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
                desc = m.group(1).strip() if m else ""
                if desc:
                    entries.append(f"• {skill_dir.name}：{desc}")
        SKILL_SUMMARY.write_text("\n".join(entries), encoding="utf-8")
        result["skills_count"] = len(entries)
        result["actions"].append(f"技能摘要：{len(entries)} 個已更新")
    except Exception as e:
        result["actions"].append(f"技能摘要失敗：{e}")

# 2. 記憶容量提醒
result["actions"].append("請執行 `memory(action='list')` 檢查容量，必要時移除低頻條目")
result["actions"].append("低頻判定：INC記錄(已存ERROR_LOG)、超過1個月未更新的設定、已穩定的決策")

CACHE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"📦 記憶歸檔檢查 — {today}")
print(f"   技能摘要：{result['skills_count']} 個")
print(f"   建議動作：{len(result['actions'])} 項")
for a in result["actions"]:
    print(f"   • {a}")
