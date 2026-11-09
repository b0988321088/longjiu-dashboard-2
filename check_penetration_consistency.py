#!/usr/bin/env python3
"""check_penetration_consistency.py — 穿透一致性檢查（P2）
比對 日報 / 穿透報告 / 緊急應變 三檔是否包含 snapshot 的穿透真值。
任一報表缺少真值 → 印出差異並回傳 exit code 1（阻止推送）。

預設檢查「當天產出組」；2026-09-04 起不再用 snapshot.date：
snapshot 的 date = 資料日可能停留多日 → 檢查器天天回頭查舊檔，
舊檔不會更新 → 同一條 ❌ 每日重複推 = 噪音（8/25 原則：重複狀態通知不推）。
緊急應變只在應變日產出（台股 13:00 / 美股 21:30 觸發）→ 缺檔為正常，不擋；
只有「存在但內容不符」才算失敗。

用法：python check_penetration_consistency.py [date] [--snapshot PATH]

2026-11-09 裁決 A+C（使用者核准）：新增兩道財務口徑閘門，解決「三報表數字全同、
驗收全 PASS，卻共同承接一句錯的分母」的盲點（本次實例：LLM 把防禦維度分母
TA−指定款 25,596,691 寫成「配置分母」，而五桶 pct 實際是占總資產）。
  閘門 1 比例反算：用 penetration.pct_denominator 宣告反算每桶，與 actual_pct
                   誤差 >0.1pp → FAIL；缺分母宣告 → FAIL。
  閘門 2 資產不變量：五桶＋衛星＋指定用途款＋在途＋待確認應收 = 總資產，
                   不符 → FAIL。
兩道都只讀不改，不改任何既定財務口徑。
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

# 五桶（與 update_all.calc_penetration / build_penetration_report 同鍵）
BUCKETS = [("台股市值型成長", "台股"), ("美股市值型成長", "美股"),
           ("防守型配息", "防守"), ("債券", "債券"), ("現金/安全網", "現金")]
TOL_PCT = 0.1      # 反算容忍 0.1pp（round 到 0.1 的天然誤差內）
TOL_TWD = 1        # 金額容忍 1 元（整數口徑）


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def gate_pct_recalc(snap):
    """閘門 1：以宣告分母反算每桶 pct，與 actual_pct 比對。回傳 (errors, den)。"""
    pen = snap.get("penetration") or {}
    pct = pen.get("actual_pct") or {}
    twd = pen.get("actual_twd") or {}
    den = _num(pen.get("pct_denominator"))
    basis = pen.get("pct_denominator_basis")
    errs = []
    if den is None or den <= 0:
        errs.append("缺少分母宣告 penetration.pct_denominator（無法驗算比例）")
        return errs, None
    if basis != "total_assets":
        errs.append(f"分母基準宣告異常：{basis!r}（定版為 total_assets）")
    ta = _num(snap.get("total_assets")) or 0
    if abs(den - ta) > TOL_TWD:
        errs.append(f"分母宣告 {den:,.0f} ≠ 總資產 {ta:,.0f}（宣告與真值不符）")
    for key, lab in BUCKETS:
        p, t = _num(pct.get(key)), _num(twd.get(key))
        if p is None or t is None:
            errs.append(f"{key} 缺 actual_pct／actual_twd，無法反算")
            continue
        calc = round(t / den * 100, 1)
        if abs(calc - p) > TOL_PCT:
            errs.append(f"{lab} 反算 {calc:.1f}% ≠ actual_pct {p:.1f}%（差 {abs(calc - p):.2f}pp）")
    return errs, den


def gate_invariant(snap):
    """閘門 2：五桶＋衛星＋指定款＋在途＋待確認應收 = 總資產。"""
    pen = snap.get("penetration") or {}
    twd = pen.get("actual_twd") or {}
    sat = pen.get("satellite_twd") or {}
    parts = {
        "五桶": sum(_num(twd.get(k)) or 0 for k, _ in BUCKETS),
        "衛星": sum(_num(v) or 0 for v in sat.values()),
        "指定用途款": _num(pen.get("restricted_cash")) or 0,
        "在途": _num(pen.get("cash_in_transit")) or 0,
        "待確認應收": _num(pen.get("pending_receivables")) or 0,
    }
    total = sum(parts.values())
    ta = _num(snap.get("total_assets")) or 0
    errs = []
    if abs(total - ta) > TOL_TWD:
        detail = "＋".join(f"{k} {v:,.0f}" for k, v in parts.items())
        errs.append(f"不變量不平：{detail} = {total:,.0f} ≠ 總資產 {ta:,.0f}（差 {total - ta:+,.0f}）")
    return errs, parts, ta

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=datetime.date.today().isoformat())
    ap.add_argument("--snapshot", default=str(BASE / "snapshot.json"),
                    help="受測 snapshot（測試注入用；預設 repo 內 snapshot.json）")
    a = ap.parse_args()
    today = a.date
    files = {
        "日報": BASE / f"daily_report_v2_{today}.html",
        "穿透報告": BASE / f"penetration_report_{today}.html",
        "緊急應變": BASE / f"emergency_report_{today}.html",
    }

    # 真值：snapshot penetration actual_pct + 總資產
    snap = json.loads(Path(a.snapshot).read_text(encoding="utf-8"))
    pen = snap.get("penetration", {}).get("actual_pct", {})
    truth_pct = {
        "台股": pen.get("台股市值型成長"),
        "美股": pen.get("美股市值型成長"),
        "防守": pen.get("防守型配息"),
        "債券": pen.get("債券"),
        "現金": pen.get("現金/安全網"),
    }
    truth_total = snap.get("total_assets", 0)
    # 精確字串（去掉逗號差異）
    truth_strs = set()
    for k, v in truth_pct.items():
        if v is not None:
            truth_strs.add(f"{v:.1f}")
    truth_total_str = f"{truth_total:,.0f}".replace(",", "")
    truth_total_alt = f"{truth_total:,.0f}"

    errors = []
    print(f"🔍 穿透一致性檢查（{today}）")
    print(f"snapshot 真值: {json.dumps(truth_pct, ensure_ascii=False)} | 總資產 {truth_total:,.0f}")

    # ── 閘門 1／2：財務口徑（2026-11-09 裁決 A+C）──────────────────────────
    g1_errs, g1_den = gate_pct_recalc(snap)
    g2_errs, g2_parts, g2_ta = gate_invariant(snap)
    if g1_den:
        print(f"閘門1 比例反算：分母宣告 {g1_den:,.0f}（{snap.get('penetration',{}).get('pct_denominator_basis','—')}）"
              f" → {'✅ PASS' if not g1_errs else '❌ FAIL'}")
    else:
        print("閘門1 比例反算：❌ FAIL（無分母宣告）")
    for e in g1_errs:
        print(f"  • {e}")
    _g2_detail = "＋".join(f"{k} {v:,.0f}" for k, v in g2_parts.items())
    print(f"閘門2 資產不變量：{_g2_detail} = {sum(g2_parts.values()):,.0f} vs 總資產 {g2_ta:,.0f}"
          f" → {'✅ PASS' if not g2_errs else '❌ FAIL'}")
    for e in g2_errs:
        print(f"  • {e}")
    errors.extend(g1_errs)
    errors.extend(g2_errs)
    _gate_n = len(errors)   # 閘門錯誤已在上方逐條印出，收尾時不再重複
    print()

    for name, path in files.items():
        if not path.exists():
            if name == "緊急應變":
                # 非應變日無緊急報告 = 正常 → 不擋（只擋「存在但內容不符」）
                print(f"  {name}: ➖ 檔案不存在（非應變日正常，跳過）")
                continue
            print(f"  {name}: ❌ 檔案不存在")
            errors.append(f"{name} 檔案不存在")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # 檢查每個穿透真值字串是否出現
        missing = []
        for k, v in truth_pct.items():
            if v is None:
                continue
            s = f"{v:.1f}"
            if s not in text:
                missing.append(f"{k} {s}%")
        # 總資產（容許逗號差異）
        total_ok = (truth_total_str in text.replace(",", "")) or (truth_total_alt in text)
        if not total_ok:
            missing.append(f"總資產 {truth_total:,.0f}")
        if missing:
            print(f"  {name}: ❌ 缺少真值 → {'、'.join(missing)}")
            errors.append(f"{name} 缺少: {'、'.join(missing)}")
        else:
            print(f"  {name}: ✅ 包含全部穿透真值")

    if errors:
        _body = errors[_gate_n:]
        print(f"\n❌ 共 {len(errors)} 項未通過（口徑閘門 {_gate_n} 項、報表比對 {len(_body)} 項）：")
        for e in _body:
            print(f"  • {e}")
        if _gate_n:
            print(f"  （口徑閘門 {_gate_n} 條已在上方逐條列示）")
        print("⚠️ 請重新產出後再推送（python gen_emergency_XXXX.py && python build_penetration_report.py && python four_source_sync.py）")
        return 1
    print("\n✅ 三報表穿透一致，可推送")
    return 0

if __name__ == "__main__":
    sys.exit(main())
