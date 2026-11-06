"""tools/test_date_phase3.py — T14–T17（第三階段：寫入語義＋內容日期）

執行：python tools/test_date_phase3.py
全部以「純函式 + 靜態原始碼檢查」驗證，**不 import 產線腳本**（避免誤觸）。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import date_integrity as di  # noqa: E402

RESULTS = []
R = date(2026, 11, 6)


def check(cid, desc, ok, detail=""):
    RESULTS.append((cid, desc, bool(ok)))
    print(f"{'✅' if ok else '❌'} {cid} {desc}" + (f" — {detail}" if detail else ""))


def read(p):
    return (BASE / p).read_text(encoding="utf-8", errors="replace")


def main():
    # ── T14：四個寫入端雙欄位同步 ───────────────────────────────
    writers = ["regenerate_report.py", "sync_all.py", "safe_update.py", "build_penetration_report.py"]
    for f in writers:
        src = read(f)
        has_rb = 'report_base_date' in src
        sets_in_same_zone = bool(re.search(r'\[.report_base_date.\]\s*=|report_base_date.\]\s*=', src))
        check(f"T14-{f.split('.')[0]}", f"{f} 同時寫入 date 與 report_base_date",
              has_rb and sets_in_same_zone)

    # ── T14b：不得把 report_base_date 寫進估值欄位 ───────────────
    bad = []
    for f in writers:
        src = read(f)
        if re.search(r'price_date\s*=\s*.*report_base_date|fund_nav_dates.*report_base_date|valuation.*=\s*report_base_date', src):
            bad.append(f)
    check("T14b", "四個寫入端未把 report_base_date 寫入估值欄位", not bad, ",".join(bad) or "無")

    # ── T15：舊 date 不得推定資產估值日 ─────────────────────────
    snap = {
        "date": "2026-11-06",                  # 相容欄位＝報告執行日
        "report_base_date": "2026-11-06",
        "securities": {"price_date": "2026-11-05"},
        "fund_nav_dates": {"a": "2026-11-02", "b": "2026-11-02"},
        "policy_valuation_dates": {"allianz": None},
        "cash_source": {"date": "2026-11-05"},
        "firstjin_detail": {"last_update": "2026-10-31"},
    }
    check("T15a", "report_base() 只用於報告基準日，回 2026-11-06", di.report_base(snap) == "2026-11-06")
    check("T15b", "證券權威日 ≠ 報告日（不得被洗成 11-06）",
          di.authority_date(snap, "tw_securities") == "2026-11-05")
    check("T15c", "基金權威日取最大值 2026-11-02", di.authority_date(snap, "funds") == "2026-11-02")
    check("T15d", "安聯估值日 null → UNKNOWN", di.authority_date(snap, "policy_allianz") == "UNKNOWN")
    try:
        di.assert_no_forbidden_sources(["snapshot.date"])
        forbidden_ok = False
    except Exception:
        forbidden_ok = True
    check("T15e", "以 snapshot.date 當日期來源 → 拋錯（fail-closed）", forbidden_ok)

    fin = di.financial_layer(snap, R)
    check("T15f", "報告日 11-06 但基金 11-02 → L2 BLOCKED", fin["status"] == di.BLOCKED,
          json.dumps(fin["layers"] if "layers" in fin else {}, ensure_ascii=False))

    # ── T16：generated_at 不得替代 content_date ─────────────────
    l3_missing = di.narrative_layer([{"text": "今日台股收盤 39,690.74", "contains_today_word": True}], R)
    check("T16a", "缺 content_date → 該段隔離（DEGRADED，不停發）",
          l3_missing["status"] == di.DEGRADED and l3_missing["suppressed"] == 1,
          l3_missing["reasons"][0] if l3_missing["reasons"] else "")

    l3_gen = di.narrative_layer([{"text": "今日台股收盤 39,690.74",
                                  "date_from_generated_at": True,
                                  "narrative_date": "2026-11-06"}], R)
    check("T16b", "以 generated_at 冒充內容日期 → BLOCKED", l3_gen["status"] == di.BLOCKED)

    l3_ok = di.narrative_layer([{"content_date": "2026-11-06", "text": "台股收盤 39,690.74（-4.53%）"}], R)
    check("T16c", "content_date 正確 → L3 PASS（正常資料可通過）", l3_ok["status"] == di.PASS)

    # ── T17：同一章節多日期敘述正確標記 ─────────────────────────
    sections = [
        {"heading": "台股", "date": "2026-11-06", "text": "加權 39,690.74（-4.53%）"},
        {"heading": "美股", "date": "2026-11-05", "text": "費半 9,011.14（-12.25%）"},
    ]
    unmarked = di.narrative_layer([{"content_date": "2026-11-06", "text": "混合章節",
                                    "sections": sections}], R)
    check("T17a", "美股段落為 11-05 未標記 → BLOCKED", unmarked["status"] == di.BLOCKED,
          unmarked["reasons"][0] if unmarked["reasons"] else "")

    stamped = di.stamp_history(sections, R)
    marked = di.narrative_layer([{"content_date": "2026-11-06", "text": "混合章節",
                                  "sections": stamped}], R)
    check("T17b", "自動加註〔歷史：2026-11-05〕後 → PASS", marked["status"] == di.PASS,
          stamped[1]["text"][:24])
    check("T17c", "當日段落不加歷史標記（不得誤標）",
          "〔歷史：" not in stamped[0]["text"])

    sec_missing = di.narrative_layer([{"content_date": "2026-11-06", "text": "x",
                                       "sections": [{"heading": "未標日期段", "text": "某數字"}]}], R)
    check("T17d", "章節缺日期 → 該章隔離（不推定、不停發）",
          sec_missing["status"] == di.DEGRADED and sec_missing["suppressed"] >= 1)

    # ── T17e：build_dashboard 不再用報告日當估值日 ───────────────
    bd = read("build_dashboard.py")
    check("T17e", "build_dashboard 改用 report_base（不取 snapshot.date 當日期）",
          "report_base" in bd and 'str(snap.get("date") or _dt.date.today()' not in bd)

    passed = sum(1 for _, _, ok in RESULTS if ok)
    total = len(RESULTS)
    print("\n" + "=" * 52)
    print(f"  T14–T17 驗收：{passed}/{total} PASS")
    print("=" * 52)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
