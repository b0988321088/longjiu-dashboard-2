# -*- coding: utf-8 -*-
"""統一 asset_id 與四層分類映射（唯讀產生，不改 snapshot）

四層：
  L1 帳務分類  — 這筆資產是什麼（證券／保單／基金平台）
  L2 策略分類  — 在槓鈴配置中的角色（互斥，總和應回到 100%）
  L3 穿透風險  — 真正承擔什麼風險（可重疊，不可相加）
  L4 實際防禦  — 下跌時能否緩衝（缺歷史序列 → 待實證）

輸出：
  data/asset_class_map.json        映射主檔（含版本、每筆可信度、來源）
  data/class_adjust_log.jsonl      append-only 校正紀錄（只有建議，未核准不得生效）
"""
import hashlib
import json
import os
import sys
from datetime import datetime

import holdings_penetration as hp

_f = hp._f

MAP_PATH = "data/asset_class_map.json"
LOG_PATH = "data/class_adjust_log.jsonl"
VERSION = "1.0"

# 策略分類規則（v1）。僅供「建議」，未經人工核准不得視為定案。
RULES = [
    # (比對字串, 策略分類, 說明)
    ("00983D", "債券", "債券 ETF"),
    ("00679B", "債券", "長天期美債 ETF"),
    ("00878", "防守型配息", "高股息 ETF（股票收益型）"),
    ("0056", "防守型配息", "高股息 ETF（股票收益型）"),
    ("00919", "防守型配息", "高股息 ETF（股票收益型）"),
    ("0050", "台股市值型成長", "台股市值型 ETF"),
    ("006208", "台股市值型成長", "台股市值型 ETF"),
    ("00713", "防守型配息", "高息低波 ETF（股票收益型）"),
    ("債", "債券", "債券型部位"),
    ("複合收益", "債券", "複合收益（債為主）"),
    ("富邦台50", "台股市值型成長", "台股市值型 ETF"),
    ("S&P500", "美股市值型成長", "美股大盤 ETF"),
    ("統一奔騰", "台股市值型成長", "台股基金"),
    ("主動統一台股", "台股市值型成長", "台股基金"),
    ("主動富邦", "債券", "複合收益主動型"),
    ("大華優利", "防守型配息", "高息 ETF"),
    ("AI收益成長", "防守型配息", "多重資產收益"),
    ("收益成長", "防守型配息", "收益成長（股債混合）"),
    ("貝萊德智慧數據", "美股市值型成長", "全球股票（美股為主）"),
    ("貝萊德全球", "美股市值型成長", "全球股票"),
    ("富達", "美股市值型成長", "全球股票（美股為主）"),
    ("入息", "債券", "入息基金（債為主）"),
    ("PIMCO", "債券", "收益增長（債為主）"),
    ("M&G入息", "債券", "入息基金（債為主）"),
    ("多重收益", "債券", "多重收益（債為主）"),
    ("多元收益", "債券", "多元收益（債為主）"),
    ("安聯收益成長", "防守型配息", "收益成長（股債混合）"),
    ("高股息", "防守型配息", "高股息基金"),
    ("優息", "防守型配息", "台股優息基金"),
    ("黃金", "分散配置", "黃金"),
    ("卓越50", "台股市值型成長", "台股 50 連結"),
    ("台灣", "台股市值型成長", "台股基金"),
    ("半導體", "美股市值型成長", "半導體主題"),
    ("科技", "美股市值型成長", "科技主題"),
    ("5G", "台股市值型成長", "台股 5G 主題"),
    ("全球", "美股市值型成長", "全球股票"),
    ("美國", "美股市值型成長", "美股"),
    ("世界", "美股市值型成長", "全球股票"),
    ("奔騰", "台股市值型成長", "台股基金"),
]

TECH_TICKERS = {"NVDA", "AAPL", "MSFT", "AVGO", "TSM", "META", "GOOGL", "GOOG",
                "AMZN", "AMD", "TSLA", "ORCL", "CRM", "ADBE", "QCOM", "TXN"}


def _slug(txt: str) -> str:
    h = hashlib.md5(str(txt).encode("utf-8")).hexdigest()[:8]
    ascii_part = "".join(c for c in str(txt) if c.isascii() and c.isalnum())[:12].upper()
    return ascii_part or h


def _strategy(name: str):
    for pat, bucket, why in RULES:
        if pat in name:
            return bucket, why
    return None, None


