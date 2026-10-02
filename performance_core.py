# -*- coding: utf-8 -*-
"""performance_core.py — 投資績效的【唯一計算層】（INC-282 A 案 Task 1，2026-10-03）

目的：消滅「同一月份、多份報表各自算 → 出現三套數字」。
所有報表（mtd_performance／investment_performance／彙整月報／動態月報）一律呼叫本模組，
不得自行重算。本檔案是純計算層：**不讀檔、不寫檔**（資料由呼叫端傳入），便於單獨驗證。

## 唯一公式（使用者 2026-10-03 裁示）
    perf_net(ym) = Σ_class 市值變化 + Σ_class 配息實收 − Σ 投資利息 − Σ 申購手續費

明確排除（不得混入）：薪資、租金、生活消費、借款本金流（撥款／清償）、資金過境（指定款移轉）、
淨資產變化、專案收入（另列，不進 net）。理由：淨資產變化會被融資時點主宰，不是績效。

## 口徑（已結束月份；當月不適用 — 當月沿用 MTD 即時計算）
以校正檔 `investment_performance_adjust.json[ym]` 為準：
    市值變化／新增投入／資金來源／估值更新／手續費／利息／專案收入／市值可靠
- 配息：校正檔 `配息[類]` 優先；缺該類時由 `snapshot.dividend_records[ym]` 自動分類
        （分類器 `classify_dividend` → `dividend_caliber.bucket_of`，單一口徑）
- 市值變化：校正檔優先；缺該類且 db 有月初基準時，以 `帳面變化 − 新增投入 − 估值更新` 推導
- 利息：校正檔 `利息` 各項合計（本口徑**不含**國泰轉貸／元大質押，屬另案 — 不得順手改）

## 缺件處理（no-hardcode-mandate：缺值不得靜默歸零）
手續費／利息／市值變化缺值 → 計 0 但列入 `missing[]`，由報表明示來源，不得假裝成真值。
"""
from __future__ import annotations

import datetime as dt

from dividend_caliber import bucket_of

CLASS_KEYS = ["股票", "基金", "保單"]

# 配息分類顯示對照（bucket_of 的分類代碼 → 報表類別）；單一口徑，勿在他處複製
_MAP = {"etf": "股票", "oneoff": "股票", "ins": "保單", "fund": "基金"}


def classify_dividend(name: str) -> str:
    """配息 key → 類別（委派 `dividend_caliber.bucket_of`，單一口徑）。"""
    return _MAP[bucket_of(name)]


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def dividend_totals(snap: dict, ym: str) -> dict:
    """`snapshot.dividend_records[ym]` → {類別: 實收配息}（同一條自動分類）。"""
    out = {c: 0.0 for c in CLASS_KEYS}
    for k, v in ((snap.get("dividend_records") or {}).get(ym) or {}).items():
        if isinstance(v, (int, float)):
            out[classify_dividend(k)] += float(v)
    return out


def month_bounds(ym: str) -> tuple[dt.date, dt.date, dt.date]:
    """ym → (月初, 月末, 上月末)。"""
    y, m = int(ym[:4]), int(ym[5:7])
    mstart = dt.date(y, m, 1)
    nxt = dt.date(y + (1 if m == 12 else 0), (1 if m == 12 else m + 1), 1)
    return mstart, nxt - dt.timedelta(days=1), mstart - dt.timedelta(days=1)


def _db_asset_on(db, day: str):
    """db 該日（含）以前最後一筆 (date, securities, funds, insurance)。"""
    return db.execute(
        "SELECT date, securities, funds, insurance FROM assets "
        "WHERE date <= ? ORDER BY date DESC LIMIT 1", (day,)).fetchone()


