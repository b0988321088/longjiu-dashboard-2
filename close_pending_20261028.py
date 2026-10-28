#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-10-28 質押 590 萬兩張 pending 卡結案（使用者「結案並閉環」）。

依據：使用者確認扣款日 22 日、只繳息、每年續約、到期 2027-09-29；
      MB 20261027 明細 10/22 實扣 9,852 ＝ 590萬×2.65%/365×23 天（反證利率）。
規則：關鍵字必須剛好命中 1 筆，否則 abort；先寫 archive 再從正本移除；備份到 repo 外。
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
PENDING = BASE / "pending_decisions.json"
ARCHIVE = BASE / "pending_decisions_archive.json"
BAK = Path.home() / "_bak_pending_20261028"
BAK.mkdir(exist_ok=True)
for f in (PENDING, ARCHIVE):
    shutil.copy2(f, BAK / f"{f.stem}_{datetime.now():%H%M%S}{f.suffix}")

pending = json.loads(PENDING.read_text(encoding="utf-8"))
archive = json.loads(ARCHIVE.read_text(encoding="utf-8"))

TARGETS = [
    ("每月現金流出未列入月支出", "PEND-20261004-06"),
    ("還本條件未知", "PEND-20261028-質押還本"),
]

REASON = (
    "2026-10-28 結案（使用者裁示）。條款已核實：每月 22 日扣息、只繳息、每年續約、"
    "首年到期 2027-09-29；首期 2026-10-22 實扣 9,852 元＝5,900,000×2.65%/365×23 天"
    "（與 MB 明細吻合，反向證實利率 2.65%）；滿月約 12,851（30 天）～13,279（31 天）。"
    "月現金流出已納入 monthly_expense_accrual 13,029（月支出 159,210 內）。"
    "殘餘風險已另立註記：每年續約屬銀行一年一決，續約失敗即回到到期一次還本 5,900,000"
    "（月提存需 491,667，月盈餘 66,758 無法支應）→ 11/03 檢視須問續約條件／維持率／"
    "可否部分還本／提前清償違約金。本結案不代表任何交易或投資授權。"
)

closed = []
for kw, new_id in TARGETS:
    hit = [c for c in pending if kw in str(c.get("title") or "")]
    if len(hit) != 1:
        raise SystemExit(f"❌ '{kw}' 命中 {len(hit)} 筆（需剛好 1 筆）→ abort，不猜")
    card = hit[0]
    card = dict(card)
    card.setdefault("id", new_id)
    card["status"] = "已結案"
    card["closed_at"] = "2026-10-28"
    card["cleanup_reason"] = REASON
    archive.append(card)
    pending.remove(hit[0])
    closed.append(card.get("title", "")[:48])

ARCHIVE.write_text(json.dumps(archive, ensure_ascii=False, indent=2).replace("\n", "\r\n"),
                   encoding="utf-8", newline="")
PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2).replace("\n", "\r\n"),
                   encoding="utf-8", newline="")

print(f"✅ 結案 {len(closed)} 筆（pending {len(pending)} 張，archive {len(archive)} 筆）")
for t in closed:
    print("   ·", t)
print(f"   備份：{BAK}")
