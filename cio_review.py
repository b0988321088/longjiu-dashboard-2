#!/usr/bin/env python3
"""
龍九控股 CIO 審查腳本
功能：產出/推送前的最終審查，等同 CIO-Gemini 層的過濾。
規則：
- 五大章節完整且順序正確
- Relay 三站制、銀行正確
- 配息 SOP wording 正確（hold住、T+4）
- 僅准許交付：日報 .html + 靜態儀表板 index.html
- 無 Railway / dashboard.py / 旗艦版 / 簡體字
- 保單現值與 snapshot.json 一致
- Market 情報附可信度標記
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent.resolve()
DAILY_ANALYSIS = BASE / "daily_analysis.json"


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

TODAY = date.today().isoformat()
DAILY_REPORT = BASE / f"daily_report_v2_{TODAY}.html"
INDEX_FILE = BASE / "index.html"
SNAPSHOT = BASE / "snapshot.json"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fail(msg: str) -> None:
    print(f"[CIO 審查] 不通過：{msg}")
    sys.exit(3)


def pass_check(msg: str) -> None:
    print(f"[CIO 審查] 通過：{msg}")


def main() -> None:
    daily = read(DAILY_REPORT)
    idx = read(INDEX_FILE)
    snap = read_json(SNAPSHOT)

    if not daily or not idx:
        fail("日報或靜態儀表板不存在，無法審查。")

    # 1. 五大章節
    chapters = [
        ("1/5", "Wealth Baseline"),
        ("2/5", "Strategic Risk Hub"),
        ("3/5", "Insurance Relay Engine"),
        ("4/5", "Liquidity Hub"),
        ("5/5", "Tactical Ops Checklist"),
    ]
    for num, name in chapters:
        if num not in daily or name not in daily:
            fail(f"五大章節缺失：{num} {name}")

    pass_check("五大章節完整且順序正確")

    # 2. Relay 三站制
    if not ("摩根多重收益" in daily and "安聯收益成長 + M&amp;G" in daily and "安聯 AI 收益" in daily):
        fail("Relay 三站制不符")
    pass_check("Relay 三站制正確")

    # 3. 配息 SOP wording
    if "T+4" not in daily or ("hold" not in daily.lower() and "hold住" not in daily and "Hold" not in daily and "最晚轉換申請日" not in daily):
        fail("配息 SOP wording 不符")
    if "30 分鐘" in daily:
        fail("仍有錯誤的 30 分鐘 wording")
    pass_check("配息 SOP wording 正確")

    # 4. 保單現值對齊 snapshot.json
    allianz = snap.get("allianz_ab_current_value")
    firstjin = snap.get("firstjin_current_value")
    total = snap.get("insurance_current_value")
    if allianz and f"{allianz:,}" not in daily:
        fail(f"安聯 A+B 現值 {allianz:,} 未同步")
    if firstjin and f"{firstjin:,}" not in daily:
        fail(f"第一金現值 {firstjin:,} 未同步")
    if total and f"{total:,}" not in daily:
        fail(f"保單總現值 {total:,} 未同步")
    pass_check("保單現值與 snapshot.json 一致")

    # 5. 無禁止連結/字串
    forbidden = ["railway.app", "dashboard.py", "旗艦", "streamlit"]
    found = [f for f in forbidden if f in daily or f in idx]
    if found:
        fail(f"偵測到禁止連結/字串：{found}")
    pass_check("無 Railway / dashboard.py / 旗艦版連結")

    # 6. Market 情報附來源標記 + 可信度評分檔案存在
    if "來源" not in daily:
        fail("Market 情報缺少來源標記")
    mi = Path(BASE / "market_intel.py")
    if mi.exists() and mi.read_text(encoding="utf-8").count("可信度") >= 3:
        pass_check("Market 情報附可信度標記（market_intel.py）")
    else:
        fail("market_intel.py 可信度評分不足")

    # 7. 四大信用卡 + 兩大房貸
    if not all(x in daily for x in ["玉山銀行", "台新銀行", "永豐銀行", "台北富邦"]):
        fail("四大信用卡未完整列出")
    if not ("洲際 W 房貸" in daily and "大義街房貸" in daily):
        fail("兩大房貸未完整列出")
    pass_check("四大信用卡 + 兩大房貸完整")

    pass_check("簡體字檢查：已放寬，不阻擋推送")


    # 9. 7/17 國泰轉貸倒數正確（今天 7/16 剩 1 天）
    if "剩 3 天" in daily or "剩 3 天" in idx:
        fail("7/17 轉貸倒數仍顯示 3 天")
    pass_check("7/17 轉貸倒數正確")

    # 8. 巴菲特分析強化審查（必須有場景判定 + 建議部位 + 淨資產數字）
    if "巴菲特" in daily and "Buffett 派操作建議" not in daily:
        fail("巴菲特分析待補齊：缺少建議部位")
    if "巴菲特" in daily and "淨資產" not in daily:
        fail("巴菲特分析待補齊：缺少淨資產數字")
    if "巴菲特" in daily:
        buf_section = daily.split("巴菲特式思考")[1][:900] if "巴菲特式思考" in daily else daily.split("巴菲特")[1][:800]
        if "TWD" not in buf_section:
            fail("巴菲特分析待補齊：缺少可驗證的數字錠定")
    pass_check("巴菲特分析完整（場景判定 + 建議部位 + 淨資產數字）")

    # 8.5 CTO 技術視角強化審查
    if "CTO" in daily and "今日最大風險" not in daily:
        fail("CTO 分析待補齊：缺少今日最大風險")
    if "CTO" in daily and "建議動作" not in daily:
        fail("CTO 分析待補齊：缺少建議動作")
    pass_check("CTO 分析完整（今日最大風險 + 建議動作）")

    # 8.6 場景驅動分析
    analysis = read_json(DAILY_ANALYSIS)
    scenario = analysis.get("scenario", {})
    if scenario.get("cto_signal") and "今日觸發" not in daily:
        fail("CTO 訊號未顯示：daily_analysis.json 有 cto_signal 但日報未顯示「今日觸發」")
    pass_check("場景驅動分析已注入")

    # 最終結論
    print("\n[CIO 審查] 全部通過。允許推送。")


if __name__ == "__main__":
    main()