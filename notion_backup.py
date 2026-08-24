"""
notion_backup.py — 龍九 Notion 備份系統
自動分類儲存截圖/簡報/影片/日報/資產數據

用法：
  python notion_backup.py snap TYPE NOTE [IMAGE_PATH]
  python notion_backup.py report
  python notion_backup.py asset

範例：
  python notion_backup.py snap 保單 "安聯A 5,062,369" screenshot.jpg
  python notion_backup.py report
"""
import sys, os, json, base64, io
from pathlib import Path
from datetime import date
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
ENV = Path.home() / 'AppData/Local/hermes/.env'

def get_token():
    for line in ENV.read_text().splitlines():
        if 'NOTION_TOKEN' in line and '=' in line:
            return line.split('=',1)[1].strip().strip('\"\' ')
    return ''

DB_ID = '3a5fc735-d433-81cd-b6e3-de735a6c4590'  # 龍九分析記錄
HEADERS = {}

def init():
    global HEADERS
    token = get_token()
    HEADERS = {'Authorization': f'Bearer {token}', 'Notion-Version': '2022-06-28', 'Content-Type': 'application/json'}

# === 類型標籤對照 ===
CATEGORIES = {
    '保單': '📸 截圖備份',
    '證券': '📸 截圖備份',
    '基金': '📸 截圖備份', 
    '銀行': '📸 截圖備份',
    'MB':   '📸 截圖備份',
    '簡報': '📑 簡報備份',
    '影片': '🎬 影片備份',
    '日報': '📰 日報備份',
    '資產': '💰 資產記錄',
    '緊急': '🚨 緊急應變',
    '情報': '🔍 情報收集',
    '信箱': '📧 信箱記錄',
    '行事曆': '📅 行事曆記錄',
    '測試': '🔧 系統測試',
    '晨報': '📋 晨間簡報',
    '週報': '📋 週報',
    '現金流': '💰 現金流分析',
    'FIRE': '🔥 FIRE進度',
    '配置': '📊 配置分析',
    '檢查': '🔍 系統檢查',
    '狀態': '📊 系統狀態',
}

def upload_image(img_path):
    """上傳圖片到 Notion（透過外部圖床或直接 base64）"""
    # Notion API 不直接支援圖片上傳，需用外部圖床
    # 暫時回傳 None，只存文字摘要
    return None

def write_snapshot(cat, title, summary, img_path=None, related=''):
    """寫入一筆備份記錄到 Notion"""
    init()
    nt = CATEGORIES.get(cat, '📸 截圖備份')
    
    props = {
        '名稱': {'title': [{'text': {'content': title[:100]}}]},
        '日期': {'date': {'start': str(date.today())}},
        '類型': {'select': {'name': nt}},
        '摘要': {'rich_text': [{'text': {'content': summary[:2000]}}]},
        '相關資產': {'rich_text': [{'text': {'content': related[:500]}}]},
    }
    
    data = {
        'parent': {'database_id': DB_ID},
        'properties': props,
    }
    
    r = requests.post('https://api.notion.com/v1/pages', headers=HEADERS, json=data)
    return r.status_code == 200

def backup_report():
    """備份今日日報5檔"""
    init()
    today = str(date.today())
    files = [
        f'daily_report_v2_{today}.html',
        f'asset_diff_{today}.html', 
        f'penetration_report_{today}.html',
        f'emergency_report_{today}.html',
        'index.html',
    ]
    
    # 讀 snapshot 取得資產摘要
    snap = {}
    try:
        snap = json.load(open(f'{BASE}/snapshot.json'))
    except: pass
    
    ins = snap.get('allianz_combined',0) + snap.get('firstjin_fl65_current_value',0)
    sec = snap.get('securities_total_market_value',0)
    cash = snap.get('real_liquid_assets',0)
    fund = snap.get('fund_market_value',0)
    total = ins + sec + cash + fund
    
    summary = (
        f'📰 日報備份 {today}\n'
        f'總流動資產: {total:,}\n'
        f'保單: {ins:,} | 證券: {sec:,} | 基金: {fund:,} | 現金: {cash:,}\n'
        f'狀態: 已推送 GitHub Pages'
    )
    
    props = {
        '名稱': {'title': [{'text': {'content': f'📰 日報備份 {today}'}}]},
        '日期': {'date': {'start': today}},
        '類型': {'select': {'name': '📰 日報備份'}},
        '摘要': {'rich_text': [{'text': {'content': summary}}]},
        '原始報告': {'rich_text': [{'text': {'content': '\n'.join(f'✅ {f}' if os.path.exists(f'{BASE}/{f}') else f'❌ {f}' for f in files)}}]},
    }
    
    data = {'parent': {'database_id': DB_ID}, 'properties': props}
    r = requests.post('https://api.notion.com/v1/pages', headers=HEADERS, json=data)
    return r.status_code == 200

def backup_asset():
    """備份今日資產數據"""
    init()
    snap = json.load(open(f'{BASE}/snapshot.json'))
    ins_ab = snap.get('allianz_combined',0)
    ins_fl65 = snap.get('firstjin_fl65_current_value',0)
    
    summary = (
        f'💰 資產快照 {date.today()}\n'
        f'安聯A+B: {ins_ab:,}\n'
        f'第一金FA81聯博: {ins_fl65:,}\n'
        f'保單合計: {ins_ab+ins_fl65:,}\n'
        f'證券: {snap.get("securities_total_market_value",0):,}\n'
        f'基金: {snap.get("fund_market_value",0):,}\n'
        f'現金: {snap.get("real_liquid_assets",0):,}\n'
        f'總流動資產: {ins_ab+ins_fl65+snap.get("securities_total_market_value",0)+snap.get("fund_market_value",0)+snap.get("real_liquid_assets",0):,}'
    )
    
    props = {
        '名稱': {'title': [{'text': {'content': f'💰 資產快照 {date.today()}'}}]},
        '日期': {'date': {'start': str(date.today())}},
        '類型': {'select': {'name': '💰 資產記錄'}},
        '摘要': {'rich_text': [{'text': {'content': summary}}]},
    }
    
    data = {'parent': {'database_id': DB_ID}, 'properties': props}
    r = requests.post('https://api.notion.com/v1/pages', headers=HEADERS, json=data)
    return r.status_code == 200

# === CLI ===
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    
    cmd = sys.argv[1]
    if cmd == 'snap':
        if len(sys.argv) < 4:
            print('用法：python notion_backup.py snap 類別 "摘要" [圖片路徑]')
            sys.exit(1)
        cat = sys.argv[2]
        note = sys.argv[3]
        img = sys.argv[4] if len(sys.argv) > 4 else None
        ok = write_snapshot(cat, f'📸 {date.today()} {cat}', note, img)
        print(f'{"✅" if ok else "❌"} Notion 備份：{cat}')
    elif cmd == 'report':
        ok = backup_report()
        print(f'{"✅" if ok else "❌"} 日報備份完成')
    elif cmd == 'asset':
        ok = backup_asset()
        print(f'{"✅" if ok else "❌"} 資產備份完成')
    else:
        print(f'未知指令：{cmd}')
