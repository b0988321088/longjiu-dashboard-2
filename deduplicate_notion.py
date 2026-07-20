import os
import json
import requests
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv('C:/Users/bot/Desktop/龍九系統/.env')
token = os.getenv('NOTION_TOKEN')
headers = {
    'Authorization': f'Bearer {token}',
    'Notion-Version': '2022-06-28',
    'Content-Type': 'application/json'
}

def get_db_title_prop(db_id):
    r = requests.get(f'https://api.notion.com/v1/databases/{db_id}', headers=headers)
    data = r.json()
    props = data.get('properties', {})
    for k in ['事件名稱', '資產名稱', '項目', '基金名稱', 'Name']:
        if k in props:
            return k, props[k]['type']
    return None, None

def get_page_title(props, title_prop):
    try:
        if title_prop in props:
            return props[title_prop].get('title', [{}])[0].get('plain_text', '')
    except Exception:
        pass
    return ''

def get_page_date(props, date_prop):
    try:
        if date_prop in props:
            return props[date_prop].get('date', {}).get('start', '')
    except Exception:
        pass
    return ''

def fetch_all_pages(db_id, date_prop=None):
    pages = []
    cursor = None
    while True:
        payload = {'page_size': 100}
        if date_prop:
            payload['filter'] = {'property': date_prop, 'date': {'equals': '2026-07-20'}}
        if cursor:
            payload['start_cursor'] = cursor
        r = requests.post(f'https://api.notion.com/v1/databases/{db_id}/query', headers=headers, json=payload)
        data = r.json()
        pages.extend(data.get('results', []))
        cursor = data.get('next_cursor')
        if not data.get('has_more'):
            break
    return pages

def archive_page(page_id):
    requests.patch(f'https://api.notion.com/v1/pages/{page_id}', headers=headers, json={'archived': True})

db_map = json.load(open('C:/Users/bot/Desktop/龍九系統/notion_db_ids.json', encoding='utf-8'))
config = {
    'master_ledger': {'date_prop': '更新日期'},
    'debt_cashflow': {'date_prop': '日期'},
    'fund_station': {'date_prop': '除息日'},
    'ops_logs': {'date_prop': None},
    'asset_investment': {'date_prop': None},
}

archived = 0
for key, cfg in config.items():
    if key not in db_map:
        continue
    db_id = db_map[key]
    date_prop = cfg['date_prop']
    pages = fetch_all_pages(db_id, date_prop)
    title_prop, title_type = get_db_title_prop(db_id)
    if not title_prop:
        print(f'{key}: no title prop found')
        continue
    groups = defaultdict(list)
    for p in pages:
        title = get_page_title(p['properties'], title_prop)
        if date_prop:
            date = get_page_date(p['properties'], date_prop)
            groups[(title, date)].append(p)
        else:
            groups[title].append(p)
    for group_key, group_pages in groups.items():
        if len(group_pages) > 1:
            # keep first, archive rest
            for p in group_pages[1:]:
                archive_page(p['id'])
                archived += 1
                print(f'Archived duplicate {key}: {group_key[0]} ({p["id"]})')

print(f'Archived {archived} duplicate pages.')
