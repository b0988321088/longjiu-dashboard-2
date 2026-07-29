# INC-全面錯誤檢討（2026-07-28）

## 症狀
一天內發生 7 次數據錯誤：
1. FL65 被 snapshot 舊值覆蓋
2. 總資產跳 48M（不動產口徑不一致）
3. DB 保險值重複加 FL65
4. 儀表板數據未更新
5. Git push 多次失敗
6. 第六章深色背景
7. 四源不一致長達 3h

## 根因
沒有先跟使用者核對數字就同步，patch over patch 越改越亂。

## 對策已實裝
1. `preflight_check.py` — 同步前先跑檢查，列出 snapshot/DB 差異 + 合理性檢查
2. `four_source_sync.py` — 一鍵同步+驗證+推送
3. `data-quality-checklist` 技能 — 記錄完整 SOP

## 更新流程（強制）
```
① preflight_check.py → 看差異列表
② 給使用者確認
③ 使用者 OK → four_source_sync.py
```

## 狀態
✅ 已關閉（2026-07-28 03:49）
