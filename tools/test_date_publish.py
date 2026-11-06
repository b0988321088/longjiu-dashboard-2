"""tools/test_date_publish.py — P1–P7 發布政策驗收

裁決（2026-11-06）：「最新資料優先、舊資料明確標示、問題局部隔離、核心錯誤才整體阻擋」。
本檔證明三件事：
  1. 資料落後／UNKNOWN **不會**讓日報停發（只能標示）。
  2. 冒充（把非當日資料說成當日／用生成時間當內容日期）**一定**擋。
  3. 問題只隔離該段，不拖垮整份。
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import date_integrity as di  # noqa: E402

R = date(2026, 11, 6)
NOW_CLOSE = datetime(2026, 11, 6, 14, 30)

PASSED, FAILED = [], []


def check(tag, desc, cond, extra=""):
    (PASSED if cond else FAILED).append(tag)
    print(f"{'✅' if cond else '❌'} {tag} {desc}" + (f" — {extra}" if extra else ""))


def snap_with(sec="2026-11-05", funds="2026-11-02", cash="2026-11-05", allianz=None,
              firstjin="2026-10-31"):
    return {
        "date": "2026-11-06", "report_base_date": "2026-11-06",
        "securities": {"price_date": sec},
        "fund_nav_dates": {"國泰": funds, "鉅亨": funds, "安聯": funds},
        "cash_source": {"date": cash},
        "firstjin_detail": {"last_update": firstjin},
        "policy_valuation_dates": {"allianz": allianz},
    }


def main() -> int:
    # ── P1：資料齊全 → 可發布、PASS ─────────────────────────────
    v = di.check(snap_with(sec="2026-11-06", funds="2026-11-06", cash="2026-11-06",
                           allianz="2026-11-06", firstjin="2026-11-06"),
                 market_meta={"date": "2026-11-06", "phase": "close", "source": "daily_analysis.json"},
                 narratives=[{"text": "台股收盤 39,690.74（-4.53%）", "content_date": "2026-11-06"}],
                 report_date=R, now=NOW_CLOSE)
    d = di.publish_decision(v, snapshot=snap_with(sec="2026-11-06", funds="2026-11-06",
                                                  cash="2026-11-06", allianz="2026-11-06",
                                                  firstjin="2026-11-06"))
    check("P1", "最新資料齊全 → PASS 且可發布",
          d["publish"] is True and v["status"] == di.PASS, f"status={v['status']}")

    # ── P2：基金落後 4 交易日 → 標示、仍可發布 ──────────────────
    s2 = snap_with()
    v2 = di.check(s2, market_meta={"date": "2026-11-06", "phase": "close", "source": "daily_analysis.json"},
                  narratives=[{"text": "台股收盤 39,690.74", "content_date": "2026-11-06"}],
                  report_date=R, now=NOW_CLOSE)
    d2 = di.publish_decision(v2, snapshot=s2)
    fund_label = [x for x in d2["labels"] if x.startswith("基金")]
    check("P2", "基金 11-02 落後 → 可發布且逐項標示", d2["publish"] is True and bool(fund_label),
          f"L2={v2['layers']['L2_financial']}｜{fund_label[0][:36] if fund_label else '無'}")

    # ── P3：安聯 UNKNOWN → 標示、仍可發布、不補造 ────────────────
    s3 = snap_with(allianz=None)
    v3 = di.check(s3, market_meta={"date": "2026-11-06", "phase": "close", "source": "daily_analysis.json"},
                  narratives=[{"text": "台股收盤 39,690.74", "content_date": "2026-11-06"}],
                  report_date=R, now=NOW_CLOSE)
    d3 = di.publish_decision(v3, snapshot=s3)
    allianz_item = [i for i in v3["detail"]["L2"]["items"] if i["key"] == "policy_allianz"][0]
    check("P3", "安聯 UNKNOWN → 可發布、值為 UNKNOWN（不補造）",
          d3["publish"] is True and not any(v for v in (allianz_item["value"] or {}).values()),
          f"value={allianz_item['value']}")

    # ── P4：13:00 盤中卻標「收盤」→ 阻擋 ────────────────────────
    v4 = di.check(snap_with(), market_meta={"date": "2026-11-06", "phase": "close",
                                           "source": "daily_analysis.json"},
                  narratives=[{"text": "台股收盤 39,690.74", "content_date": "2026-11-06"}],
                  report_date=R, now=datetime(2026, 11, 6, 13, 0))
    d4 = di.publish_decision(v4, snapshot=snap_with())
    check("P4", "盤中冒充收盤 → 阻擋整份", d4["publish"] is False and bool(d4["blocking"]),
          d4["blocking"][0][:40] if d4["blocking"] else "")

    # ── P5：generated_at 冒充 content_date → 阻擋 ────────────────
    v5 = di.check(snap_with(), market_meta={"date": "2026-11-06", "phase": "close",
                                           "source": "daily_analysis.json"},
                  narratives=[{"text": "今日大盤量縮", "content_date": None,
                               "date_from_generated_at": True}],
                  report_date=R, now=NOW_CLOSE)
    d5 = di.publish_decision(v5, snapshot=snap_with())
    check("P5", "以 generated_at 冒充內容日期 → 阻擋整份",
          d5["publish"] is False and v5["detail"]["L3"]["status"] == di.BLOCKED)

    # ── P6：段落缺日期 → 只隔離該段，整份仍可發 ─────────────────
    v6 = di.check(snap_with(), market_meta={"date": "2026-11-06", "phase": "close",
                                           "source": "daily_analysis.json"},
                  narratives=[{"text": "今日大盤量縮"}, {"text": "台股收盤 39,690.74", "content_date": "2026-11-06"}],
                  report_date=R, now=NOW_CLOSE)
    d6 = di.publish_decision(v6, snapshot=snap_with())
    check("P6", "單段缺日期 → 隔離該段、其餘照發",
          d6["publish"] is True and len(d6["isolated"]) == 1, f"isolated={len(d6['isolated'])}")

    # ── P7：報告宣稱估值日 11-06，權威日 11-05 → 冒充 → 阻擋 ────
    s7 = snap_with()
    v7 = di.check(s7, market_meta={"date": "2026-11-06", "phase": "close", "source": "daily_analysis.json"},
                  narratives=[{"text": "台股收盤 39,690.74", "content_date": "2026-11-06"}],
                  report_date=R, now=NOW_CLOSE)
    d7 = di.publish_decision(v7, claims=[{"asset": "tw_securities", "claimed": "2026-11-06"}], snapshot=s7)
    check("P7", "宣稱估值日 ≠ 權威日（核心資產）→ 阻擋", d7["publish"] is False,
          d7["blocking"][0][:44] if d7["blocking"] else "")

    total = len(PASSED) + len(FAILED)
    print("\n" + "=" * 52)
    print(f"  P1–P7 驗收：{len(PASSED)}/{total} PASS")
    print("=" * 52)
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
