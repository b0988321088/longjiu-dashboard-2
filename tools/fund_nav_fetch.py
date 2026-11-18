#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""保單基金淨值抓取 — 唯讀觀察版（第一階段）

用途
    每日抓 MoneyDJ 公開淨值，用「單位數 × NAV × 匯率」推算保單帳戶價值，
    與 snapshot 的保單真值（截圖／App）比對，累積誤差樣本。

邊界（刻意限制）
    · 不改 snapshot、不進日報／儀表板，只輸出 data/fund_nav_<date>.json
    · 抓不到或 NAV 與參考值不符者標 ok=false，不納入推算
    · 匯率暫用真值日固定值（policy_nav_basis 的 fx），誤差來源之一，如實記錄

用法
    python tools/fund_nav_fetch.py            # 抓取並寫入 data/
    python tools/fund_nav_fetch.py --print    # 只印出，不寫檔
"""
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
SNAPSHOT = BASE / "snapshot.json"

HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9",
}

# MoneyDJ 代碼：境外基金走 yp010001、境內基金走 yp010000
# ref_nav / ref_date 為 2026-11-17 App 截圖值，用來驗證抓到的 NAV 是否同一檔同一級別
FUNDS = {
    "tlz64":  {"page": "yp010001", "name": "安聯收益成長AM(美元)",        "ccy": "USD", "ref_nav": 7.9765},
    "mmg55":  {"page": "yp010001", "name": "M&G入息A(美元避險月配)F",      "ccy": "USD", "ref_nav": 75.4854},
    "pima1":  {"page": "yp010001", "name": "PIMCO收益增長M(月收息強化)",   "ccy": "USD", "ref_nav": 12.42},
    "shzv6":  {"page": "yp010001", "name": "貝萊德世界黃金A10美元",        "ccy": "USD", "ref_nav": 25.85},
    "acyt162": {"page": "yp010000", "name": "元大高股息龍頭B配息",         "ccy": "TWD", "ref_nav": 20.82},
    "ac0050": {"page": "yp010000", "name": "元大台灣卓越50",              "ccy": "TWD", "ref_nav": 90.1596},
    "mmg23":  {"page": "yp010001", "name": "M&G入息A(美元避險月配)",       "ccy": "USD", "ref_nav": 10.056},
}

# 持倉：(帳戶, 基金代碼, MoneyDJ代碼, 幣別, 單位數, 真值台幣, 備註)
#   ref_nav_ok=False 表示公開 NAV 與 App 對不上，只記錄不納入推算
HOLDINGS = [
    ("allianz_a", "USDEQ3490", "tlz64",   "USD", 9950.851679627,   2609545, ""),
    ("allianz_a", "USDEQ6550", "pima1",   "USD", 3867.786085079,   1579342, ""),
    ("allianz_a", "USDEQ5440", None,      "USD", None,              685946, "無單位數，未納入推算"),
    ("allianz_b", "NTDEQ2640", "acyt162", "TWD", 11618.932208288,   241906, ""),
    ("allianz_b", "NTDET0010", "ac0050",  "TWD", 9657.916572796,    870754, "App NAV 90.1596 與公開 93.69 不符（疑平台調整價）"),
    ("allianz_b", "USDEQ3490", "tlz64",   "USD", 1826.410827706,    478964, ""),
    ("allianz_b", "USDEQ5700", "mmg55",   "USD", 254.563972213,     631760, ""),
    ("allianz_b", "USDEQ6730", "shzv6",   "USD", 167.276977265,     142164, ""),
    ("firstjin",  "ID05",      "mmg23",   "USD", 5700.98491,       1881254, ""),
]


def fetch_nav(mj_code):
    meta = FUNDS[mj_code]
    url = f"https://www.moneydj.com/funddj/ya/{meta['page']}.djhtm?a={mj_code}"
    req = urllib.request.Request(url, headers=HDR)
    raw = urllib.request.urlopen(req, timeout=30).read()
    html = None
    for enc in ("utf-8", "big5", "cp950"):
        try:
            html = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if html is None:
        html = raw.decode("utf-8", "replace")

    m_nav = re.search(r"(?:最新值|最新淨值)\s*([\d]{1,4}\.[\d]{2,6})", html)
    nav = float(m_nav.group(1)) if m_nav else None
    if nav is None:
        m2 = re.search(r">\s*([\d]{1,4}\.[\d]{2,6})\s*<", html)
        nav = float(m2.group(1)) if m2 else None

    m_date = re.search(r"(\d{4})/(\d{2})/(\d{2})", html)
    nav_date = f"{m_date.group(1)}-{m_date.group(2)}-{m_date.group(3)}" if m_date else None

    ref = meta.get("ref_nav")
    # 門檻 1%：容許平台淨值日期差一天（保單平台多用前一交易日 NAV，日差異 <1%）；
    # 但足以擋掉「抓錯級別」（實測錯級別差距達 5 倍以上）
    ok = nav is not None and (ref is None or abs(nav - ref) / ref < 0.01)
    return {"name": meta["name"], "nav": nav, "nav_date": nav_date, "ok": ok, "ref_nav": ref}


def main():
    snap = json.load(SNAPSHOT.open(encoding="utf-8"))
    basis = snap.get("policy_nav_basis") or {}
    fx = (basis.get("allianz_b") or {}).get("fx") or 32.877
    fx_date = (basis.get("allianz_b") or {}).get("fx_date") or ""

    navs = {}
    for mj in {h[2] for h in HOLDINGS if h[2]}:
        try:
            navs[mj] = fetch_nav(mj)
        except Exception as e:
            navs[mj] = {"name": FUNDS[mj]["name"], "nav": None, "nav_date": None,
                        "ok": False, "ref_nav": FUNDS[mj].get("ref_nav"), "error": f"{type(e).__name__}: {e}"}

    accounts = {}
    for acct, code, mj, ccy, units, truth, note in HOLDINGS:
        acc = accounts.setdefault(acct, {"estimated": 0.0, "truth": 0.0, "covered_truth": 0.0,
                                         "skipped": [], "rows": []})
        acc["truth"] += truth
        row = {"code": code, "ccy": ccy, "units": units, "truth_twd": truth, "note": note}

        nav_ok = bool(mj) and navs.get(mj, {}).get("ok") and navs[mj].get("nav")
        if units is None or not nav_ok:
            row["estimated_twd"] = None
            row["skip_reason"] = note or ("無單位數" if units is None else "NAV 不可用")
            acc["skipped"].append(code)
        else:
            nav = navs[mj]["nav"]
            est = units * nav * (fx if ccy == "USD" else 1.0)
            row["estimated_twd"] = round(est, 0)
            row["nav"] = nav
            row["nav_date"] = navs[mj]["nav_date"]
            acc["estimated"] += est
            acc["covered_truth"] += truth
        acc["rows"].append(row)

    out = {
        "date": date.today().isoformat(),
        "fx_usd_twd": fx,
        "fx_date": fx_date,
        "fx_note": "匯率暫用真值日固定值，非當日即時匯率（誤差來源之一）",
        "navs": navs,
        "accounts": {},
    }
    for acct, acc in accounts.items():
        est, truth = acc["estimated"], acc["truth"]
        out["accounts"][acct] = {
            "estimated_twd": round(est, 0),
            "truth_twd": truth,
            "diff_twd": round(est - truth, 0),
            "diff_pct": round((est - truth) / truth * 100, 2) if truth else None,
            "coverage_pct": round(acc["covered_truth"] / truth * 100, 1) if truth else 0.0,
            "skipped": acc["skipped"],
            "rows": acc["rows"],
        }

    tot_est = sum(a["estimated_twd"] for a in out["accounts"].values())
    tot_truth = sum(a["truth_twd"] for a in out["accounts"].values())
    out["total"] = {"estimated_twd": round(tot_est, 0), "truth_twd": tot_truth,
                    "diff_twd": round(tot_est - tot_truth, 0),
                    "diff_pct": round((tot_est - tot_truth) / tot_truth * 100, 2) if tot_truth else None}

    if "--print" in sys.argv:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    DATA.mkdir(exist_ok=True)
    path = DATA / f"fund_nav_{out['date']}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"NAV 抓取 {len(navs)} 檔｜輸出 {path.relative_to(BASE)}")
    for acct, a in out["accounts"].items():
        flag = "🟢" if a["diff_pct"] is not None and abs(a["diff_pct"]) < 0.5 else "🟡"
        skip = f"｜未納入 {','.join(a['skipped'])}" if a["skipped"] else ""
        print(f"  {flag} {acct:10s} 推算 {a['estimated_twd']:>10,} vs 真值 {a['truth_twd']:>10,} "
              f"差 {a['diff_twd']:>+8,}（{a['diff_pct']:+.2f}%）覆蓋 {a['coverage_pct']}%{skip}")
    t = out["total"]
    print(f"  合計 推算 {t['estimated_twd']:,} vs 真值 {t['truth_twd']:,} 差 {t['diff_twd']:+,}（{t['diff_pct']:+.2f}%）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
