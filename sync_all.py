"""三源同步：db → snapshot → history 一次到位（通用版）
用法：python sync_all.py --insurance=9694964 --securities=2375390 --funds=795157 --cash=4483408"""
import json, sqlite3, sys
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent.resolve()
SNAP = BASE / "snapshot.json"
DB = BASE / "dragon_assets.db"
HIST = BASE / "asset_diff_history.json"
TODAY = datetime.now().strftime("%Y-%m-%d")

# 三源欄位對照表
FIELDS = {
    "insurance": {
        "db": "insurance",
        "snap": ["insurance_current_value"],
        "hist": ["insurance_current", "insurance_total"],
        "label": "保單",
        "detail_key": "insurance_detail",
        "detail_subkey": "安聯保單A+B 現值",
    },
    "securities": {
        "db": "securities",
        "snap": ["securities_total_market_value"],
        "hist": ["securities_market"],
        "label": "證券",
    },
    "funds": {
        "db": "funds",
        "snap": ["fund_market_value"],
        "hist": ["fund_market"],
        "label": "基金",
    },
    "cash": {
        "db": "cash_total",
        "snap": ["real_liquid_assets"],
        "hist": ["cash"],
        "label": "現金",
    },
    "total_assets": {
        "db": "total_assets",
        "snap": ["total_assets"],
        "hist": ["total_assets"],
        "label": "總資產",
    },
    "bonds": {
        "db": "bonds",
        "snap": [],
        "hist": [],
        "label": "債券",
    },
}

def sync_updates(updates: dict):
    """updates = {'insurance': 9694964, 'securities': 2375390, ...}"""
    snap = json.loads(SNAP.read_text())
    db = sqlite3.connect(str(DB))
    db.row_factory = sqlite3.Row
    hist = json.loads(HIST.read_text())
    
    changes = []
    
    # 取得今天的 db 列或複製前一天
    today_row = db.execute("SELECT * FROM assets WHERE date=?", (TODAY,)).fetchone()
    if not today_row:
        yesterday = db.execute("SELECT * FROM assets ORDER BY date DESC LIMIT 1").fetchone()
        if yesterday:
            db.execute('''INSERT INTO assets (date, cash_total, bonds, securities, insurance, funds, real_estate, total_assets)
                VALUES (?,?,?,?,?,?,?,?)''',
                (TODAY, yesterday["cash_total"], yesterday["bonds"], yesterday["securities"],
                 yesterday["insurance"], yesterday["funds"], yesterday["real_estate"], yesterday["total_assets"]))
            db.commit()
    
    for key, val in updates.items():
        if key not in FIELDS:
            print(f"  ⚠️ 未知欄位: {key}")
            continue
        f = FIELDS[key]
        old_val = None
        
        # 更新 db
        if f["db"]:
            old_row = db.execute(f"SELECT {f['db']} FROM assets WHERE date=?", (TODAY,)).fetchone()
            if old_row:
                old_val = old_row[0]
            db.execute(f"UPDATE assets SET {f['db']}=? WHERE date=?", (val, TODAY))
        
        # 更新 snapshot
        for s_key in f["snap"]:
            old_snap_val = snap.get(s_key, 0)
            if old_val is None: old_val = old_snap_val
            snap[s_key] = val
        
        # 更新 history
        for h_key in f["hist"]:
            if TODAY in hist:
                old_hist_val = hist[TODAY].get(h_key, 0)
                if old_val is None: old_val = old_hist_val
                hist[TODAY][h_key] = val
        
        # 更新 detail（如有）
        if key == "insurance":
            if TODAY in hist and "insurance_detail" in hist[TODAY]:
                hist[TODAY]["insurance_detail"]["保單總現値"] = val
                # 如果安聯A+B也在更新中，一併改
                if "insurance_detail" in updates:
                    pass  # 由呼叫方提供詳細
        
        old_label = f"{old_val:,.0f}" if old_val else "?"
        changes.append(f"  {f['label']}: {old_label} → {val:,}")
    
    # 如果同時有保險細項更新
    if "insurance_detail" in updates:
        detail = updates["insurance_detail"]
        if TODAY in hist and "insurance_detail" in hist[TODAY]:
            for k, v in detail.items():
                hist[TODAY]["insurance_detail"][k] = v
                changes.append(f"  {k}: → {v:,}")
    
    # 寫入
    db.commit()
    db.close()
    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=2))
    HIST.write_text(json.dumps(hist, ensure_ascii=False, indent=2))
    
    print(f"✅ 三源同步完成（{TODAY}）")
    for c in changes:
        print(c)

def parse_args():
    updates = {}
    detail = {}
    for arg in sys.argv[1:]:
        if "=" in arg:
            k, v = arg.split("=", 1)
            k = k.lstrip("--")
            if k.startswith("detail_"):
                detail[k.replace("detail_", "")] = float(v)
            elif k in FIELDS:
                updates[k] = float(v)
    if detail:
        updates["insurance_detail"] = detail
    return updates

if __name__ == "__main__":
    u = parse_args()
    if not u:
        print("用法: python sync_all.py --insurance=9694964 --securities=2375390")
        print("      python sync_all.py --insurance=9694964 --detail_安聯保單A+B 現值=7735984")
        sys.exit(1)
    sync_updates(u)
