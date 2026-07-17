# Railway Dashboard 除錯 SOP

## 觸發時機
- 儀表板顯示 **0 TWD** / **0.0%** / **0.0 月**
- 顯示 **尚無資料**
- 本機修改後 Railway 仍舊頁

## 除錯檢查清單（依序執行）

### Step 1：確認 Railway 是否活著
```bash
curl -s https://<railway-url>/_stcore/health
```
- 預期 `ok`
- `bad gateway` / `timeout` → Railway 容器掛了，等 2-3 分鐘再試

### Step 2：確認 CDN 是否過期
```bash
curl -s https://<railway-url>/ | wc -c
```
- 891 bytes → 仍在吐舊版 Streamlit shell（CDN 未過期）
- >5000 bytes 且含 dashboard 內容 → CDN 已過期

### Step 3：確認 GitHub 檔案版本
```bash
python -c "import json; d=json.load(open('framework_snapshot_YYYY-MM-DD.json')); print(d.get('_cache_buster','none'))"
```
- 確認 `_cache_buster` timestamp 是否最新
- 確認 `pages` wrapper 5個 key 皆存在
- 確認 `page1.total_income` 不為 0

### Step 4：確認 dashboard.py 有 cache bust
```bash
grep -n "st.cache_data.clear" dashboard.py
```
- 必須在 `load_snapshot()` 尾端有 `st.cache_data.clear()`

### Step 5：強制 Railway rebuild
若前三項都正常但畫面仍舊：
1. 用 Contents API 上傳 dashboard.py（加一行註解或微小修改）
2. 等 60-90 秒
3. 重新整理頁面（**必須加 `?v=<timestamp>` 或 `Ctrl+Shift+R` 強制重新載入**）

### Step 6：snapshot 檔名快取 bust
若 Step 5 仍無效：
1. 複製 snapshot 為 `framework_snapshot_YYYY-MM-DD_final.json`
2. 修改 dashboard.py 的 glob pattern 包含 `*_final.json`
3. 上傳 dashboard.py + 新 snapshot 檔名
4. 等 90 秒後強制重新整理

## 常見症狀對照表

| 症狀 | 原因 | 解決方案 |
|------|------|----------|
| 0 TWD / 尚無資料 | `st.cache_data` 快取空 snapshot | Step 4 + Step 5 |
| 891 bytes 舊頁 | Railway CDN 快取 | Step 2 + 等過期 |
| 數字正確但卡在舊值 | `st.cache_data.clear()` 未生效 | Step 6 換檔名 |
| 本機 push 超時 | SSH/HTTPS 網路限制 | 改用 Contents API |
| TypeError: generator + generator | glob() 回傳 generator，不能直接用 + 合併 | 必須用 list() 轉換後再相加 |

## 預防措施
1. dashboard.py 永久保留 `st.cache_data.clear()`（不得移除）
2. snapshot 更新時同步 bump `_cache_buster`
3. 推送後告知用戶等 90 秒 + 強制重新整理（`Ctrl+Shift+R`）
4. 禁止用 `sleep` 等待快取過期作為唯一解決方案
5. `glob()` 回傳 generator 必須用 `list()` 轉換後再用 `+` 合併
6. `st.cache_data.clear()` 必須放在 `load_snapshot()` **呼叫之前**，不得放在函數內部
7. 簡體字檢查 regex 只比對真正的簡體字元，不包含繁簡同形字（轉/貸/國）
8. `summary` 在 snapshot 是 string，不是 dict；page3 renderer 不得對它呼叫 `.get()`

## 本次實際案例（E-031/E-032）
- **現象**：Railway 上顯示 `TypeError: unsupported operand(s) for +: 'generator' and 'generator'`
- **原因**：`cwd.glob("*.json") + cwd.glob("*_final.json")` 兩個 generator 不能直接相加
- **修正**：`list(cwd.glob("*.json")) + list(cwd.glob("*_final.json"))`
- **教訓**：patch 時必須考慮資料型別，不能只看語法
