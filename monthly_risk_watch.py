#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""monthly_risk_watch.py — 月累積報酬率警戒（相對口徑）＋影子模式紀錄

2026-11-05 使用者裁決（三項）：
  ① 虧損警戒採**相對百分比**：月累積報酬率 -1%／-2%／-3% 三級（不用固定金額，
     不受資產規模變化影響，2,000萬／3,000萬套同一條規則）。
  ② 先跑 **3 個月影子模式**（至 2027-02-05）：只顯示燈號，不改 G1/G2/G3、不自動減碼／解凍、
     每日保存計算結果與觸發原因，月度檢討誤報漏報。
  ③ 儀表板第一屏（「財務安全護城河水位」上方）顯示：本月損益與報酬率、當前燈號、
     距下一級差距、當日投資風險裁示。

四項執行限制（同批裁決）：
  * 15 日滾動損益（-596,522／-2.20%）≠ 月累積損益，只能當歷史風險校準參考，不得冒充 MTD。
  * 分母固定口徑：投資組合期初淨值，外部投入／提領以時間加權（TWR）處理。
  * 影子模式即使未觸發也保存每日報酬率、燈號、資料品質。
  * **資料不完整不得顯示綠燈** → 灰燈「資料不足」。

計算來源（禁自算、禁第二套引擎）：
  一律委派 `performance_core.monthly_performance()`（月度唯一入口）：
   - 走勢報酬率：該月 `twr.overall`（daily chain-linked、flow 於日初計入分母、配息加回）
   - 金額變動：該月 `net`（帳面淨變動，含配息／費用；與報酬率口徑不同，顯示時必須分開標示）
   - 不可用時退回 `rate`（非 TWR）並把品質降級；兩者皆不可用 → 灰燈、不裁示。

裁決文字僅為**提示**：影子期內不得據此交易；投資凍結令與再平衡授權規則不受影響。
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent

# ── 規則（單一來源；日報與儀表板都讀這裡）─────────────────────────────
LEVELS = (
    # (門檻%, 代碼, 燈號, 標籤)
    (-3.0, "severe", "🔴", "紅燈｜重大回撤"),
    (-2.0, "alert", "🟠", "橘燈｜全面風險審查"),
    (-1.0, "watch", "🟡", "黃燈｜檢查損失來源"),
)
LEVEL_OK = ("green", "🟢", "綠燈｜正常")
LEVEL_UNKNOWN = ("unknown", "⚪", "灰燈｜資料不足")

# 影子模式：2026-11-05 起 3 個月（寫死區間是刻意的——期滿須人工裁決才可能轉正式）
SHADOW_START = "2026-11-05"
SHADOW_UNTIL = "2027-02-05"
SHADOW_LOG = BASE / "data" / "monthly_risk_shadow.jsonl"


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def rule_table() -> list:
    """給文件／卡片用的規則表（避免各處重複寫 -1/-2/-3）。"""
    return [{"門檻": thr, "代碼": code, "燈號": icon, "標籤": lab} for thr, code, icon, lab in LEVELS]


def classify(ret_pct) -> tuple:
    """月累積報酬率(%) → (代碼, 燈號, 標籤)。ret_pct 不可用 → 灰燈。"""
    r = _num(ret_pct)
    if r is None:
        return LEVEL_UNKNOWN
    for thr, code, icon, lab in LEVELS:      # -3 先比、再 -2、再 -1
        if r <= thr:
            return (code, icon, lab)
    return LEVEL_OK


def next_gap(ret_pct) -> dict:
    """距下一級警戒還差幾 pp（已觸發則回該級本身）。"""
    r = _num(ret_pct)
    if r is None:
        return {"next": None, "gap_pp": None, "text": "資料不足，無法計算"}
    # 由淺到深找「還沒跌到、且最接近」的一級（LEVELS 是深→淺，故反序）
    for thr, code, icon, lab in reversed(LEVELS):
        if r > thr:
            return {"next": thr, "code": code, "icon": icon, "label": lab,
                    "gap_pp": round(r - thr, 2),
                    "text": f"再跌 {abs(round(r - thr, 2)):.2f}pp 觸 {icon} {lab.split('｜')[1]}"}
    return {"next": LEVELS[0][0], "code": LEVELS[0][1], "gap_pp": 0.0,
            "text": "已達最深一級（紅燈）"}


