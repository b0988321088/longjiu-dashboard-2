#!/usr/bin/env python3
"""同義（派生）欄位重算：以真值覆寫 snapshot.json 內所有該保持一致的值。

為什麼要這支（2026-11-17）：
    `securities.holdings`、`funds_cathay`、`total_stock_value`、`securities_breakdown`
    這類同義欄位靠人工清單同步，漏一次就靜默出錯一整週。既有閘門只會「報」，不會「修」，
    而我（agent）每次手動補完還會忘掉下一個 —— 所以把修復也做成工具。

設計原則：
    真值定義只寫在 derived() 一處。因此「檢查」與「修復」不可能分歧；要加新別名，
    就只能在這裡加，順便就被兩邊同時套用。
    只重算「純派生」欄位；total_assets／holdings 明細這類真值一律不動。

用法：
    python tools/resync_aliases.py            # 只檢查（唯讀，預設）
    python tools/resync_aliases.py --fix      # 實際寫回（先備份 snapshot.json.bak-resync）
    python tools/resync_aliases.py --fix --quiet   # cron 用：無事完全靜默
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from json_guard import safe_json_write  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SNAP = REPO / "snapshot.json"


def derived(snap: dict) -> dict:
    """真值 → 所有派生欄位。這裡是唯一真值定義處。"""
    out: dict = {}

    sec = snap.get("securities") or {}
    holds = sec.get("holdings") or []
    if holds:
        sec_total = round(sum(float(h.get("market_value") or 0) for h in holds), 2)
        out["securities.total_market_value"] = sec_total
        # 同日多個別名共用同一真值（歷史遺留，消費端各自讀不同名字）
        for k in ("securities_total_market_value", "securities_market_value",
                  "securities_current_value", "total_stock_value"):
            out[k] = sec_total
        out["securities_breakdown"] = {
            str(h.get("ticker")): round(float(h.get("market_value") or 0), 2) for h in holds
        }

    fb = snap.get("funds_breakdown") or {}
    cathay = fb.get("國泰直購") or {}
    if cathay:
        c = round(sum(float(v) for v in cathay.values()), 2)
        out["funds_cathay"] = c
        out["funds_cathay_market_value"] = c
        # 2026-11-18：國泰直購逐檔明細也是同義欄位（漏同步會讓門檻SoT擋住 sync_all）
        out["funds_cathay_breakdown"] = {k: float(v) for k, v in cathay.items()}

    # 基金別名群（2026-11-18：漏同步會讓 asset_sync 擋住 sync_all）
    if snap.get("funds") is not None:
        _fv = float(snap["funds"])
        for _k in ("fund_market", "fund_market_value", "funds_total", "fund_total_market_value"):
            if _k in snap:
                out[_k] = _fv
    if snap.get("total_assets") is not None and snap.get("total_liabilities") is not None:
        out["net_worth"] = round(float(snap["total_assets"]) - float(snap["total_liabilities"]), 2)

    return out


def _get(snap: dict, dotted: str):
    cur = snap
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _set(snap: dict, dotted: str, val) -> None:
    parts = dotted.split(".")
    cur = snap
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = val


def _same(a, b) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return False
        return all(_same(a[k], b[k]) for k in a)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 0.5
    return a == b


def main() -> int:
    ap = argparse.ArgumentParser(description="同義（派生）欄位重算")
    ap.add_argument("--fix", action="store_true", help="實際寫回（預設只檢查）")
    ap.add_argument("--quiet", action="store_true", help="cron 用：無事時完全靜默")
    a = ap.parse_args()

    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    want = derived(snap)

    diffs = []
    for path, expect in want.items():
        cur = _get(snap, path)
        if not _same(cur, expect):
            diffs.append((path, cur, expect))

    if not diffs:
        if not a.quiet:
            print(f"✅ 派生欄位全部與真值一致（{len(want)} 項）")
        return 0

    def fmt(v):
        if isinstance(v, dict):
            return f"dict({len(v)} 檔)"
        if isinstance(v, (int, float)):
            return f"{float(v):,.0f}"
        return str(v)

    if not a.fix:
        print(f"❌ {len(diffs)} 項派生欄位與真值不一致：")
        for path, cur, expect in diffs:
            print(f"   · {path}: {fmt(cur)} → {fmt(expect)}")
        print("   （--fix 才寫回）")
        return 1

    shutil.copy(SNAP, SNAP.with_suffix(".json.bak-resync"))
    for path, _cur, expect in diffs:
        _set(snap, path, expect)
    fmt_used = safe_json_write(SNAP, snap)

    print(f"✅ 已同步 {len(diffs)} 項派生欄位（備份 snapshot.json.bak-resync）")
    for path, cur, expect in diffs:
        print(f"   · {path}: {fmt(cur)} → {fmt(expect)}")
    print(f"   格式沿用：indent={fmt_used['indent']}｜尾換行={fmt_used['trailing_newline']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
