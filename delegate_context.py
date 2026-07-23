#!/usr/bin/env python3
"""delegate_context.py — delegate CIO 前自動載入 Notion 脈絡
用法：python delegate_context.py "任務描述"
輸出：context 字串（含最新快照 + 決策摘要），直接 pipe 給 delegate_task"""

import json
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent
CACHE = BASE / "notion_context_cache.json"
ANALYSIS = BASE / "daily_analysis.json"
SNAPSHOT = BASE / "snapshot.json"

def build_context(task: str = ""):
    parts = [f"任務：{task}", ""]
    
    # 1. Notion 快取脈絡
    if CACHE.exists():
        try:
            c = json.loads(CACHE.read_text(encoding="utf-8"))
            src = c.get("source", "?")
            dt = c.get("date", "?")
            parts.append(f"📡 Notion 脈絡（{src} / {dt}）")
        except: pass
    
    # 2. 最新 snapshot 摘要
    if SNAPSHOT.exists():
        try:
            s = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
            parts.append(f"📊 最新資產：總資產 {s.get('total_assets',0):,} / 淨值 {s.get('net_worth',0):,} / 現金 {s.get('cash_total',0):,}")
            rb = s.get("rent_breakdown", {})
            if rb:
                parts.append(f"🏠 房租：{' + '.join(f'{v:,}' for v in rb.values())} = {sum(rb.values()):,}")
        except: pass
    
    # 3. 今日分析摘要
    if ANALYSIS.exists():
        try:
            a = json.loads(ANALYSIS.read_text(encoding="utf-8"))
            b = a.get("briefing", "")
            if b:
                parts.append(f"📰 今日情報：{b[:200]}")
        except: pass
    
    return "\n".join(parts)

if __name__ == "__main__":
    import sys
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    print(build_context(task))
