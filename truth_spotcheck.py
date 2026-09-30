#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""truth_spotcheck.py — 真值回歸抽點（跨報告閘門外的第二層）

背景（2026-09-30 CIO 18:30 審計建議②＋使用者 P0 規格）：
    跨報告閘門驗的是「四份報告彼此講一樣」，不是「與真實一致」。四份報告可以一起錯
    而閘門照樣全綠 → 一致性是必要條件，不是真實性的保證。
    故加一層互證：
      ・固定必抽（每日）：Cash、Debt、US30Y、Restricted Cash —— 這四項是「撐不撐得住」
        與「能不能解凍」的判準原料，錯一個就會產生錯決策。
      ・輪替抽（每日 2 項）：其餘關鍵欄位（保單／證券／基金／水位／信用卡…）。
    輸出 snapshot 值 + as_of + 來源鏈，供人眼與券商截圖／銀行對帳單對點。
    as_of 落後真值日 → 標 ⚠️ 落後（該欄不得用於判定）。

用法：
    python truth_spotcheck.py             # 固定 4 項 + 今日輪替 2 項
    python truth_spotcheck.py --list      # 列出全部可抽欄位
    python truth_spotcheck.py --pick 3 5  # 指定抽第 3、5 項
    python truth_spotcheck.py --all       # 全部輸出（月檢視用）
    python truth_spotcheck.py --fixed     # 只抽固定 4 項
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
MAX_LAG_DAYS = 3          # 假日容忍；超過 → 標落後


def _money(v) -> str:
    try:
        return f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return str(v)


def _lag(ref: str, as_of: str):
    try:
        return (dt.date.fromisoformat(str(ref)[:10]) - dt.date.fromisoformat(str(as_of)[:10])).days
    except Exception:
        return None


def build_pool(snap: dict, st: dict) -> list[dict]:
    """可抽欄位池：每項 = {名稱, 值, as_of, 來源, 對點方式, 固定}"""
    cd = snap.get("cash_detail") or {}
    cl = snap.get("cash_layers") or {}
    rc = snap.get("restricted_cash") or {}
    full = str(snap.get("date") or "—")
    csrc = snap.get("cash_source")
    cash_date = (csrc.get("date") if isinstance(csrc, dict) else csrc) or full
    nav = snap.get("fund_nav_dates") or {}
    rcs = (cl.get("restricted_cash") or {}) if cl else {}
    restricted = rcs.get("total") if rcs else (rc.get("金額") if isinstance(rc, dict) else rc)
    try:
        restricted = float(restricted or 0)
    except (TypeError, ValueError):
        restricted = 0.0
    unrestricted = cl.get("unrestricted_cash")
    if unrestricted is None:
        try:
            unrestricted = float(snap.get("cash_total") or 0) - restricted
        except (TypeError, ValueError):
            unrestricted = 0

    return [
        {
            "名稱": "現金（Cash／可動用）",
            "值": (f"總 {_money(cl.get('cash_total') or snap.get('cash_total'))}"
                   f"／可動用 {_money(unrestricted)}"
                   f"（底線 {_money((cl.get('emergency_cash') or {}).get('金額'))}"
                   f"＋乾粉 {_money(cl.get('dry_powder'))}）"),
            "as_of": cash_date,
            "來源": "snapshot.cash_layers（cash_total − restricted_cash）＋ cash_detail",
            "對點方式": "與 Moneybook 帳戶 CSV／各網銀活存截圖核對；指定用途款不得當普通現金",
            "固定": True,
        },
        {
            "名稱": "負債（Debt）",
            "值": _money(snap.get("total_liabilities")),
            "as_of": full,
            "來源": "snapshot.total_liabilities（房貸＋保單借貸＋質押＋信用卡）",
            "對點方式": "與各銀行貸款餘額截圖／對帳單、保單借款餘額核對",
            "固定": True,
        },
        {
            "名稱": "US30Y（凍結／解凍判準）",
            "值": f"{st.get('last_rate')}%（連續 {st.get('streak')} 日 ≥ 紅線）",
            "as_of": str(st.get("last_date") or "—"),
            "來源": "us30y_state.json（FRED＋Yahoo）；紅線 5.30（us30y_monitor.RED_LINE）",
            "對點方式": "與 FRED DGS30 收盤值核對；as_of 落後 → 該次不得判定解凍",
            "固定": True,
        },
        {
            "名稱": "Restricted Cash（指定用途款）",
            "值": f"{_money(restricted)}（原始撥款 {_money(rc.get('原始撥款') if isinstance(rc, dict) else 0)}）",
            "as_of": str((rc.get("最後更新") if isinstance(rc, dict) else None) or full),
            "來源": "snapshot.restricted_cash（明細逐筆狀態：已清償／執行中／未動用）",
            "對點方式": "與轉帳憑證／App 截圖核對；先註記後入帳（截圖＝真值）",
            "固定": True,
        },
        {
            "名稱": "生活帳戶水位（玉山＋台北富邦）",
            "值": f"玉山 {_money(cd.get('臺幣綜存'))}／富邦 {_money(cd.get('數位活儲'))}",
            "as_of": cash_date,
            "來源": "snapshot.cash_detail（Moneybook 帳戶匯入）",
            "對點方式": "與玉山／富邦 App 餘額截圖核對（安全線各 40,000）",
        },
        {
            "名稱": "保單現值（安聯 A＋B）",
            "值": _money(snap.get("insurance_current_value")),
            "as_of": (nav.get("安聯保單內基金（App）") or full),
            "來源": "snapshot.insurance_current_value（安聯 App 各檔基金市值合計）",
            "對點方式": "與安聯 App「保單現值」截圖核對（含三張保單）",
        },
        {
            "名稱": "證券市值（台股＋複委託）",
            "值": _money(snap.get("securities_total")),
            "as_of": full,
            "來源": "snapshot.securities_total（券商 App 未實現損益頁）",
            "對點方式": "與券商 App「持有股票市值」截圖核對",
        },
        {
            "名稱": "基金市值（鉅亨＋國泰直購）",
            "值": _money(snap.get("fund_market_value")),
            "as_of": f"國泰 {nav.get('國泰直購（富達/聯博/B11）','—')}／鉅亨 {nav.get('鉅亨（一般申購＋自由Pay）','—')}",
            "來源": "snapshot.fund_market_value（funds_cathay＋鉅亨）",
            "對點方式": "與鉅亨／國泰 App 庫存截圖核對",
        },
        {
            "名稱": "基金質押借款餘額／利率",
            "值": f"{_money(snap.get('fund_pledge_loan'))} @ {snap.get('fund_pledge_rate')}",
            "as_of": full,
            "來源": "snapshot.fund_pledge_loan（國泰撥款 9/29 590 萬@2.65%）",
            "對點方式": "與國泰世華 App 借款餘額／撥款通知書核對",
        },
        {
            "名稱": "信用卡待繳",
            "值": _money(snap.get("cc_liability")),
            "as_of": full,
            "來源": "snapshot.cc_liability（Moneybook 各卡最新截止日）",
            "對點方式": "與各卡 App 帳單金額核對（全自動扣繳，只查餘額是否足夠）",
        },
        {
            "名稱": "總資產",
            "值": _money(snap.get("total_assets")),
            "as_of": full,
            "來源": "snapshot.total_assets（四源同步）",
            "對點方式": "與券商／銀行 App 各帳戶總額截圖逐項核對",
        },
    ]