def build(snap: dict) -> dict:
    fh = hp._j("data/fund_holdings.json").get("holdings") or {}
    recs, dup = hp._dedupe_within_carrier(hp._carrier_records(snap))
    total = hp._f(snap.get("total_assets") or snap.get("grand_total") or 0)

    def penetration_for(name):
        """回傳 (level, 科技權重%, 來源, 日期, 命中key)"""
        for key, item in fh.items():
            k = str((item.get("match") or {}).get("key") or "")
            mtype = (item.get("match") or {}).get("type")
            hit = (k and k in name) if mtype == "name_contains" else False
            if hit:
                lv = item.get("level") or "未穿透"
                tech = sum(h.get("weight", 0) for h in (item.get("top_holdings") or [])
                           if str(h.get("ticker", "")).upper() in TECH_TICKERS)
                return lv, round(tech, 2), item.get("source"), item.get("date"), key
        return "未穿透", None, None, None, None

    entries, unmatched = [], []
    for r in recs:
        name = r["name"]
        if r["carrier"] == "SEC":
            aid = f"SEC-TW-{r.get('code') or _slug(name)}"
            l1 = "證券"
        elif r["carrier"].startswith("POLICY"):
            aid = f"{r['carrier']}-{_slug(name)}"
            l1 = "保單"
        else:
            aid = f"{r['carrier']}-{_slug(name)}"
            l1 = "基金平台"

        lv, tech, src, date, hit_key = penetration_for(name)
        s_bucket, s_why = _strategy(name)

        # 可信度：官方前十大且有日期 = B（僅前十大不是完整持倉，故不給 A）
        conf = "B" if (lv == "已穿透" and date) else ("C" if lv == "部分穿透" else "D")

        if s_bucket is None:
            unmatched.append({"asset_id": aid, "名稱": name, "金額": round(r["amount"])})
            s_bucket = "待映射"

        entries.append({
            "asset_id": aid,
            "名稱": name,
            "載體": r["label"],
            "金額": round(r["amount"]),
            "佔總資產_pct": round(r["amount"] / total * 100, 3) if total else None,
            "L1_帳務分類": l1,
            "L2_策略分類": s_bucket,
            "L2_依據": s_why or "無規則命中，待人工指定",
            "L3_穿透風險": {
                "穿透等級": lv,
                "前十大科技權重_pct": tech,
                "持股資料日期": date,
                "來源": src,
                "風險標籤": (["科技集中"] if (tech or 0) >= 30 else []) + ([] if lv == "已穿透" else ["資料不足"]),
            },
            "L4_實際防禦": {
                "評級": "待實證",
                "說明": ("無獨立價格序列可回測" if ("債" in name or "黃金" in name)
                         else "未取得下跌期間實證，不推定為防禦資產"),
            },
            "可信度": conf,
            "策略分類狀態": "待核准" if s_bucket != "待映射" else "未映射",
            "映射來源": f"asset_class_map v{VERSION} / 規則v1 + fund_holdings.json",
        })

    # 現金與指定款：帳務上是同一筆現金，策略上「可動用」與「指定用途」必須分開
    _cl = snap.get("cash_layers") or {}
    _rs = _cl.get("restricted_cash")
    _rest = _f(_rs.get("total")) if isinstance(_rs, dict) else _f(snap.get("restricted_cash"))
    _cash = _f(snap.get("cash_total") or _cl.get("cash_total"))
    for aid, nm, amt, bucket, note in [
        ("CASH-FREE", "可動用現金（活存/貨幣型）", max(0.0, _cash - _rest), "現金/安全網", "現金底線 70 萬"),
        ("CASH-RESTRICTED", "指定款（不可動用）", _rest, "指定款", "用途已指定，不得計入可動用"),
    ]:
        if amt:
            entries.append({
                "asset_id": aid, "名稱": nm, "載體": "現金", "金額": round(amt),
                "佔總資產_pct": round(amt / total * 100, 3) if total else None,
                "L1_帳務分類": "現金", "L2_策略分類": bucket, "L2_依據": note,
                "L3_穿透風險": {"穿透等級": "現金", "前十大科技權重_pct": None,
                                "持股資料日期": None, "來源": "snapshot.cash_layers", "風險標籤": []},
                "L4_實際防禦": {"評級": "已實證（不會跟跌，但無息）", "說明": "現金是唯一無市場風險部位"},
                "可信度": "A", "策略分類狀態": "待核准",
                "映射來源": f"asset_class_map v{VERSION} / 規則v1 + snapshot.cash_layers",
            })

    agg = {}
    for e in entries:
        agg[e["L2_策略分類"]] = agg.get(e["L2_策略分類"], 0) + e["金額"]
    return {
        "schema_version": VERSION,
        "產生時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "資料日": __import__("date_integrity").report_base(snap),
            "估值日": {"證券": __import__("date_integrity").authority_date(snap, "tw_securities"),
                       "基金": __import__("date_integrity").authority_date(snap, "funds"),
                       "安聯": __import__("date_integrity").authority_date(snap, "policy_allianz")},
        "總資產": round(total),
        "說明": "四層並列，L1/L2 互斥（總和回 100%），L3/L4 可重疊且不與 L1/L2 相加。"
                "策略分類為規則建議，未經人工核准不得視為定案。",
        "對帳": {
            "映射合計": round(sum(e["金額"] for e in entries)),
            "snapshot總資產": round(total),
            "差額": round(sum(e["金額"] for e in entries) - total),
            "狀態": "⚠️ 分項合計與 total_assets 不一致，待真值日核對（不自行調整）"
                    if abs(sum(e["金額"] for e in entries) - total) >= 1 else "✅ 一致",
        },
        "L2_合計": {k: round(v) for k, v in agg.items()},
        "L2_合計_pct": {k: round(v / total * 100, 2) for k, v in agg.items()} if total else {},
        "未映射": unmatched,
        "assets": entries,
        "_duplicate_rows": dup,
    }


