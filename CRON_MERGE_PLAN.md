# 龍九系統 Cron 合併記錄（2026-07-23）

## 合併前後
- 原有：29 個
- 已移除：7 個失效 + 6 個被取代 = 13 個
- 新增：3 個 wrapper（intel_sync_wrapper.py, morning_wrapper.py, nightly_wrapper.py）
- **現有：15 個**

## Cron 列表

### 每日
| 時間 | 名稱 | 類型 | 腳本 |
|---|---|---|---|
| 06:00 | 龍九晨間自動化 | no_agent | morning_wrapper.py |
| 07:30 | 每日信箱整理 | agent | — |
| 22:00 | 龍九夜間維護 | no_agent | nightly_wrapper.py |

### 工作日 (週一至五)
| 時間 | 名稱 | 類型 | 腳本 |
|---|---|---|---|
| 06-17 整點 | 龍九情報同步 | no_agent | intel_sync_wrapper.py |
| 13:00 | 台股緊急應變 | agent | — |
| 21:00 | 美股緊急應變 | no_agent | emergency_1330.py |
| 21:30 | 龍九晚報 | no_agent | update_all.py |

### 每週特定
| 時間 | 名稱 | 排程 |
|---|---|---|
| 週一 02:00 | 每週儀表板維護 | 週一 |
| 週一 06:00 | ETF成分股權重AI更新 | 週一 |
| 週四 09:00 | budgeting管家 | 週四 |
| 週五多時段 | 龍九高階審查群 | 週五 |
| 週日 09:00 | Gmail每週清理 | 週日 |
| 週日 10:00 | notion-weekly-trend | 週日 |

### 晚間獨立
| 時間 | 名稱 |
|---|---|
| 18:00 | CIO每日戰略審查 |
| 19:00 | 跨代理記憶同步 |
| 22:05 | Notion AI 週報 |

### Wrapper Scripts 位置
- `morning_wrapper.py` → cost_monitor → calendar_sync → update_all
- `nightly_wrapper.py` → notion_sync → nightly_maintenance
- `intel_sync_wrapper.py` → hunter_intel → notion_bridge

### 已移除（原因）
- 7/10轉貸提醒（日期已過）
- 龍九週五檢討會議（可取代）
- Notion AI每日決策摘要（腳本不存在）
- 龍九晚報（腳本不存在）
- 龍九資產變化對照（已暫停，由update_all涵蓋）
- 日報推送08:30（已暫停）
- 龍九自動週報（已暫停）
- 龍九早晨一條龍（被晨間wrapper取代）
- Calendar同步（被晨間wrapper取代）
- AI費用日報（被晨間wrapper取代）
- notion-sync（被夜間wrapper取代）
- 龍九夜間整理（被夜間wrapper取代）
- Hunter情報（被情報wrapper取代）
- Notion戰略手稿同步（被情報wrapper取代）
