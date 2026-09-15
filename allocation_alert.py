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

# 2026-09-15 INC-187：門檻收斂 → 一律讀 snapshot.thresholds_2026_0915 單一真值。
# 原硬編碼（台20／美30／防20／債15／現15，容忍 10pp）是 7 月口徑，
# 與使用者 9/13 裁示（台10／美30／防30／債25／現5）衝突 → 已改為動態讀取。
_TARGET_FALLBACK = {
    "台股市值型成長": 10,
    "美股市值型成長": 30,
    "防守型配息": 30,
    "債券": 25,
    "現金/安全網": 5,
}
_TOLERANCE_FALLBACK_PP = 6


def load_thresholds(snapshot_path):
    """回傳 (桶目標 dict, 導流容忍帶 pp)。讀不到 SoT 才用 fallback（fail-safe 不 fail-open 用舊值）。"""
    try:
        with open(snapshot_path, "r", encoding="utf-8") as _f:
            _t = (json.load(_f).get("thresholds_2026_0915") or {})
        _bt = _t.get("桶目標_pct") or {}
        _lad = _t.get("動作階梯_pp") or {}
        if not _bt:
            return dict(_TARGET_FALLBACK), _TOLERANCE_FALLBACK_PP
        return {
            "台股市值型成長": _bt.get("台股市值型", 10),
            "美股市值型成長": _bt.get("美股市值型", 30),
            "防守型配息": _bt.get("防守型配息", 30),
            "債券": _bt.get("債券", 25),
            "現金/安全網": _bt.get("現金", 5),
        }, float(_lad.get("導流", _TOLERANCE_FALLBACK_PP))
    except Exception:
        return dict(_TARGET_FALLBACK), _TOLERANCE_FALLBACK_PP

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
    target_pct_map, deviation_pp = load_thresholds(SNAPSHOT_FILE)   # INC-187：改讀 SoT

    alerts = []
    for asset_type, target_pct in target_pct_map.items():
        actual_pct = actual_penetration.get(asset_type, 0)
        deviation = actual_pct - target_pct

        if abs(deviation) > deviation_pp:
            alerts.append(
                f"{asset_type} 偏離過大！目標: {target_pct:.2f}%，實際: {actual_pct:.2f}%，偏離: {deviation:.2f}pp。"
            )

    # 2026-09-15 INC-187：① 防守桶在「合併口徑 ≥ 凍結承接 60%」時不報（8/21 裁示凍結承接，
    # 報它只是噪音）② US30Y ≥ 煞車線時在訊息開頭標註「只回報不動作」，避免被當成下單指示。
    _def_comb = (snapshot.get("defensive_combined_metric", {}) or {}).get("佔比", 0) or 0
    _freeze_def = float(_def_comb) >= float((((snapshot.get("thresholds_2026_0915") or {})
                                             .get("防守合併口徑_pct") or {}).get("凍結承接", 60)))
    if _freeze_def:
        alerts = [a for a in alerts if not a.startswith("防守型配息")]
    _brake_txt = ""
    try:
        _r8b = (snapshot.get("rhythm08", {}) or {}).get("indicators", {}) or {}
        _u30 = float(_r8b.get("us30y") or 0)
        _brake_ln = float((((snapshot.get("thresholds_2026_0915") or {}).get("風險煞車") or {})
                           .get("us30y_pct", 5.30)))
        if _u30 and _u30 >= _brake_ln:
            _brake_txt = f"（⏸️ 風險煞車生效：US30Y {_u30}% ≥ {_brake_ln}% → 只回報不動作）\n\n"
    except Exception:
        _brake_txt = ""

    if alerts:
        alert_message = _brake_txt + "資產配置警報！\n\n" + "\n".join(alerts)
        send_telegram_alert(alert_message)
        sys.exit(1) # 有警報時退出碼為 1
    else:
        print("資產配置正常，無偏離警報。")
        sys.exit(0) # 無警報時退出碼為 0

if __name__ == "__main__":
    main()