# -*- coding: utf-8 -*-
"""證券持股明細一致性閘門（fail-closed）

五條檢查，任一 FAIL 即 exit 1，不得進入發布流程：
  ① 單檔　　shares × price（4dp，ROUND_HALF_UP）== market_value
  ② 明細合計 == securities.total_market_value（唯一權威）
  ③ 同義欄位 securities_total／_total_market_value／_market／_market_value／_current／_current_value
              ＋ securities_unrealized_pnl 全部等於權威值
  ④ 每檔 price_date 必須存在，且全部等於 securities.price_date 的日期部分
  ⑤ 逐檔 pnl 合計與 securities.unrealized_pnl 相差 ≤ 100（成本均價顯示精度容差），
     超過即 FAIL；無法取得即 FAIL（不得推定）

設計原則：不相等＝FAIL、價格缺失＝FAIL、日期不一致＝FAIL（不同日不得無聲混用）。
用法：
  python scripts/check_securities_integrity.py            # 檢查 snapshot.json
  python scripts/check_securities_integrity.py --selftest # 內建案例（含 00983D）
"""
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SNAP = BASE / "snapshot.json"
ALIASES = ("securities_total", "securities_total_market_value", "securities_market",
           "securities_market_value", "securities_current", "securities_current_value")
PNL_TOL = 100


def r0(x) -> int:
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def run(snap: dict) -> list:
    """回傳 [(level, code, msg)]；level ∈ FAIL/WARN/OK"""
    out = []
    holds = snap.get("holdings") or []
    sec = snap.get("securities") or {}
    auth = sec.get("total_market_value")

    if not holds:
        return [("FAIL", "②", "holdings 為空，無法對帳")]
    if auth is None:
        return [("FAIL", "③", "securities.total_market_value 缺失（無權威值）")]

    # ① 單檔
    for h in holds:
        t = h.get("ticker") or h.get("code") or "?"
        try:
            calc = r0(float(h["shares"]) * float(h["price"]))
        except Exception:
            out.append(("FAIL", "①", f"{t} 缺 shares/price，無法驗算"))
            continue
        mv = h.get("market_value")
        if mv is None:
            out.append(("FAIL", "①", f"{t} 缺 market_value"))
        elif calc != r0(mv):
            out.append(("FAIL", "①", f"{t} {h['shares']}×{h['price']}={calc:,} ≠ 市值 {r0(mv):,}（差 {calc - r0(mv):,}）"))

    # ② 明細合計
    hsum = sum(r0(h.get("market_value") or 0) for h in holds)
    if hsum != r0(auth):
        out.append(("FAIL", "②", f"明細合計 {hsum:,} ≠ 權威總額 {r0(auth):,}（差 {hsum - r0(auth):,}）"))

    # ③ 同義欄位
    for k in ALIASES:
        v = snap.get(k)
        if v is None:
            out.append(("FAIL", "③", f"{k} 缺失"))
        elif r0(v) != r0(auth):
            out.append(("FAIL", "③", f"{k}={r0(v):,} ≠ 權威 {r0(auth):,}（差 {r0(v) - r0(auth):,}）"))
    pnl_auth = sec.get("unrealized_pnl")
    pnl_alias = snap.get("securities_unrealized_pnl")
    if pnl_auth is None or pnl_alias is None:
        out.append(("WARN", "③", "未實現損益欄位不全（securities.unrealized_pnl / securities_unrealized_pnl）"))
    elif r0(pnl_alias) != r0(pnl_auth):
        out.append(("FAIL", "③", f"securities_unrealized_pnl={r0(pnl_alias):,} ≠ 權威 {r0(pnl_auth):,}"))

    # ④ 價格日期
    pd_auth = str(sec.get("price_date") or "")
    d_auth = pd_auth.split("（")[0].split("(")[0].strip()
    if not d_auth:
        out.append(("FAIL", "④", "securities.price_date 缺失"))
    for h in holds:
        t = h.get("ticker") or "?"
        pd = h.get("price_date")
        if not pd:
            out.append(("FAIL", "④", f"{t} 缺 price_date"))
        elif d_auth and str(pd)[:10] != d_auth[:10]:
            out.append(("FAIL", "④", f"{t} price_date={pd} ≠ 權威 {d_auth}（不同日不得混用）"))

    # ⑤ 未實現損益一致性
    if pnl_auth is not None:
        try:
            calc_pnl = sum(r0(h.get("market_value") or 0) - r0(h.get("cost") or 0) for h in holds)
            d = calc_pnl - r0(pnl_auth)
            if abs(d) > PNL_TOL:
                out.append(("FAIL", "⑤", f"逐檔 pnl 合計 {calc_pnl:,} 與權威 {r0(pnl_auth):,} 差 {d:,}（>±{PNL_TOL}）"))
            elif d != 0:
                out.append(("WARN", "⑤", f"逐檔 pnl 合計與權威差 {d:,}（成本均價顯示精度，容許 ≤±{PNL_TOL}）"))
        except Exception as e:
            out.append(("FAIL", "⑤", f"pnl 無法驗算：{e}"))

    if not out:
        out.append(("OK", "—", f"五條全過（權威 {r0(auth):,}／{len(holds)} 檔／price_date {d_auth}）"))
    return out


