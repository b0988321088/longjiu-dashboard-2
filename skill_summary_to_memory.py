#!/usr/bin/env python3
"""skill_summary_to_memory.py — 掃描所有 skills，產出摘要字串供寫入 memory"""
import yaml, glob, re
from pathlib import Path

SKILLS_DIR = Path.home() / "AppData/Local/hermes/skills"
OUTPUT = Path(__file__).resolve().parent / "skill_summary_cache.txt"

entries = []
for skill_dir in sorted(SKILLS_DIR.iterdir()):
    md = skill_dir / "SKILL.md"
    if md.exists():
        text = md.read_text(encoding="utf-8")
        # 從 frontmatter 抓 description
        m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        desc = m.group(1).strip() if m else ""
        if desc:
            entries.append(f"• {skill_dir.name}：{desc}")

summary = "\n".join(entries)
OUTPUT.write_text(summary, encoding="utf-8")
print(f"✅ 技能摘要：{len(entries)} 個技能")
print(summary[:500])
