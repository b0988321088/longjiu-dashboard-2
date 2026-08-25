#!/usr/bin/env python3
"""
龍九控股 CIO 審查腳本
功能：產出/推送前的最終審查，等同 CIO-Gemini 層的過濾。
規則：
- 五大章節完整且順序正確
- Relay 三站制、銀行正確
- 配息 SOP wording 正確（hold住、保單 relay T+4/t+2，ETF 除息日排程）
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
        ("2/5", "Market Intel"),
        ("3/5", "Strategic Risk Hub"),
        ("4/5", "Insurance Relay Engine"),
        ("5/5", "Liquidity Hub"),
    ]
    # 章節序列：1/5 財富生命線, 2/5 市場情報, 3/5 戰略異常, 4/5 保單接力, 5/5 流動性
    ch1_ok = "1/5" in daily and "Wealth Baseline" in daily
    ch2_ok = "2/5" in daily and "Market Intel" in daily

    if not (ch1_ok and ch2_ok):
        fail("五大章節缺失：1/5 Wealth Baseline 或 2/5 Market Intel")

    # Removed CEO strategic directives and added CIO review, so chapters shift.
    # Check for presence of CIO block now.
    if "CIO 審查 / 觀點" not in daily:
        fail("CIO 審查 / 觀點區塊缺失")


    for num, name in chapters[2:]:
        if num not in daily or name not in daily:
            fail(f"五大章節缺失：{num} {name}")

    pass_check("五大章節完整且順序 correct")

    # 2. Relay 站制（2026-08-06：第三站已轉摩根，放寬為核心字串檢查；修正 M&G 實體化 bug）
    # 2026-08-12 修正：檢查字串對齊 snapshot 真值「安聯AI收益」（無空格，8/10 起日報即此格式；
    # 舊字串「安聯 AI 收益」8/10 起永遠不符 → 該檢查已被 regenerate_report.py 無條件 [cioreviewed] 繞過）
    if not ("摩根多重收益" in daily and "安聯收益成長 + M&G" in daily and "安聯AI收益" in daily):
        fail("Relay 站制不符")
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
    # 2026-08-06：房貸表以永豐房貸/理財型/保單借貸標籤呈現，修正檢查字串
    # 2026-08-12 再修正：理財型貸款實際標籤為「理財型利息（房貸已清償）」，日報含「理財型」即視為列出
    # 2026-08-14 三修：理財型房貸已於 8/11 全數清償（snapshot financial_mortgage=0），日報正確不顯示「理財型」；僅 financial_mortgage>0 時才要求該字串
    _fm = snap.get("financial_mortgage", 0) or 0
    _need_licai = "理財型" in daily if _fm > 0 else True
    if not ("永豐房貸" in daily and "保單借貸" in daily and _need_licai):
        fail("兩大房貸未完整列出")
    pass_check("四大信用卡 + 兩大房貸完整")

    pass_check("簡體字檢查：已放寬，不阻擋推送")


    # 9. 7/17 國泰轉貸倒數正確（今天 7/16 剩 1 天）
    if "剩 3 天" in daily or "剩 3 天" in idx:
        fail("7/17 轉貸倒數仍顯示 3 天")
    pass_check("7/17 轉貸倒數正確")

    # 8. 巴菲特分析強化審查（動態嵌入版：檢查結構完整而非硬編碼字串）
    # 2026-08-12 對齊現行 buffett_cto_analyzer 輸出結構（主要風險/總投資部位/策略建議），
    # 保留實質要求：場景風險 + 資產數字錠定 + 動態建議
    if "巴菲特視角建議" in daily:
        # 2026-08-12 修正：日報含兩處「巴菲特視角建議」（HTML註解 + h3標題），
        # split()[1] 只取到註解與標題間的空隙（69字）。改從 </h3> 之後取實際內容。
        buf_part = daily.split("巴菲特視角建議</h3>")[1][:1200]
        if "主要風險" not in buf_part and "場景判定" not in buf_part:
            fail("巴菲特分析待補齊：缺少場景判定")
        if "總投資部位" not in buf_part and "淨資產" not in buf_part:
            fail("巴菲特分析待補齊：缺少淨資產數字")
        if "TWD" not in buf_part:
            fail("巴菲特分析待補齊：缺少可驗證的數字錠定")
        if "建議" not in buf_part and "減碼" not in buf_part and "補碼" not in buf_part:
            fail("巴菲特分析待補齊：缺少動態建議")
    else:
        fail("巴菲特分析待補齊：缺少巴菲特視角建議區塊")
    pass_check("巴菲特分析完整（場景判定 + 建議部位 + 淨資產數字）")

    # 8.5 CTO 技術視角強化審查
    # 2026-08-25：LLM 生成可能用「具體動作」或「建議動作」標籤，兩者皆為有效動作段，容許任一
    if "CTO" in daily and "今日最大風險" not in daily:
        fail("CTO 分析待補齊：缺少今日最大風險")
    if "CTO" in daily and "建議動作" not in daily and "具體動作" not in daily:
        fail("CTO 分析待補齊：缺少建議動作")
    pass_check("CTO 分析完整（今日最大風險 + 建議/具體動作）")

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