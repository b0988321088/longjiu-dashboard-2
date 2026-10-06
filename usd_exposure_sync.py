#!/usr/bin/env python3
"""美元曝險單一計算層（2026-10-07 使用者裁決：改由腳本自動產生，廢除手動維護）。

背景：usd_exposure_monitor.current 原為人工維護 → 停在 2026-09-13（美股桶 24.5%），
與引擎現值（10/06 為 38.9%）脫節，合計 59.0% 低估；沒有任何程式會更新它。
本模組把「算法」變成程式：每日必跑路徑（build_penetration_report.py）呼叫，
亦可用 `python usd_exposure_sync.py` 單獨重算。

口徑（沿用 2026-09-14 使用者核准定案，僅改為自動計算）：
    美元曝險 = 美股桶（penetration.actual_twd.美股市值型成長）
             + 美元計價基金（非美股桶，B11 已歸防守/債券桶 → 只計一次）
             + 保單美元債券（保單 A/B 基金債券部位＋第一金債券部位 ＝ _meta.ins_bonds）
             + 美元定存 + 美元債券梯
門檻 = usd_exposure_monitor.threshold（2026-09-12 裁示 50→60）。

寫入單一真值：
    snapshot.usd_exposure_monitor.current.{updated_at, 美股桶, 美元計價基金（非美股桶）,
        保單美元債券, 美元定存, 美元債券梯, 合計, 狀態, 口徑}
    snapshot.usd_exposure_pct
"""
import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"

# 美元計價基金（非美股桶）名稱關鍵字 — 這些部位已歸防守/債券桶，但仍是美元曝險
_USD_FUND_HINTS = ("貝萊德智慧數據收益成長",)


def _num(v):
    if isinstance(v, dict):
        v = v.get("value")
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _usd_fund_value(snap: dict) -> float:
    """美元計價基金（非美股桶）市值：跨 breakdown 字典找同一檔，只取一次（禁重複計）。"""
    for key in ("funds_cathay_breakdown", "fund_breakdown_cathay", "funds_breakdown"):
        blk = snap.get(key) or {}
        found = 0.0
        for grp, items in blk.items():
            pool = items if isinstance(items, dict) else {grp: items}
            for name, val in pool.items():
                if any(h in str(name) for h in _USD_FUND_HINTS):
                    found = max(found, _num(val))
        if found:
            return found
    return 0.0


def compute_usd_exposure(snap: dict, pen: dict = None, total: float = None) -> dict:
    """回傳 {美股桶, 美元計價基金（非美股桶）, 保單美元債券, 美元定存, 美元債券梯, 合計, 狀態, ...}（pct）。"""
    if pen is None:
        from update_all import calc_penetration
        pen = calc_penetration(snap["cash_total"], snap["insurance_total"],
                               snap["securities_total_market_value"], snap["fund_market"], snap=snap)
    if total is None:
        total = _num(snap.get("total_assets"))
    mon = snap.get("usd_exposure_monitor") or {}
    prev = mon.get("current") or {}
    thr = float(mon.get("threshold") or 60)

    us_bucket = float(pen.get("美股市值型成長") or 0)
    usd_funds = _usd_fund_value(snap)
    ins_bonds = float((pen.get("_meta") or {}).get("ins_bonds") or 0)
    # 非引擎可推導項（定存／債券梯）沿用既有真值，缺則 0（不得捏造）
    usd_td = _num(prev.get("美元定存"))
    usd_ladder = _num(prev.get("美元債券梯"))

    def pct(x):
        return round(x / total * 100, 1) if total else 0.0

    out = {
        "美股桶": pct(us_bucket),
        "美元計價基金（非美股桶）": pct(usd_funds),
        "保單美元債券": pct(ins_bonds),
        "美元定存": pct(usd_td),
        "美元債券梯": pct(usd_ladder),
    }
    total_pct = round(sum(out.values()), 1)
    out["合計"] = total_pct
    out["_twd_amounts"] = {"美股桶": us_bucket, "美元計價基金": usd_funds, "保單美元債券": ins_bonds,
                           "美元定存": usd_td, "美元債券梯": usd_ladder, "分母_總資產": total}
    if total_pct >= thr:
        out["狀態"] = (f"🟡 {total_pct}% ≥ 門檻 {thr:.0f}%（僅顯示：不觸發資產調整；"
                      f"政策門檻待 10 月戰略檢討）")
    elif total_pct >= thr - 5:
        out["狀態"] = f"🟡 接近上限 {total_pct}% ≤ {thr:.0f}%（緩衝 {round(thr - total_pct, 1)}pp）"
    else:
        out["狀態"] = f"🟢 {total_pct}% < {thr:.0f}%"
    out["門檻"] = thr
    # 2026-10-07 使用者裁決（只顯示、不觸發）：美元曝險自動化＝真值回歸，不是重新制定資產政策。
    # 68~70% 為新觀測結果，但 60/65/70 三級門檻與 2026-09-12「放寬到 60」的政策存在衝突 →
    # 不得讓程式把政策衝突直接轉成資產操作。故一律標記 advisory_only，門檻與口徑本輪均不動。
    out["advisory_only"] = True
    out["政策提示"] = ("2026-10-07 裁決：僅顯示，不觸發「不再增加美元資產」；"
                    "門檻 60/65/70 與 9/12 放寬政策之衝突留待 10 月戰略檢討。")
    return out


def sync_usd_exposure(snap: dict, pen: dict = None, total: float = None, verbose: bool = True) -> dict:
    """就地更新 snap['usd_exposure_monitor']['current'] 與 snap['usd_exposure_pct']（不寫檔）。"""
    cur = compute_usd_exposure(snap, pen=pen, total=total)
    mon = snap.setdefault("usd_exposure_monitor", {})
    prev = mon.get("current") or {}
    new = {
        "updated_at": date.today().isoformat(),
        "美股桶": cur["美股桶"],
        "美元計價基金（非美股桶）": cur["美元計價基金（非美股桶）"],
        "保單美元債券": cur["保單美元債券"],
        "美元定存": cur["美元定存"],
        "美元債券梯": cur["美元債券梯"],
        "合計": cur["合計"],
        "門檻": cur["門檻"],
        "狀態": cur["狀態"],
        "口徑": "引擎自動產生（usd_exposure_sync.py；build_penetration_report 每日呼叫）— 2026-10-07 起廢除手動維護",
        "金額明細": cur["_twd_amounts"],
    }
    if prev.get("口徑校正_20260914"):
        new["口徑校正_20260914"] = prev["口徑校正_20260914"]
    mon["current"] = new
    # 2026-10-07 裁決：advisory_only 為消費端唯一判準（只顯示、不觸發資產調整）
    mon["advisory_only"] = bool(cur.get("advisory_only"))
    mon["政策提示"] = cur.get("政策提示")
    snap["usd_exposure_pct"] = cur["合計"]
    if verbose:
        print("  美元曝險 " + "＋".join(f"{k} {v}%" for k, v in new.items()
              if k in ("美股桶", "美元計價基金（非美股桶）", "保單美元債券", "美元定存", "美元債券梯"))
              + f" = {new['合計']}%（門檻 {new['門檻']:.0f}%）")
    return new


def main():
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    sync_usd_exposure(snap, verbose=True)
    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print("  ✅ 已寫入 snapshot.usd_exposure_monitor.current ＋ usd_exposure_pct")


if __name__ == "__main__":
    main()
