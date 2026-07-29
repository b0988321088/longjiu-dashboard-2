# INC-儀表板版本錯誤（2026-07-28）

## 症狀
GitHub Pages 主頁顯示「龍九資產管理系統」靜態頁，非正確儀表板

## 根因
- `update_all.py` 在四源不一致時會覆蓋 index.html 為最小版
- 後續 `four_source_sync.py` / `regenerate_report.py` 未重新注入正確儀表板
- Git push 沒推到更新後的 index.html

## 對策
1. `four_source_sync.py` 產出報告後強制重新注入儀表板（呼叫 `_inject_dashboard`）
2. 每次 deploy 後 curl 確認主頁正確
3. 已修正並推上 GitHub

## 狀態
✅ 已修正（2026-07-28 03:34）
