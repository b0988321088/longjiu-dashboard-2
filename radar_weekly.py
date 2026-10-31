# -*- coding: utf-8 -*-
"""radar_weekly.py — 機構流向雷達 週六 COT/Fed 版（08:30 cron 192f1784d305）

2026-10-31 根治（「每週六 rc=3」的結構性失敗）：
    原版自己走 產出 → git add 四檔 → auto_push --script。其中 index.html（公開首頁）與
    rebalance_dashboard_YYYY-MM-DD.html 都不在 publish_allowlist（10/12 裁決 A：radar 產物
    不納入自動發布；公開首頁必須真 CIO），而閘門是以「整批變更集合」判定 —— 只要同批含
    任一強制檔案，整批就升級為 must_cio → rc=3 fail-closed 拒推。結果是每週六都要人工補跑
    cio_lane 才推得出去。
    修法：本檔不再自己維護推送邏輯，直接重用 radar_push.py 的完整車道（單一實作）：
      產出四步 → 只 stage 自身產物 → commit → 閘門判定 → 需審查就自動送真 CIO（cio_lane）
      → auto_push 唯一出口 → 遠端 sha 驗證。
    差別只在摘要輸出：週六要完整 COT/Fed 摘要（summary_mode="full"），週一/三維持 watchdog
    （只有 ⚠️ ALERTS 才出聲）。

退出碼契約同 radar_push（一路傳回 cron，不再全回 0）：
    0 完成或無事可做｜1 產線失敗｜3 審查未通過拒推｜4 push 重試失敗
    5 遠端 sha 不符｜6 環境問題｜7 refspec 治理拒推｜8 審查車道例外（fail-closed）
"""
import sys
from pathlib import Path

BASE = r"C:\Users\bot\Desktop\longjiu_system"

# cron 從 ~/AppData/Local/hermes/scripts 啟動，sys.path[0] 只有該目錄；
# radar_push／publish_gate／cio_lane 只存在 repo → 先把 repo 根目錄插進搜尋路徑。
# 以 publish_gate.py 存在作為「BASE 真的是正式 repo」的標記，避免插錯目錄。
if BASE not in sys.path and (Path(BASE) / "publish_gate.py").exists():
    sys.path.insert(0, BASE)

import radar_push  # noqa: E402  ← 推送車道單一實作

if __name__ == "__main__":
    sys.exit(radar_push.main(summary_mode="full"))
