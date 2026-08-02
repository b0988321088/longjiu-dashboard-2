"""
Google Token 重新授權（自管理 PKCE，手機可操作）
執行：python reauth_google.py "<callback_url>"
流程：
1. 執行 python reauth_google.py（無參數）→ 產生授權連結 + 保存 verifier
2. 瀏覽器開啟連結，登入授權（Gmail + Calendar）
3. 授權後跳轉 localhost（無法連線正常），複製整段 URL
4. 執行 python reauth_google.py "<貼上的URL>" → 完成
"""
import base64, hashlib, json, os, re, secrets, sys, urllib.parse
from pathlib import Path

import requests

CLIENT_SECRET = Path.home() / 'AppData/Local/hermes/google_client_secret.json'
TOKEN_PATH = Path.home() / 'AppData/Local/hermes/google_token.json'
VERIFIER_PATH = Path.home() / 'AppData/Local/hermes/google_pkce_verifier.txt'
REDIRECT_URI = 'http://localhost:63393/'

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]


def gen_verifier():
    return secrets.token_urlsafe(96)


def gen_challenge(verifier):
    d = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(d).rstrip(b'=').decode()


def main():
    cs = json.load(open(CLIENT_SECRET))['installed']

    if len(sys.argv) < 2:
        # 產生授權連結
        verifier = gen_verifier()
        VERIFIER_PATH.write_text(verifier, encoding='utf-8')
        challenge = gen_challenge(verifier)
        params = {
            'response_type': 'code',
            'client_id': cs['client_id'],
            'redirect_uri': REDIRECT_URI,
            'scope': ' '.join(SCOPES),
            'state': secrets.token_urlsafe(8),
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
            'prompt': 'consent',
            'access_type': 'offline',
        }
        url = 'https://accounts.google.com/o/oauth2/auth?' + urllib.parse.urlencode(params)
        print("🔗 請開啟此連結授權（登入 Google → 允許 Gmail+行事曆權限）：")
        print(url)
        print("\n授權後瀏覽器跳轉 localhost（顯示無法連線是正常的）")
        print("複製網址列整段 URL，執行：")
        print(f'python reauth_google.py "<貼上URL>"')
        return

    # 用 callback URL 換 token
    callback = sys.argv[1]
    m = re.search(r'[?&]code=([^&]+)', callback)
    if not m:
        print("❌ 找不到授權碼，請確認貼上完整網址")
        sys.exit(1)
    code = urllib.parse.unquote(m.group(1))
    if not VERIFIER_PATH.exists():
        print("❌ 找不到 verifier，請先執行無參數版產生連結")
        sys.exit(1)
    verifier = VERIFIER_PATH.read_text(encoding='utf-8').strip()

    r = requests.post('https://oauth2.googleapis.com/token', data={
        'code': code,
        'client_id': cs['client_id'],
        'client_secret': cs['client_secret'],
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code',
        'code_verifier': verifier,
    })
    if r.status_code != 200:
        print(f"❌ 換 token 失敗: {r.status_code} {r.text[:300]}")
        sys.exit(1)

    tok = r.json()
    # 轉換為 google_auth 需要的 authorized_user 格式
    auth_user = {
        "token": tok.get("access_token", ""),
        "refresh_token": tok.get("refresh_token", ""),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": cs["client_id"],
        "client_secret": cs["client_secret"],
        "scopes": SCOPES,
    }
    TOKEN_PATH.write_text(json.dumps(auth_user), encoding="utf-8")
    VERIFIER_PATH.unlink(missing_ok=True)
    print(f"✅ 授權完成！Token 已寫入 {TOKEN_PATH}")
    print(f"   Scopes: {SCOPES}")
    print("   現在可以執行 python calendar_sync.py 同步行事曆")


if __name__ == "__main__":
    main()
