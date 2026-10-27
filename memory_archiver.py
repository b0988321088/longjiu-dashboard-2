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

# 2. 記憶容量（讀真實檔案算字元，不猜）
MEM_DIR = Path.home() / "AppData/Local/hermes/memories"
for fname, limit in (("MEMORY.md", 2200), ("USER.md", 1375)):
    p = MEM_DIR / fname
    if not p.exists():
        continue
    used = len(p.read_text(encoding="utf-8"))
    pct = used / limit * 100
    tag = "MEMORY" if fname == "MEMORY.md" else "USER"
    if fname == "MEMORY.md":
        result["memory_pct"] = f"{pct:.0f}%"
    result["actions"].append(f"{tag} 容量：{used:,}/{limit:,} 字元（{pct:.0f}%）")
    if pct >= 90:
        result["actions"].append(f"{tag} ≥90% → 用 memory(operations=[...]) 單批合併／刪除低頻條目（無 list 動作）")
result["actions"].append("低頻判定：已清償或已過期事件、超過1個月未更新的設定、已定案且穩定的決策")

# 3. ERROR_LOG 摘要
try:
    el = BASE / "ERROR_LOG_20260710.md"
    if el.exists():
        el_text = el.read_text(encoding="utf-8")
        incs = re.findall(r"(INC-\d+)\s*[-:：]\s*(.*?)(?=\n(?:INC-|\Z))", el_text + "\n", re.DOTALL)
        result["inc_count"] = len(incs)
        result["actions"].append(f"INC 記錄：{len(incs)} 條（詳見 error_summary_cache.txt）")
except:
    pass

# 4. 記憶體重塑提示（技能描述由 skills 索引載入，不佔 memory）
result["actions"].append("技能描述不存 memory（由 skills 索引載入）→ 不需為此刪條目；只在 >90% 時合併")

CACHE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"📦 記憶歸檔檢查 — {today}")
print(f"   技能摘要：{result['skills_count']} 個")
print(f"   建議動作：{len(result['actions'])} 項")
for a in result["actions"]:
    print(f"   • {a}")
