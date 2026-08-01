
## INC-Cron腳本未同步（2026-08-01）
- 時間：09:00 前後
- 錯誤：每月現金流報告 cron 警示「Script not found: hermes/scripts/cashflow_analysis.py」
- 根因：cron job 的 script 需存在於 hermes/scripts/，但腳本只放在 longjiu_system/，未同步（與 2026-07-19 memory_sync.py 問題相同）
- 影響：cashflow_analysis.py、decision_auto_close.py（08:05 error）、etf_holding_report.py（7/27 error）、build_final.py 皆缺
- 修復：全部複製到 hermes/scripts/，逐一驗證存在
- 防呆：hermes/scripts/ 需定期與 longjiu_system 同步（git push 後 auto-sync 或手動檢查）
- 狀態：✅ 已解決
