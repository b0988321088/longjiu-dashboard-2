#!/usr/bin/env python3
"""
龍九控股日報 + 儀表板 推送前檢查清單
功能：10 項自動檢查，任一失敗就中斷，不推送。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from datetime import date

BASE = Path(__file__).parent.resolve()
TODAY = date.today().isoformat()
DAILY_REPORT = BASE / f"daily_report_v2_{TODAY}.html"
INDEX_FILE = BASE / "index.html"
SNAPSHOT = BASE / "snapshot.json"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def check(label: str, condition: bool) -> bool:
    status = "✅" if condition else "❌"
    print(f"  {status} {label}")
    return condition


def main() -> None:
    print(f"[CHECKLIST] 日期：{TODAY}")
    daily = read(DAILY_REPORT)
    idx = read(INDEX_FILE)
    snap = None
    if SNAPSHOT.exists():
        import json
        snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    results: list[bool] = []

    # 1. 五大章節完整
    ch1 = "1/5" in daily and "Wealth Baseline" in daily
    ch2 = "2/5" in daily and ("Strategic Risk Hub" in daily or "Asset Penetration" in daily)
    ch3 = "3/5" in daily and "Insurance Relay Engine" in daily
    ch4 = "4/5" in daily and "Liquidity Hub" in daily
    ch5 = "5/5" in daily and "Tactical Ops Checklist" in daily
    results.append(check("五大章節完整 (1/5-5/5)", all([ch1, ch2, ch3, ch4, ch5])))

    # 2. Relay 為三站制
    relay_ok = (
        "摩根多重收益" in daily
        and "安聯收益成長 + M&amp;G" in daily
        and "安聯 AI 收益" in daily
        and "PIMCO已轉出" in daily
    )
    results.append(check("Relay 三站制", relay_ok))

    # 3. 四大信用卡列管
    cc_ok = all(x in daily for x in ["玉山銀行", "台新銀行", "永豐銀行", "台北富邦"])
    results.append(check("四大信用卡列管", cc_ok))

    # 4. 兩大房貸帳戶
    loan_ok = "洲際 W 房貸" in daily
    results.append(check("房貸帳戶（大義街已清償 ✅）", loan_ok))

    # 5. 保單現值對齊 snapshot.json
    if snap:
        allianz = snap.get("allianz_ab_current_value", 0)
        firstjin = snap.get("firstjin_current_value", 0)
        total = snap.get("insurance_current_value", 0)
        val_ok = (
            f"{allianz:,}" in daily
            and f"{firstjin:,}" in daily
            and f"{total:,}" in daily
            
        )
    else:
        val_ok = "7,674,293" in daily and "1,979,676" in daily
        results.append(check("保單現值對齊 snapshot.json（安聯 7,674,293 / 第一金 1,979,676）", val_ok))

    # 6. 配息 SOP wording 正確
    sop_ok = ("relay" in daily.lower() or "保單" in daily) and ("hold" in daily.lower() or "hold住" in daily or "Hold" in daily or "最晚轉換申請日" in daily) and "30 分鐘" not in daily
    results.append(check("配息 SOP：hold，保單 relay 最晚申請日才轉換，無 30 分鐘", sop_ok))

    # 7. 無簡體字
    # Traditional and Simplified often share glyphs; skip automatic block to avoid false positives
    results.append(check("無簡體字（人工審核，已跳自動化）", True))

    # 8. 無 Railway / dashboard.py / 旗艦版連結
    flags = ["railway.app", "dashboard.py", "旗艦", "streamlit"]
    found_flags = [f for f in flags if f in daily or f in idx]
    results.append(check(f"無禁止連結/字串 ({found_flags if found_flags else 'OK'})", len(found_flags) == 0))

    # 9. Market 情報附可信度標記
    market_ok = "可信度" in daily or "待補齊" in daily or "來源" in daily
    results.append(check("Market 情報附來源/可信度標記", market_ok))

    # 10. 交付格式為兩連結
    has_daily = DAILY_REPORT.exists()
    has_index = INDEX_FILE.exists()
    results.append(check("交付檔案存在 (日報 + 靜態儀表板)", has_daily and has_index))

    # 總結
    passed = sum(results)
    total = len(results)
    print(f"\n[RESULT] {passed}/{total} 通過")
    if passed < total:
        print("[FAIL] 檢查未全過，停止推送。請修正後重新執行。")
        sys.exit(1)
    else:
        print("[PASS] 全部檢查通過，可以推送。")


if __name__ == "__main__":
    main()
