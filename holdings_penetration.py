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


def _carrier_records(snap: dict) -> list:
    """把每個「持有載體」的部位攤平。

    載體＝實際持有帳戶／保單平台（不同載體即使同一檔基金也是真實不同資產）。
    回傳每筆：{carrier, label, code, name, amount}
    """
    recs = []

    def add(cid, label, name, amt, code=None):
        if name and amt:
            recs.append({"carrier": cid, "label": label, "code": code,
                         "name": str(name), "amount": _f(amt)})

    for h in (snap.get("holdings") or []):        # 證券帳戶
        if h.get("ticker"):
            add("SEC", "證券帳戶", h.get("name") or h["ticker"],
                h.get("market_value") or h.get("value"), str(h["ticker"]))

    _ins = snap.get("insurance_detail")
    if not _ins:                                  # snapshot 無 → 退回差異分析最後一天（同一真值來源）
        _h = _j("asset_diff_history.json")
        _last = sorted(_h)[-1] if _h else None
        _ins = (_h.get(_last) or {}).get("insurance_detail") if _last else None
    cur_id, cur_label = "POLICY-OTHER", "保單"
    for k, v in (_ins or {}).items():
        ks = str(k).strip()
        if ks.startswith("━"):                     # 第一金等其他保單：以跨行分隔線另起載體
            _nm = ks.lstrip("━").replace("現值", "").replace("現値", "").strip()
            _nm = _nm.split("（")[0].split("(")[0].strip()[:12] or "其他保單"
            cur_id, cur_label = f"POLICY-{_nm}", _nm
            if isinstance(v, (int, float)) and "總現" not in ks:
                add(cur_id, cur_label, _nm, v)     # 這一行本身就是部位（含金額）
            continue
        if ks.startswith("【"):
            _nm = ks.replace("【", "").replace("】", "").replace("現值", "").strip()
            cur_id, cur_label = f"POLICY-{_nm}", _nm
            continue
        if not isinstance(v, (int, float)) or "合計" in ks or "總現" in ks:
            continue
        add(cur_id, cur_label, ks, v)

    for grp_name, grp in (snap.get("funds_breakdown") or {}).items():   # 基金平台（子帳戶各自一載體）
        if not isinstance(grp, dict) or grp_name.endswith("小計"):
            continue
        for nm, val in grp.items():
            if isinstance(val, (int, float)):
                add(f"FUND-{grp_name}", f"基金-{grp_name}", nm, val)
    return recs


def _dedupe_within_carrier(recs: list) -> tuple:
    """同一載體內「同名」視為同一部位：同額→重複資料列只算一次；不同額→取較大並標異常。"""
    seen, out, dup = {}, [], []
    for r in recs:
        k = (r["carrier"], r["name"])
        if k not in seen:
            seen[k] = r
            out.append(r)
            continue
        keep = seen[k]
        if abs(keep["amount"] - r["amount"]) < 1:
            dup.append({"carrier": r["carrier"], "name": r["name"], "amount": r["amount"],
                        "處置": "同載體重複資料列，只計一次"})
        else:
            dup.append({"carrier": r["carrier"], "name": r["name"], "取用": max(keep["amount"], r["amount"]),
                        "另一筆": min(keep["amount"], r["amount"]), "處置": "同載體同名不同額，取較大並標異常"})
            keep["amount"] = max(keep["amount"], r["amount"])
    return out, dup


