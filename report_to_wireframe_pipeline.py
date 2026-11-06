#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report_to_wireframe_pipeline.py — 【已停用 / DEPRECATED，2026-11-06】

停用理由（2026-11-06 使用者裁決「wireframe 死腳本處理」）：

1. 引用關係已查證為零：
   - 全庫 grep `report_to_wireframe` → 0 個 import／subprocess 呼叫端
   - cron／排程搜尋 → 0 命中
   - 唯一相關者是本檔自己產出的 `framework_snapshot_*.json`，無下游讀取

2. 停用前的實質缺陷（保留於 git 歷史與 .bak 備份，不在此重現）：
   - slot_map 指向不存在的資料路徑 `page1.liquidity.runway_months`
     （snapshot 現行口徑為頂層 `cash_runway_months`，page1 已標 DEPRECATED）
   - 六個以上硬編碼 fallback：43.8／71,286／16,142／55.5／431,874／6.5，
     另有一整組 2026-07-09 的 cash_flow 假設值（215,244／143,958／80,100／80,000／
     55,144／99,458／30,000／10,000／4,500／104,934／5,300,000）
   - 取不到真值時 fallback 到硬編碼 → fail-open，會輸出看似正常的假數字

3. 因此採「安全停用」而非修復：直接執行即 fail-closed 退出，不產生任何檔案。

若未來要復活：
   - 必須全部欄位改由正式資料來源派生（snapshot 頂層 `cash_runway_months` 等）
   - 取不到值時必須明確標 `unavailable` 或拋錯，**不得 fallback 到任何常數**
   - 需重新走 CIO 審查與發布授權
"""

from __future__ import annotations

import sys

DEPRECATED = True
DEPRECATED_SINCE = "2026-11-06"
DEPRECATED_REASON = "死腳本（0 引用／0 排程）且含不存在資料路徑與硬編碼 fallback"


def main() -> int:
    """fail-closed：任何呼叫都不得產出檔案或假數字。"""
    msg = (
        "⛔ report_to_wireframe_pipeline.py 已於 "
        f"{DEPRECATED_SINCE} 停用。\n"
        f"   原因：{DEPRECATED_REASON}\n"
        "   現行真值請讀 snapshot.json 頂層欄位（如 cash_runway_months），\n"
        "   儀表板請走 build_dashboard.py／build_audit_dashboard.py。"
    )
    print(msg, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
