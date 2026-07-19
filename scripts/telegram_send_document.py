import sys
from pathlib import Path
import urllib.error
import urllib.request

def post_document(path: str, caption: str, token: str, chat_id: str):
    send_url = f"https://api.telegram.org/bot{token}/sendDocument"
    data = Path(path).read_bytes()
    boundary = "----formdata1234567890"
    body = bytearray()
    lines = []
    lines.append("--" + boundary + "\r\n")
    lines.append('Content-Disposition: form-data; name="chat_id"\r\n\r\n')
    lines.append(str(chat_id) + "\r\n")
    lines.append("--" + boundary + "\r\n")
    lines.append('Content-Disposition: form-data; name="caption"\r\n\r\n')
    lines.append(caption + "\r\n")
    lines.append("--" + boundary + "\r\n")
    lines.append('Content-Disposition: form-data; name="document"; filename="' + Path(path).name + '"\r\n')
    lines.append("Content-Type: application/octet-stream\r\n\r\n")
    for part in lines:
        body.extend(part.encode("utf-8"))
    body.extend(data)
    body.extend(("\r\n--" + boundary + "--\r\n").encode("utf-8"))
    req = urllib.request.Request(send_url, data=bytes(body), headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"[telegram] document {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"[telegram] document {e.code}: {e.read().decode('utf-8', errors='ignore')[:240]}")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("usage: telegram_send_document.py <path> <caption> <bot_token> <chat_id>")
        raise SystemExit(1)
    post_document(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