def resolve_amounts(snap: dict, audit: dict | None = None) -> dict:
    """把 fund_holdings.json 的每一筆對到實際市值（動態，不在資料檔寫死金額）。

    對不到就回 0 並標 unresolved —— 這是刻意的 fail-visible，不猜。
    """
    hd = (_j("data/fund_holdings.json").get("holdings") or {})
    recs = _carrier_records(snap)
    recs, dup_rows = _dedupe_within_carrier(recs)
    if audit is not None:
        audit["重複資料列"] = dup_rows
    out = {}
    for key, item in hd.items():
        m = item.get("match") or {}
        t, k = m.get("type"), str(m.get("key") or "")
        hit = []
        if t == "ticker":
            hit = [r for r in recs if r["carrier"] == "SEC" and r.get("code") == k]
            if not hit:
                hit = [r for r in recs if r["carrier"] == "SEC" and k and k in r["name"]]
        elif t == "name_contains":
            hit = [r for r in recs if k and k in r["name"]]
        # 不同載體各自計入後合併；同載體重複資料列已在 _dedupe_within_carrier 去除
        amt = sum(r["amount"] for r in hit)
        out[key] = dict(item, amount=amt, resolved=bool(hit),
                        carriers=[{"carrier": r["carrier"], "label": r["label"],
                                   "amount": round(r["amount"], 0)} for r in hit])
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
    _dates = {k: i.get("date") for k, i in items.items()
              if i.get("level") == "已穿透" and i.get("date")}
    _uniq = sorted(set(_dates.values()))
    return {
        "可合併商品數": sum(1 for i in items.values() if i.get("level") == "已穿透"),
        "資料時點": _dates,
        "時點是否一致": len(_uniq) <= 1,
        "最舊資料日": _uniq[0] if _uniq else None,
        "最新資料日": _uniq[-1] if _uniq else None,
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


# ── 去重修正前後差異報告（3 → 驗收用） ─────────────────────────
def dedupe_diff(snap: dict) -> dict:
    """比較「舊全域 max()」與「新按載體合計」的金額差異，量化低估幅度。"""
    hd = (_j("data/fund_holdings.json").get("holdings") or {})
    recs = _carrier_records(snap)
    recs_d, _ = _dedupe_within_carrier(recs)
    tot = _f(snap.get("total_assets") or snap.get("grand_total") or 0)
    rows = []
    for key, item in hd.items():
        m = item.get("match") or {}
        t, k = m.get("type"), str(m.get("key") or "")
        if t == "ticker":
            hit = [r for r in recs_d if r["carrier"] == "SEC" and r.get("code") == k]
        else:
            hit = [r for r in recs_d if k and k in r["name"]]
        new = sum(r["amount"] for r in hit)
        old = max([r["amount"] for r in hit], default=0.0)
        if abs(new - old) >= 1:
            rows.append({"key": key, "名稱": item.get("名稱"), "舊_max": round(old),
                         "新_合計": round(new), "差額": round(new - old),
                         "載體": [{"label": r["label"], "amount": round(r["amount"])} for r in hit],
                         "對總資產影響_pp": round((new - old) / tot * 100, 3) if tot else None})
    rows.sort(key=lambda r: -r["差額"])
    return {"總資產": tot, "低估合計": round(sum(r["差額"] for r in rows)),
            "影響_pp": round(sum(r["差額"] for r in rows) / tot * 100, 3) if tot else None,
            "明細": rows}


def _selftest() -> bool:
    """使用者指定的四個驗收案例（合成資料，不動真值）。"""
    fh = {"holdings": {"T": {"名稱": "測試基金", "match": {"type": "name_contains", "key": "測試基金"}}}}
    snap = {"holdings": [], "funds_breakdown": {},
            "insurance_detail": {"【保單A】現值": 2_000_000,
                                 "F1 測試基金 (50%)": 1_000_000,      # 同載體重複資料列（Python dict 會折疊，保留單列即可；F601 靜態閘門）
                                 "【保單B】現值": 800_000,
                                 "F1 測試基金 (40%)": 800_000,
                                 "F2 其他基金 (40%)": 900_000,
                                 "保單總現値": 1_800_000}}
    import tempfile, os, json as _json
    bak = None
    fpath = "data/fund_holdings.json"
    try:
        bak = open(fpath, encoding="utf-8").read()
        _json.dump(fh, open(fpath, "w", encoding="utf-8"), ensure_ascii=False)
        audit = {}
        out = resolve_amounts(snap, audit)["T"]
        cases = [
            ("①同保單重複來源只計一次", out["amount"] == 1_800_000, out["amount"]),
            ("②不同保單同一基金合計", out["amount"] == 1_800_000 and len(out["carriers"]) == 2, out["carriers"]),
            ("③同載體重複資料列只算一次並標記", _dedupe_within_carrier(
                [{"carrier": "POLICY-A", "label": "A", "code": None, "name": "測試基金", "amount": 1e6}] * 2
            ) == ([{"carrier": "POLICY-A", "label": "A", "code": None, "name": "測試基金", "amount": 1e6}],
                  [{"carrier": "POLICY-A", "name": "測試基金", "amount": 1e6, "處置": "同載體重複資料列，只計一次"}]), None),
            ("④資料不完整不猜測", resolve_amounts({"holdings": [], "funds_breakdown": {}}, {})["T"]["resolved"] is False, None),
        ]
    finally:
        if bak is not None:
            open(fpath, "w", encoding="utf-8").write(bak)
    ok = True
    for nm, cond, val in cases:
        print(("  ✅ " if cond else "  ❌ ") + nm + ("" if cond else f"  → {val}"))
        ok = ok and cond
    print("  " + ("全部通過" if ok else "有案例失敗"))
    return ok
