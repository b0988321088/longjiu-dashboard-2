#!/usr/bin/env python
"""drawdown_review.py — 月度跌幅檢討（資料驅動，不寫死數字）

用途
  回答三件事：①這個月資產跌多少、跌在哪裡 ②當時的決策對不對
  ③下次遇到同樣情況，規則要改哪一條

資料來源（皆為既有真值，不新增人工輸入）
  snapshot.json                              當期真值
  ~/龍九備份/YYYY-MM-DD_snapshot.json        每日歷史（含上月末基線）
  emergency_report_*.html / daily_report_v2_*.html   加權指數收盤（優先取緊急應變報告）

輸出
  drawdown_review_YYYY-MM.html   完整檢討頁（手機優先、離線可用）
  data/drawdown_YYYY-MM.json     本次計算的所有數字（可回溯、可比對）

嵌入
  build_national_fund.py 以 section_html() 取精簡版，放在國安基金頁最上方

用法
  python drawdown_review.py            # 本月
  python drawdown_review.py 2026-11    # 指定月份
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
BACKUP_DIRS = [
    Path(os.environ.get("LZ_BACKUP_DIR", "")) if os.environ.get("LZ_BACKUP_DIR") else None,
    Path.home() / "龍九備份",
]
LIFE_FLOOR = 700_000


# ---------------------------------------------------------------- 基礎工具
def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def money(v) -> str:
    return "—" if v is None else f"{_num(v):,.0f}"


def wan(v) -> str:
    return "—" if v is None else f"{_num(v) / 10_000:,.1f} 萬"


def signed_money(v) -> str:
    v = _num(v)
    return f"{v:+,.0f}"


def signed_pct(v, d=1) -> str:
    return "—" if v is None else f"{_num(v):+.{d}f}%"


def pct(v, d=1) -> str:
    return "—" if v is None else f"{_num(v):.{d}f}%"


def chg_pct(new, old):
    old = _num(old)
    if not old:
        return None
    return (_num(new) - old) / old * 100


def _first_existing(paths):
    for p in paths:
        if p and p.exists():
            return p
    return None


def backup_dir() -> Path:
    p = _first_existing(BACKUP_DIRS)
    if p is None:
        raise SystemExit("❌ 找不到每日快照備份目錄（~/龍九備份）——無法做期間比較")
    return p


# ---------------------------------------------------------------- 序列
def _snapshots(month: str) -> list[tuple[str, dict]]:
    """回傳 [(date, snapshot)]，含上月末基線，只保留當月以前的最後一筆 + 當月全部"""
    bdir = backup_dir()
    rows = []
    for f in sorted(bdir.glob("*_snapshot.json")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})_snapshot\.json$", f.name)
        if not m:
            continue
        try:
            rows.append((m.group(1), _load(f)))
        except Exception:
            continue
    head = [r for r in rows if r[0] < f"{month}-01"]
    body = [r for r in rows if r[0][:7] == month]
    out = ([head[-1]] if head else []) + body
    # 當期真值（snapshot.json）常比夜間備份新 —— 以它為期末
    live = BASE / "snapshot.json"
    if live.exists():
        s = _load(live)
        d = str(s.get("date") or "")[:10]
        if d[:7] == month and (not out or d > out[-1][0]):
            out.append((d, s))
        elif d[:7] == month and out and d == out[-1][0]:
            out[-1] = (d, s)
    return out


def _index_series(snaps: list[tuple[str, dict]]) -> tuple[dict, dict]:
    """加權指數收盤：日報 v2 優先（收盤定稿），若與前一日同值（沿用舊值）則改用緊急應變報告"""
    out, src = {}, {}
    want = {d for d, _ in snaps}
    for d in sorted(want):
        daily = BASE / f"daily_report_v2_{d}.html"
        emerg = BASE / f"emergency_report_{d}.html"
        emerg = emerg if emerg.exists() else BASE / f"emergency_taiex_report_{d}.html"
        vals = {}
        for path, tag in ((daily, "日報 v2"), (emerg, "緊急應變報告")):
            if not path.exists():
                continue
            txt = re.sub(r"<[^>]+>", " ", path.read_text(encoding="utf-8", errors="ignore"))
            m = re.search(r"加權指數\s*[:：]?\s*(\d{2},\d{3}(?:\.\d+)?)", txt)
            if m:
                v = _num(m.group(1).replace(",", ""))
                if 10_000 < v < 200_000:
                    vals[tag] = v
        pick = None
        if "日報 v2" in vals:
            prev = [out[k] for k in out if k < d]
            if not prev or abs(vals["日報 v2"] - prev[-1]) > 0.005:   # 非沿用舊值
                pick = ("日報 v2", vals["日報 v2"])
            elif "緊急應變報告" in vals:
                pick = ("緊急應變報告", vals["緊急應變報告"])
        elif "緊急應變報告" in vals:
            pick = ("緊急應變報告", vals["緊急應變報告"])
        if pick:
            out[d], src[d] = pick[1], pick[0]
    return out, src


def _trading_days(snaps: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    """去掉週末重複快照（週六日沿用週五價，留著會讓走勢出現假的平台段）"""
    import datetime as _dt
    keep = []
    for d, s in snaps:
        try:
            wd = _dt.date.fromisoformat(d).weekday()
        except ValueError:
            continue
        if wd < 5 or not keep:      # 第一筆是上月末基線，即使是週末也保留（其價格＝上月末收盤）
            keep.append((d, s))
    return keep or snaps


# ---------------------------------------------------------------- 歸因
def _platform_funds(s: dict) -> dict:
    """平台基金（國泰直購＋鉅亨）：類別 → 金額"""
    d = {}
    cathay = s.get("fund_breakdown_cathay") or s.get("funds_cathay_breakdown") or {}
    if cathay:
        d["國泰直購"] = {k: _num(v) for k, v in cathay.items()}
    fb = s.get("funds_breakdown") or {}
    for key in ("一般申購", "自由Pay"):
        if isinstance(fb.get(key), dict):
            d[f"鉅亨·{key}"] = {k: _num(v) for k, v in fb[key].items()}
    return d


def _allianz(s: dict) -> dict:
    ib = s.get("insurance_breakdown") or {}
    d = {}
    for key, label in (("policy_a_funds", "安聯 A"), ("policy_b_funds", "安聯 B")):
        if isinstance(ib.get(key), dict):
            d[label] = {k: _num(v) for k, v in ib[key].items()}
    return d


def compute(month: str) -> dict:
    snaps = _trading_days(_snapshots(month))
    if len(snaps) < 2:
        raise SystemExit(f"❌ {month} 快照不足（{len(snaps)} 筆），無法比較")

    base_date, base = snaps[0]
    cur_date, cur = snaps[-1]
    series = [(d, _num(s.get("total_assets"))) for d, s in snaps]
    idx, idx_src = _index_series(snaps)

    a0, a1 = _num(base.get("total_assets")), _num(cur.get("total_assets"))
    peak_date, peak_val = max(series, key=lambda r: r[1])
    trough_date, trough_val = min(series, key=lambda r: r[1])
    if peak_date > trough_date:  # 峰在谷後 → 以期末回撤為主
        peak_date, peak_val = max([r for r in series if r[0] <= trough_date] or [series[0]], key=lambda r: r[1])

    # ---- 部位歸因（四類，須閉合到總資產）
    def buckets(s):
        return {
            "證券（台股／美股 ETF、個股）": _num(s.get("securities_total_market_value")),
            "平台基金（國泰直購＋鉅亨）": _num(s.get("fund_market_value")),
            "保單（安聯 A/B＋第一金）": _num(s.get("insurance_total") or
                                        (_num((s.get("insurance_breakdown") or {}).get("allianz_ab_total")) +
                                         _num((s.get("insurance_breakdown") or {}).get("firstjin_total")))),
            "現金（活存／數位帳戶）": _num(s.get("cash_total") or s.get("cash")),
        }

    b0, b1 = buckets(base), buckets(cur)
    attrib = []
    for k in b0:
        chg = b1[k] - b0[k]
        attrib.append({
            "label": k, "start": b0[k], "end": b1[k], "chg": chg,
            "pct": chg_pct(b1[k], b0[k]), "share": None,
        })
    total_loss = sum(min(0.0, r["chg"]) for r in attrib) or 1.0
    for r in attrib:
        r["share"] = (r["chg"] / total_loss * 100) if r["chg"] < 0 else None
    bucket_sum0, bucket_sum1 = sum(b0.values()), sum(b1.values())

    # ---- 兩段式拆解（第一波 / 反彈 / 第二波）
    def at(date):
        for d, s in snaps:
            if d == date:
                return s
        return None

    legs = []
    zig = _legs(series)
    local_peak_date = zig[-2][1] if len(zig) >= 2 else base_date
    for d0, d1 in zig:
        s0, s1 = at(d0), at(d1)
        if not s0 or not s1:
            continue
        v0, v1 = _num(s0.get("total_assets")), _num(s1.get("total_assets"))
        i0, i1 = idx.get(d0), idx.get(d1)
        legs.append({
            "from": d0, "to": d1, "chg": v1 - v0, "pct": chg_pct(v1, v0),
            "idx_from": i0, "idx_to": i1, "idx_pct": chg_pct(i1, i0) if i0 and i1 else None,
        })

    # ---- 個股／ETF
    def holdings(s):
        return {h.get("ticker"): h for h in ((s.get("securities") or {}).get("holdings") or [])}

    h0, h1 = holdings(base), holdings(cur)
    prev_h = {h.get("ticker"): h for h in ((at(local_peak_date) or {}).get("securities") or {}).get("holdings") or []}
    sec_rows = []
    for t, h in h1.items():
        mv0 = _num((h0.get(t) or {}).get("market_value"))
        mv1 = _num(h.get("market_value"))
        mvp = _num((prev_h.get(t) or {}).get("market_value"))
        cost = _num(h.get("cost"))
        sec_rows.append({
            "ticker": t, "name": h.get("name", ""), "shares": h.get("shares"),
            "mv_start": mv0, "mv_peak": mvp, "mv_end": mv1,
            "mtd_pct": chg_pct(mv1, mv0) if mv0 else None,
            "p2t_pct": chg_pct(mv1, mvp) if mvp else None,
            "pnl_pct": (mv1 - cost) / cost * 100 if cost else None,
            "new": t not in h0,
        })
    sec_rows.sort(key=lambda r: (r["mtd_pct"] is None, r["mtd_pct"]))

    # ---- 基金逐檔
    p0, p1 = _platform_funds(base), _platform_funds(cur)
    fund_rows = []
    for grp in p1:
        for name, v1 in p1[grp].items():
            v0 = _num((p0.get(grp) or {}).get(name))
            fund_rows.append({"group": grp, "name": _short_name(name), "start": v0,
                              "end": v1, "chg": v1 - v0,
                              "pct": chg_pct(v1, v0) if v0 else None})
    fund_rows.sort(key=lambda r: (r["pct"] is None, _num(r["pct"])))
    a0f, a1f = _allianz(base), _allianz(cur)
    pol_rows = []
    for grp in a1f:
        for name, v1 in a1f[grp].items():
            v0 = _num((a0f.get(grp) or {}).get(name))
            pol_rows.append({"group": grp, "name": _short_name(name), "start": v0,
                             "end": v1, "chg": v1 - v0,
                             "pct": chg_pct(v1, v0) if v0 else None})
    f0 = _num((base.get("insurance_breakdown") or {}).get("firstjin_total"))
    f1 = _num((cur.get("insurance_breakdown") or {}).get("firstjin_total"))
    pol_rows.append({"group": "第一金", "name": "第一金人壽（保單帳戶）", "start": f0, "end": f1,
                     "chg": f1 - f0, "pct": chg_pct(f1, f0) if f0 else None})
    pol_rows.sort(key=lambda r: (r["pct"] is None, _num(r["pct"])))

    # ---- 台股純度（把藏在保單/平台裡的台股挖出來）
    tw_keys = ("元大台灣", "元大卓越", "路博邁台灣", "台新美日台", "台中銀台灣",
               "國泰台灣高股息", "安聯台灣科技", "統一", "台灣")
    mk_tw = lambda s: sum(v for g in _platform_funds(s).values() for k, v in g.items()
                          if any(x in k for x in tw_keys))
    pol_tw0 = sum(v for g in _allianz(base).values() for k, v in g.items()
                  if any(x in k for x in ("元大台灣", "元大卓越")))
    pol_tw1 = sum(v for g in _allianz(cur).values() for k, v in g.items()
                  if any(x in k for x in ("元大台灣", "元大卓越")))
    sec_non_tw = {"00983D", "00646"}
    sec_tw0 = sum(_num((h or {}).get("market_value")) for t, h in h0.items() if t not in sec_non_tw)
    sec_tw1 = sum(_num((h or {}).get("market_value")) for t, h in h1.items() if t not in sec_non_tw)
    tw = {
        "securities": {"start": sec_tw0, "end": sec_tw1, "chg": sec_tw1 - sec_tw0,
                       "pct": chg_pct(sec_tw1, sec_tw0) if sec_tw0 else None},
        "policy": {"start": pol_tw0, "end": pol_tw1, "chg": pol_tw1 - pol_tw0,
                   "pct": chg_pct(pol_tw1, pol_tw0) if pol_tw0 else None},
        "platform": {"start": mk_tw(base), "end": mk_tw(cur),
                     "chg": mk_tw(cur) - mk_tw(base),
                     "pct": chg_pct(mk_tw(cur), mk_tw(base)) if mk_tw(base) else None},
    }
    tw["total"] = {k: sum(tw[x][k] for x in tw if isinstance(tw[x], dict)) for k in ("start", "end", "chg")}
    tw["total"]["pct"] = chg_pct(tw["total"]["end"], tw["total"]["start"]) if tw["total"]["start"] else None

    # ---- 當月實際買進（股數增加者，記錄買進當日價）
    h1dict = holdings(cur)
    buys = []
    for i in range(1, len(snaps)):
        d, s1 = snaps[i]
        prev = {h.get("ticker"): h for h in ((snaps[i - 1][1].get("securities") or {}).get("holdings") or [])}
        for h in ((s1.get("securities") or {}).get("holdings") or []):
            t = h.get("ticker")
            s0 = _num((prev.get(t) or {}).get("shares"))
            sh = _num(h.get("shares"))
            if sh > s0:
                px_buy = _num(h.get("price"))          # 買進當日快照價
                px_now = _num((h1dict.get(t) or {}).get("price"))  # 最新價
                buys.append({"date": d, "ticker": t, "name": h.get("name", ""),
                             "shares": int(sh - s0), "price": px_buy, "price_now": px_now,
                             "chg": (px_now - px_buy) * (sh - s0) if px_buy else None,
                             "pct": chg_pct(px_now, px_buy) if px_buy else None})

    # ---- 質押 LTV（含每日自算序列與本月買進當日的 LTV）
    ltv = cur.get("ltv_stage_now") or {}
    gate = cur.get("us30y_gate") or {}
    pl_detail = (gate.get("unfreeze_conditions") or {}).get("pledge_ltv") or {}
    loan = _num(cur.get("fund_pledge_loan"))
    ltv_series = []
    for d, s in snaps:
        fb = s.get("fund_breakdown_cathay") or {}
        pool = sum(_num(v) for v in fb.values())
        if pool and loan:
            ltv_series.append({"date": d, "pool": pool, "ltv": loan / pool * 100})
    for b in buys:
        hit = next((r for r in ltv_series if r["date"] == b["date"]), None)
        b["ltv_at_buy"] = round(hit["ltv"], 2) if hit else None
    pledge = {
        "ltv_pct": _num(pl_detail.get("LTV_pct")) or _num(ltv.get("LTV_pct")),
        "stage": pl_detail.get("階段") or ltv.get("階段"),
        "as_of": pl_detail.get("LTV_app_date") or ltv.get("判定日") or ltv.get("基準日"),
        "loan": loan,
        "collateral": _num(pl_detail.get("擔保品市值")),
        "green_cap": _num(pl_detail.get("綠上限_pct")),
        "stop_line": _num(pl_detail.get("政策停止線_pct")),
        "buffer_pp": _num(pl_detail.get("距停止線_pct")),
        "pool_can_drop": _num(pl_detail.get("池值可跌_pct")),
        "series": ltv_series,
        "min_ltv": min((r["ltv"] for r in ltv_series), default=None),
        "max_ltv": max((r["ltv"] for r in ltv_series), default=None),
        "sell_role": (gate.get("unfreeze_conditions") or {}).get("減碼角色", ""),
        "unfreeze_allowed": gate.get("unfreeze_allowed"),
        "unfreeze_missing": ((gate.get("unfreeze_conditions") or {}).get("未達") or []),
        "cathay_note": (cur.get("fund_pledge_note") or "")[:120],
    }
    defense_txt = ((cur.get("penetration") or {}).get("alert") or "")
    m_def = re.search(r"防守合併口徑\s*([\d.]+)%", defense_txt)

    # ---- 市場面
    market = {
        "index_start": idx.get(base_date), "index_end": idx.get(cur_date),
        "index_pct": chg_pct(idx.get(cur_date), idx.get(base_date)) if idx.get(base_date) else None,
        "index_peak": idx.get(local_peak_date), "index_peak_pct":
            chg_pct(idx.get(cur_date), idx.get(local_peak_date)) if idx.get(local_peak_date) else None,
        "sources": idx_src,
        "us30y": _num(gate.get("value")),
        "us30y_red": _num(gate.get("red_line")),
        "us30y_streak": gate.get("red_line_streak_days"),
        "us30y_as_of": gate.get("as_of"),
        "defense_pct": _num(m_def.group(1)) if m_def else None,
    }

    data = {
        "month": month,
        "period": {"start": base_date, "end": cur_date, "days": len(snaps)},
        "assets": {"start": a0, "end": a1, "chg": a1 - a0, "pct": chg_pct(a1, a0),
                   "net_worth_start": _num(base.get("net_worth")),
                   "net_worth_end": _num(cur.get("net_worth")),
                   "liab_end": _num(cur.get("total_liabilities"))},
        "peak": {"date": peak_date, "value": peak_val},
        "trough": {"date": trough_date, "value": trough_val},
        "p2t": {"chg": trough_val - peak_val,
                "pct": chg_pct(trough_val, peak_val) if peak_val else None},
        "local_peak": {"date": local_peak_date,
                       "value": next((v for d, v in series if d == local_peak_date), None)},
        "local_peak_to_trough": {
            "chg": trough_val - next((v for d, v in series if d == local_peak_date), trough_val),
            "pct": chg_pct(trough_val, next((v for d, v in series if d == local_peak_date), None))},
        "attrib": attrib, "attrib_closure_gap": round(bucket_sum1 - a1, 1),
        "legs": legs, "securities": sec_rows, "funds": fund_rows, "policy": pol_rows,
        "tw": tw, "buys": buys, "pledge": pledge, "market": market,
        "series": [{"date": d, "assets": v, "index": idx.get(d)} for d, v in series],
        "penetration": (cur.get("penetration") or {}).get("actual_pct") or {},
        "cash": {"total": _num(cur.get("cash_total")),
                 "unrestricted": _num((cur.get("cash_layers") or {}).get("unrestricted_cash")),
                 "floor": LIFE_FLOOR},
    }
    data["market"]["usd_twd"] = ((cur.get("radar_state") or {}) if isinstance(cur.get("radar_state"), dict) else {}).get("twd")

    # ── 投資績效口徑（2026-11-19 使用者指正：-4% 是資產變動率，不是投資績效）
    #    恆等式：總資產變動 = 市場損益 + 帳務修正 + 淨投入 + 現金淨流
    #    市場損益 = 投資部位變動 − 帳務修正 − 本期投入（買進不再算報酬）
    _inv0 = sum(_num(b.get("start")) for b in attrib if not b["label"].startswith("現金"))
    _inv1 = sum(_num(b.get("end")) for b in attrib if not b["label"].startswith("現金"))
    _buy_cost = sum(_num(b.get("shares")) * _num(b.get("price")) for b in buys)
    _cash_chg = next((_num(b.get("chg")) for b in attrib if b["label"].startswith("現金")), 0.0)
    _cal = ((_load(BASE / "data" / "caliber_adjustments.json").get("months") or {}).get(month) or {})
    _adj = _num(_cal.get("total_adjustment"))
    _pnl_all = _inv1 - _inv0 - _buy_cost
    _pnl_mkt = _pnl_all - _adj
    _denom = _inv0 + _buy_cost / 2
    data["caliber"] = {
        "invest_start": _inv0, "invest_end": _inv1, "net_invest": _buy_cost,
        "pnl_total": _pnl_all, "accounting_adj": _adj, "pnl_market": _pnl_mkt,
        "pnl_market_pct": (_pnl_mkt / _denom * 100) if _denom else None,
        "assets_change": a1 - a0, "net_flow": _cash_chg,
        "items": _cal.get("items") or [],
        "source": "data/caliber_adjustments.json",
        "closure_gap": round((_pnl_all + _buy_cost + _cash_chg) - (a1 - a0), 1),
    }
    return data


def _legs(series, thr: float = 1.0):
    """ZigZag：以 1% 反轉確認轉折，把當月壓成「跌段／反彈段」交替"""
    if len(series) < 3:
        return [(series[0][0], series[-1][0])] if series else []
    pivots = [series[0]]
    dirn = 0
    for d, v in series[1:]:
        last = pivots[-1][1]
        if dirn == 0:
            if v > last:
                pivots[-1] = (d, v)
            elif (last - v) / last * 100 >= thr:
                pivots.append((d, v))
                dirn = -1
            continue
        if dirn < 0:
            if v < pivots[-1][1]:
                pivots[-1] = (d, v)
            elif (v - pivots[-1][1]) / pivots[-1][1] * 100 >= thr:
                pivots.append((d, v))
                dirn = 1
        else:
            if v > pivots[-1][1]:
                pivots[-1] = (d, v)
            elif (pivots[-1][1] - v) / pivots[-1][1] * 100 >= thr:
                pivots.append((d, v))
                dirn = -1
    if pivots[-1][0] != series[-1][0]:
        pivots.append(series[-1])
    return [(pivots[i][0], pivots[i + 1][0]) for i in range(len(pivots) - 1)]


def _short_name(n: str) -> str:
    n = re.sub(r"^[A-Z]{2,}EQ\d+\s+|^[A-Z]{2,}T\d+\s+", "", n or "")
    n = n.replace("基金", "").replace("美元", "USD").replace("台幣", "TWD")
    return n[:34]


# ---------------------------------------------------------------- 渲染
CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;padding:14px;background:#0b1220;color:#e2e8f0;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang TC","Microsoft JhengHei",sans-serif;
 font-size:14px;line-height:1.65;-webkit-text-size-adjust:100%}
h1{font-size:19px;margin:2px 0 4px}
h2{font-size:15px;margin:24px 0 8px;padding-left:9px;border-left:4px solid #f87171}
.card{background:#131c2e;border:1px solid #1f2b42;border-radius:12px;padding:12px 13px;margin:10px 0}
.hero{background:linear-gradient(135deg,#2a1013,#1b1420);border:1px solid #7f1d1d}
.sub{font-size:11.5px;color:#93a3bb}
.kpi{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.kpi>div{flex:1 1 96px;background:#0f1a2b;border:1px solid #1f2b42;border-radius:10px;padding:8px 9px}
.kpi .v{font-size:17px;font-weight:800;font-variant-numeric:tabular-nums;color:#fff}
.kpi .l{font-size:10.5px;color:#93a3bb;margin-top:2px}
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
th,td{padding:6px 4px;border-bottom:1px solid #1f2b42;vertical-align:top;text-align:left}
th{color:#93a3bb;font-weight:600;font-size:11px;background:#0f1a2b}
.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.neg{color:#f87171}.pos{color:#34d399}.dim{color:#93a3bb}
.kv{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px dashed #1f2b42}
.kv:last-child{border-bottom:0}
.kv b{color:#fff}
.warn{background:#2a1710;border:1px solid #7c2d12;color:#fed7aa}
.ok{background:#0f2418;border:1px solid #14532d;color:#bbf7d0}
ul{margin:6px 0 0;padding-left:18px}li{margin:5px 0}
.foot{margin:18px 0 6px;font-size:11px;color:#64748b}
.bar{height:6px;background:#1f2b42;border-radius:3px;overflow:hidden;margin-top:4px}
.bar>i{display:block;height:100%;background:#f87171}
.tag{display:inline-block;font-size:10.5px;padding:1px 7px;border-radius:999px;background:#1e3a5f;color:#93c5fd;border:1px solid #2b4c74;margin-right:5px}
.legend{font-size:11px;color:#93a3bb;margin-top:4px}
.legend i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin:0 4px 0 10px}
"""


