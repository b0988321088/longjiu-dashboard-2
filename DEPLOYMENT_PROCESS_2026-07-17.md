# 龍九控股 自動部署流程紀錄

**日期：** 2026-07-17  
**記錄者：** Hermes Agent  
**狀態：** ✅ 已完成並驗證

---

## 1. 目標

建立單一入口自動化：

```
python daily_deploy.py
  ├─ run_daily.py        → 產出日報 + 儀表板 + changelog
  ├─ daily_checklist.py  → 10/10 檢查
  ├─ cio_review.py       → CIO 5 關卡審查
  ├─ git push clean-main → GitHub Pages
  └─ Telegram bot        → 推送日報連結
```

---

## 2. 環境配置

### 2.1 .env（local only，已進 .gitignore）

```bash
GITHUB_REPO=b0988321088/longjiu-dashboard-2
GITHUB_BRANCH=clean-main
TG_TOKEN=8779681290:AAHDRu_kuWl2RWDXuwogcrzhkR92sBQr94s
TG_CHAT_ID=8886571290
```

**重要規則：**
- `.env` 不进 git，保護敏感資訊
- `GITHUB_BRANCH` 固定為 `clean-main`（舊 main/master 已刪除）
- `TG_TOKEN` 來自 BotFather，`TG_CHAT_ID` 來自 @userinfobot

### 2.2 Git 遠端

```
origin  git@github.com-longjiu:b0988321088/longjiu-dashboard-2.git (fetch)
origin  git@github.com-longjiu:b0988321088/longjiu-dashboard-2.git (push)
```

SSH deploy key：`~/.ssh/longjiu_ed25519`

---

## 3. 問題診斷與修復紀錄

### 3.1 daily_deploy.py branch 寫死為 main

**現象：** Contents API push 返回 401  
**原因：** `"branch": "main"` 硬編碼，但 repo 預設 branch 是 `clean-main`  
**修復：** 改為讀 `.env` 的 `GITHUB_BRANCH`，默認 `clean-main`  
**Commit：** `b06da04`

### 3.2 GitHub token 讀取失敗

**現象：** Contents API 401  
**原因：** `~/.git-credentials` 格式為 `https://***@github.com`，原程式 `line.split(":")[-1].split("@")[0]` 取不到 token  
**修復：** 改為 `line.split("@")[0].split("://")[-1]`  
**後續決定：** 完全捨棄 Contents API，改用 `git push origin clean-main`（透過 SSH deploy key）  
**Commit：** `670ba33`

### 3.3 Telegram 400 Bad Request

**現象：** `telegram: 400`  
**初步猜測：** token / chat_id 錯誤  
**診斷過程：**

```
# 1. 驗證 token + chat_id 有效性
status: 200  ✅（用 data= 傳 plain text 成功）

# 2. 比對 daily_deploy.py 的 payload
payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
```

**真正原因：** `parse_mode: "Markdown"` 導致 Telegram 解析錯誤

```
Bad Request: can't parse entities: Can't find end of the entity starting at byte offset 105
```

訊息內容中的 URL 包含特殊字元（`?v=20260717`），在 Markdown 解析模式下被誤判為實體（entity）開始但沒有正確結尾。

**修復：** 移除 `parse_mode` 參數  
**Commit：** `3ee668d`（含 scenario-driven market analysis 一起推送）

**修復後結果：**
```
telegram: 200  ✅
```

---

## 4. 最終驗證

### 4.1 命令行輸出

```
[DEPLOY] 日期：2026-07-17
[STEP] run_daily → ✅
[STEP] checklist → ✅ 10/10
[STEP] cio_review → ✅
push daily_report_v2_2026-07-17.html via git: 0 ✅
push index.html via git: 0 ✅
telegram: 200 ✅
[DONE] 全部流程完成
```

### 4.2 線上驗證

- 日報：https://b0988321088.github.io/longjiu-dashboard-2/daily_report_v2_2026-07-17.html
- 儀表板：https://b0988321088.github.io/longjiu-dashboard-2/index.html
- Telegram：✅ 已收到推送訊息

---

## 5. 關鍵教訓

### 5.1 Telegram API 使用原則

| 項目 | 正確做法 | 錯誤做法 |
|------|---------|---------|
| parse_mode | 不用（plain text） | `"Markdown"` |
| URL 處理 | 直接 embedded text | `[text](url)` Markdown 連結 |
| payload 格式 | `data=` 或 `json=` 都可 | 混用特殊字元 + Markdown |

**核心原則：** 日報推送訊息只有文字 + URL，不需要任何 Markdown 渲染，`parse_mode` 只會增加失敗風險。

### 5.2 Git push 策略

| 方法 | 優點 | 缺點 |
|------|------|------|
| Contents API | 不需要 git | 401 token 問題、格式麻煩 |
| git push via SSH | 原生、穩定 | 需要 SSH key |

**結論：** 有 SSH deploy key 的情況下，直接用 `git push` 更簡單可靠。

### 5.3 環境變數管理

- 所有敏感資訊統一在 `.env`
- `.env` 已進 `.gitignore`
- `daily_deploy.py` 只讀環境變數，不硬編碼

---

## 6. 未來排程建議

### 6.1 Windows 排程（每天 08:00）

```bash
schtasks /create /tn "龍九日報" /tr "python C:\Users\bot\Desktop\龍九系統\daily_deploy.py" /sc daily /st 08:00
```

### 6.2 失敗排查優先順序

1. `run_daily.py` 產出是否成功？
2. `daily_checklist.py` 是否 10/10？
3. `cio_review.py` 是否通過？
4. `git push` 是否成功？（SSH key 是否正常）
5. Telegram 400？（檢查 parse_mode / chat_id / bot 會話）

---

## 7. 相關 Commit

```
670ba33 fix: daily_deploy uses git push with GITHUB_BRANCH from env; removed Contents API 401 path
3ee668d feat: scenario-driven market analysis; Buffett/CTO scene-specific; CTO max-risk sentence
f57cfe7 feat: add CTO explicit max-risk sentence + Buffett allocation CTA; changelog embedded
d5d1048 feat: changelog now compares today vs yesterday report structure and snapshot numbers
b06da04 feat: daily_deploy reads branch/token from env; clean-main default
```

---

## 8. Bot 資訊

- **Bot Name:** @benbenbentw_bot
- **用途:** 接收龍九日報自動推送
- **Token:** 已儲存於 `.env`（不公開）
- **Chat ID:** 8886571290（Laing Benbenben）
- **建立日期:** 7月7日

---

## 9. 後續待辦

- [ ] 建立 Telegram 頻道/群組，考慮多人接收
- [ ] 監控 bot token 消耗（避免觸發 Telegram rate limit）
- [ ] 建立 weekly 自動部署報告
- [ ] ceo_advisor.py 重建（延後）

---

*文件版本：v1.0*  
*最後更新：2026-07-17*
