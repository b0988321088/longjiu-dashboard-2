#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""holdings_penetration.py — 穿透式風險引擎（2026-11-05 使用者裁示）

定位：獨立計算引擎，不改 industry_penetration.py、不改 penetration 口徑、不改任何配置目標。
輸出四塊，供儀表板「資產防護中心」與日報共用：
  1) coverage   穿透覆蓋率（已穿透／部分／未穿透，含未穿透金額與原因）
  2) overlap    跨商品重複持股（只合併『已穿透』的部分，其餘不推定）
  3) dual       科技曝險雙口徑（桶口徑 vs GICS 產業口徑，明確標示不可相加）
  4) corr/hedge 桶間相關性與歷史下跌實測（只用 DB 既有序列；資料不足一律如實標示）

鐵則：
  * 未穿透不得假設低風險；不得以未驗證數據產生交易建議。
  * 相關性不是因果；歷史避險不保證未來。
  * 本引擎唯讀，不寫 snapshot、不改門檻、不產生交易授權。
"""
from __future__ import annotations

import json
import sqlite3
from itertools import combinations
from pathlib import Path

BASE = Path(__file__).resolve().parent
HOLD = BASE / "data" / "fund_holdings.json"

BUCKETS = ("securities", "funds", "insurance", "cash_total")
BUCKET_CN = {"securities": "台股／證券", "funds": "基金", "insurance": "保單", "cash_total": "現金"}


def _j(p, d=None):
    try:
        return json.loads((BASE / p).read_text(encoding="utf-8"))
    except Exception:
        return d if d is not None else {}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def resolve_amounts(snap: dict) -> dict:
    """把 fund_holdings.json 的每一筆對到實際市值（動態，不在資料檔寫死金額）。

    對不到就回 0 並標 unresolved —— 這是刻意的 fail-visible，不猜。
    """
    hd = (_j("data/fund_holdings.json").get("holdings") or {})
    tick = {}
    for h in (snap.get("holdings") or []):
        if h.get("ticker"):
            tick[str(h["ticker"])] = _f(h.get("market_value") or h.get("value"))
    pool = []                                   # 保單內部位（名稱 → 金額）
    _ins = snap.get("insurance_detail")
    if not _ins:                                # snapshot 沒有時退回差異分析最後一天（同一真值來源）
        _h = _j("asset_diff_history.json")
        _last = sorted(_h)[-1] if _h else None
        _ins = (_h.get(_last) or {}).get("insurance_detail") if _last else None
    for k, v in (_ins or {}).items():
        if isinstance(v, (int, float)) and not str(k).startswith("【") and "合計" not in str(k) and "總現" not in str(k):
            pool.append((str(k), _f(v)))
    for f in (snap.get("fund_holdings") or []):
        pool.append((str(f.get("name") or ""), _f(f.get("market_value") or f.get("value"))))
    for grp in (snap.get("funds_breakdown") or {}).values():
        if isinstance(grp, dict):
            for nm, val in grp.items():
                if isinstance(val, (int, float)):
                    pool.append((str(nm), _f(val)))

    out = {}
    for key, item in hd.items():
        m = item.get("match") or {}
        t, k = m.get("type"), str(m.get("key") or "")
        amt, resolved = 0.0, False
        if t == "ticker":
            amt, resolved = tick.get(k, 0.0), k in tick
        elif t == "name_contains":
            hits = [v for nm, v in pool if k and k in nm]
            if hits:
                amt, resolved = max(hits), True      # 同標的取最大單筆，避免重複計入
        out[key] = dict(item, amount=amt, resolved=resolved)
    return out


def coverage(items: dict) -> dict:
    tot = sum(i["amount"] for i in items.values())
    by = {"已穿透": 0.0, "部分穿透": 0.0, "未穿透": 0.0}
    unresolved = []
    for k, i in items.items():
        lv = i.get("level") or "未穿透"
        by[lv] = by.get(lv, 0.0) + i["amount"]
        if not i.get("resolved"):
            unresolved.append({"key": k, "名稱": i.get("名稱"), "原因": "金額無法對應到 snapshot"})
    return {
        "總額": round(tot, 0),
        "分級": {k: round(v, 0) for k, v in by.items()},
        "分級佔比": {k: (round(v / tot * 100, 2) if tot else None) for k, v in by.items()},
        "未對應": unresolved,
        "完整度": (round(by["已穿透"] / tot * 100, 2) if tot else None),
        "說明": "完整度＝已穿透金額佔本資料層總額；未穿透不代表無風險",
    }


def overlap(items: dict, top: int = 10) -> dict:
    """跨商品重複持股：只合併 level=已穿透 的個股權重，其餘不推定。"""
    agg = {}
    for k, i in items.items():
        if (i.get("level") != "已穿透") or not i.get("top_holdings") or not i.get("amount"):
            continue
        for h in i["top_holdings"]:
            t = str(h.get("ticker") or "").strip()
            nm = str(h.get("name") or "")
            # 只合併真正的個股；ETF/期貨/黃金/TBA/TIPS/可轉債 不是同一檔股票，不得併入
            if (not t) or t in ("—", "-", "None"):
                continue
            if any(x in nm.upper() for x in ("ETF", "FUTR", "FUTURE", "GOLD", "TBA", "TIPS", "可轉債")):
                continue
            rec = agg.setdefault(t, {"ticker": t, "name": h.get("name"), "twd": 0.0, "holders": []})
            rec["twd"] += i["amount"] * _f(h.get("weight")) / 100.0
            rec["holders"].append({"product": k, "weight": _f(h.get("weight")), "amount": i["amount"]})
    rows = sorted(agg.values(), key=lambda x: -x["twd"])[:top]
    return {
        "可合併商品數": sum(1 for i in items.values() if i.get("level") == "已穿透"),
        "重複持股": [
            {"ticker": r["ticker"], "name": r["name"], "twd": round(r["twd"], 0),
             "持有商品數": len(r["holders"]),
             "明細": r["holders"]}
            for r in rows
        ],
        "說明": "僅含已穿透商品；未穿透商品的個股曝險未知，不得視為 0",
    }


def dual_tech(snap: dict) -> dict:
    """科技曝險雙口徑：桶口徑（目標 15%）vs GICS 資訊科技（產業穿透）。"""
    pen = snap.get("penetration") or {}
    act = pen.get("actual_pct") or {}
    barrel = act.get("美股市值型成長_科技")
    gics = None
    completeness = None
    gics_date = None
    try:
        import industry_penetration as ip
        p = ip.calc_industry_penetration(snap)
        ind = p.get("產業") or {}
        row = ind.get("資訊科技") or {}
        gics = row.get("佔比")
        un = ind.get("未分類(其他權重)") or {}
        tot = sum(_f(v.get("金額")) for v in ind.values()) or 0
        completeness = round(100 - (_f(un.get("金額")) / tot * 100), 2) if tot else None
        gics_date = pen.get("updated_at")
    except Exception as e:
        gics = None
        completeness = None
        gics_date = f"計算失敗：{type(e).__name__}"
    return {
        "桶口徑_pct": barrel,
        "桶口徑_定義": "美股市值型成長桶內的科技部位（不含台股與基金間接持股）",
        "GICS_pct": gics,
        "GICS_定義": "全部資產依 GICS 產業穿透後的資訊科技（含台股半導體與基金間接持股）",
        "GICS_完整度_pct": completeness,
        "GICS_資料日": gics_date,
        "可相加": False,
        "說明": "兩個數字衡量不同維度且重疊，不可相加；比較風險時以 GICS 為準",
    }


def _series() -> dict:
    try:
        c = sqlite3.connect(str(BASE / "dragon_assets.db"))
        rows = c.execute(
            "SELECT date, securities, funds, insurance, cash_total FROM assets ORDER BY date").fetchall()
        c.close()
    except Exception:
        return {}
    dates = [r[0] for r in rows]
    return {k: [float(r[i]) for r in rows] for i, k in enumerate(BUCKETS, start=1)} | {"__dates": dates}


def _rets(v):
    return [(v[i] / v[i - 1] - 1) * 100 for i in range(1, len(v)) if v[i - 1]]


def _corr(a, b):
    n = min(len(a), len(b))
    if n < 3:
        return None
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va <= 0 or vb <= 0:
        return None
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return round(cov / (va ** 0.5 * vb ** 0.5), 3)


def correlation(windows=(30, 60, 250)) -> dict:
    s = _series()
    if not s:
        return {"資料不足": True, "說明": "讀不到 dragon_assets.db"}
    out = {}
    for w in windows:
        avail = len(s.get("__dates") or [])
        if avail < w + 1:                       # 樣本不足不得用短窗冒充長窗
            out[f"{w}日"] = {"資料不足": True, "樣本數": max(0, avail - 1),
                             "說明": f"DB 僅 {avail} 筆日資料，需 {w + 1} 筆"}
            continue
        r = {k: _rets(s[k][-w - 1:]) for k in BUCKETS if len(s[k]) >= 3}
        n = min((len(v) for v in r.values()), default=0)
        if n < 20:
            out[f"{w}日"] = {"資料不足": True, "樣本數": n,
                             "說明": f"DB 僅 {len(s.get('__dates') or [])} 筆日資料，{w} 日滾動需 ≥20 個樣本"}
            continue
        pairs = {}
        for a, b in combinations(BUCKETS, 2):
            if a in r and b in r:
                v = _corr(r[a], r[b])
                if v is not None:
                    pairs[f"{BUCKET_CN[a]}×{BUCKET_CN[b]}"] = v
        out[f"{w}日"] = {"樣本數": n, "相關係數": pairs}
    out["說明"] = ("相關性只描述同向程度，不是因果；債券無獨立序列（DB bonds 恆為 0）故未列；"
                   "現金序列主要反映資金調度而非市場連動，解讀時須排除")
    return out


_HEDGE_CACHE = {}


def hedge_history(threshold=-1.0) -> dict:
    """歷史下跌實測：以台股加權單日跌幅 ≤ threshold 的日子，看各桶當日變化。"""
    if threshold in _HEDGE_CACHE:              # 同一行程只抓一次行情
        return _HEDGE_CACHE[threshold]
    s = _series()
    tw = None
    try:
        import urllib.request
        from datetime import datetime
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII"
               "?range=1mo&interval=1d")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            d = json.loads(resp.read().decode())
        res = d["chart"]["result"][0]
        ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
        tw = {datetime.utcfromtimestamp(t + 8 * 3600).strftime("%Y-%m-%d"): float(c)
              for t, c in zip(ts, cl) if c is not None}
    except Exception:
        return {"資料不足": True, "說明": "台股序列取得失敗"}
    if not s or not tw:
        return {"資料不足": True}

    days, dates = [], s["__dates"]
    twd = sorted(tw)
    for i in range(1, len(twd)):
        r = (tw[twd[i]] / tw[twd[i - 1]] - 1) * 100
        if r <= threshold:
            days.append((twd[i], r))
    rows, hit = [], 0
    for day, twr in days:
        if day not in dates:
            continue
        j = dates.index(day)
        if j == 0:
            continue
        rec = {"日期": day, "台股_pct": round(twr, 2)}
        for k in BUCKETS:
            prev, cur = s[k][j - 1], s[k][j]
            rec[BUCKET_CN[k] + "_pct"] = round((cur / prev - 1) * 100, 3) if prev else None
        rows.append(rec)
        hit += 1
    _HEDGE_CACHE[threshold] = {
        "下跌日數": hit,
        "門檻": f"台股加權單日 ≤ {threshold}%",
        "樣本": rows,
        "說明": "債券與黃金在 DB 無獨立序列，無法單獨測其緩衝；此表只顯示桶層級實測",
    }
    return _HEDGE_CACHE[threshold]


def run(snap: dict | None = None) -> dict:
    snap = snap if snap is not None else _j("snapshot.json")
    items = resolve_amounts(snap)
    return {
        "generated_at": snap.get("generated_at"),
        "coverage": coverage(items),
        "overlap": overlap(items),
        "dual": dual_tech(snap),
        "correlation": correlation(),
        "hedge": hedge_history(),
        "items": {k: {kk: vv for kk, vv in v.items() if kk != "top_holdings"} for k, v in items.items()},
    }


def _main() -> int:
    r = run()
    print(json.dumps(r, ensure_ascii=False, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
