#!/usr/bin/env python3
"""action_loop.py — 行動閉環追蹤（P0-3）
1. 每次產出對策表時，存建議快照 rebalance_snapshot.json
2. 下期比對實際資產 → 標記 已執行/部分執行/未執行
3. 檢核缺口是否收斂；未收斂標註原因

流程：
- tactical_table.py 產出後呼叫 save_snapshot()
- 下次產出時呼叫 compare() 自動比對
"""
import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAPSHOT_FILE = BASE / "rebalance_snapshot.json"

def save_snapshot(table: dict, snap: dict):
    """儲存本期待執行建議快照"""
    records = []
    for r in table["rows"]:
        if r["是否交易"] or r["建議動作"] in ("增持", "減碼"):
            records.append({
                "資產分類": r["資產分類"],
                "偏離pp": r["偏離pp"],
                "建議動作": r["建議動作"],
                "精算金額": r["精算金額"],
                "階梯等級": r["階梯等級"],
                "現況占比": r["現況占比"],
            })
    snapshot = {
        "date": date.today().isoformat(),
        "us30y": table.get("us30y"),
        "frozen": table.get("frozen"),
        "total_assets": snap.get("total_assets", 0),
        "recommendations": records,
    }
    SNAPSHOT_FILE.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 建議快照已儲存（{len(records)} 筆建議）→ rebalance_snapshot.json")

def compare(table: dict, snap: dict) -> dict:
    """比對上一期快照 vs 本期實際 → 執行狀態追蹤"""
    if not SNAPSHOT_FILE.exists():
        print("ℹ️ 無上一期快照（首次執行，僅儲存）")
        save_snapshot(table, snap)
        return {"status": "first_run"}

    prev = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
    prev_date = prev.get("date", "?")
    prev_total = prev.get("total_assets", 0)
    cur_total = snap.get("total_assets", 0)

    # 本期 actual_pct（對策表已含）
    cur_rows = {r["資產分類"]: r for r in table["rows"]}

    tracking = []
    for rec in prev.get("recommendations", []):
        asset = rec["資產分類"]
        cur = cur_rows.get(asset, {})
        prev_dev = rec["偏離pp"]
        cur_dev = cur.get("偏離pp", 0)

        # 判斷執行狀態：缺口收斂 = 已朝目標方向移動
        if rec["建議動作"] in ("增持", "減碼"):
            # 增持：負偏離變小 = 收斂；減碼：正偏離變小 = 收斂
            if rec["建議動作"] == "增持":
                improved = cur_dev > prev_dev  # -10 → -8 = 收斂
            else:
                improved = cur_dev < prev_dev  # +8 → +5 = 收斂
            # 收斂幅度
            change = abs(cur_dev) - abs(prev_dev)
            if improved and change > 1:
                status = "已執行"
            elif improved:
                status = "部分執行"
            else:
                status = "未執行"
        else:
            status = "觀察(無動作)"
            change = 0

        # 未收斂原因推斷
        reason = ""
        if status == "未執行" and change < -0.5:
            if abs(cur_dev) > abs(prev_dev):
                reason = "市場反向波動" if cur_dev * prev_dev > 0 else "市場波動"
            else:
                reason = "待確認"

        tracking.append({
            "資產分類": asset,
            "上期偏離": round(prev_dev, 1),
            "本期偏離": round(cur_dev, 1),
            "建議動作": rec["建議動作"],
            "精算金額": rec["精算金額"],
            "執行狀態": status,
            "缺口變化": round(change, 1),
            "未達標原因": reason,
        })

    result = {
        "上一期": prev_date,
        "本期": date.today().isoformat(),
        "總資產變化": f"{prev_total:,} → {cur_total:,}",
        "追蹤": tracking,
        "統計": {
            "已執行": sum(1 for t in tracking if t["執行狀態"] == "已執行"),
            "部分執行": sum(1 for t in tracking if t["執行狀態"] == "部分執行"),
            "未執行": sum(1 for t in tracking if t["執行狀態"] == "未執行"),
        },
    }
    # 儲存本期快照（供下期比對）
    save_snapshot(table, snap)
    return result

def main():
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    from tactical_table import build_table
    us30y = None
    try:
        st = json.loads((BASE / "us30y_state.json").read_text(encoding="utf-8"))
        us30y = st.get("last_rate")
    except Exception:
        pass
    table = build_table(snap, us30y)
    result = compare(table, snap)
    print(f"\n=== 行動閉環追蹤 ===")
    if result.get("status") == "first_run":
        print("首次執行，已儲存基準快照")
        return
    print(f"上一期: {result['上一期']} → 本期: {result['本期']}")
    print(f"總資產: {result['總資產變化']}")
    for t in result["追蹤"]:
        print(f"  {t['資產分類']:8s} {t['執行狀態']:6s} 偏離 {t['上期偏離']:+.1f}→{t['本期偏離']:+.1f} ({t['缺口變化']:+.1f}) {t['未達標原因']}")
    print(f"統計: {result['統計']}")

if __name__ == "__main__":
    main()
