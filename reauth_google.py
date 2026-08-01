"""
Google Token 重新授權 — 加入 Calendar scope
執行：python reauth_google.py
會開啟瀏覽器讓使用者登入 Google 並授權 Calendar + Gmail 權限
"""
import json, sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_SECRET = Path.home() / 'AppData/Local/hermes/google_client_secret.json'
TOKEN_PATH = Path.home() / 'AppData/Local/hermes/google_token.json'

# 合併所有需要的 scopes（Gmail + Calendar）
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]


def main():
    if not CLIENT_SECRET.exists():
        print(f"❌ 找不到 client secret: {CLIENT_SECRET}")
        sys.exit(1)
    print("1️⃣  開啟瀏覽器進行 Google 授權...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0, prompt='consent')
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    print(f"✅ 授權完成！Token 已寫入 {TOKEN_PATH}")
    print(f"   Scopes: {creds.scopes}")
    print("   現在可以執行 python calendar_sync.py 同步行事曆")


if __name__ == "__main__":
    main()
