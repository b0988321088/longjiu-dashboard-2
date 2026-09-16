#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性：把 2026-09-15「儀表板完成清單併入修正」這筆變更登錄進 work_log.json。
規則沿用 closing_log.py：date/category/item/detail、item 前 25 字去重、寫入前備份、寫入後驗證。
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path.home() / "Desktop" / "longjiu_system"
WORKLOG = BASE / "work_log.json"

ENTRY = {
    "date": "2026-09-15",
    "category": "修正",
    "item": "儀表板『本週完成清單』併入修正（🔧）＋未閉環卡排除修正＋item HTML 轉義",
    "detail": (
        "work_log 的「修正」類（累計 26 筆）原本兩處失真：①不進本週完成清單（漏帳，今日 5 筆修正全隱形）"
        "②不被視為閉環 → 被錯誤列在「🛠️ 系統工作日誌（未閉環）」，該卡由 29 筆虛胖。"
        "修法：①build_dashboard.py 靜態層改收 完成(✅)/修正(🔧)，item 加 html.escape(quote=False)"
        "（item 內含 <p class=\"text-lead\"> 字面，不轉義會注入 DOM）＋範圍標籤分項計數；"
        "②index_template.html JS 層同口徑（CAT_ICON）與分項計數；③CLOSED_CAT 補「修正」→ 未閉環卡 29→3 筆（應辦2+決策1）。"
        "驗收：AST OK、node --check 9 段 inline script OK、靜態＝JS＝98 項（✅73｜🔧25）、未轉義 0、placeholder 0、"
        "以線上頁面抽出的真實 JS 跑 stub DOM → 渲染 98 列（🔧25）、CIO 7 組實測 APPROVE、"
        "commit b2bace0747（tree 4c3f36b0）已推雙分支、線上 index.html 與本機逐字一致。"
    ),
}

def main() -> int:
    w = json.loads(WORKLOG.read_text(encoding="utf-8"))
    key = ENTRY["item"][:25]
    for e in w:
        if str(e.get("item", ""))[:25] == key:
            print("⏭️ 已存在同筆（前 25 字相同），跳過")
            return 0
    bak = WORKLOG.with_name(f"work_log.json.bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(WORKLOG, bak)
    before = len(w)
    w.append(ENTRY)
    WORKLOG.write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")
    chk = json.loads(WORKLOG.read_text(encoding="utf-8"))
    if len(chk) != before + 1 or chk[-1].get("item") != ENTRY["item"]:
        shutil.copy2(bak, WORKLOG)
        print("❌ 驗證失敗，已還原備份", file=sys.stderr)
        return 1
    print(f"✅ 已新增 1 筆（work_log {before}→{len(chk)}；備份 {bak.name}）")
    print(" -", ENTRY["category"], "|", ENTRY["item"][:60])
    return 0

if __name__ == "__main__":
    sys.exit(main())