def stance(ret_pct, quality: str) -> str:
    """當日投資風險裁示（提示、非指令；影子期內不得據此交易）。"""
    if quality != "ok":
        return "資料不足 → 不裁示（先補齊估值來源）"
    code, _icon, _lab = classify(ret_pct)
    if code == "severe":
        return "防守｜提出減碼檢視清單（需你核准；不自動執行）"
    if code == "alert":
        return "防守準備｜停止新增、檢視集中度（不自動賣出）"
    if code == "watch":
        return "觀察｜暫緩加碼，追蹤損失來源"
    return "HOLD｜維持不動"


def in_shadow(today=None) -> bool:
    d = (today or dt.date.today()).isoformat() if not isinstance(today, str) else today[:10]
    return SHADOW_START <= d <= SHADOW_UNTIL


def assess(snap: dict, db=None, today=None) -> dict:
    """當月風險摘要（唯一入口）。回傳 dict，永不拋例外（缺資料＝灰燈）。"""
    today = today or dt.date.today()
    if isinstance(today, str):
        today = dt.date.fromisoformat(today[:10])
    ym = today.strftime("%Y-%m")
    own_db = False
    if db is None:
        try:
            db = sqlite3.connect(str(BASE / "dragon_assets.db"))
            own_db = True
        except Exception:
            db = None
    try:
        import performance_core as pc
        adjust = json.loads((BASE / "investment_performance_adjust.json").read_text(encoding="utf-8"))
        # 與績效報告完全同源：同一份月份清單、同一個 monthly_history 入口
        # （build_performance_monthly.py 亦如此），避免日報/績效頁各算一個數。
        mks = sorted(k for k in adjust if len(k) == 7 and k[4] == "-")
        if ym not in mks:
            mks.append(ym)
        hist = pc.monthly_history(mks, snap=snap, adjust_all=adjust, db=db, today=today)
        row = next((r for r in hist.get("months", []) if r.get("month") == ym), None)
        if row is None:
            raise LookupError(f"{ym} 不在月度績效序列中")
    except Exception as e:                   # noqa: BLE001
        return {"ym": ym, "ret_pct": None, "quality": "insufficient",
                "quality_note": "資料不足",
                "reason": f"月度績效不可用（{type(e).__name__}: {e}）",
                "level": LEVEL_UNKNOWN[0], "icon": LEVEL_UNKNOWN[1], "label": LEVEL_UNKNOWN[2],
                "net_twd": None, "gap": next_gap(None), "stance": stance(None, "insufficient"),
                "shadow": in_shadow(today), "asof": None}
    finally:
        if own_db and db is not None:
            try:
                db.close()
            except Exception:
                pass

    twr = (row.get("twr") or {})
    rate = _num(row.get("rate"))
    ret_pct, quality, reason = None, "insufficient", ""
    if twr.get("reliable") and _num(twr.get("twr")) is not None:
        ret_pct, quality = round(_num(twr["twr"]) * 100, 2), "ok"
        reason = "TWR（daily chain-linked、flow 日初計入分母、含配息與匯率）"
    elif _num(twr.get("twr")) is not None:
        ret_pct, quality = round(_num(twr["twr"]) * 100, 2), "degraded"
        reason = "TWR 未達可靠門檻（" + str(twr.get("reason") or "點數不足") + "）→ 僅參考"
    elif rate is not None:
        ret_pct, quality = round(rate * 100, 2), "degraded"
        reason = "TWR 不可用（" + str(twr.get("reason") or "日估值不足") + "）→ 以月內淨值變動率顯示"
    else:
        reason = "TWR 與淨值變動率皆不可用"

    code, icon, label = classify(ret_pct)
    return {
        "ym": ym,
        "ret_pct": ret_pct,
        "quality": quality,                 # ok / degraded / insufficient
        "quality_note": {"ok": "時間加權、含配息與匯率（TWR）",
                         "degraded": "降級：非時間加權（僅參考，不作為裁決依據）",
                         "insufficient": "資料不足"}[quality],
        "reason": reason,
        "net_twd": _num(row.get("net")),     # 帳面淨變動（含配息/費用）≠ 報酬率
        "level": code, "icon": icon, "label": label,
        "gap": next_gap(ret_pct),
        "stance": stance(ret_pct, quality),
        "shadow": in_shadow(today),
        "asof": row.get("asof") or snap.get("date") or today.isoformat(),
        "mv0": _num(row.get("mv0")),
        "days": row.get("days"),
        "usable": row.get("usable"),
        "by_class": row.get("twr_by_class") or {},
    }