def monthly_performance(ym: str, *, snap: dict, adjust_all: dict, db=None,
                        reliable: bool | None = None) -> dict:
    """唯一計算層：回傳某月投資績效（已結束月份口徑）。

    回傳 dict：
      rows[]     每類 {c, mkt, invest, src, upd, gross, div, fee, pnl, basis}
      grand      Σ pnl（三類損益合計，未扣利息）
      div/fee    配息合計／手續費合計
      interest   投資利息合計（校正檔 `利息`）
      net        grand − interest ＝ canonical 投資績效
      project    專案收入（另列，不進 net）
      missing[]  缺件欄位（手續費／利息／市值變化）→ 報表須明示，不得靜默
    """
    a = (adjust_all.get(ym) or {})
    rel = bool(a.get("市值可靠", True)) if reliable is None else bool(reliable)
    adj_mv = a.get("市值變化") or {}
    adj_inv = a.get("新增投入") or {}
    adj_src = a.get("資金來源") or {}
    adj_div = a.get("配息") or {}
    adj_fee = a.get("手續費") or {}
    adj_interest = a.get("利息") or {}
    updates = [u for u in (a.get("估值更新") or []) if isinstance(u, dict)]

    auto_div = dividend_totals(snap, ym)

    # db 起訖帳面（推導市值變化用；無 db 或無月初基準 → None）
    mv0 = mv1 = None
    if db is not None and rel:
        _, month_end, prev_end = month_bounds(ym)
        try:
            end_row = _db_asset_on(db, month_end.isoformat())
            start_row = _db_asset_on(db, prev_end.isoformat())
        except Exception:  # noqa: BLE001 — db 不可用時不阻擋，只是無法推導
            end_row = start_row = None
        if end_row:
            mv1 = {"股票": _num(end_row[1]), "基金": _num(end_row[2]), "保單": _num(end_row[3])}
            if start_row:
                mv0 = {"股票": _num(start_row[1]), "基金": _num(start_row[2]), "保單": _num(start_row[3])}

    rows, missing = [], []
    for c in CLASS_KEYS:
        inv = _num(adj_inv.get(c, 0))
        src = adj_src.get(c, "")
        upd = sum(_num(u.get("金額")) for u in updates
                  if (u.get("類") or u.get("類別")) == c)
        div = _num(adj_div.get(c, auto_div.get(c, 0)))
        fee = _num(adj_fee.get(c, 0))
        if not rel:
            gross = mkt = 0.0
            basis = "無月初基準，不計"
            missing.append(f"{c}市值變化")
        elif c in adj_mv:
            mkt = _num(adj_mv[c])
            gross = mkt + inv
            basis = "校正檔指定"
        elif mv0 and mv1:
            gross = mv1[c] - mv0[c]
            mkt = gross - inv - upd
            basis = "推導"
        else:
            gross = mkt = 0.0
            basis = "無月初基準，不計"
            missing.append(f"{c}市值變化")
        rows.append({"c": c, "mkt": mkt, "invest": inv, "src": src, "upd": upd,
                     "gross": gross, "div": div, "fee": fee,
                     "mv0": (mv0[c] if mv0 else None),
                     "pnl": mkt + div - fee, "basis": basis})

    if not adj_fee:
        missing.append("手續費")
    if not adj_interest:
        missing.append("利息")

    grand = sum(r["pnl"] for r in rows)
    interest = sum(_num(v) for v in adj_interest.values())
    return {
        "month": ym,
        "reliable": rel,
        "rows": rows,
        "grand": grand,
        "div": sum(r["div"] for r in rows),
        "fee": sum(r["fee"] for r in rows),
        "interest": interest,
        "interest_by": dict(adj_interest),
        "interest_registered": bool(adj_interest),
        "net": grand - interest,
        "project": _num(a.get("專案收入", 0)),
        "missing": missing,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 歷史視圖（2026-10-03 使用者裁示）：月份「角色／可用性」與聚合的唯一判準
# 鐵則：7/8/9/10 月屬於哪一區（Baseline／歷史參考／資本基準月／基準後）一律由本層決定，
#       報表端（HTML/JS）不得自行用月份字串判斷 → 防止前端人工判斷漂移。
# 角色來源＝校正檔該月 `角色` 欄位（資料宣告、可審查）；市值不可靠則強制 legacy。
# ─────────────────────────────────────────────────────────────────────────────

ROLE_LEGACY = "legacy"                    # 市值不可靠：僅現金型 → Baseline／不可比
ROLE_REFERENCE = "reference"              # 資本結構改變前的歷史參考月（非正式基準）
ROLE_CAPITAL_BASELINE = "capital_baseline"  # 新資本基準月（結構性變化後的第一個完整月）
ROLE_POST_BASELINE = "post_baseline"      # 基準月之後（含當月進行中）

USE_COMPLETE = "complete"                 # 可進入累計／平均
USE_IN_PROGRESS = "in_progress"           # 當月未結束 → 獨立顯示
USE_NOT_COMPARABLE = "not_comparable"     # 不可比 → 只展示，不進任何聚合

USABLE_LABEL = {
    USE_COMPLETE: "完整月",
    USE_IN_PROGRESS: "進行中",
    USE_NOT_COMPARABLE: "不可比",
}
ROLE_LABEL = {
    ROLE_LEGACY: "Baseline／不可比",
    ROLE_REFERENCE: "歷史參考／非正式基準",
    ROLE_CAPITAL_BASELINE: "⭐ 新資本基準月",
    ROLE_POST_BASELINE: "基準後",
}


def declared_baseline_month(adjust_all: dict):
    """校正檔中宣告為資本基準月的月份（可多筆時取最新）；無宣告 → None。"""
    return max((ym for ym in adjust_all
                if len(ym) == 7 and ((adjust_all.get(ym) or {}).get("角色") == ROLE_CAPITAL_BASELINE)),
               default=None)


def month_role(res: dict, meta: dict, *, baseline_month=None, today: dt.date | None = None) -> str:
    """月份角色（唯一判準）：市值不可靠 → legacy；宣告基準月 → capital_baseline；
    基準月之後（含當月）→ post_baseline；其餘 → reference。"""
    today = today or dt.date.today()
    declared = (meta or {}).get("角色")
    if not res.get("reliable", True) or declared == ROLE_LEGACY:
        return ROLE_LEGACY
    if baseline_month and res.get("month") == baseline_month:
        return ROLE_CAPITAL_BASELINE
    if baseline_month and res.get("month") > baseline_month:
        return ROLE_POST_BASELINE
    return ROLE_REFERENCE


def month_usability(res: dict, *, today: dt.date | None = None) -> str:
    """可否進入累計：市值不可靠 → not_comparable；當月 → in_progress；其餘 → complete。"""
    today = today or dt.date.today()
    if not res.get("reliable", True):
        return USE_NOT_COMPARABLE
    if res.get("month") == today.strftime("%Y-%m"):
        return USE_IN_PROGRESS
    return USE_COMPLETE


def estimate_interest(adjust_all: dict, exclude: str) -> tuple[float, str]:
    """最近一個「已登錄利息」的月份 → (利息合計, 來源月份)；無則 (0.0, "")。

    用途：當月利息尚未登錄時，報表可標示「同口徑暫估」——來源必須是可追溯的登錄值，
    不得在報表端寫死數字（no-hardcode-mandate）。
    """
    for ym in sorted((k for k in adjust_all if len(k) == 7 and k < exclude), reverse=True):
        interest = (adjust_all[ym] or {}).get("利息") or {}
        if interest:
            return sum(_num(v) for v in interest.values()), ym
    return 0.0, ""


def monthly_history(months, *, snap: dict, adjust_all: dict, db=None,
                    today: dt.date | None = None) -> dict:
    """歷史月度績效（報表與閘門共用的唯一入口）。

    - `role`  報告角色（legacy／reference／capital_baseline／post_baseline）
    - `usable` 是否可進入聚合（complete／in_progress／not_comparable）
    - `post_accum` 基準後累計：**只計「基準月之後且已完成」的月份**
      （基準月本身、歷史參考月、Baseline 不可比月、進行中月一律不列入）
    """
    today = today or dt.date.today()
    baseline = declared_baseline_month(adjust_all)
    out = []
    for ym in months:
        res = monthly_performance(ym, snap=snap, adjust_all=adjust_all, db=db)
        meta = adjust_all.get(ym) or {}
        role = month_role(res, meta, baseline_month=baseline, today=today)
        usable = month_usability(res, today=today)
        mstart, mend, _ = month_bounds(ym)
        days = (mend - mstart).days + 1 if usable != USE_IN_PROGRESS \
            else (min(today, mend) - mstart).days + 1
        est, est_from = (None, "")
        if usable == USE_IN_PROGRESS and not res["interest_registered"]:
            est_v, est_from = estimate_interest(adjust_all, ym)
            est = est_v if est_from else None
        mv_total0 = sum(r["mv0"] for r in res["rows"] if r.get("mv0")) or None
        out.append({
            "month": ym,
            "label": ym.replace("-", "/"),
            "role": role,
            "role_label": ROLE_LABEL[role],
            "usable": usable,
            "usable_label": USABLE_LABEL[usable],
            "is_current": usable == USE_IN_PROGRESS,
            "days": days,
            "reliable": res["reliable"],
            "rows": res["rows"],
            "grand": res["grand"],
            "div": res["div"],
            "fee": res["fee"],
            "interest": res["interest"],
            "interest_registered": res["interest_registered"],
            "interest_est": est,
            "interest_est_from": est_from,
            "net": res["net"],
            "net_same_caliber": (res["net"] - est) if est is not None else res["net"],
            "net_per_day": (res["net"] / days) if days else 0.0,
            "mv_total0": mv_total0,
            "rate": (sum(r["mkt"] for r in res["rows"]) / mv_total0) if mv_total0 else None,
            "missing": res["missing"],
            "project": res["project"],
        })
    post = [m for m in out if m["role"] == ROLE_POST_BASELINE and m["usable"] == USE_COMPLETE]
    total = sum(m["net"] for m in post)
    return {
        "months": out,
        "baseline_month": baseline,
        "post_months": [m["month"] for m in out if m["role"] == ROLE_POST_BASELINE],
        "post_accum": {
            "start": post[0]["month"] if post else (baseline or None),
            "n": len(post),
            "sum": total,
            "avg": (total / len(post)) if post else 0.0,
        },
        # 僅供「歷史參考」展示，永不進入 post_accum
        "reference_months": [m["month"] for m in out if m["role"] in (ROLE_REFERENCE, ROLE_LEGACY)],
    }
