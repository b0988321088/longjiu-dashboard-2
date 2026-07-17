# Railway 部署異常處理流程

**事件編號**: INC-2026-07-13-001
**日期**: 2026-07-13
**症狀**: GitHub 已推送新代碼，但 Railway 線上仍跑舊版（v5.0.6 映像）
**影響**: 日報與儀表板已更新為 2026-07-13 最終版，但線上用戶看到的是舊版

---

## 根本原因

| 原因 | 說明 |
|------|------|
| Railway 綁定舊映像 | Railway 綁定到 v5.0.6 映像，git push 未觸發 rebuild |
| git push 超時 | Windows 上行頻寬不足，git push origin main 卡住 |
| 自動部署中斷 | push timeout → Railway 未收到新的 github webhook |

---

## 標準處理步驟（未來遇到相同問題照做）

### Step 1：確認 GitHub 狀態
```bash
# 檢查最新 commit SHA
git log --oneline -3

# 檢查遠端檔案 SHA（等同於確認是否有新版本）
python -c "
import requests, os, base64
token=open(os.path.expanduser('~/.git-credentials')).read().strip().split(':')[-1].split('@')[0]
url='https://api.github.com/repos/b0988321088/longjiu-dashboard-2/contents/index.html'
r=requests.get(url, headers={'Authorization':f'token {token}'})
print('SHA:', r.json().get('sha','N/A'))
"
```

### Step 2：確認線上狀態
```bash
# 檢查 Railway 線上回傳的內容
curl -s https://<你的 Railway 網址> | head -20

# 檢查是否為 Streamlit 旗艦版或靜態版
# Streamlit 會回傳 "<title>Streamlit</title>"
# 靜態版會回傳 "<title>龍九資產管理系統</title>"
```

### Step 3：判斷線上版本
```bash
# 線上版本標籤
curl -s https://<你的 Railway 網址> | grep -o "v[0-9.]*" | head -1

# 或檢查版本註解
curl -s https://<your-url>/api/version 2>/dev/null || echo "No version API"
```

### Step 4：觸發 Railway Rebuild
由於 git push 超時，改用以下方法：

**方法 A：Railway CLI（推薦，永久方案）**
```bash
# 安裝 Railway CLI
npm install -g @railway/cli

# 登入
railway login

# 連結專案
railway link

# 觸發 rebuild
railway redeploy
```

**方法 B：Railway Dashboard 手動 Redeploy**
1. 前往 https://railway.app/dashboard
2. 選擇 longjiu-dashboard-2 project
3. 點選 Deployments 頁籤
4. 點選最新部署的 "..." 選單
5. 選擇 "Redeploy"

**方法 C：GitHub Contents API 強制更新（臨時）**
```python
import requests, os, base64
token=open(os.path.expanduser('~/.git-credentials')).read().strip().split(':')[-1].split('@')[0]
url='https://api.github.com/repos/b0988321088/longjiu-dashboard-2/contents/{filename}'
r=requests.get(url, headers={'Authorization':f'token {token}'})
sha=r.json().get('sha','')
with open(filename,'rb') as f:
    b64=base64.b64encode(f.read()).decode()
payload={'message':'trigger rebuild','content':b64,'sha':sha}
requests.put(url, headers={'Authorization':f'token {token}'}, json=payload)
```

### Step 5：驗證部署成功
```bash
# 等待 30-60 秒後檢查
curl -s https://<your-url> | grep "<title>" | head -1

# 檢查是否有新版本標籤
curl -s https://<your-url> | grep -o "2026-07-13" | head -1
```

### Step 6：通知用戶
部署成功後，發送新連結給用戶確認。

---

## 預防措施

1. **永久方案**：安裝 Railway CLI，以後部署用 `railway redeploy`，不走 git push
2. **監控**：建立 cron job 每小時檢查 Railway 線上版本是否與 GitHub 一致
3. **快速補救**：建立 `trigger_rebuild.py` 腳本，一鍵重推

---

## 相關文件

- 日報：`daily_report_v2_2026-07-13.md`
- 異常記錄：本文件
- Railway 專案：https://railway.app/dashboard