def stress(snap: dict, shocks=(-5.0, -10.0)) -> list:
    """資產價格衝擊情境（唯讀推算，不是預測）。

    只讓「投資部位」隨衝擊縮水；現金、房產不動（現金不因帳面虧損而減少，
    故不以跑道天數誤導）。質押池假設與大盤同幅下跌 → 同步換算 LTV 與維持率。
    """
    def _f(v):
        return _num(v) or 0.0

    total = _f(snap.get("total_assets"))
    cash = _f(snap.get("cash_total"))
    invest = max(0.0, total - cash)
    pl = snap.get("cathay_pledge_0911") or {}
    loan = _f(snap.get("fund_pledge_loan"))
    pool = pl.get("擔保池") or {}
    coll = _f(pool.get("合計")) or _f((pl.get("擔保品明細") or {}).get("合計"))
    out = []
    for s in shocks:
        d = invest * (s / 100.0)
        row = {"shock_pct": s, "assets_delta": round(d, 0),
               "total_after": round(total + d, 0),
               "total_delta_pct": round(d / total * 100, 2) if total else None}
        if loan and coll:
            pool_after = coll * (1 + s / 100.0)
            row["ltv_after"] = round(loan / pool_after * 100, 2)
            row["maintenance_after"] = round(pool_after / loan * 100, 1)
            # 回內部停止線 53% 需還多少（正數＝需還本）
            row["repay_to_53"] = round(max(0.0, loan - 0.53 * pool_after), 0)
        out.append(row)
    return out

def log_daily(result: dict, path: Path | None = None) -> None:
    """影子模式紀錄：即使未觸發也寫（每日一筆，同日覆寫）。"""
    p = path or SHADOW_LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {k: result.get(k) for k in
           ("ym", "ret_pct", "quality", "level", "label", "net_twd", "asof", "shadow", "stance")}
    row["date"] = dt.date.today().isoformat()
    row["gap"] = (result.get("gap") or {}).get("text")
    keep = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                old = json.loads(line)
            except Exception:
                continue
            if old.get("date") != row["date"]:
                keep.append(json.dumps(old, ensure_ascii=False))
    keep.append(json.dumps(row, ensure_ascii=False))
    p.write_text("\n".join(keep) + "\n", encoding="utf-8")


def _main() -> int:
    """CLI：python monthly_risk_watch.py [--backtest] [--json]"""
    import sys
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    if "--backtest" in sys.argv:
        import performance_core as pc
        adjust = json.loads((BASE / "investment_performance_adjust.json").read_text(encoding="utf-8"))
        db = sqlite3.connect(str(BASE / "dragon_assets.db"))
        try:
            mks = sorted(k for k in adjust if len(k) == 7 and k[4] == "-")
            today = dt.date.today()
            cur = today.strftime("%Y-%m")
            if cur not in mks:
                mks.append(cur)
            h = pc.monthly_history(mks, snap=snap, adjust_all=adjust, db=db, today=today)
        finally:
            db.close()
        print(f"歷史回測（口徑：performance_core.monthly_history；樣本 {len(h['months'])} 個月）")
        for r in h["months"]:
            twr = (r.get("twr") or {}).get("twr")
            pct = round(_num(twr) * 100, 2) if _num(twr) is not None else (
                round(_num(r.get("rate")) * 100, 2) if _num(r.get("rate")) is not None else None)
            code, icon, label = classify(pct)
            print(f"  {r['month']} role={r['role']:<16} usable={r['usable']:<14} "
                  f"net={(_num(r.get('net')) or 0):>12,.0f} ret={('—' if pct is None else f'{pct:+.2f}%'):>8} "
                  f"→ {icon} {label}")
        return 0
    res = assess(snap)
    log_daily(res)
    if "--json" in sys.argv:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print(f"本月投資風險摘要（{res['ym']}）")
        print(f"  報酬率 {res['ret_pct']}%｜品質 {res['quality']}（{res['quality_note']}）")
        print(f"  帳面淨變動 {res['net_twd']}｜{res['icon']} {res['label']}")
        print(f"  距下一級：{res['gap']['text']}")
        print(f"  裁示：{res['stance']}｜影子模式 {res['shadow']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