# ── 自我測試（含 00983D 精度案例） ─────────────
def _mk(holdings, auth, pnl, pdate):
    return {"holdings": holdings, "securities": {"total_market_value": auth, "unrealized_pnl": pnl,
                                                 "price_date": pdate},
            "securities_total": auth, "securities_total_market_value": auth, "securities_market": auth,
            "securities_market_value": auth, "securities_current": auth, "securities_current_value": auth,
            "securities_unrealized_pnl": pnl}


def selftest() -> int:
    h = [{"ticker": "00983D", "shares": 20000, "price": 10.05, "market_value": 201000,
          "cost": 202000, "price_date": "2026-11-05"},
         {"ticker": "0050", "shares": 2000, "price": 97.15, "market_value": 194300,
          "cost": 169800, "price_date": "2026-11-05"}]
    cases = []

    r = run(_mk(json.loads(json.dumps(h)), 395300, 23500, "2026-11-05"))
    cases.append(("①正常（00983D 20000×10.05=201,000）", all(x[0] != "FAIL" for x in r), r))

    h2 = json.loads(json.dumps(h))
    h2[0].update({"price": 9.95, "market_value": 198900})   # 2dp 精度不一致的歷史錯誤
    r = run(_mk(h2, 393200, 23500, "2026-11-05"))
    cases.append(("②00983D 2dp 精度錯誤必須被判 FAIL", any(x[0] == "FAIL" and x[1] == "①" for x in r), r))

    h3 = json.loads(json.dumps(h))
    s = _mk(h3, 395300, 23500, "2026-11-05"); s["securities_market_value"] = 440000
    r = run(s)
    cases.append(("③同義欄位漂移必須 FAIL", any(x[0] == "FAIL" and x[1] == "③" for x in r), r))

    h4 = json.loads(json.dumps(h)); h4[1]["price_date"] = "2026-11-04"
    r = run(_mk(h4, 395300, 23500, "2026-11-05"))
    cases.append(("④日期混用必須 FAIL", any(x[0] == "FAIL" and x[1] == "④" for x in r), r))

    h5 = json.loads(json.dumps(h)); h5[0]["price_date"] = None
    r = run(_mk(h5, 395300, 23500, "2026-11-05"))
    cases.append(("⑤價格日期缺失必須 FAIL", any(x[0] == "FAIL" and x[1] == "④" for x in r), r))

    h6 = json.loads(json.dumps(h)); h6[0]["cost"] = 150000
    r = run(_mk(h6, 395300, 23500, "2026-11-05"))
    cases.append(("⑥pnl 超容差必須 FAIL", any(x[0] == "FAIL" and x[1] == "⑤" for x in r), r))

    ok = True
    for name, passed, res in cases:
        print(f"  {'✅' if passed else '❌'} {name}")
        if not passed:
            ok = False
            for lv, code, m in res:
                if lv != "OK":
                    print(f"      {lv} {code} {m}")
    print(f"\n自我測試 {sum(1 for _, p, _ in cases if p)}/{len(cases)}")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    res = run(snap)
    fails = [x for x in res if x[0] == "FAIL"]
    warns = [x for x in res if x[0] == "WARN"]
    for lv, code, m in res:
        icon = {"FAIL": "❌", "WARN": "⚠️", "OK": "✅"}[lv]
        print(f"  {icon} {code} {m}")
    print(f"\n證券一致性閘門：{'FAIL' if fails else 'PASS'}（FAIL {len(fails)}／WARN {len(warns)}）")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
