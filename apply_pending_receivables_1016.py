#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_pending_receivables_1016.py — 卡 #15 ①③：新增「暫時性占用／待確認應收」科目

依 CIO 2026-10-09 審查（APPROVE／1 major）：威剛 3260 申購預扣 290,070（2026-10-07，
台新民權活儲存款-證券 290,742 → 672）已離開現金帳戶、尚未退款，且 snapshot 無任何科目認列
→ 總資產／淨值低估 290,070。

本腳本只做「科目建置＋總資產加回」：
  • 新增 snapshot.pending_receivables（不混用 penetration.cash_in_transit）
  • total_assets 加回該筆（現金側已排除 → 不得再動 cash）
  • 不改任何桶位／可動用現金／跑道／覆蓋率（依審查結論：不受影響）
  • ④ 10/14 雙分支結轉（未中籤／中籤）**不在本腳本**，待中籤結果另案處理（不得預先改寫真值）

備份放在 repo **外**（$LOCALAPPDATA/Temp）：repo 內備份會被全庫掃描型 detector 誤判為未授權檔案。
可重跑（idempotent）：已存在且金額相同 → 不改。
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
BAK = Path(os.environ.get("LOCALAPPDATA", str(BASE))) / "Temp" / "_bak_pending_receivables_20261016"

ITEM = {
    "項目": "威剛 3260 申購預扣（台新民權活儲存款-證券）",
    "金額": 290070,
    "日期": "2026-10-07",
    "狀態": "待確認（未中籤退款／中籤轉證券 尚未定案；定案後依 ④ 雙分支結轉）",
    "證據": "10 月 MB 逐筆對帳殘差 0（週減 214,014 = 圈存 −290,070 ＋ 保單息結清 −32,931 ＋ 房租水電 −5,548；被配息 +49,120 與薪資 +39,777 抵銷）",
}
AMT = 290070

snap = json.loads(SNAP.read_text(encoding="utf-8"))
pr = snap.get("pending_receivables")
if isinstance(pr, dict) and float(pr.get("合計") or 0) == AMT:
    print("ℹ️ 已存在且金額相同 → 不改（idempotent）")
    raise SystemExit(0)

BAK.mkdir(parents=True, exist_ok=True)
shutil.copy2(SNAP, BAK / SNAP.name)
print(f"備份：{BAK / SNAP.name}")

before_total = float(snap.get("total_assets") or 0)
snap["pending_receivables"] = {
    "note": "暫時性占用／待確認應收（INC-292／卡 #15，2026-10-16 建置）。"
            "語意＝款項已離開現金帳戶、尚未回到任何資產科目；不得與 penetration.cash_in_transit 混用。"
            "不變量：五桶＋衛星＋指定用途款＋在途＋待確認應收＝總資產。",
    "items": [ITEM],
    "合計": AMT,
    "updated_at": datetime.now().astimezone().isoformat(),
}
snap["total_assets"] = before_total + AMT

SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"✅ 已建科目：待確認應收 {AMT:,}")
print(f"   total_assets {before_total:,.0f} → {snap['total_assets']:,.0f}（+{AMT:,}）")
print("   未動：桶位／可動用現金／跑道／覆蓋率／cash_in_transit")
