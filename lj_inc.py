import json
import os
import sys
import datetime

INC_EVENTS_FILE = 'inc_events.jsonl'

def _load_incidents():
    incidents = []
    if os.path.exists(INC_EVENTS_FILE):
        with open(INC_EVENTS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    incidents.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"⚠️ 無法解析 inc_events.jsonl 中的行: {line.strip()} - 錯誤: {e}", file=sys.stderr)
    return incidents

def _save_incidents(incidents):
    with open(INC_EVENTS_FILE, 'w', encoding='utf-8') as f:
        for incident in incidents:
            f.write(json.dumps(incident, ensure_ascii=False) + '\n')

def list_incidents():
    incidents = _load_incidents()
    open_incidents = [inc for inc in incidents if inc.get('status') == 'open']
    
    if not open_incidents:
        print("✅ 目前沒有開啟中的事件。")
        return
    
    print("開啟中的事件列表：")
    for inc in open_incidents:
        inc_id_short = inc.get('id', 'N/A')[:8]
        first_seen = datetime.datetime.fromisoformat(inc['first_seen']).strftime('%Y-%m-%d %H:%M:%S')
        last_seen = datetime.datetime.fromisoformat(inc['last_seen']).strftime('%Y-%m-%d %H:%M:%S')
        print(f"  ID: {inc_id_short} (發生於 {inc['snapshot_date']})")
        print(f"    來源: {inc['source']}")
        print(f"    錯誤: {'；'.join(inc['errors'])}")
        print(f"    次數: {inc['count']} (首次: {first_seen}, 最後: {last_seen})")
        print(f"    狀態: {inc['status'].capitalize()}")
        print("-" * 20)

def close_incident(incident_id_prefix):
    incidents = _load_incidents()
    found = False
    for inc in incidents:
        if inc.get('id', '').startswith(incident_id_prefix) and inc.get('status') == 'open':
            inc['status'] = 'closed'
            inc['closed_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            found = True
            break
    
    if found:
        _save_incidents(incidents)
        print(f"✅ 事件 {incident_id_prefix} 已關閉。")
    else:
        print(f"❌ 未找到開啟中且 ID 匹配 '{incident_id_prefix}' 的事件。")

def main():
    if len(sys.argv) == 1 or sys.argv[1] == 'list':
        list_incidents()
    elif len(sys.argv) == 3 and sys.argv[1] == 'close':
        close_incident(sys.argv[2])
    else:
        print("用法:")
        print("  python lj_inc.py list          - 列出所有開啟中的事件")
        print("  python lj_inc.py close <ID_PREFIX> - 關閉指定 ID 前綴的事件")
        sys.exit(1)

if __name__ == "__main__":
    main()