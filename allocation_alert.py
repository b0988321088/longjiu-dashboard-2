import json
import os
import sys

# 定義檔案路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 預設為 snapshot.json，可以通過命令行參數覆蓋
SNAPSHOT_FILE = os.path.join(BASE_DIR, 'snapshot.json')

# 檢查命令行參數，如果提供了，則使用該參數作為 SNAPSHOT_FILE
if len(sys.argv) > 1:
    SNAPSHOT_FILE = os.path.join(BASE_DIR, sys.argv[1])

# 目標資產配置 (百分比)
TARGET_ALLOCATION = {
    "台股市值型成長": 20,
    "美股市值型成長": 30,
    "防守型配息": 20,
    "債券": 15,
    "現金/安全網": 15,
}

# 偏離容忍度 (百分點)
DEVIATION_TOLERANCE_PP = 10

def send_telegram_alert(message):
    # 使用 cron 遞送機制：直接 print → cron 會自動送到 Telegram
    # 同時嘗試從 .env 讀取 TG_TOKEN 備援（若 token 有效會雙重發送）
    from pathlib import Path
    env_path = Path.home() / 'AppData/Local/hermes/.env'
    token = ''
    chat_id = ''
    for line in env_path.read_text().splitlines():
        if 'TG_TOKEN' in line and '=' in line:
            token = line.split('=',1)[1].strip().strip('\"\' ')
        if 'TG_CHAT_ID' in line and '=' in line:
            chat_id = line.split('=',1)[1].strip().strip('\"\' ')
    
    print(f'🚨 {message}')
    
    if token and chat_id:
        try:
            import requests
            r = requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
                json={'chat_id': chat_id, 'text': f'🚨 {message}'}, timeout=10)
        except:
            pass

def main():
    if not os.path.exists(SNAPSHOT_FILE):
        print(f"錯誤: 找不到 {SNAPSHOT_FILE}")
        sys.exit(1)

    try:
        with open(SNAPSHOT_FILE, 'r', encoding='utf-8') as f:
            snapshot = json.load(f)
    except json.JSONDecodeError as e:
        print(f"錯誤: 無法解析 {SNAPSHOT_FILE}: {e}")
        sys.exit(1)

    actual_penetration = snapshot.get('penetration', {}).get('actual_pct', {})

    alerts = []
    for asset_type, target_pct in TARGET_ALLOCATION.items():
        actual_pct = actual_penetration.get(asset_type, 0)
        deviation = actual_pct - target_pct

        if abs(deviation) > DEVIATION_TOLERANCE_PP:
            alerts.append(
                f"{asset_type} 偏離過大！目標: {target_pct:.2f}%，實際: {actual_pct:.2f}%，偏離: {deviation:.2f}pp。"
            )

    if alerts:
        alert_message = "資產配置警報！\n\n" + "\n".join(alerts)
        send_telegram_alert(alert_message)
        sys.exit(1) # 有警報時退出碼為 1
    else:
        print("資產配置正常，無偏離警報。")
        sys.exit(0) # 無警報時退出碼為 0

if __name__ == "__main__":
    main()