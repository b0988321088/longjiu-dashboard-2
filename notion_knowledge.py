"""龍九共享知識層 — 所有代理透過此模組讀寫 Notion"""
import os, requests, json, datetime
from pathlib import Path

BASE = Path(__file__).parent
ENV_FILE = BASE / ".env"

def _token() -> str:
    t = os.environ.get("NOTION_TOKEN", "")
    if t: return t
    with open(ENV_FILE) as f:
        for line in f:
            if "NOTION_TOKEN" in line and "=" in line and "YOUR" not in line:
                return line.split("=",1)[1].strip().strip('"')
    return ""

def _db_id(key: str) -> str:
    v = os.environ.get(key, "")
    if v: return v
    with open(ENV_FILE) as f:
        for line in f:
            if key in line and "=" in line and "YOUR" not in line:
                return line.split("=",1)[1].strip().strip('"')
    return ""

def _headers() -> dict:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def write_snapshot(ta, sec, ins, funds, cash, note=""):
    """寫入每日資產快照"""
    db = _db_id("NOTION_DAILY_SNAPSHOT_DB_ID")
    if not db: return ""
    t = datetime.date.today().isoformat()
    p = {"parent":{"database_id":db},"properties":{
        "日期":{"date":{"start":t}},
        "名稱":{"title":[{"text":{"content":f"{t} 資產快照"}}]},
        "總資產":{"number":ta},"證券":{"number":sec},"保單":{"number":ins},
        "基金":{"number":funds},"現金":{"number":cash},
        "備註":{"rich_text":[{"text":{"content":note[:2000]}}]},
    }}
    try:
        r = requests.post("https://api.notion.com/v1/pages", headers=_headers(), json=p, timeout=10)
        return r.json().get("id","") if r.status_code==200 else ""
    except: return ""

def write_analysis(agent, summary, full="", tags=""):
    """寫入分析記錄（CIO/Pro/Hermes）"""
    db = _db_id("NOTION_ANALYSIS_DB_ID")
    if not db: return ""
    m = {"CIO":"CIO審查","Pro":"Pro分析","Hermes":"Hermes更新","決策":"決策記錄"}
    t = m.get(agent.split()[0] if agent else "","CIO審查")
    d = datetime.date.today().isoformat()
    p = {"parent":{"database_id":db},"properties":{
        "日期":{"date":{"start":d}},
        "名稱":{"title":[{"text":{"content":f"{d} {agent}分析"}}]},
        "類型":{"select":{"name":t}},
        "摘要":{"rich_text":[{"text":{"content":summary[:2000]}}]},
        "原始報告":{"rich_text":[{"text":{"content":full[:2000]}}]},
        "相關資產":{"rich_text":[{"text":{"content":tags[:2000]}}]},
    }}
    try:
        r = requests.post("https://api.notion.com/v1/pages", headers=_headers(), json=p, timeout=10)
        return r.json().get("id","") if r.status_code==200 else ""
    except: return ""

def query_latest(db_key="NOTION_DAILY_SNAPSHOT_DB_ID", limit=5):
    """查詢最近的記錄（所有代理共用）"""
    db = _db_id(db_key)
    if not db: return []
    p = {"sorts":[{"property":"日期","direction":"descending"}],"page_size":limit}
    try:
        r = requests.post(f"https://api.notion.com/v1/databases/{db}/query", headers=_headers(), json=p, timeout=10)
        if r.status_code!=200: return []
        rr = []
        for pg in r.json().get("results",[]):
            pr = pg.get("properties",{})
            e = {"id":pg.get("id",""),"url":pg.get("url","")}
            for k,v in pr.items():
                pt = v.get("type","")
                if pt=="title": e["title"]="".join(t.get("plain_text","") for t in v.get("title",[]))
                elif pt=="number": e[k]=v.get("number")
                elif pt=="date": e[k]=v.get("date",{}).get("start","")
                elif pt=="rich_text": e[k]="".join(t.get("plain_text","") for t in v.get("rich_text",[]))
                elif pt=="select": e[k]=v.get("select",{}).get("name","")
            rr.append(e)
        return rr
    except: return []

if __name__=="__main__":
    import sys
    if len(sys.argv)>1 and sys.argv[1]=="test":
        r = query_latest(limit=3)
        print(f"最近 {len(r)} 筆記錄:")
        for e in r:
            print(f"  {e.get('title','?'):30s} | 總資產: {e.get('總資產','?')}")
