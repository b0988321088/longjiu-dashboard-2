"""Gmail 信箱整理自動化腳本
使用方式：python gmail_cleanup.py [--dry-run]
功能：
  1. 刪除廣告郵件 (category:promotions)
  2. 歸檔過期通知 (older_than:1m)
  3. 套用標籤分類到既有郵件
  4. 建立自動過濾器（需 gmail.settings scope）

Token 路徑：~/AppData/Local/hermes/google_token.json
"""
import json, os, sys, time
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

DRY_RUN = "--dry-run" in sys.argv

# ── Gmail API ──
token_path = Path(os.path.expanduser("~/AppData/Local/hermes/google_token.json"))
creds = Credentials.from_authorized_user_file(str(token_path), [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    # 2026-08-10 修正：移除 gmail.labels/settings.basic/calendar.events —
    # 備份 token 只授權 gmail.modify+calendar，多列會 refresh invalid_scope。
    # 過濾器（需 settings.basic）為選擇性功能，未授權時安靜跳過（見下方 try/except）
])
if creds.expired and creds.refresh_token:
    creds.refresh(Request())
    # 不寫回 token 檔：避免用狹窄 scope 清單覆寫掉其他權限（2026-08-02 修正）
service = build("gmail", "v1", credentials=creds)

# ── 批次工具函數 ──
def _list_ids(query):
    ids = []
    pt = None
    while True:
        r = service.users().messages().list(userId="me", q=query, maxResults=500, pageToken=pt).execute()
        for m in r.get("messages", []):
            ids.append(m["id"])
        pt = r.get("nextPageToken")
        if not pt:
            break
    return ids

def batch_trash(query, label):
    ids = _list_ids(query)
    if not ids:
        print(f"  ℹ️ {label}: 0 封")
        return 0
    if DRY_RUN:
        print(f"  ⏩ [乾跑] {label}: {len(ids)} 封 → 刪除")
        return len(ids)
    for i in range(0, len(ids), 1000):
        service.users().messages().batchModify(userId="me", body={"ids": ids[i:i+1000], "addLabelIds": ["TRASH"]}).execute()
    print(f"  ✅ {label}: {len(ids)} 封已刪除")
    return len(ids)

def batch_archive(query, label):
    ids = _list_ids(query)
    if not ids:
        print(f"  ℹ️ {label}: 0 封")
        return 0
    if DRY_RUN:
        print(f"  ⏩ [乾跑] {label}: {len(ids)} 封 → 歸檔")
        return len(ids)
    for i in range(0, len(ids), 1000):
        service.users().messages().batchModify(userId="me", body={"ids": ids[i:i+1000], "removeLabelIds": ["INBOX"]}).execute()
    print(f"  ✅ {label}: {len(ids)} 封已歸檔")
    return len(ids)

def batch_label(query, label_name, remove_inbox=True):
    """將符合 query 的郵件套用 label_name，可選同時歸檔"""
    existing = {l["name"]: l["id"] for l in service.users().labels().list(userId="me").execute().get("labels", [])}
    label_id = existing.get(label_name)
    if not label_id:
        print(f"  ❌ 標籤 '{label_name}' 不存在，跳過")
        return 0
    ids = _list_ids(query)
    if not ids:
        print(f"  ℹ️ {label_name}: 0 封")
        return 0
    if DRY_RUN:
        print(f"  ⏩ [乾跑] {label_name}: {len(ids)} 封 → 套用標籤{' + 歸檔' if remove_inbox else ''}")
        return len(ids)
    body = {"addLabelIds": [label_id]}
    if remove_inbox:
        body["removeLabelIds"] = ["INBOX"]
    for i in range(0, len(ids), 1000):
        body["ids"] = ids[i:i+1000]
        service.users().messages().batchModify(userId="me", body=body).execute()
    print(f"  ✅ {label_name}: {len(ids)} 封已套用標籤{' + 歸檔' if remove_inbox else ''}")
    return len(ids)

# ── 執行 ──
print(f"📬 Gmail 信箱整理 {'[乾跑模式]' if DRY_RUN else ''}")
print("=" * 40)

# 1. 刪廣告
print("\n📥 任務一：清理廣告與訂閱")
batch_trash("category:promotions", "廣告郵件")

# 2. 歸檔舊通知
print("\n📥 任務二：歸檔過期通知")
batch_archive(
    "subject:(會議紀錄 OR 系統通知 OR 通報) older_than:1m",
    "舊通知/會議紀錄"
)

# 3. 建立/確保標籤存在
print("\n📥 任務三：建立標籤")
labels = ["01_待處理", "02_等待中", "03_財務與帳單", "04_專案歸檔",
          "🔐 帳號安全", "💼 保險", "📰 財經新聞", "🛠️ 開發通知", "📸 OneDrive回憶",
          "📱 社群通知", "🍎 Apple", "🎮 娛樂", "✈️ 旅遊", "📋 稅務",
          "🏦 玉山銀行", "🏦 台新銀行", "🏦 國泰世華", "🏦 永豐銀行",
          "🏦 富邦銀行", "🏦 星展銀行", "🏦 兆豐銀行", "🏦 凱基證券", "苗栗站中五段"]