def _emit(it: dict, idx: int, ref: str) -> None:
    lag = _lag(ref, it["as_of"]) if it.get("as_of") not in (None, "", "—") else None
    warn = " ⚠️ 落後（該欄不得用於判定）" if (lag is not None and lag > MAX_LAG_DAYS) else ""
    print(f"\n[{idx}] {it['名稱']}{warn}")
    print(f"    值      ：{it['值']}")
    print(f"    as_of   ：{it['as_of']}" + (f"（落後 {lag} 天）" if lag is not None else ""))
    print(f"    來源鏈  ：{it['來源']}")
    print(f"    對點方式：{it['對點方式']}")


def main() -> int:
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    try:
        st = json.loads((BASE / "us30y_state.json").read_text(encoding="utf-8"))
    except Exception:
        st = {}
    pool = build_pool(snap, st)
    today = date.today()
    ref = str(snap.get("date") or today.isoformat())

    argv = sys.argv[1:]
    if "--list" in argv:
        for i, it in enumerate(pool, 1):
            print(f"{i:2d}. {'[固定] ' if it.get('固定') else '       '}{it['名稱']}｜{it['值']}｜as_of {it['as_of']}")
        return 0

    fixed = [i for i, it in enumerate(pool) if it.get("固定")]
    if "--pick" in argv:
        idxs = [int(x) - 1 for x in argv[argv.index("--pick") + 1:] if x.isdigit()]
    elif "--all" in argv:
        idxs = list(range(len(pool)))
    elif "--fixed" in argv:
        idxs = fixed
    else:
        rot = [i for i in range(len(pool)) if i not in fixed]
        start = today.toordinal() % len(rot) if rot else 0
        idxs = fixed + [rot[(start + k) % len(rot)] for k in range(min(2, len(rot)))]

    print(f"🔍 真值回歸抽點（{today.isoformat()}｜真值日 {ref}）")
    print(f"口徑：跨報告閘門只驗『報告彼此一致』；本抽點驗『與真實一致』→ 抽固定 4 項"
          f"（Cash／Debt／US30Y／Restricted Cash）＋輪替 {max(0, len(idxs) - len(fixed))} 項")
    for i in idxs:
        if 0 <= i < len(pool):
            _emit(pool[i], i + 1, ref)
    print("\n不符 → 登錄 error_register.md 並回報；相符 → 無需動作。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
