"""tools/test_market_section.py — 第 5 章三段式 fallback 驗收（方案 A）

執行：python tools/test_market_section.py
全部用臨時目錄的假資料，不動真實 daily_analysis.json／緊急應變 JSON。
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from daily_report_assembly import compose_market_section  # noqa: E402

TODAY = "2026-11-06"
PASSED, FAILED = [], []


def check(tag, desc, cond, extra=""):
    (PASSED if cond else FAILED).append(tag)
    print(f"{'✅' if cond else '❌'} {tag} {desc}" + (f" — {extra}" if extra else ""))


def mk(tmp, emergency=None, daily=None):
    d = Path(tmp)
    (d / "data").mkdir(parents=True, exist_ok=True)
    if emergency is not None:
        (d / "data" / "emergency_llm_analysis.json").write_text(
            json.dumps(emergency, ensure_ascii=False), encoding="utf-8")
    if daily is not None:
        (d / "daily_analysis.json").write_text(
            json.dumps(daily, ensure_ascii=False), encoding="utf-8")
    return d


DAILY = {
    "date": "20261106", "generated_at": "2026-11-06T07:00:00",
    "market": {"twii": "39,690.74 (-4.53%)", "tsm": "2,080.00 (-7.14%)",
               "sox": "9,011.14 (-12.25%)", "us": "道瓊 51,523.06 (-3.44%)",
               "cpi": "未取得"},
    "signals": {"sell_signals": ["台股加權大跌 -4.53%"], "buy_signals": []},
    "news": [{"title": "美股血洗拖累台股", "url": "https://x"}],
    "scenario_summary": "市場震盪，維持防禦",
    "briefing": "",
}


def main() -> int:
    # ── Q1：緊急應變 content_date = 今日 → 第一來源 ──────────────
    with tempfile.TemporaryDirectory() as t:
        d = mk(t, emergency={"content_date": TODAY, "full_report": "今日盤中觀察…"}, daily=DAILY)
        r = compose_market_section(d, TODAY, datetime(2026, 11, 6, 7, 0))
        check("Q1", "LLM 內容日期正確 → 第一來源", r["tier"] == 1 and r["html"] == "",
              f"tier={r['tier']}")

    # ── Q2：LLM 日期不符 → 第二來源 ────────────────────────────
    with tempfile.TemporaryDirectory() as t:
        d = mk(t, emergency={"date": "2026-11-05", "full_report": "昨日內容"}, daily=DAILY)
        r = compose_market_section(d, TODAY, datetime(2026, 11, 6, 7, 0))
        check("Q2", "LLM 日期不符 → 改用 daily_analysis", r["tier"] == 2 and "39,690.74" in r["html"],
              f"tier={r['tier']}")

    # ── Q3：兩者皆不可用 → 第三來源 ────────────────────────────
    with tempfile.TemporaryDirectory() as t:
        d = mk(t)
        r = compose_market_section(d, TODAY, datetime(2026, 11, 6, 7, 0))
        check("Q3", "無可信來源 → 明示未取得（不補位）",
              r["tier"] == 3 and "本日市場資料未取得" in r["html"])

    # ── Q4：台股標前一交易日收盤（07:00 抓取）──────────────────
    with tempfile.TemporaryDirectory() as t:
        d = mk(t, daily=DAILY)
        r = compose_market_section(d, TODAY, datetime(2026, 11, 6, 7, 0))
        check("Q4", "台股標「前一交易日收盤」", "台股" in r["html"] and "前一交易日收盤" in r["html"])

    # ── Q5：美股標最近一次已完成收盤 ───────────────────────────
    with tempfile.TemporaryDirectory() as t:
        d = mk(t, daily=DAILY)
        r = compose_market_section(d, TODAY, datetime(2026, 11, 6, 7, 0))
        check("Q5", "美股標「最近一次已完成收盤」", "最近一次已完成收盤" in r["html"])

    # ── Q6：13:00 抓的盤中值，14:30 不得標成收盤 ───────────────
    with tempfile.TemporaryDirectory() as t:
        _d13 = dict(DAILY, generated_at="2026-11-06T13:00:34")
        d = mk(t, daily=_d13)
        r = compose_market_section(d, TODAY, datetime(2026, 11, 6, 14, 30))
        check("Q6", "13:00 盤中值 → 標「盤中（非收盤）」（不得因現在時刻變成收盤）",
              "盤中，非收盤" in r["html"] and "當日收盤" not in r["html"])

    # ── Q7：內文不得用「今日」描述行情 ─────────────────────────
    with tempfile.TemporaryDirectory() as t:
        _dj = dict(DAILY, scenario_summary="今日震盪，維持防禦")
        d = mk(t, daily=_dj)
        r = compose_market_section(d, TODAY, datetime(2026, 11, 6, 7, 0))
        check("Q7", "內文不得出現「今日」", "今日" not in r["html"], r["html"][:40])

    # ── Q8：抓取時刻不明 → 不聲稱收盤 ─────────────────────────
    with tempfile.TemporaryDirectory() as t:
        _dn = {k: v for k, v in DAILY.items() if k != "generated_at"}
        d = mk(t, daily=_dn)
        r = compose_market_section(d, TODAY, datetime(2026, 11, 6, 7, 0))
        check("Q8", "無 generated_at → 標「時點不明（不標收盤）」",
              "時點不明" in r["html"] and "當日收盤" not in r["html"])

    # ── Q9：date 非今日（檔案很新）→ 不得用 mtime 判斷 ─────────
    with tempfile.TemporaryDirectory() as t:
        _ds = dict(DAILY, date="20261105")
        d = mk(t, daily=_ds)
        r = compose_market_section(d, TODAY, datetime(2026, 11, 6, 7, 0))
        check("Q9", "daily_analysis.date 非今日 → 第三來源（不看檔案時間）", r["tier"] == 3)

    # ── Q10：真實 11/06 檔案 → 第二來源且無「今日」─────────────
    r = compose_market_section(BASE, "2026-11-06", datetime(2026, 11, 6, 7, 0))
    check("Q10", "真實市場資料可組稿（11/06）", r["tier"] in (1, 2) and "as-of 2026-11-06" in r["html"],
          f"tier={r['tier']}")
    if r["html"]:
        check("Q10b", "真實組稿內文不含「今日」", "今日" not in r["html"])

    # ── Q11：美股時區以美東 09:30–16:00 判定（含 DST）───────────
    from daily_report_assembly import _market_phase_labels
    _t22 = _market_phase_labels(datetime(2026, 11, 6, 22, 0), datetime(2026, 11, 6, 22, 0))
    _t23 = _market_phase_labels(datetime(2026, 11, 6, 23, 0), datetime(2026, 11, 6, 23, 0))
    _t05 = _market_phase_labels(datetime(2026, 11, 7, 5, 0), datetime(2026, 11, 7, 5, 0))
    check("Q11", "美股時區：台北22:00=ET09:00（盤前不標盤中）、23:00=盤中、05:00=ET16:00（收盤）",
          _t22[1] == "最近一次已完成收盤" and _t23[1] == "盤中，非收盤" and _t05[1] == "最近一次已完成收盤",
          f"22:00→{_t22[1]}｜23:00→{_t23[1]}｜05:00→{_t05[1]}")

    total = len(PASSED) + len(FAILED)
    print("\n" + "=" * 52)
    print(f"  Q1–Q10 驗收：{len(PASSED)}/{total} PASS")
    print("=" * 52)
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
