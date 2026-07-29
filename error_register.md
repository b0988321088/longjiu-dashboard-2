# 龍九系統異常記錄
自動記錄 by four_source_sync.py / safe_update.py
最後更新：2026-07-29

## INC-20260729-001：regenerate_report.py 缺少 commit 導致檔案未推送
**發現日期：** 2026-07-29
**症狀：** GitHub Pages 上的日報/差異/穿透連結 404，本機有檔但 Pages 上無
**根因：** regenerate_report.py 第199行 git push `--force` 前無 git add + git commit，等於推空
**修復：** 補上 git add 報表檔 + git commit -m 再 push
**影響檔案：** regenerate_report.py
**預防：** auto-push 段落必須先 add + commit 再推；檢查 git status 確認有變動才推

## INC-20260729-002：body CSS 選擇器遺失導致日報字型/背景失效
**發現日期：** 2026-07-29
**症狀：** 日報無自訂字型、背景色 #f5f5f7、body padding 16px 全部失效
**根因：** run_daily.py 第366行 CSS f-string 中 `body {` 被省略，屬性孤立
**修復：** 補回 `body {{ ... }}` 合併兩個分散區塊
**影響檔案：** run_daily.py
**預防：** 修改 CSS f-string 後 grep `<style>` 確認選擇器完整；CIO 審查應含 CSS 語法檢查

## INC-20260729-003：緊急應變區塊深色背景與日報淺色主題衝突
**發現日期：** 2026-07-29
**症狀：** 第六章緊急應變區塊背景深藍 #1e293b、字色 #e2e8f0，使用者看不見內容
**根因：** run_daily.py 第633行 inline style 硬編碼深色
**修復：** 改為 background:#fffbeb / color:#1d1d1f 淺色主題
**影響檔案：** run_daily.py
**預防：** 緊急應變區塊 inline style 必須用淺色；push 前 grep `#1e293b` 確認日報 HTML

## INC-20260729-004：緊急應變連結寫死 TODAY 日期導致 404
**發現日期：** 2026-07-29
**症狀：** 緊急應變報告連結指向 emergency_report_2026-07-29.html 但該檔不存在（緊急應變 cron 21:30 才跑）
**根因：** regenerate_report.py 第64-67行用 f-string 寫死 TODAY
**修復：** 改為 sorted(BASE.glob("emergency_report_2*.html")) 動態取最新檔
**影響檔案：** regenerate_report.py
**預防：** 日報中所有連結不應假設今日檔案存在，應 fallback 到最新可用版本

## INC-20260729-005：CIO 觀點永遠靜態「情緒持平」無動態分析
**發現日期：** 2026-07-29
**症狀：** 日報第六章 CIO 觀點永遠顯示「本日市場情緒持平，無重大異常」，不反映當日市場實際狀況
**根因：** run_daily.py 第354-356行 CIO 內容為硬編碼靜態文字，未從 daily_analysis.json 讀取市場資料
**修復：** CIO 改用 daily_analysis.json 的 market/signals 欄位即時生成；新增 `cio_content_html` 參數支援外部傳入動態內容
**影響檔案：** run_daily.py
**預防：** render_daily_report() 中所有分析性區塊應從 daily_analysis.json 動態產生，不可有永不改變的靜態文字

