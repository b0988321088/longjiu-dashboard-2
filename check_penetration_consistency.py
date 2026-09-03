#!/usr/bin/env python3
"""check_penetration_consistency.py — 穿透一致性檢查（P2）
比對 日報 / 穿透報告 / 緊急應變 三檔是否包含 snapshot 的穿透真值。
任一報表缺少真值 → 印出差異並回傳 exit code 1（阻止推送）。

預設檢查「當天產出組」；2026-09-04 起不再用 snapshot.date：
snapshot 的 date = 資料日可能停留多日 → 檢查器天天回頭查舊檔，
舊檔不會更新 → 同一條 ❌ 每日重複推 = 噪音（8/25 原則：重複狀態通知不推）。
緊急應變只在應變日產出（台股 13:00 / 美股 21:30 觸發）→ 缺檔為正常，不擋；
只有「存在但內容不符」才算失敗。

用法：python check_penetration_consistency.py [date]
"""
import datetime
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

def main():
    # 預設 = 當天（晨間 07:00 重產後的今日報表）
    today = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    files = {
        "日報": BASE / f"daily_report_v2_{today}.html",
        "穿透報告": BASE / f"penetration_report_{today}.html",
        "緊急應變": BASE / f"emergency_report_{today}.html",
    }

    # 真值：snapshot penetration actual_pct + 總資產
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    pen = snap.get("penetration", {}).get("actual_pct", {})
    truth_pct = {
        "台股": pen.get("台股市值型成長"),
        "美股": pen.get("美股市值型成長"),
        "防守": pen.get("防守型配息"),
        "債券": pen.get("債券"),
        "現金": pen.get("現金/安全網"),
    }
    truth_total = snap.get("total_assets", 0)
    # 精確字串（去掉逗號差異）
    truth_strs = set()
    for k, v in truth_pct.items():
        if v is not None:
            truth_strs.add(f"{v:.1f}")
    truth_total_str = f"{truth_total:,.0f}".replace(",", "")
    truth_total_alt = f"{truth_total:,.0f}"

    errors = []
    print(f"🔍 穿透一致性檢查（{today}）")
    print(f"snapshot 真值: {json.dumps(truth_pct, ensure_ascii=False)} | 總資產 {truth_total:,.0f}")
    print()

    for name, path in files.items():
        if not path.exists():
            if name == "緊急應變":
                # 非應變日無緊急報告 = 正常 → 不擋（只擋「存在但內容不符」）
                print(f"  {name}: ➖ 檔案不存在（非應變日正常，跳過）")
                continue
            print(f"  {name}: ❌ 檔案不存在")
            errors.append(f"{name} 檔案不存在")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # 檢查每個穿透真值字串是否出現
        missing = []
        for k, v in truth_pct.items():
            if v is None:
                continue
            s = f"{v:.1f}"
            if s not in text:
                missing.append(f"{k} {s}%")
        # 總資產（容許逗號差異）
        total_ok = (truth_total_str in text.replace(",", "")) or (truth_total_alt in text)
        if not total_ok:
            missing.append(f"總資產 {truth_total:,.0f}")
        if missing:
            print(f"  {name}: ❌ 缺少真值 → {'、'.join(missing)}")
            errors.append(f"{name} 缺少: {'、'.join(missing)}")
        else:
            print(f"  {name}: ✅ 包含全部穿透真值")

    if errors:
        print(f"\n❌ {len(errors)} 個檔案不一致：")
        for e in errors:
            print(f"  • {e}")
        print("⚠️ 請重新產出後再推送（python gen_emergency_XXXX.py && python build_penetration_report.py && python four_source_sync.py）")
        return 1
    print("\n✅ 三報表穿透一致，可推送")
    return 0

if __name__ == "__main__":
    sys.exit(main())
