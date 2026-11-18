#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""資料新鮮度：每個資產來源的 as_of、落後天數、可信度分級。

為什麼要有這支（2026-11-18）：
    11/18 的總資產 25,970,345 其實是六個不同日期的拼盤 ——
    11/17 證券 ＋ 11/16 國泰基金 ＋ 11/13 鉅亨 ＋ 11/13 安聯
    ＋ 11/16 第一金 ＋ 11/16 現金。
    報表上看不出哪一個是舊的，於是「過去五天的跌」被壓縮成「今天掉 46 萬」，
    使用者合理的反應是「為什麼突然跌這麼多」。
    本工具把 as_of 變成可讀狀態，並給出三級標記；總資產的「可信基準日」
    = 所有來源中最舊的那一個（min），不是最後更新日。

分級：0–3 天 fresh（🟢）／4–7 天 warn（🟡）／>7 天 stale（🔴）

用法：
    python tools/freshness.py              # 文字表
    python tools/freshness.py --json       # JSON（給日報／儀表板注入）
    python tools/freshness.py --exit-code  # 任一來源 stale → rc=1（可放閘門）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SNAP = REPO / "snapshot.json"

# 類別 → (顯示名, data_freshness 鍵, 退路取值函式名)
LABELS = [
    ("securities", "證券", 12.5),
    ("funds_cathay", "國泰基金", 14.3),
    ("funds_heng", "鉅亨基金", 4.5),
    ("insurance_allianz", "安聯保單", 12.2),
    ("insurance_firstjin", "第一金保單", 1.9),
    ("cash", "現金", 7.9),
]

FRESH_MAX = 3
WARN_MAX = 7


def _parse(d) -> date | None:
    if not d:
        return None
    if isinstance(d, date):
        return d
    s = str(d).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _fallback(snap: dict) -> dict:
    """沒有 data_freshness 區塊時，從既有欄位拼出各來源日期。"""
    sec = snap.get("securities") or {}
    fbd = snap.get("firstjin_detail") or {}
    return {
        "securities": sec.get("price_date") or sec.get("as_of"),
        "funds_cathay": snap.get("funds_cathay_as_of") or snap.get("cathay_cum_dividend_asof"),
        "funds_heng": snap.get("funds_heng_as_of") or snap.get("fund_note_20261118"),
        "insurance_allianz": snap.get("allianz_as_of") or snap.get("last_insurance_update"),
        "insurance_firstjin": snap.get("firstjin_as_of") or fbd.get("as_of"),
        "cash": snap.get("cash_as_of") or snap.get("moneybook_export_date"),
    }


def compute(snap: dict, today: date | None = None) -> dict:
    today = today or date.today()
    src = (snap.get("data_freshness") or {})
    fb = _fallback(snap)
    rows = []
    for key, label, _w in LABELS:
        entry = src.get(key) or {}
        as_of = _parse(entry.get("as_of")) or _parse(fb.get(key))
        lag = (today - as_of).days if as_of else None
        if lag is None:
            level, mark = "unknown", "⚪"
        elif lag <= FRESH_MAX:
            level, mark = "fresh", "🟢"
        elif lag <= WARN_MAX:
            level, mark = "warn", "🟡"
        else:
            level, mark = "stale", "🔴"
        rows.append({
            "key": key,
            "label": label,
            "as_of": as_of.isoformat() if as_of else None,
            "lag_days": lag,
            "level": level,
            "mark": mark,
            "source": entry.get("source") or "",
        })
    known = [r for r in rows if r["as_of"]]
    base = min(known, key=lambda r: r["as_of"]) if known else None
    return {
        "today": today.isoformat(),
        "rows": rows,
        "base_as_of": base["as_of"] if base else None,
        "base_label": base["label"] if base else None,
        "base_lag_days": base["lag_days"] if base else None,
        "stale_count": sum(1 for r in rows if r["level"] == "stale"),
        "warn_count": sum(1 for r in rows if r["level"] == "warn"),
    }


def render_text(res: dict) -> str:
    lines = [f"資料新鮮度（今日 {res['today']}）"]
    for r in res["rows"]:
        lag = f"{r['lag_days']} 天" if r["lag_days"] is not None else "無資料"
        lines.append(f"  {r['mark']} {r['label']:<6} {r['as_of'] or '—':<12} 落後 {lag}"
                     + (f"｜{r['source']}" if r["source"] else ""))
    lines.append(f"→ 總資產可信基準日：{res['base_as_of'] or '—'}"
                 f"（最舊來源：{res['base_label'] or '—'}，落後 {res['base_lag_days']} 天）")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="資料新鮮度檢查")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    ap.add_argument("--exit-code", action="store_true", help="有 stale 來源時 rc=1")
    a = ap.parse_args()

    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    res = compute(snap)
    print(json.dumps(res, ensure_ascii=False, indent=1) if a.json else render_text(res))
    if a.exit_code and res["stale_count"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
