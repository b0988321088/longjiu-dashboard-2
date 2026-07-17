# 記憶整合報告

生效：2026-07-16

## 三層記憶結構

```
第一層：Context Window（短期工作記憶）
    ↓
第二層：state.db FTS5（跨 session 檢索，663.8 MB，sessions=165，messages=82081）
    ↓
第三層：holographic memory_store.db（長期語義共用，7 條事實）
```

## 資料庫定位

| 資料庫 | 角色 | 大小/筆數 |
|-------|------|---------|
| `state.db` | 對話歷史、165 sessions、82081 messages + FTS5 | 663.8 MB |
| `memory_store.db` | 團隊事實、實體關係、HRR 向量 | 4 KB (7 facts) |
| `MEMORY.md` | 系統提示記憶（static，~2KB） | 常駐載入 |
| `snapshot.json` | 資產負債快照 | ~10 KB |
| `Company_Ledger.md` | 資產負債真值（Markdown） | ~5 KB |

## 事實庫統計

| 指標 | 值 |
|------|-----|
| 總事實 | 7 |
| 實體數 | 4 |
| fact-entity 連結 | 6 |
| 高信號 (>0.8) | 0（current） |
| 來源 sessions | cron + telegram + subagent |

## 實體 ontology

```
信用卡
資產負債
轉貸
系統/技術
```

## 共用機制

1. **讀取**：代理在任務開始時，先 `probe(entity)` 或 `search(query)` 取得共用記憶
2. **寫入**：任務完成後 `memory(action="add", content="[agent][date][task] result")`
3. **分類**：自動 entity extraction + trust_score（0.5 預設；高信號事實可手動調 0.8+）
4. **去重**：LIKE fallback + FTS5 + related 三層過濾

## auto_extract 配置

- `holographic.json`: auto_extract=true
- 寫入鐵則：`[agent][date][task] result`
- Notion 為人類可讀介面，非同步備份

## 已知限制

1. FTS5 中文無空格詞彙需 LIKE fallback 擔保 → retrieval.py 已 patch
2. trust_score 預設 0.5，需手動調整高信號事實
3. entities 需手動 ontology 定義或 auto-extract 密度觀察

## 下一步

- 累積至 20+ 高信號事實後評估去重邏輯
- 月底前維持 holographic，不增加 mem0 規費