def proposals(m: dict, ov: dict) -> list:
    """產生四級回饋建議（只記錄，不生效）。"""
    out, seen = [], set()

    def add(kind, level, aid, name, why, action, conf):
        pid = hashlib.md5(f"{kind}|{aid}|{why}".encode("utf-8")).hexdigest()[:10]
        if pid in seen:
            return
        seen.add(pid)
        out.append({"建議ID": pid, "類型": kind, "等級": level, "asset_id": aid, "標的": name,
                    "金額": round([a for a in m["assets"] if a["asset_id"] == aid][0]["金額"]) if aid else None,
                    "理由": why, "建議": action, "可信度": conf,
                    "狀態": "待審核", "提出時間": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

    for a in m["assets"]:
        tech = (a["L3_穿透風險"] or {}).get("前十大科技權重_pct")
        if tech is not None and tech >= 30 and "科技集中" not in (a["L3_穿透風險"]["風險標籤"]):
            add("風險集中", 2, a["asset_id"], a["名稱"], f"前十大科技權重 {tech}%", "新增科技風險標籤（不改策略分類）", a["可信度"])
        elif tech is not None and tech >= 30:
            add("風險集中", 2, a["asset_id"], a["名稱"], f"前十大科技權重 {tech}%",
                "保留原策略分類，新增科技產業風險標籤", a["可信度"])
        if a["L2_策略分類"] == "待映射":
            add("分類待補", 1, a["asset_id"], a["名稱"], "無策略分類規則命中", "人工指定策略分類", "D")
        if (a["L3_穿透風險"] or {}).get("穿透等級") == "未穿透":
            add("資料不足", 1, a["asset_id"], a["名稱"], "底層持股未取得，不得視為低風險", "保留未穿透標記，勿推定", "D")
        if "配息" in a["名稱"] or "高股息" in a["名稱"]:
            add("防禦待實證", 4, a["asset_id"], a["名稱"], "高股息在下跌期間與台股同向，未取得完整回測",
                "標示待實證，不得直接列為防禦資產", "C")

    for r in (ov.get("重複持股") or [])[:3]:
        add("底層集中", 2, None, r["name"], f"{r['持有商品數']} 檔基金重複持有，合計 {r['twd']:,.0f}",
            "列入風險標籤，不自動要求賣出", "B")
    return out


def main() -> int:
    snap = hp._j("snapshot.json")
    m = build(snap)
    json.dump(m, open(MAP_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    ov = hp.run(snap).get("overlap") or {}
    props = proposals(m, ov)

    exist = set()
    if os.path.exists(LOG_PATH):
        for line in open(LOG_PATH, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    exist.add(json.loads(line)["建議ID"])
                except Exception:
                    pass
    added = 0
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        for p in props:
            if p["建議ID"] in exist:
                continue
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
            added += 1

    print(f"映射 {len(m['assets'])} 筆 / 未映射 {len(m['未映射'])} 筆 / 建議新增 {added} 條（既有 {len(exist)}）")
    for k, v in sorted(m["L2_合計_pct"].items(), key=lambda x: -x[1]):
        print(f"  {k:16s} {v:6.2f}%  {m['L2_合計'][k]:>12,}")
    print("  合計", round(sum(m["L2_合計_pct"].values()), 2), "%")

    # ── 對帳：規則映射 vs 官方桶位（差異必須解釋，不強制相等）──
    pen = (snap.get("penetration") or {}).get("actual_pct") or {}
    print("\n對帳（規則映射 vs snapshot 官方桶位）：")
    for k, v in m["L2_合計_pct"].items():
        off = pen.get(k)
        if off is None:
            print(f"  {k:14s} {v:6.2f}%   官方：非既有桶位")
        else:
            print(f"  {k:14s} {v:6.2f}%   官方 {off:5.2f}%   差 {v - off:+.2f}pp")
    print("  說明：規則v1建議，未經人工核准；差異來自名稱規則未完全對齊既有桶位，不視為錯誤。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
