"""tools/test_date_integrity.py — T1–T12 驗收（INC-20261106-01）

執行：python tools/test_date_integrity.py
設計原則：
  · 測試程式全部 PASS ←→ 11/06 原始案例三層全 FAIL  兩者不矛盾：
    前者證明攔截機制正確，後者證明問題案例真的被攔截。
  · 全部以真實 snapshot.json 為輸入（唯讀），不修改任何資料。
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import date_integrity as di  # noqa: E402

RESULTS = []


def check(case_id, desc, ok, detail=""):
    RESULTS.append((case_id, desc, bool(ok), detail))
    print(f"{'✅' if ok else '❌'} {case_id} {desc}" + (f" — {detail}" if detail else ""))


def load_snapshot():
    return json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))


def main():
    snap = load_snapshot()
    R = date(2026, 11, 6)          # 報告基準日（11/06）
    NOW_PRE_CLOSE = datetime(2026, 11, 6, 13, 30)   # 收盤前
    NOW_POST_CLOSE = datetime(2026, 11, 6, 14, 0)   # 收盤後

    # ── T1 DNS 全失敗、昨日快取存在 ───────────────────────────────
    l1 = di.market_layer(None, R, NOW_POST_CLOSE)
    check("T1", "DNS 全失敗＋昨日快取 → L1 BLOCKED", l1["status"] == di.BLOCKED, l1["reasons"][0])

    # ── T2 DNS 正常、快取日期仍是昨日 ─────────────────────────────
    l1 = di.market_layer({"date": "2026-11-05", "phase": "close", "source": "cache"}, R, NOW_POST_CLOSE)
    check("T2", "快取為昨日不得當今日 → 非 PASS", l1["status"] != di.PASS, f"{l1['status']}")

    # ── T3 週末／停市日不增加延遲 ─────────────────────────────────
    lag = di.trading_days_between(date(2026, 11, 6), date(2026, 11, 8))  # 五 → 日
    check("T3", "週末不計延遲交易日", lag == 0, f"lag={lag}")

    # ── T4 核心行情缺漏、財務正常 ─────────────────────────────────
    l1 = di.market_layer(None, R, NOW_POST_CLOSE)
    bank_exempt = {"securities": {"price_date": "2026-11-06"},
                   "fund_nav_dates": {"A": "2026-11-06"},
                   "firstjin_detail": {"last_update": "2026-11-06"},
                   "policy_valuation_dates": {"安聯A": "2026-11-06"},
                   "cash_source": {"date": "2026-11-06"}}
    l2 = di.financial_layer(bank_exempt, R)
    check("T4", "市場 BLOCKED／財務 PASS 可並存", l1["status"] == di.BLOCKED and l2["status"] == di.PASS,
          f"L1={l1['status']} L2={l2['status']}")

    # ── T5 13:45 前宣稱 close → BLOCKED；intraday → DEGRADED ──────
    l1_close = di.market_layer({"date": "2026-11-06", "phase": "close"}, R, NOW_PRE_CLOSE)
    l1_intra = di.market_layer({"date": "2026-11-06", "phase": "intraday"}, R, NOW_PRE_CLOSE)
    check("T5", "盤中冒充收盤 → BLOCKED", l1_close["status"] == di.BLOCKED, l1_close["reasons"][0])
    check("T5b", "盤中值僅 DEGRADED、不得 PASS", l1_intra["status"] == di.DEGRADED, f"{l1_intra['status']}")

    # ── T6 真實 snapshot：證券 11-05／基金 11-02 → 落後＝標示（不停發）─────
    l2_real = di.financial_layer(snap, R)
    funds_item = [i for i in l2_real["items"] if i["key"] == "funds"][0]
    sec_item = [i for i in l2_real["items"] if i["key"] == "tw_securities"][0]
    check("T6", "基金 11-02（落後 4 交易日）→ DEGRADED 並標示最後有效日", funds_item["status"] == di.DEGRADED and funds_item["value"],
          f"{funds_item['value']}")
    check("T6b", "證券 11-05 → DEGRADED（落後 1 日，非 PASS）", sec_item["status"] == di.DEGRADED,
          f"{sec_item['status']}")

    # ── T7 第 5 章歷史敘述未標記 ──────────────────────────────────
    l3 = di.narrative_layer([{"text": "13:00 盤中 41,862.47(-2.53%)→收盤 41,574.72(-3.20%)",
                              "content_date": "2026-11-05", "contains_today_word": True}], R)
    check("T7", "歷史敘述未標〔歷史〕→ BLOCKED", l3["status"] == di.BLOCKED, l3["reasons"][0])
    l3_ok = di.narrative_layer([{"text": "〔歷史：2026-11-05〕13:00 盤中 41,862.47→收盤 41,574.72",
                                 "content_date": "2026-11-05", "contains_today_word": False}], R)
    check("T7b", "已標〔歷史〕→ PASS", l3_ok["status"] == di.PASS, l3_ok["status"])

    # ── T8 同區塊雙值 ────────────────────────────────────────────
    l3 = di.narrative_layer([], R, value_pairs=[{"label": "台股加權",
                                                 "values": ["39,987.41", "39,987.72"]}])
    check("T8", "同區塊雙值 → BLOCKED", l3["status"] == di.BLOCKED, l3["reasons"][0])

    # ── T9 無來源數字（補造）────────────────────────────────────
    l3 = di.narrative_layer([], R, unsourced=[{"label": "費半", "value": "9,011.14", "source": None}])
    check("T9", "無來源數字 → BLOCKED", l3["status"] == di.BLOCKED, l3["reasons"][0])

    # ── T10 分項可追溯；總額一致不得豁免 ─────────────────────────
    all_have_source = all(i["source"] for i in l2_real["items"])
    blocked_items = [i["label"] for i in l2_real["items"] if i["status"] != di.PASS]
    check("T10", "每分項皆具來源欄位（可追溯）", all_have_source, f"{len(l2_real['items'])} 分項")
    check("T10b", "基金/保單落後仍逐項標示（不得被總額一致豁免）", "基金" in blocked_items and "安聯保單" in blocked_items, f"{blocked_items}")

    # ── T11 保單估值日 null → BLOCKED（不得填推估）────────────────
    s2 = json.loads(json.dumps(snap))
    s2.pop("policy_valuation_dates", None)
    l2b = di.financial_layer(s2, R)
    pj = [i for i in l2b["items"] if i["key"] == "policy_allianz"][0]
    check("T11", "安聯估值日缺失 → UNKNOWN 標示、且不補造日期",
          pj["status"] == di.DEGRADED and not any(v for v in (pj["value"] or {}).values()), pj["display"])

    # ── T12 禁用來源（market_snapshot 當 fallback）───────────────
    raised = False
    try:
        di.assert_no_forbidden_sources(["snapshot.market_snapshot"])
    except RuntimeError:
        raised = True
    check("T12", "market_snapshot 當日期來源 → 直接拋錯", raised)

    # ── 11/06 原始案例：L1／L2／L3 三層全 FAIL ───────────────────
    verdict = di.check(
        snap,
        market_meta={"date": "2026-11-06", "phase": "close", "source": "daily_analysis.json"},
        narratives=[{"text": "13:00 盤中 41,862.47(-2.53%)→收盤 41,574.72(-3.20%)",
                     "content_date": "2026-11-05", "contains_today_word": True}],
        report_date=R, now=NOW_PRE_CLOSE,
    )
    layers = verdict["layers"]
    # 裁決（2026-11-06）：落後不再當「FAIL」，但**冒充**必須被擋。
    # 11/06 原案 = 13:00 盤中用「收盤」宣稱（L1 冒充）＋ 內文 11-05 數字稱「今日」（L3 冒充）
    _dec0 = di.publish_decision(verdict, snapshot=snap)
    check("CASE", "11/06 原始案例：L1/L3 冒充 → 阻擋發布",
          layers["L1_market"] == di.BLOCKED and layers["L3_narrative"] == di.BLOCKED
          and _dec0["publish"] is False and len(_dec0["blocking"]) >= 2,
          json.dumps(layers, ensure_ascii=False) + f"｜blocking={len(_dec0['blocking'])}")
    check("CASE1b", "11/06 落後項目（L2）改為標示而非停發",
          layers["L2_financial"] == di.DEGRADED and bool(_dec0["labels"]),
          f"L2={layers['L2_financial']}｜labels={len(_dec0['labels'])}")
    check("CASE2", "整體 BLOCKED → 禁止市場因果結論",
          verdict["status"] == di.BLOCKED and verdict["market_conclusion_allowed"] is False)

    # ── T13 基金金額／日期雙寫（裁決①）────────────────────────────
    dual_bad = di.fund_dual_write_check(12568172, 12684574,
                                        {"A": "2026-11-02"}, {"A": "2026-11-02"})
    dual_ok = di.fund_dual_write_check(12568172, 12684574,
                                       {"A": "2026-11-02"}, {"A": "2026-11-05"})
    check("T13", "金額更新但日期未同步 → BLOCKED（本日實例）", dual_bad["status"] == di.BLOCKED,
          dual_bad["reasons"][0])
    check("T13b", "金額與日期雙寫 → PASS", dual_ok["status"] == di.PASS)

    # ── 匯總 ────────────────────────────────────────────────────
    passed = sum(1 for _, _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("\n" + "=" * 52)
    print(f"  T1–T13 驗收：{passed}/{total} PASS")
    print("=" * 52)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