def _chart(series: list[dict]) -> str:
    pts = [r for r in series if r["assets"]]
    if len(pts) < 3:
        return ""
    a0 = pts[0]["assets"]
    i0 = next((r["index"] for r in pts if r["index"]), None)
    w, h, pad_l, pad_r, pad_t, pad_b = 320, 172, 34, 44, 12, 22
    ys = []
    for r in pts:
        ys.append((r["assets"] / a0 * 100 - 100) if a0 else 0)
        if r["index"] and i0:
            ys.append((r["index"] / i0 * 100 - 100))
    lo, hi = min(ys + [-2]), max(ys + [1])
    span = (hi - lo) or 1

    def xy(i, v):
        x = pad_l + (w - pad_l - pad_r) * (i / max(1, len(pts) - 1))
        y = pad_t + (h - pad_t - pad_b) * (1 - (v - lo) / span)
        return x, y

    a_line = " ".join(f"{xy(i, r['assets'] / a0 * 100 - 100)[0]:.1f},{xy(i, r['assets'] / a0 * 100 - 100)[1]:.1f}"
                      for i, r in enumerate(pts) if a0 and r["assets"])
    i_line = " ".join(f"{xy(i, r['index'] / i0 * 100 - 100)[0]:.1f},{xy(i, r['index'] / i0 * 100 - 100)[1]:.1f}"
                      for i, r in enumerate(pts) if r["index"] and i0)
    grid = []
    v = -5
    while v > lo:
        y = xy(0, v)[1]
        grid.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" y2="{y:.1f}" stroke="#1f2b42" stroke-width="0.8"/>'
                    f'<text x="{pad_l - 5}" y="{y + 3:.1f}" fill="#64748b" font-size="8.5" text-anchor="end">{v}%</text>')
        v -= 5
    y0 = xy(0, 0)[1]
    labels = []
    for i in (0, len(pts) // 2, len(pts) - 1):
        x = xy(i, 0)[0]
        labels.append(f'<text x="{x:.1f}" y="{h - 6}" fill="#64748b" font-size="8.5" text-anchor="middle">{pts[i]["date"][5:]}</text>')
    a_end = pts[-1]["assets"] / a0 * 100 - 100 if a0 else 0
    last_x, last_y = xy(len(pts) - 1, a_end)
    return f"""<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" role="img" aria-label="當月資產與大盤走勢">
<line x1="{pad_l}" y1="{y0:.1f}" x2="{w - pad_r}" y2="{y0:.1f}" stroke="#334155" stroke-width="1"/>
{''.join(grid)}
<polyline points="{i_line}" fill="none" stroke="#60a5fa" stroke-width="1.6" stroke-linejoin="round"/>
<polyline points="{a_line}" fill="none" stroke="#f87171" stroke-width="2.2" stroke-linejoin="round"/>
<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3" fill="#f87171"/>
<text x="{last_x + 5:.1f}" y="{last_y + 3:.1f}" fill="#f87171" font-size="9" font-weight="700">{a_end:+.1f}%</text>
{''.join(labels)}
</svg>
<div class="legend"><i style="background:#f87171"></i>總資產（起算=100）<i style="background:#60a5fa"></i>加權指數</div>"""


def _attrib_table(d) -> str:
    """歸因表：帳面 vs 真實（扣帳務因素）。

    2026-11-19 使用者指正：基金帳面 -536,104 看似虧最多，實含日幣匯率記錯 -368,877，
    真實只 -167,227。故並列「帳務」與「真實變化」，占跌幅改以真實口徑計算。
    """
    _items = {i.get("class"): _num(i.get("amount"))
              for i in ((d.get("caliber") or {}).get("items") or [])}

    def _adj(label: str) -> float:
        if label.startswith("平台基金"):
            return _items.get("基金", 0.0)
        if label.startswith("證券"):
            return _items.get("股票", 0.0)
        if label.startswith("保單"):
            return _items.get("保單", 0.0)
        return 0.0

    _rows = []
    for r in sorted(d["attrib"], key=lambda x: x["chg"]):
        _a = _adj(r["label"])
        _real = _num(r["chg"]) - _a
        _rp = (_real / _num(r["start"]) * 100) if _num(r["start"]) else None
        _rows.append((r, _a, _real, _rp))
    _loss = sum(-x[2] for x in _rows if x[2] < 0) or 0.0

    rows = ""
    for r, _a, _real, _rp in _rows:
        _share = (abs(_real) / _loss * 100) if (_real < 0 and _loss) else None
        rows += (f'<tr><td>{r["label"]}</td>'
                 f'<td class="n {"neg" if r["chg"] < 0 else "pos"}">{signed_money(r["chg"])}'
                 f'<br><span style="color:#94a3b8;font-size:11px">{signed_pct(r["pct"])}</span></td>'
                 f'<td class="n">{signed_money(_a) if _a else "—"}</td>'
                 f'<td class="n {"neg" if _real < 0 else "pos"}">{signed_money(_real)}'
                 f'<br><span style="color:#94a3b8;font-size:11px">{signed_pct(_rp)}</span></td>'
                 f'<td class="n">{pct(_share, 0) if _share is not None else "—"}</td></tr>')
    _pol = next((x for x in _rows if x[0]["label"].startswith("保單")), None)
    _sec = next((x for x in _rows if x[0]["label"].startswith("證券")), None)
    _cmp = ""
    if _pol and _sec:
        _cmp = (f'部位 {money(_pol[0]["start"])} 的保單跌 {signed_pct(_pol[0]["pct"], 2)}，'
                f'虧的金額超過部位 {money(_sec[0]["start"])} 的證券跌 {signed_pct(_sec[0]["pct"], 2)}；'
                '只看金額會被部位大小誤導，看比例才看得出誰真的出問題。')
    return (f'<table><tr><th>部位</th><th class="n">帳面變化</th><th class="n">帳務</th>'
            f'<th class="n">真實變化</th><th class="n">占跌幅</th></tr>{rows}</table>'
            f'<div class="sub" style="margin-top:6px">真實＝帳面 − 帳務因素（日幣匯率記錯、ETF 除息時點差）；'
            f'占跌幅以真實口徑計算。{_cmp}</div>')


def _legs_table(d) -> str:
    rows = ""
    for L in d["legs"]:
        arrow = "↘" if L["chg"] < 0 else "↗"
        rows += (f'<tr><td>{L["from"][5:]} → {L["to"][5:]} {arrow}</td>'
                 f'<td class="n {"neg" if L["chg"] < 0 else "pos"}">{signed_money(L["chg"])}</td>'
                 f'<td class="n {"neg" if _num(L["pct"]) < 0 else "pos"}">{signed_pct(L["pct"])}</td>'
                 f'<td class="n {"neg" if _num(L["idx_pct"]) < 0 else "pos"}">{signed_pct(L["idx_pct"])}</td></tr>')
    return ('<table><tr><th>區間</th><th class="n">資產變化</th><th class="n">資產%</th>'
            f'<th class="n">大盤%</th></tr>{rows}</table>')


def _sec_table(d) -> str:
    rows = ""
    for r in d["securities"]:
        tag = ' <span class="tag">本月新進</span>' if r["new"] else ""
        rows += (f'<tr><td>{r["ticker"]}<div class="sub">{r["name"]}{tag}</div></td>'
                 f'<td class="n">{money(r["mv_start"])}</td><td class="n">{money(r["mv_end"])}</td>'
                 f'<td class="n {"neg" if _num(r["mtd_pct"]) < 0 else "pos"}">{signed_pct(r["mtd_pct"])}</td>'
                 f'<td class="n {"neg" if _num(r["p2t_pct"]) < 0 else "pos"}">{signed_pct(r["p2t_pct"])}</td>'
                 f'<td class="n {"neg" if _num(r["pnl_pct"]) < 0 else "pos"}">{signed_pct(r["pnl_pct"])}</td></tr>')
    return ('<table><tr><th>標的</th><th class="n">月初</th><th class="n">最新</th>'
            f'<th class="n">月內</th><th class="n">峰→谷</th><th class="n">未實現</th></tr>{rows}</table>')


def _fund_table(rows, title="") -> str:
    out = ""
    for r in rows:
        out += (f'<tr><td>{r["name"]}<div class="sub">{r["group"]}</div></td>'
                f'<td class="n">{money(r["start"])}</td><td class="n">{money(r["end"])}</td>'
                f'<td class="n {"neg" if r["chg"] < 0 else "pos"}">{signed_money(r["chg"])}</td>'
                f'<td class="n {"neg" if _num(r["pct"]) < 0 else "pos"}">{signed_pct(r["pct"])}</td></tr>')
    return ('<table><tr><th>基金</th><th class="n">月初</th><th class="n">最新</th>'
            f'<th class="n">變化</th><th class="n">%</th></tr>{out}</table>')


def render(d: dict, embedded: bool = False) -> str:
    a, m, tw, pl = d["assets"], d["market"], d["tw"], d["pledge"]
    cal = d.get("caliber") or {}
    mv_pct = cal.get("pnl_market_pct")
    mv_alpha = (mv_pct or 0) - (m["index_pct"] or 0)
    bond_row = next((r for r in d["securities"] if r["ticker"] == "00983D"), None)
    bond_pct = bond_row["mtd_pct"] if bond_row else None
    cash_pct = next((r["pct"] for r in d["attrib"] if r["label"].startswith("現金")), None)
    alpha = (a["pct"] or 0) - (m["index_pct"] or 0)
    tw_total_chg = tw["total"]["chg"]
    loss = a["chg"]
    buys = d["buys"]
    buys_txt = "、".join(f'{b["ticker"]} {b["shares"]} 股（{b["date"][5:]} @{b["price"]:,.2f}，現 {signed_pct(b["pct"])}）'
                         for b in buys) if buys else "無"

    title_tag = ("<div style=\"font-size:16px;font-weight:800;margin:2px 0 4px\">" if embedded else "<h1>")
    title_end = "</div>" if embedded else "</h1>"
    # 多殺多評估摘要（資料來自 market_squeeze.py；不存在就整卡略過）
    sq_card = ""
    try:
        _sq = json.loads((BASE / "data" / "market_squeeze.json").read_text(encoding="utf-8"))
    except Exception:
        _sq = {}
    if _sq:
        _p, _m, _i = _sq.get("pledge") or {}, _sq.get("market") or {}, _sq.get("index") or {}
        sq_card = f"""<div class="card">
  <div class="sub">同月份的市場結構評估</div>
  <div class="kv"><span>多殺多判定</span><b>{_sq.get('stage', '—')}</b></div>
  <div class="kv"><span>指數自波段高</span><b>{signed_pct(_i.get('from_peak'))}（{money(_i.get('now'))}）</b></div>
  <div class="kv"><span>可補繳現金能撐到</span><b>池跌 {pct(_p.get('cash_limit_drop'), 1)}（{wan(_p.get('avail_cash'))}）</b></div>
  <div style="margin-top:6px"><a href="market_squeeze_{_sq.get('date', '')}.html"
     style="color:#7dd3fc;font-weight:700;font-size:13px">→ 完整評估（四層證據／補繳預案／情境）</a></div>
</div>
"""

    head = f"""
<div class="card hero">
  {title_tag}📉 {d['period']['start']} → {d['period']['end']} 跌幅檢討{title_end}
  <div class="sub">資料：snapshot 快照 {d['period']['days']} 筆｜金額單位 TWD</div>
  <div class="kpi">
    <div><div class="v {'neg' if (mv_pct or 0) < 0 else ''}">{signed_pct(mv_pct, 2)}</div><div class="l">投資報酬<br>（市場價格變動）</div></div>
    <div><div class="v neg">{signed_money(cal.get('assets_change') or loss)}</div><div class="l">資產變動<br>{signed_pct(a['pct'])}</div></div>
    <div><div class="v">{signed_pct(mv_alpha, 1)}</div><div class="l">相對大盤<br>（大盤 {signed_pct(m['index_pct'])}）</div></div>
  </div>
  <div class="kv" style="margin-top:8px"><span>投資部位</span><b>{money(cal.get('invest_start'))} → {money(cal.get('invest_end'))}</b></div>
  <div class="kv"><span>帳務修正（不計入績效）</span><b>{signed_money(cal.get('accounting_adj'))}</b></div>
  <div class="kv"><span>本期投入（買進成本）</span><b>{money(cal.get('net_invest'))}</b></div>
  <div class="kv"><span>現金淨流動</span><b>{signed_money(cal.get('net_flow'))}</b></div>
  <div class="kv"><span>總資產</span><b>{money(a['start'])} → {money(a['end'])}</b></div>
  <div class="kv"><span>淨值（資產−負債）</span><b>{money(a['net_worth_start'])} → {money(a['net_worth_end'])}</b></div>
  <div class="kv"><span>質押 LTV（{pl.get('as_of') or '—'}）</span>
    <b>{pct(pl.get('ltv_pct'), 2)}（{pl.get('stage') or '—'}）</b></div>
</div>
"""

    caliber_card = f"""
<div class="card">
  <div class="sub">三個數字的差別（橫向加總剛好閉合）</div>
  <div class="kv"><span>① 投資報酬</span><b>{signed_pct(mv_pct, 2)}　只算市場價格變動</b></div>
  <div class="kv"><span>② 帳務修正</span><b>{signed_money(cal.get('accounting_adj'))}　日幣匯率記錯、ETF 除息時點差</b></div>
  <div class="kv"><span>③ 本期投入</span><b>{money(cal.get('net_invest'))}　買進成本，屬資金移動</b></div>
  <div class="kv"><span>④ 現金淨流動</span><b>{signed_money(cal.get('net_flow'))}　收支與買賣現金</b></div>
  <div class="kv"><span>＝ 資產變動</span><b>{signed_money(cal.get('assets_change'))}（{signed_pct(a['pct'])}）</b></div>
  <div class="sub" style="margin-top:6px">閉合差 {cal.get('closure_gap')}；帳務來源 {cal.get('source')}。
    <b>資產變動</b>是你帳戶實際少掉的金額，<b>投資報酬</b>才是投資表現——兩者不該混用同一個百分比。</div>
</div>
"""
    chart = caliber_card + f'<div class="card">{_chart(d["series"])}</div>'

    verdict = f"""
<h2>一、結論先講</h2>
<div class="card ok">
  <ul>
    <li><b>跌幅本身不大，問題在結構。</b>大盤 {signed_pct(m['index_pct'])}，投資報酬只 {signed_pct(mv_pct, 2)}（少跌 {mv_alpha:.1f}pp；資產變動 {signed_pct(a['pct'])} 另含帳務與金流）——
        資產配置有效，因為台股只占 {pct(d['penetration'].get('台股市值型成長'))}、七成是美元資產。</li>
    <li><b>但「台股純度」的部位全軍覆沒。</b>證券＋保單內台股＋平台台股基金合計 {wan(tw['total']['start'])} → {wan(tw['total']['end'])}，
        虧 {signed_money(tw_total_chg)}（{signed_pct(tw['total']['pct'])}），佔整體虧損的
        {(tw_total_chg / loss * 100) if loss else 0:.0f}%。跌的錢幾乎都在台股。</li>
    <li><b>抗跌的不是「防守桶」，是債券與現金。</b>防守合併口徑 {pct(m['defense_pct'])} 這個月照樣跌，
        因為月配基金實質是股債混合；真正守住的是 00983D（{signed_pct(bond_pct)}）與現金（{signed_pct(cash_pct)}）。</li>
    <li><b>真正該盯的是質押水位。</b>LTV {pct(pl.get('ltv_pct'), 2)} 已在警戒區（{pct(pl.get('green_cap'))}–{pct(pl.get('stop_line'))}），
        距 {pct(pl.get('stop_line'))} 停止線只剩 {pl.get('buffer_pp'):.2f}pp／池值可再跌 {abs(pl.get('pool_can_drop') or 0):.2f}%
        —— 帳面 −{abs(a['pct'] or 0):.1f}% 已經吃掉大半緩衝。</li>
  </ul>
</div>
{sq_card}
"""

    attrib = f"""
<h2>二、錢從哪裡消失</h2>
<div class="card">
  {_attrib_table(d)}
  <div class="sub" style="margin-top:6px">月末閉合差 {money(d['attrib_closure_gap'])}（應為 0，非 0 表示 snapshot 科目未對齊）</div>
</div>
<div class="card">
  <div class="sub"><b>跌的兩段，性質不同</b></div>
  {_legs_table(d)}
  <div class="sub" style="margin-top:6px">第一段：大盤 {signed_pct(next((L['idx_pct'] for L in d['legs'] if L['chg'] < 0), None))} 我們只小跌（部位在台股比重低）；
    中間反彈我們只吃三分之一 —— 這是低台股比重的代價，也是這波沒重傷的原因；第二段補跌最傷，因為主動型 ETF 與台股基金跌更多。</div>
</div>
"""

    sec = f"""
<h2>三、證券逐檔（依月內跌幅排序）</h2>
<div class="card">{_sec_table(d)}
<div class="sub" style="margin-top:6px">峰→谷＝{d['peak']['date']} 高點 → {d['trough']['date']} 低點，用來分辨「本來就弱」與「這波被殺」。</div>
</div>
"""

    pol = f"""
<h2>四、保單與平台基金</h2>
<div class="card">
  <div class="sub"><b>保單帳戶（安聯 A/B＋第一金）</b>｜保單被當成防守，但 B 帳戶裡藏著台股</div>
  {_fund_table(d['policy'])}
</div>
<div class="card">
  <div class="sub"><b>平台基金（國泰直購＋鉅亨）</b></div>
  {_fund_table(d['funds'][:12])}
</div>
"""

    tw_block = f"""
<h2>五、台股純度（把藏在保單與基金裡的台股挖出來）</h2>
<div class="card">
  <table>
    <tr><th>位置</th><th class="n">月初</th><th class="n">最新</th><th class="n">變化</th><th class="n">%</th></tr>
    <tr><td>證券（ETF／個股，排除債券與 S&amp;P500）</td><td class="n">{money(tw['securities']['start'])}</td>
      <td class="n">{money(tw['securities']['end'])}</td>
      <td class="n neg">{signed_money(tw['securities']['chg'])}</td><td class="n neg">{signed_pct(tw['securities']['pct'])}</td></tr>
    <tr><td>保單內台股基金（元大卓越50、元大高股息龍頭）</td><td class="n">{money(tw['policy']['start'])}</td>
      <td class="n">{money(tw['policy']['end'])}</td>
      <td class="n neg">{signed_money(tw['policy']['chg'])}</td><td class="n neg">{signed_pct(tw['policy']['pct'])}</td></tr>
    <tr><td>平台台股基金（鉅亨／路博邁、0050 連結、台新日圓級別）</td><td class="n">{money(tw['platform']['start'])}</td>
      <td class="n">{money(tw['platform']['end'])}</td>
      <td class="n neg">{signed_money(tw['platform']['chg'])}</td><td class="n neg">{signed_pct(tw['platform']['pct'])}</td></tr>
    <tr><th>合計</th><th class="n">{money(tw['total']['start'])}</th><th class="n">{money(tw['total']['end'])}</th>
      <th class="n neg">{signed_money(tw['total']['chg'])}</th><th class="n neg">{signed_pct(tw['total']['pct'])}</th></tr>
  </table>
  <div class="sub" style="margin-top:6px">「台股市值型 12.0%」只算到證券與穿透後的市值型部位；保單/平台裡的台股基金在報表上被歸類為「配息」，
    實際曝險比報表顯示的高 —— 這是本月最該修的口徑。</div>
</div>
"""

    idx_by_date = {r["date"]: r["index"] for r in d["series"] if r["index"]}
    act = [r for r in d["securities"] if r["ticker"] in ("00981A", "00984A", "00927")]
    act_mv = sum(r["mv_end"] for r in act)
    act_chg = sum(_num(r["mv_end"]) - _num(r["mv_start"]) for r in act)
    act_pct = chg_pct(act_mv, act_mv - act_chg) if act_mv else None
    big_fund = max(((r["end"], r["name"]) for r in d["funds"]), default=(0, ""))
    conc = (big_fund[0] / pl["collateral"] * 100) if pl.get("collateral") else None
    buy_rebound = None
    if buys and idx_by_date:
        bd = buys[0]["date"]
        prior = [v for k, v in idx_by_date.items() if k < bd]
        if prior and idx_by_date.get(bd):
            buy_rebound = (idx_by_date[bd] / min(prior) - 1) * 100

    market = f"""
<h2>六、當時市場發生什麼</h2>
<div class="card">
  <div class="kv"><span>加權指數（10 月末 → {d['trough']['date']}）</span><b>{money(m['index_start'])} → {money(m['index_end'])}（{signed_pct(m['index_pct'])}）</b></div>
  <div class="kv"><span>{d['local_peak']['date']} 波段高 → {d['trough']['date']}</span><b>{money(m['index_peak'])} → {money(m['index_end'])}（{signed_pct(m['index_peak_pct'])}）</b></div>
  <ul>
    <li><b>主跌段是 AI 供應鏈估值重定價，不是基本面衰退。</b>外資連三賣、ABF 載板／CCL 自高點修正 40–50%，
        但金融股同期逆勢創高 → 屬單點去槓桿，不是系統風險（來源：11/19 緊急應變報告）。</li>
    <li><b>台股跌得比美股重。</b>同期 S&amp;P 僅小跌、費半幾乎持平，台股卻 {signed_pct(m['index_pct'])} →
        本地槓桿與主動型 ETF 補跌，跌的是估值不是獲利。</li>
    <li><b>長天期殖利率仍在高檔。</b>US30Y {pct(m['us30y'], 2)}（紅線 {pct(m['us30y_red'], 2)}，已連 {m['us30y_streak']} 日）→
        債券價格受壓，所謂「債券抗跌」是相對抗跌，不是不跌。</li>
  </ul>
  <div class="sub">指數來源：{', '.join(sorted(set(m['sources'].values())))}｜US30Y 讀值日 {m['us30y_as_of'] or '—'}</div>
</div>
"""

    review = f"""
<h2>七、檢討（事實 → 根因 → 修正）</h2>
<div class="card warn">
  <ol style="margin:6px 0 0;padding-left:18px">
    <li><b>「防守 {pct(m['defense_pct'])}」這個數字會騙人。</b>它這個月照樣虧，因為口徑是「有沒有配息」，
        不是「抗不抗跌」——月配基金是股債混合（股 38–65%），保單 B 帳戶裡還有
        {wan(tw['policy']['start'])} 的台股基金（本月 {signed_pct(tw['policy']['pct'])}）。<br>
        <span class="dim">根因：</span>防守用配息分類，把「有現金流」誤當成「低波動」。<br>
        <span class="dim">修正（提案，待裁決）：</span>另設「抗跌口徑」＝債券＋現金＝
        {pct((d['penetration'].get('債券') or 0) + (d['penetration'].get('現金/安全網') or 0))}，
        日報並列顯示；月配基金不再自動歸防守。</li>
    <li><b>主動型 ETF 是最大單一虧損源。</b>{'/'.join(r['ticker'] for r in act)} 本月合計
        {signed_money(act_chg)}（{signed_pct(act_pct)}），同期大盤 {signed_pct(m['index_pct'])} —— 跌幅是大盤的
        {abs((act_pct or 0) / (m['index_pct'] or 1)):.1f} 倍。<br>
        <span class="dim">根因：</span>主動型／主題型 ETF 的 Beta 放大，且全押 AI 題材，等於在 12% 的台股桶裡再集中一次。<br>
        <span class="dim">修正（提案，待裁決）：</span>主動型 ETF 合計上限總資產 10%、不再新增；
        反彈至成本 −10% 內分批減。</li>
    <li><b>加碼當下，質押已在警戒區。</b>本月買進：{buys_txt}。
        {f"買進日 LTV {buys[0]['ltv_at_buy']:.2f}%、且指數自波段低點已反彈 {buy_rebound:.1f}% —— 買在反彈第一根。" if buys and buy_rebound is not None else ""}
        依 11/18 才上線的階段制（45–53%＝警戒、不加碼），這兩筆現在不該成立；11/10 當時用舊規則（≤53% 視為綠燈）所以合法。
        <span class="dim">（買進日期為快照入帳日，實際成交可能在前一交易日。）</span><br>
        <span class="dim">根因：</span>舊規則把 45–53% 當綠燈，讓「接近停止線」看起來像安全；且建倉條件只有價格區間，沒有趨勢確認。<br>
        <span class="dim">修正（提案，待裁決）：</span>加碼前檢查 LTV 階段＝綠（&lt;{pct(pl.get('green_cap'))}），
        並要求指數自波段低點反彈 ≥5% 且 5 日不破前低；單批金額減半。</li>
    <li><b>高點沒減碼，問題在「報表說法」不一致，不是規則。</b>{d['local_peak']['date']} 指數 {money(m['index_peak'])}、
        美股超配 {"+{:.1f}pp".format((d['penetration'].get('美股市值型成長') or 0) - 30)}，結果整段沒減。
        閘門明明寫「{pl.get('sell_role') or '減碼不受本函式限制'}」，
        但雷達週計劃把它印成「煞車中，只回報不動作」→ 執行端依簡報行事，就變成什麼都沒做。<br>
        <span class="dim">根因：</span>同一條規則在兩份產出有兩種說法（閘門＝減碼可執行；週計劃＝不動作）。<br>
        <span class="dim">修正（提案，待裁決）：</span>雷達週計劃的美股列改讀 <code>us30y_gate.減碼角色</code>，
        不得自行寫成煞車；並在日報加一行「可執行減碼」。</li>
    <li><b>真正該盯的是質押水位，不是帳面 −{abs(a['pct'] or 0):.1f}%。</b>LTV {pct(pl.get('ltv_pct'), 2)}
        （{pl.get('stage')}，綠線 &lt;{pct(pl.get('green_cap'))}、停止線 {pct(pl.get('stop_line'))}），
        距停止線只剩 {pl.get('buffer_pp'):.2f}pp／池值可再跌 {abs(pl.get('pool_can_drop') or 0):.2f}%；
        且單一基金（{big_fund[1]}）占池 {pct(conc)}。<br>
        <span class="dim">根因：</span>池值被當成「離追繳線還很遠」的靜態數字，沒有當每日水位；集中度沒有上限。<br>
        <span class="dim">修正（提案，待裁決）：</span>池值列每日第一順位；單一基金占池上限 50%（現 {pct(conc)} 已觸線），
        跌 3% 就先算好補繳金額（不動作，先備好）。</li>
  </ol>
</div>
"""

    nxt = f"""
<h2>八、下一步（只列既有規則現況，沒有新動作）</h2>
<div class="card">
  <table>
    <tr><th>項目</th><th class="n">現況</th><th>觸發／門檻</th><th>動作</th></tr>
    <tr><td>台股加碼（B6–B10）</td><td class="n">{pct(d['penetration'].get('台股市值型成長'))}</td>
        <td>解凍三條件：US30Y &lt; {pct(m['us30y_red'], 2)}、LTV 階段回綠（&lt;{pct(pl.get('green_cap'))}）、現金 ≥100 萬
        （未達：{'、'.join(pl.get('unfreeze_missing') or []) or '—'}）</td><td>暫停，等條件到位</td></tr>
    <tr><td>美股減碼</td><td class="n">{pct(d['penetration'].get('美股市值型成長'))}（目標 30%）</td>
        <td>不受 US30Y 限制（減碼恆可執行）；單筆 ≤20 萬、4–6 週</td><td>可執行，未執行</td></tr>
    <tr><td>主動型 ETF</td><td class="n">{wan(act_mv)}</td>
        <td>提案上限 10% 總資產（現 {pct(act_mv / (a['end'] or 1) * 100)}）</td><td>待裁決</td></tr>
    <tr><td>質押池</td><td class="n">LTV {pct(pl.get('ltv_pct'), 2)}</td>
        <td>池值再跌 {abs(pl.get('pool_can_drop') or 0):.2f}% → 觸 {pct(pl.get('stop_line'))} 停止線</td><td>不加碼、先備補繳金額</td></tr>
    <tr><td>現金</td><td class="n">{wan(d['cash']['total'])}</td>
        <td>生活底線 {wan(d['cash']['floor'])}；可動用 {wan(d['cash']['unrestricted'])}</td><td>不動</td></tr>
  </table>
</div>
<div class="card">
  <div class="sub"><b>這個月做對的事（不要因為檢討就改掉）</b></div>
  <ul>
    <li>恐慌段（{d['legs'][0]['to'] if d['legs'] else ''} 指數 {money(d['legs'][0]['idx_to']) if d['legs'] else '—'}）
        沒有賣出任何部位 —— 賣在低點會讓回撤變成永久的。</li>
    <li>沒有追高：全月只按計畫買 {len(buys)} 筆、合計 {wan(sum(_num(b.get('shares')) * _num(b.get('price')) for b in buys))}，
        其餘現金留著。</li>
    <li>保單不因短期淨值回落轉換（本月維持）—— 轉換只會在成本更高的時候發生。</li>
    <li>台股只有 {pct(d['penetration'].get('台股市值型成長'))}，所以大盤 {signed_pct(m['index_pct'])} 時只 {signed_pct(a['pct'])}；
        低台股比重是這波沒重傷的主因，不要因為「少賺」就拉高。</li>
  </ul>
</div>
"""

    foot = f"""
<div class="foot">產生時間 {d['period']['end']}｜drawdown_review.py（資料驅動，可重跑）｜
來源：snapshot.json、每日快照 {d['period']['days']} 筆、緊急應變報告／日報加權指數
{"｜完整頁：drawdown_review_" + d['month'] + ".html" if embedded else ""}<br>
本頁為紀律檢討，非投資建議；第 ①③④⑤ 條的規則修正屬提案，需你裁決後才寫入 thresholds。</div>
"""

    body = head + chart + verdict + attrib + sec + pol + tw_block + market + review + nxt
    if embedded:
        patch_css = """<style>
.kpi{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.kpi>div{flex:1 1 96px;background:#0f1a2b;border:1px solid #1f2b42;border-radius:10px;padding:8px 9px}
.kpi .v{font-size:17px;font-weight:800;font-variant-numeric:tabular-nums;color:#fff}
.kpi .l{font-size:10.5px;color:#93a3bb;margin-top:2px}
.neg{color:#f87171}.pos{color:#34d399}.dim{color:#93a3bb}
.bar{height:6px;background:#1f2b42;border-radius:3px;overflow:hidden;margin-top:4px}
.bar>i{display:block;height:100%;background:#f87171}
.tag{display:inline-block;font-size:10.5px;padding:1px 7px;border-radius:999px;background:#1e3a5f;color:#93c5fd;border:1px solid #2b4c74;margin-right:5px}
.legend{font-size:11px;color:#93a3bb;margin-top:4px}
.legend i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin:0 4px 0 10px}
</style>"""
        body = patch_css + head + verdict + attrib + review + f"""
<div class="card"><div class="sub">完整逐檔、保單/基金拆解與市場事件：
<a href="drawdown_review_{d['month']}.html" style="color:#7dd3fc"><b>開啟完整檢討頁 →</b></a></div></div>""" + foot
        return body
    return f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{d['month']} 跌幅檢討｜龍九控股</title><style>{CSS}</style></head>
<body>{body}{foot}</body></html>
"""


def section_html(month: str | None = None) -> str:
    """給其他頁面嵌入的精簡版；資料不足時回空字串（不讓母頁壞掉）"""
    try:
        return render(compute(month or _default_month()), embedded=True)
    except Exception as e:  # noqa: BLE001
        return f'<div class="card warn">跌幅檢討未產生：{e}</div>'


def _default_month() -> str:
    try:
        return str(_load(BASE / "snapshot.json").get("date"))[:7]
    except Exception:
        import datetime
        return datetime.date.today().strftime("%Y-%m")


def main():
    month = sys.argv[1] if len(sys.argv) > 1 else _default_month()
    d = compute(month)
    out_html = BASE / f"drawdown_review_{month}.html"
    out_html.write_text(render(d), encoding="utf-8", newline="\n")
    (BASE / "data").mkdir(exist_ok=True)
    (BASE / "data" / f"drawdown_{month}.json").write_text(
        json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    a = d["assets"]
    print(f"✅ {out_html.name}｜{d['period']['start']}→{d['period']['end']}"
          f"｜總資產 {money(a['start'])}→{money(a['end'])}（{signed_pct(a['pct'])}）"
          f"｜大盤 {signed_pct(d['market']['index_pct'])}｜閉合差 {money(d['attrib_closure_gap'])}")
    return d


if __name__ == "__main__":
    main()
