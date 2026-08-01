
## INC-GCal Token 缺 Calendar Scope（2026-08-01）
- 時間：08:50 前後
- 錯誤：calendar_sync.py 執行失敗 — invalid_scope: Bad Request
- 根因：google_token.json 只有 Gmail scopes（gmail.modify + gmail.labels），缺少 calendar / calendar.events；calendar_sync 請求 Calendar 權限被拒
- 影響：行事曆雙向同步失效，日報排程無法自動對照 GCal（高雄行程為手動補入 schedule_events.json）
- 修復：python reauth_google.py（瀏覽器授權，加入 Calendar scopes）→ 完成後重跑 python calendar_sync.py 驗證
- 歷史：2026-07-27 曾重新授權 Gmail token（相同流程）
- 狀態：⏳ 待使用者執行授權（需要瀏覽器登入 Google）