label_map = {l["name"]: l["id"] for l in service.users().labels().list(userId="me").execute().get("labels", [])}
for name in labels:
    if name not in label_map:
        if not DRY_RUN:
            label = service.users().labels().create(userId="me", body={"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}).execute()
            label_map[name] = label["id"]
        print(f"  ✅ 建立標籤：{name}")
    else:
        print(f"  ℹ️ 標籤已存在：{name}")

# 4. 套用標籤到既有郵件
print("\n📥 任務四：分類既有郵件")
batch_label("subject:(交易 OR 帳單 OR 通知 OR 投資 OR 貸款)", "03_財務與帳單", remove_inbox=True)
batch_label("subject:(日報 OR 系統通報 OR 會議紀錄)", "04_專案歸檔", remove_inbox=True)
# 分類標籤
batch_label("from:(security@ OR no-reply@google OR google.com) OR from:(noreply@github.com) OR subject:(安全通知 OR 登入成功)", "🔐 帳號安全")
batch_label("from:(firstlife OR 第一金人壽 OR 安聯人壽) OR subject:(保單 OR 人壽)", "💼 保險")
batch_label("from:(鉅亨 OR 晨訊 OR 大紀元 OR 國泰期貨) OR subject:(投顧週報 OR 晨訊 OR 美股盤後)", "📰 財經新聞")
batch_label("from:(github.com OR railway OR notifications@github)", "🛠️ 開發通知")
batch_label("from:(onedrive OR onedrive@)", "📸 OneDrive回憶")
# 其他分類
batch_label("from:(instagram)", "📱 社群通知")
batch_label("from:(apple.com OR insideapple)", "🍎 Apple")
batch_label("from:(playstation)", "🎮 娛樂")
batch_label("from:(starlux OR 星宇)", "✈️ 旅遊")
batch_label("from:(etax OR 稅務)", "📋 稅務")
# 銀行分類
for bank, kw in [("🏦 玉山銀行","esun OR email.esunbank"), ("🏦 台新銀行","taishinbank"),
                  ("🏦 國泰世華","cathaybk OR cathay OR cathaysec"), ("🏦 永豐銀行","sinopac"),
                  ("🏦 富邦銀行","taipeifubon OR fubon"), ("🏦 星展銀行","dbsbank OR dbs"),
                  ("🏦 兆豐銀行","megabank OR megatrust"), ("🏦 凱基證券","kgieworld")]:
    batch_label(f"from:({kw})", bank)
batch_label("from:(中五段-苗栗站 OR hinet.net) subject:(苗栗)", "苗栗站中五段")
# 刪廣告/垃圾
batch_trash("subject:(登入成功 OR 登入通知) from:(esun OR taishin)", "登入通知(可刪)")
batch_trash("from:(uber OR yahoo購物 OR shopee OR deviantart OR 菁英交友 OR academicsingles)", "廣告垃圾")
batch_trash("from:(pressplay OR greenpeace OR 綠色和平 OR nextbank OR 將來銀行)", "廣告垃圾")
batch_trash("from:(gamma.app OR pdfguru OR thebestpdf OR 阿爾發 OR patreon OR 耶萊娜)", "廣告垃圾")

# 5. 建立過濾器（選擇性，依權限）
print("\n📥 任務五：建立自動過濾器（選擇性）")
filters_def = [
    ("subject:(交易 OR 帳單 OR 通知 OR 投資 OR 貸款)", "03_財務與帳單"),
    ("subject:(日報 OR 系統通報 OR 會議紀錄)", "04_專案歸檔"),
]
if not DRY_RUN:
    try:
        existing_filters = service.users().settings().filters().list(userId="me").execute().get("filter", [])
        for q, label_name in filters_def:
            label_id = label_map.get(label_name)
            exists = bool(label_id) and any(
                label_id in (f.get("action", {}).get("addLabelIds", []) or [])
                for f in existing_filters
            )
            if not exists and label_id:
                service.users().settings().filters().create(userId="me", body={
                    "criteria": {"query": q},
                    "action": {"addLabelIds": [label_id], "removeLabelIds": ["INBOX"]}
                }).execute()
                print(f"  ✅ 建立過濾器：{label_name}")
            else:
                print(f"  ℹ️ 過濾器已存在或標籤缺失：{label_name}")
    except Exception as e:
        if "insufficient" in str(e).lower() or "403" in str(e):
            print("  ⏭️ 過濾器管理未授權（gmail.settings.basic）→ 選擇性功能跳過，清理不受影響")
        else:
            print(f"  ⚠️ 建立過濾器失敗：{e}")

print(f"\n{'='*40}")
print(f"✨ Gmail 整理完成！")
