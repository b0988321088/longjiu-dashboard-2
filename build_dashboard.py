#!/usr/bin/env python3
"""build_dashboard.py — 儀表板動態注入（2026-08-26 建立）
問題：index_template.html 大量寫死財務值（保單/現金/配息/房租）→ 一鍵更新後儀表板舊值
解法：每次從 snapshot.json 讀真值 → replace 模板寫死值 → 產 index.html
用法：python build_dashboard.py（sync_all 已整合為步驟）
"""
from report_components import band_filter as _band_filter
import json, re
import public_mask  # 2026-10-12 資安處置：公開面遮蔽（唯一實作）
from datetime import date, timedelta
from pathlib import Path
from scripts.components.volatility_monitor import make_volatility_report
from dividend_caliber import bucket_of
import passive_caliber as _pcal  # 2026-09-27 被動收入口徑唯一來源（保守/實收/壓力 + FI 跑道）
from sot_targets import (sot_monthly_expense, sot_monthly_income, dry_display,  # INC-270 月支出／月收入單一入口；2026-10-11 工單A 乾粉顯示單一實作
                         defensive_caliber)  # 2026-10-15 P1-1：防守（配息資產合計）真值單一來源

BASE = Path(__file__).resolve().parent

def dividend_bucket(name: str) -> str:
    """配息條目 → 儀表板三桶鍵（委派 dividend_caliber.bucket_of，單一口徑）。

    2026-09-23：本函式原本自帶一份分類規則（與投資績效／日報／追蹤器共 4 份副本）
    → 已收斂為呼叫正典；一次性項（台灣特品現金股息）在儀表板仍歸 other（另列不計入三桶）。
    """
    _b = bucket_of(name)
    return "other" if _b == "oneoff" else _b


def _fmt(n):
    return f"{n:,.0f}"


def cash_caliber(snap):
    """現金底線（SoT＝thresholds_2026_0915.現金_twd）。

    2026-09-27 使用者裁示：現金底線＝**單一口徑**生活底線 700,000（取消 9/15 加設的追繳緩衝 50 萬）。
    2026-09-25 INC cash_floor_two_calibers_unlabeled 的「雙口徑未標示」問題隨此裁示消滅 →
    顯示端一律單口徑；`single` 旗標保留（buffer<=0 時為 True）供未來恢復多層底線時切換。
    """
    cw = ((snap.get("thresholds_2026_0915") or {}).get("現金_twd") or {})
    life = float(cw.get("生活底線") or snap.get("cash_floor") or 0)
    buf = float(cw.get("追繳緩衝") or 0)
    cash_all = float(snap.get("cash_total") or snap.get("cash") or 0)
    # 2026-09-29 使用者核准（restricted 隔離）：指定用途款（質押撥款待清償）不可當乾粉/生活緩衝
    # → 本口徑的 cash ＝ 可動用現金；真實現金另以 cash_all 回傳（現金合計卡仍顯示真值）。
    from sot_targets import restricted_cash as _rst_fn   # 單一實作（CIO minor3）
    restricted = _rst_fn(snap)
    cash = max(0.0, cash_all - restricted)
    total = float(cw.get("合計底線") or (life + buf))
    return {
        "cash": cash, "cash_all": cash_all, "restricted": restricted,
        "life": life, "buffer": buf, "total": total,
        # 2026-10-11 工單A：`dry` 維持「餘裕」（≥0）語意；新增 dry_signed（有正負號）與
        #   shortfall（短少）。消費端**禁止**再寫 `dry or 舊值`——乾粉不足時 dry=0 會讓
        #   falsy 判斷回退到 snapshot.乾粉執行_0926 的 9/29 值（119,182），把短少洗成餘裕。
        "dry": max(0.0, cash - life),
        "dry_signed": int(round(cash - life)),
        "shortfall": int(round(max(0.0, life - cash))),
        "life_ok": cash >= life,
        "gap": max(0.0, total - cash),
        "single": buf <= 0,   # 2026-09-27：單一口徑（追繳緩衝取消）→ 顯示端省略緩衝字樣
    }

def relay_schedule_html(stations) -> str:
    """配息接力戰略時序（三站卡片）— 2026-10-10 動態化。

    原寫死在 index_template.html（每月停在舊月份）；改由 snapshot.relay_stations 生成，
    更新配息時間／T+4截止只需改 snapshot，不必動模板。配息基準日唯一來源仍為 relay_calendar.md。
    """
    _order = [("第一站（月初）", "emerald"), ("第二站（月中）", "blue"), ("第三站（月底）", "emerald")]
    _cards = []
    for _key, _color in _order:
        _st = (stations or {}).get(_key)
        if not isinstance(_st, dict):
            continue
        _fund = str(_st.get("基金", "") or "")
        _payout = str(_st.get("配息時間", "") or "")
        _t4 = str(_st.get("T+4截止", "") or "")
        _desc = str(_st.get("說明") or _st.get("流向") or "")
        _m = re.search(r"([0-9]{1,2}/[0-9]{1,2})", _payout)
        _first = _m.group(1) if _m else ""
        _m2 = re.match(r"([0-9/]+)", _t4)
        _t4s = _m2.group(1) if _m2 else _t4
        _tag = _key.split("（")[0]
        _cards.append(f"""                <div class="relative pl-6 border-l-2 border-{_color}-500">
                    <div class="absolute -left-1.5 top-1.5 w-3 h-3 bg-{_color}-500 rounded-full"></div>
                    <div class="flex justify-between items-center">
                        <h4 class="text-xs font-bold text-{_color}-400">【{_tag} {_first}】{_fund}</h4>
                        <span class="text-[10px] bg-{_color}-500/20 text-{_color}-300 px-2 py-0.5 rounded">基準 {_first}｜T+4截止 {_t4s}</span>
                    </div>
                    <p class="text-xs text-slate-300 mt-1">{_desc}</p>
                </div>""")
    return (chr(13) + chr(10)).join(_cards) if _cards else '                <p class="text-xs text-slate-400">接力資料待更新</p>'

def build_perf_card(snap):
    """投資績效卡（2026-10-31 使用者裁決：四分類，只列可算項）。

    口徑鐵則（不得放寬）：
    - 股票＝成本基礎累計報酬（非年化、非 XIRR；XIRR 待 Moneybook 資金流重建）
    - 保單＝市值 vs 投入成本；累計配息只列參考，不得當報酬率（配息型可能含本金返還）
    - 基金無成本基礎 → 只列市值，不計算報酬
    - 淨值雙軌：含房（財富面）／流動（流動性面）；房產估值非可動用現金
    回傳 (html, as_of)
    """
    def _n(v):
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    def _m(v):
        return f"{v:,.0f}"

    def _pct(v):
        try:
            return f"{float(v):+.2f}%"
        except Exception:
            return "—"

    sec = snap.get("securities") or {}
    mv = _n(sec.get("total_market_value") or snap.get("securities_total"))
    up = _n(sec.get("unrealized_pnl"))
    up_pct = sec.get("unrealized_pnl_pct")
    rp = _n(sec.get("realized_pnl"))
    cost = mv - up
    ins = _n(snap.get("insurance_total"))
    p_cost = _n(snap.get("allianz_cost")) + _n(snap.get("firstjin_cost"))
    p_div = _n(snap.get("allianz_cum_dividend")) + _n(snap.get("firstjin_cum_dividend"))
    fund = _n(snap.get("funds_total"))
    ta = _n(snap.get("total_assets"))
    tl = _n(snap.get("total_liabilities"))
    re_v = _n(snap.get("real_estate_value"))
    na_l = ta - tl
    na_i = _n(snap.get("net_worth_incl_re")) or (ta + re_v - tl)
    re_asof = str(snap.get("real_estate_value_as_of") or "2026-08-08（佐證待補）")
    as_of = str(sec.get("price_date") or snap.get("securities_price_date")
                or snap.get("last_updated") or "—")

    def cell(label, main, color, subs):
        sub_html = "".join(f'<span class="mr-2">{x}</span>' for x in subs)
        return (f'<div class="p-2 rounded-lg bg-slate-800/60">'
                f'<div class="flex items-baseline justify-between gap-2">'
                f'<span class="text-slate-300">{label}</span>'
                f'<b class="{color}">{main}</b></div>'
                f'<div class="text-[10px] text-slate-400 mt-1 leading-snug">{sub_html}</div></div>')

    cells = []
    # ① 金融投資（股票）
    _c = "text-emerald-400" if up >= 0 else "text-red-400"
    cells.append(cell("金融投資（股票）", f"{up:+,.0f}（{_pct(up_pct)}）", _c,
                      [f"市值 {_m(mv)}", f"成本 {_m(cost)}", f"已實現 {rp:+,.0f}"]))
    # ② 保單
    p_gap = ins - p_cost
    p_gap_pct = (p_gap / p_cost * 100) if p_cost else 0
    _c2 = "text-emerald-400" if p_gap >= 0 else "text-red-400"
    cells.append(cell("保單（帳面）", f"{p_gap:+,.0f}（{p_gap_pct:+.2f}%）", _c2,
                      [f"市值 {_m(ins)}", f"投入 {_m(p_cost)}",
                       f"累計配息 {_m(p_div)}（含本金返還，不列報酬）"]))
    # ③ 基金
    cells.append(cell("基金（僅市值）", _m(fund), "text-slate-100",
                      ["無成本基礎 → 依 10/31 定案不計算報酬", "XIRR 待資金流重建"]))
    # ④ 財富（雙軌淨值）
    _c3 = "text-emerald-400" if na_i >= 0 else "text-red-400"
    _c4 = "text-emerald-400" if na_l >= 0 else "text-red-400"
    cells.append(cell("含房淨值", _m(na_i), _c3,
                      [f'流動淨值 <b class="{_c4}">{na_l:,.0f}</b>',
                       f"房產 {_m(re_v)}（估值 {re_asof}，非可動用）"]))
    return "".join(cells), as_of


def build_perf_month_card(snap):
    """本月投資績效＋資金成本（2026-10-31 使用者要求加入儀表板）。

    鐵則：全部走 performance_core.monthly_performance（唯一計算層）與
    build_investment_performance.load_loans（負債口徑單一來源），本函式不自行算績效公式。
    資金成本淨利差用「保守常態配息」口徑（與投資績效月報一致），不混當月實收。
    """
    import datetime as _dt
    import sqlite3 as _sq
    import performance_core as _pc
    import build_investment_performance as _bip

    def _m(v):
        try:
            return f"{float(v):,.0f}"
        except Exception:
            return "—"

    ym = str(snap.get("date") or _dt.date.today().isoformat())[:7]
    adj = _bip.load_adjust()
    a = adj.get(ym, {}) or {}
    db = _sq.connect(str(BASE / "dragon_assets.db"))
    try:
        core = _pc.monthly_performance(ym, snap=snap, adjust_all=adj, db=db,
                                       reliable=bool(a.get("市值可靠", True)))
    finally:
        db.close()
    rows = {x["c"]: x for x in core["rows"]}
    grand = sum(x["pnl"] for x in core["rows"])

    loans = _bip.load_loans(snap, a.get("資金成本", {}))
    bal = sum(l["balance"] for l in loans)
    m_int = sum(l["monthly"] for l in loans)
    m_pay = sum(l["payment"] for l in loans)
    wacc = (m_int * 12 / bal) if bal else 0
    inv = ((snap.get("securities_total_market_value") or 0)
           + (snap.get("funds_total") or 0) + (snap.get("insurance_total") or 0))
    div_m = snap.get("dividend_month_expected") or 100000
    dy = (div_m * 12 / inv) if inv else 0
    spread = dy - wacc
    if spread >= 0.012:
        lc, lt = "text-emerald-400", "🟢 充足"
    elif spread >= 0:
        lc, lt = "text-yellow-400", "🟡 偏薄"
    else:
        lc, lt = "text-red-400", "🔴 為負"

    p_cost = (snap.get("allianz_cost") or 0) + (snap.get("firstjin_cost") or 0)
    p_div = (snap.get("allianz_cum_dividend") or 0) + (snap.get("firstjin_cum_dividend") or 0)
    p_real = ((snap.get("insurance_total") or 0) - p_cost) + p_div

    def cell2(label, main, color, subs):
        sub_html = "".join(f'<span class="mr-2">{x}</span>' for x in subs)
        return (f'<div class="p-2 rounded-lg bg-slate-800/60">'
                f'<div class="flex items-baseline justify-between gap-2">'
                f'<span class="text-slate-300">{label}</span>'
                f'<b class="{color}">{main}</b></div>'
                f'<div class="text-[10px] text-slate-400 mt-1 leading-snug">{sub_html}</div></div>')

    out = []
    _cg = "text-emerald-400" if grand >= 0 else "text-red-400"
    out.append(cell2(f"本月投資績效（{ym}）", f"{grand:+,.0f}", _cg, [
        f"股票 {_m(rows.get('股票', {}).get('pnl'))}",
        f"基金 {_m(rows.get('基金', {}).get('pnl'))}",
        f"保單 {_m(rows.get('保單', {}).get('pnl'))}",
    ]))
    out.append(cell2("資金成本（加權）", f"{wacc*100:.2f}%/年", "text-slate-100", [
        f"借款 {_m(bal)}",
        f"純月息 {_m(m_int)}／月付 {_m(m_pay)}",
    ]))
    out.append(cell2("配息殖利率 vs 成本", f"{spread*100:+.2f}pp {lt}", lc, [
        f"保守月配 {_m(div_m)}→殖利率 {dy*100:.2f}%",
        "口徑＝保守常態（非當月實收）",
    ]))
    _cp = "text-emerald-400" if p_real >= 0 else "text-red-400"
    out.append(cell2("保單累計真實績效", f"{p_real:+,.0f}", _cp, [
        f"投入 {_m(p_cost)}",
        f"帳面 {_m((snap.get('insurance_total') or 0) - p_cost)}＋累計配息 {_m(p_div)}",
    ]))
    return ('<div class="mt-3 pt-3 border-t border-slate-700/60">'
            '<div class="text-[11px] text-teal-300 font-bold mb-1">本月績效與資金成本</div>'
            '<div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-slate-200">'
            + "".join(out) + "</div></div>")


# ─────────────────────────────────────────────────────────────
# 每月收入與獲利總覽（2026-10-31 規格 v2）
# 鐵則：算不出就「—」；不補 0、不用估算、不用上月值頂替；
#       配息分類不命中 → unclassified（不得自動歸基金/ETF）；
#       房貸利息四道檢查任一失敗 → 「利息資料待核」，房租淨收益整列不計算。
# ─────────────────────────────────────────────────────────────
def _mio_n(v, default=None):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _mio_money(v):
    return f"{v:,.0f}" if isinstance(v, (int, float)) else "—"


def _mio_pct(part, whole):
    try:
        return f"{part / whole * 100:.1f}%"
    except Exception:
        return "—"


def _mio_norm(s):
    return str(s).replace("（", "(").replace("）", ")").replace(" ", "").strip()


def _mio_liab_rows(limit=120):
    """讀 liabilities 最近 N 筆（新→舊）。失敗回 []，不編造。"""
    try:
        import sqlite3
        con = sqlite3.connect(str(BASE / "dragon_assets.db"))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT date, mortgage_yy, mortgage_yydu, mortgage_xz, mortgage_cathay "
            "FROM liabilities ORDER BY date DESC LIMIT ?", (limit,)).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"  ⚠️ monthly_overview：讀 liabilities 失敗 ({e})")
        return []


def _mio_paid_actual(snap, month):
    """MB 當月房貸實扣（結構化 `mortgage_paid_actual[YYYY-MM]` = {"永豐": x, "國泰": y}）。

    缺／格式不符 → None（不可從 note 文字或推導值回填）。僅支援分帳結構，
    因國泰為按日計息（30 天 25,644／31 天 26,498），與永豐年化月付不同口徑，
    合併成單一總額會讓 ±10 互證失去意義。
    """
    m = snap.get("mortgage_paid_actual") or {}
    if not isinstance(m, dict):
        return None
    v = m.get(month)
    if not isinstance(v, dict):
        return None
    out = {"永豐": _mio_n(v.get("永豐")), "國泰": _mio_n(v.get("國泰"))}
    if out["永豐"] is None and out["國泰"] is None:
        return None
    return out


def _mio_interest(snap, rows, paid_actual=None):
    """房貸利息：C1 本金推導（月差法優先／同月 7 日備援）＋ C4 三態互證。

    回傳 (interest or None, detail, tag, status)
      status = VERIFIED（MB 實扣互證）／DERIVED_UNVERIFIED（僅推導）／FAIL（不可用或矛盾）
    C1 鐵則：月差法須為不同月份；本金須介於月付 30%–100%，
             過大＝提前還本／額外撥款淨額，過小＝疑部分扣款，一律不採用。
    """
    if not rows or len(rows) < 2:
        return None, {}, "無餘額歷史", "FAIL"
    from datetime import date as _date

    def _d(x):
        return _date.fromisoformat(str(x)[:10])

    def _sum3(r):
        vals = [r.get(k) for k in ("mortgage_yy", "mortgage_yydu", "mortgage_xz")]
        if any(v is None for v in vals):
            return None
        return sum(float(v) for v in vals)

    try:
        rows = sorted(rows, key=lambda r: str(r.get("date"))[:10], reverse=True)
        cur = rows[0]
        cur_d = _d(cur["date"])
    except Exception:
        return None, {}, "日期解析失敗", "FAIL"
    cur_m = cur_d.strftime("%Y-%m")
    bal_cur = _sum3(cur)
    if bal_cur is None:
        return None, {}, "本期餘額欄位缺值", "FAIL"

    det = {}
    P = None
    source = ""
    # ── C1-A 月差法：上月最後一筆 vs 本月最後一筆（不同月份才算）
    prev_rows = []
    for r in rows[1:]:
        try:
            if _d(r["date"]).strftime("%Y-%m") < cur_m:
                prev_rows.append(r)
        except Exception:
            continue
    if prev_rows:
        prev = sorted(prev_rows, key=lambda r: str(r["date"])[:10], reverse=True)[0]
        bal_prev = _sum3(prev)
        if bal_prev is not None:
            try:
                gap = (cur_d - _d(prev["date"])).days
            except Exception:
                gap = None
            if gap and gap > 0:
                _p = round(bal_prev - bal_cur)
                det.update({"d0": str(prev["date"])[:10], "d1": str(cur["date"])[:10], "gap": gap})
                if _p > 0:
                    P, source = _p, "month_diff"
    # ── C1-B 備援：同月扣款前後 ≤7 天（僅在月差法不可用時）
    if P is None:
        intra = []
        for r in rows[1:]:
            if str(r["date"])[:10][:7] == cur_m:
                intra.append(r)
                break
        if intra:
            cand = intra[0]
            bal_c = _sum3(cand)
            if bal_c is not None:
                try:
                    gap = (cur_d - _d(cand["date"])).days
                except Exception:
                    gap = None
                _p = round(bal_c - bal_cur)
                if gap and 0 < gap <= 7 and _p > 0:
                    P, source = _p, "intra_month"
                    det.update({"d0": str(cand["date"])[:10], "d1": str(cur["date"])[:10], "gap": gap})
    if P is None:
        return None, det, "本金無法推導（無有效月差或扣款前後餘額）", "FAIL"

    syn = _mio_n(snap.get("mortgage_sinopac_monthly"), 0) or 0
    cat = _mio_n(snap.get("mortgage_cathay_monthly"), 0) or 0
    _dd = snap.get("mortgage_due_day") or {}
    det.update({"P": P, "source": source, "sinopac": syn, "bal": bal_cur,
                "due_day": (_dd.get("永豐") if isinstance(_dd, dict) else None)})
    # 本金合理性（排除提前還本／額外撥款淨額／部分扣款）
    if P >= syn:
        return None, det, "含提前還本或額外撥款", "FAIL"
    if P < syn * 0.3:
        return None, det, "本金偏低疑部分扣款", "FAIL"
    I = round(syn - P)
    I_cathay = round(cat)
    rate = (I * 12 / bal_cur * 100) if bal_cur else 0
    det.update({"I": I, "rate": round(rate, 2), "I_cathay": I_cathay})
    if not (1.5 <= rate <= 4.0):
        return None, det, "隱含利率異常", "FAIL"
    cr = _mio_n(snap.get("mortgage_cathay_rate"), 0) or 0
    if cr:
        exp_cat = float(snap.get("mortgage_cathay") or 0) * cr / 12
        if abs(exp_cat - cat) > max(1.0, exp_cat * 0.01):
            det["exp_cat"] = round(exp_cat)
            return None, det, "國泰利息與利率不符", "FAIL"

    total = I + I_cathay
    det["total"] = total
    # ── C4 三態（獨立證據；P+I≈月付 不算驗證）
    if paid_actual is None:
        det.update({"paid_actual": None, "diff": None})
        return total, det, "", "DERIVED_UNVERIFIED"
    _py = paid_actual.get("永豐")
    _pc = paid_actual.get("國泰")
    if _py is None:
        det.update({"paid_actual": None, "diff": None})
        return total, det, "", "DERIVED_UNVERIFIED"
    _dy = round((P + I) - _py)
    det.update({"paid_yf": round(_py), "diff_yf": _dy})
    if abs(_dy) > 10:
        return None, det, f"永豐實扣差 {_dy:+,.0f}（>10）", "FAIL"
    if _pc is not None:
        _dc = round(I_cathay - _pc)
        det.update({"paid_cathay": round(_pc), "diff_cathay": _dc})
        # 國泰按日計息（30/31 天差約 350），容忍 400；超出視為矛盾
        if abs(_dc) > 400:
            return None, det, f"國泰實扣差 {_dc:+,.0f}（>400）", "FAIL"
    return total, det, "", "VERIFIED"


def _mio_div_split(snap, month):
    """配息逐筆分類（精確字串查表；未命中 → unclassified，不自動歸類）。"""
    rec = (snap.get("dividend_records") or {}).get(month) or {}
    cmap = snap.get("dividend_class_map") or {}
    nmap = {_mio_norm(k): v for k, v in cmap.items()}
    out = {"policy_credit": 0.0, "fund": 0.0, "etf": 0.0, "unclassified": []}
    total = 0.0
    for name, amt in rec.items():
        if not isinstance(amt, (int, float)):
            continue
        total += float(amt)
        cls = nmap.get(_mio_norm(name))
        if cls in ("policy_credit", "fund", "etf"):
            out[cls] += float(amt)
        else:
            out["unclassified"].append((name, float(amt)))
    return out, total


def _mio_opening(history):
    """期初＝當月第一筆（本月最早一筆）。

    2026-10-31 實作修正：原設計取「上月最後一筆」，但 2026-09-30 條目處於保單借貸
    4,000,000 清償過渡期（負債含借貸、資產未同步），9/30→10/1 淨值憑空跳增 1,978,063，
    直接採用會把帳務重分類誤顯示為「本月賺 215 萬」。改取本月第一筆（2026-10-01），
    與使用者規格驗收基準一致（10/1→10/31）。回傳 (entry or None, 標籤)。
    """
    if not history:
        return None, "歷史資料不足"
    dates = sorted(history)
    cur_m = dates[-1][:7]
    same = [d for d in dates if d[:7] == cur_m]
    if same:
        return history[min(same)], ""
    return None, "歷史資料不足"


def build_monthly_overview(snap, history):
    """回傳 (card_html, trace_html, status_html)。"""
    month = str(snap.get("date") or "")[:7]
    warn = []

    # ── 六個數字 ──
    sal = _mio_n(snap.get("monthly_salary"))
    if sal is None:
        sal = _mio_n(snap.get("salary"))
    if sal is None:
        sr = (snap.get("salary_records") or {}).get(month)
        sal = _mio_n((sr or {}).get("實發") or (sr or {}).get("amount")) if isinstance(sr, dict) else _mio_n(sr)
    rent = _mio_n(snap.get("rent_monthly_actual"), _mio_n(snap.get("rent_monthly_total")))
    div = _mio_n(snap.get("dividend_month_actual"), _mio_n(snap.get("monthly_dividend_total")))
    exp = _mio_n(snap.get("monthly_expense"))
    basis = _mio_n(snap.get("working_surplus"))

    have_all = all(x is not None for x in (sal, rent, div, exp))
    total_income = (sal + rent + div) if have_all else None
    surplus = (total_income - exp) if have_all else None
    if not have_all:
        warn.append("收入三項或支出缺值 → 總收入／盈餘不計算")

    # ── 配息分類 ──
    split, div_raw = _mio_div_split(snap, month)
    div_sum = split["policy_credit"] + split["fund"] + split["etf"] + sum(a for _, a in split["unclassified"])
    if abs(div_sum - div_raw) > 1:
        warn.append("配息分類不平，數字暫不採計")
    if split["unclassified"]:
        warn.append("配息有未分類項目，不得歸入基金／ETF")

    # ── 房貸利息與房租淨收益 ──
    liab = _mio_liab_rows()
    _paid = _mio_paid_actual(snap, month)
    interest, idet, itag, istatus = _mio_interest(snap, liab, _paid)
    rent_net = None
    _irs = ""
    if interest is not None and rent is not None:
        rent_net = rent - interest
        _irs = "MB 實扣互證" if istatus == "VERIFIED" else "推導值，未與 MB 實扣互證"
    elif itag:
        warn.append(f"利息資料待核（{itag}）→ 房租淨收益不計算")

    # ── 期初與損益 ──
    prev, ptag = _mio_opening(history)
    sec = snap.get("securities") or {}
    up_now = _mio_n(sec.get("unrealized_pnl"))
    rp_now = _mio_n(sec.get("realized_pnl"))
    op = snap.get("unrealized_pnl_opening") or {}
    _ost = str(op.get("source_type") or "")
    up_open = None
    up_note = ""
    if op:
        if _ost == "manual_provisional":
            up_open = _mio_n(op.get("value"))
            up_note = (f"†人工補值 {op.get('as_of')}（{op.get('source_ref')}）"
                       if up_open is not None else "人工補值缺值")
        elif _ost == "system":
            up_open = _mio_n(op.get("value"))
        else:
            # 來源不可信（缺 source_type）→ 不採用，且不再回退 history（避免把人工值偽裝成系統值）
            up_note = "期初來源不可信（缺 source_type）"
    if up_open is None and not op:
        if prev is not None and prev.get("unrealized_pnl") is not None:
            up_open = _mio_n(prev.get("unrealized_pnl"))
            up_note = f"期初 {prev.get('date')}"
        else:
            up_note = ptag or "歷史資料不足"
    up_chg = (up_now - up_open) if (up_now is not None and up_open is not None) else None

    fund_now = _mio_n(snap.get("funds_total"))
    ins_now = _mio_n(snap.get("insurance_total"))
    fund_chg = (fund_now - _mio_n(prev.get("fund_market"))) if (prev and fund_now is not None and prev.get("fund_market") is not None) else None
    ins_chg = (ins_now - _mio_n(prev.get("insurance_current"))) if (prev and ins_now is not None and prev.get("insurance_current") is not None) else None

    na_now = _mio_n(snap.get("net_worth_incl_re"))
    na_open = None
    if prev:
        if prev.get("net_worth_incl_re") is not None:
            na_open = _mio_n(prev.get("net_worth_incl_re"))
        elif prev.get("real_estate") is not None:
            na_open = _mio_n(prev.get("total_assets")) + _mio_n(prev.get("real_estate")) - _mio_n(prev.get("total_liabilities"))
    na_chg = (na_now - na_open) if (na_now is not None and na_open is not None) else None
    na_note = "含配息入帳與市價波動，非投資報酬"
    try:
        _pl = _mio_n(prev.get("total_liabilities")) if prev else None
        _cl = _mio_n(snap.get("total_liabilities"))
        if _pl is not None and _cl is not None and exp:
            _jump = abs(_pl - _cl)
            if _jump > exp * 3:
                na_chg = None
                na_note = f"期間負債變動 {_jump:,.0f}（結構性，如保單借貸清償）→ 月度淨值變化不可比"
    except Exception:
        pass

    # ── 卡片 HTML ──
    def big(label, value, sub, color="text-emerald-400"):
        return (f'<div class="p-3 rounded-lg bg-slate-800/60">'
                f'<div class="text-[10px] text-slate-400">{label}</div>'
                f'<div class="text-xl font-bold {color} mt-0.5">{value}</div>'
                f'<div class="text-[10px] text-slate-400 mt-1 leading-snug">{sub}</div></div>')

    def line(label, value, color="text-slate-100", note=""):
        note_html = ('<div class="text-[10px] text-slate-500">' + note + '</div>') if note else ""
        return (f'<div class="flex items-baseline justify-between gap-2 text-[11.5px] py-0.5">'
                f'<span class="text-slate-300">{label}</span>'
                f'<span class="{color} font-semibold">{value}</span></div>' + note_html)

    inc_txt = "—"
    if total_income is not None:
        inc_txt = (f'薪資 {_mio_money(sal)}（{_mio_pct(sal, total_income)}）· '
                   f'房租 {_mio_money(rent)}（{_mio_pct(rent, total_income)}）· '
                   f'配息 {_mio_money(div)}（{_mio_pct(div, total_income)}）')
    sur_color = "text-emerald-400" if (surplus or 0) >= 0 else "text-red-400"
    sur_txt = (f"{surplus:+,.0f}" if surplus is not None else "—")
    basis_txt = (f"基準口徑 {basis:+,.0f}（配息保守採計 100,000）" if basis is not None else "基準口徑 —")

    div_lines = []
    div_lines.append(line("基金／ETF 配息", _mio_money(split["fund"] + split["etf"])))
    div_lines.append(line("保單撥回", _mio_money(split["policy_credit"]), "text-amber-300",
                          "可能包含本金返還，尚未確認實際收益成分"))
    if split["unclassified"]:
        _uamt = sum(a for _, a in split["unclassified"])
        div_lines.append(line(f"未分類 {len(split['unclassified'])} 筆", _mio_money(_uamt), "text-red-400",
                              "待人工確認，不得歸基金／ETF"))
    div_lines.append(line("合計現金入帳", _mio_money(div_raw), "text-slate-100"))

    cards = [
        big("本月總收入", _mio_money(total_income), inc_txt),
        big("本月收支盈餘（實收）", sur_txt, basis_txt, sur_color),
        (f'<div class="p-3 rounded-lg bg-slate-800/60">'
         f'<div class="text-[10px] text-slate-400">本月配息拆解</div>'
         f'<div class="mt-1">{"".join(div_lines)}</div></div>'),
    ]

    # 次要：損益（非報酬）
    def chg_txt(v, suffix=""):
        return f"{v:+,.0f}{suffix}" if isinstance(v, (int, float)) else "—"

    sec_lines = [
        line("股票未實現損益變動", chg_txt(up_chg),
             "text-emerald-400" if (up_chg or 0) >= 0 else "text-red-400",
             "未實現損益變動，非完整總報酬" + (f"｜{up_note}" if up_note else "")),
        line("股票已實現損益", chg_txt(rp_now)),
        line("基金帳面變動", chg_txt(fund_chg), "text-slate-100",
             (f"含申購資金，不視為本月增值｜期初 {prev.get('date')}" if fund_chg is not None else "歷史資料不足")),
        line("保單帳面變動", chg_txt(ins_chg), "text-slate-100",
             (f"與保單撥回分開呈現｜期初 {prev.get('date')}" if ins_chg is not None else "歷史資料不足")),
        line("房租淨收益", chg_txt(rent_net),
             "text-emerald-400" if (rent_net or 0) >= 0 else "text-red-400",
             (f"租金 {_mio_money(rent)} − 利息 {_mio_money(interest)}（{_irs}）｜房屋稅、地價稅、修繕未計"
              if rent_net is not None else "利息資料待核，不計算")),
        line("含房淨值變化", chg_txt(na_chg),
             "text-emerald-400" if (na_chg or 0) >= 0 else "text-red-400", na_note),
    ]

    card_html = (
        f'<div class="grid grid-cols-1 sm:grid-cols-3 gap-2">{"".join(cards)}</div>'
        f'<div class="mt-2 p-3 rounded-lg bg-slate-800/40">'
        f'<div class="text-[10px] text-slate-400 mb-1">本月資產損益（非報酬）</div>'
        f'{"".join(sec_lines)}</div>'
    )

    # ── 追溯明細 ──
    tr = []
    tr.append(f'<div class="text-[11px] text-slate-300">本月總收入：'
              f'月薪 {_mio_money(sal)}（monthly_salary）＋ 房租 {_mio_money(rent)}（rent_monthly_actual）'
              f'＋ 配息 {_mio_money(div)}（dividend_month_actual）＝ <b>{_mio_money(total_income)}</b></div>')
    drec = (snap.get("dividend_records") or {}).get(month) or {}
    dlist = "、".join(f"{k} {v:,.0f}" for k, v in sorted(drec.items(), key=lambda x: -x[1]) if isinstance(v, (int, float)))
    tr.append(f'<div class="text-[11px] text-slate-400 mt-1">配息逐筆（{len(drec)} 筆）：{dlist}</div>')
    if interest is not None:
        _psrc = "月差法" if idet.get("source") == "month_diff" else "同月扣款前後備援"
        _pv = (f'；MB 實扣 {idet.get("paid_actual"):,.0f}，差 {idet.get("diff"):+,.0f}'
               if idet.get("paid_actual") is not None else "；MB 實扣未結構化（本值為推導）")
        tr.append(f'<div class="text-[11px] text-slate-400 mt-1">房租淨收益：租金 {_mio_money(rent)} − '
                  f'永豐利息 {idet.get("I"):,.0f}（月付 {_mio_n(idet.get("sinopac"), 0):,.0f} − 本金 {idet.get("P"):,.0f}，{_psrc}）'
                  f'− 國泰利息 {idet.get("I_cathay"):,.0f}；餘額日 {idet.get("d0")}→{idet.get("d1")}（{idet.get("gap")} 天）'
                  f'；隱含年利率 {idet.get("rate")}%；互證 {istatus}'
                  f'；扣款日 {str(idet.get("due_day")) + " 日" if idet.get("due_day") else "未知（未結構化）"}{_pv}</div>')
    else:
        _pv2 = (f'；MB 實扣 {idet.get("paid_actual"):,.0f}，差 {idet.get("diff"):+,.0f}'
                if idet.get("paid_actual") is not None else "")
        tr.append(f'<div class="text-[11px] text-amber-400 mt-1">房租淨收益：利息資料待核（{itag}）{_pv2}</div>')
    tr.append(f'<div class="text-[11px] text-slate-400 mt-1">股票損益：期初 {_mio_money(up_open)}'
              f'{("（" + up_note + "）") if up_note else ""} ／期末 {_mio_money(up_now)}／差 {chg_txt(up_chg)}；'
              f'已實現 {_mio_money(rp_now)}</div>')
    tr.append(f'<div class="text-[11px] text-slate-400 mt-1">含房淨值變化：期初 {_mio_money(na_open)}／'
              f'期末 {_mio_money(na_now)}／差 {chg_txt(na_chg)}；外部淨投入 0（收入非新投入）</div>')
    trace_html = ('<details class="mt-2"><summary class="cursor-pointer text-[11px] text-teal-300">'
                  '▸ 追溯明細（每個數字怎麼來的）</summary>'
                  f'<div class="mt-1 p-2 rounded bg-slate-900/60">{"".join(tr)}</div></details>')

    status_html = ""
    if warn:
        status_html = ('<div class="mt-2 text-[10.5px] text-amber-300 bg-amber-500/10 rounded px-2 py-1">'
                       + "；".join(warn) + "</div>")
    return card_html, trace_html, status_html


def main():
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    tpl = (BASE / "index_template.html").read_text(encoding="utf-8")
    # 2026-09-01 修正：系統時間寫死（原模板 2026-08-29）→ 動態當天
    import datetime as _dt
    tpl = tpl.replace("系統時間：2026-08-29", "系統時間：" + _dt.date.today().strftime("%Y-%m-%d"))

    # 2026-09-10 資金在途（贖回在途款）：未入帳前不沖銷資產（使用者 9/10 指正）
    _pr = snap.get("pending_redemption") or {}
    if _pr:
        _pending_note = (
            '<span class="font-bold text-sky-300">💰 資金在途（' + str(_pr.get("贖回日", "")) + '）：</span>'
            '<span class="text-slate-300">' + str(_pr.get("項目", "")) + " "
            + _fmt(_pr.get("金額", 0)) + " 已送贖回，款項在途（預期 " + str(_pr.get("入帳日_預期", "")) + " 入帳）。"
            + "⚠️ 入帳前不沖銷資產：仍計入基金市值，總資產維持 " + _fmt(snap.get("total_assets", 0))
            + "；實際入帳後才 基金→現金 轉列（以實際入帳金額為準）。</span>"
        )
    else:
        _pending_note = ""
    tpl = tpl.replace("__PENDING_REDEMPTION__", _pending_note)

    # 2026-09-11 修：US30Y 曾寫死「5.22%（8/28 收盤）」→ 改動態讀 us30y_state.json
    # 2026-10-14 v1.2（TD-20261015-02）P3 修正：紅線門檻與兩種連續天數皆改讀真值，
    #   不再寫死 5.30，也不再拿模式A 的 streak 冒充「紅線連續 N 日」。
    try:
        _st30 = json.loads((BASE / "us30y_state.json").read_text(encoding="utf-8"))
        _r30 = float(_st30["last_rate"])
        _d30 = _st30.get("last_date", "")
    except Exception:
        _st30, _r30, _d30 = {}, None, ""
    try:
        import us30y_monitor as _mon30
        _rl30 = float(_mon30.RED_LINE)
    except Exception:
        _rl30 = None
    _ma30 = _st30.get("mode_a_streak")
    _rlst30 = _st30.get("red_line_streak")
    _role = _st30.get("gate_role") or "宏觀風險警示（不否決台股分批；長債新增凍結）"
    if _r30 is None or _rl30 is None:
        _us30y_line = "US30Y 資料無法取得（us30y_state.json／門檻缺漏）"
    else:
        _streaks = []
        if isinstance(_ma30, (int, float)):
            _streaks.append(f"模式A警戒連續 {int(_ma30)} 日")
        if isinstance(_rlst30, (int, float)):
            _streaks.append(f"紅線 ≥{_rl30:.2f}% 連續 {int(_rlst30)} 日")
        _s_txt = ("；".join(_streaks) + "；") if _streaks else ""
        _gap = _r30 - _rl30
        _rel = f"已站上紅線 {_gap:.2f}pp" if _gap >= 0 else f"距紅線 {abs(_gap):.2f}pp"
        _us30y_line = (f"US30Y {_r30:.2f}%（{_d30} 收盤；{_s_txt}{_rel}）"
                       f"＝{_role}（v1.2）")
    tpl = tpl.replace("__US30Y_LINE__", _us30y_line)

    # ── 從 snapshot 計算真值 ──
    cash = snap.get("cash_total", 0) or 0
    ins = snap.get("insurance_total", 0) or 0
    allianz = snap.get("allianz_combined", 0) or 0
    firstjin = snap.get("firstjin_fl65_current_value", snap.get("firstjin_current_value", 0)) or 0
    cum_div = snap.get("firstjin_cum_dividend", 0) or 0   # 2026-10-10：移除寫死退路 111,513
    mdb = snap.get("monthly_dividend_breakdown", {}) or {}
    # 2026-08-29 修正：配息一律用 dividend_records 當月實收（mdb 是常態預估口徑，
    # 之前用 mdb 覆蓋模板實收值 → 第一金顯示 35,583 常態被標「已入帳」，實收應為 25,538）
    # 2026-09-01 修正：月份動態化（原寫死 2026-08 → 9月仍顯示 8 月配息 138,627）
    import datetime as _dt
    _today_m = _dt.date.today().strftime("%Y-%m")
    _dr = snap.get("dividend_records", {}).get(_today_m, {}) or {}
    firstjin_div = sum(v for k, v in _dr.items() if "第一金" in k and isinstance(v, (int, float))) or 0
    az_div = _dr.get("安聯保單撥回", 0) or 0
    div_ins = az_div + firstjin_div
    div_total = sum(v for k, v in _dr.items() if isinstance(v, (int, float))) or 0
    expense = sot_monthly_expense(snap)
    if not expense:
        raise ValueError("snapshot.monthly_expense <= 0：拒絕以 0 當分母（詳見 sot_monthly_expense）")
    # 薪水（當月已收，salary_records 動態）
    salary = 0
    for k, v in (snap.get("salary_records", {}) or {}).items():
        if str(k).startswith(_today_m):
            salary += (v.get("amount", 0) if isinstance(v, dict) else v) or 0

    # 租金已收（當月）
    rent_got = 0
    for k, v in (snap.get("rent_received_records", {}) or {}).items():
        if str(k).startswith(_today_m):
            if isinstance(v, dict):
                rent_got += sum(x for x in v.values() if isinstance(x, (int, float)))
            elif isinstance(v, (int, float)):
                rent_got += v
    got_total = salary + div_total + rent_got

    # ── replace 模板寫死值（2026-08-26 盤點清單）──
    rep = {
        "111,513": _fmt(cum_div),          # 第一金累計配息
        "102,469": _fmt(div_ins),          # 保單配息合計（實收）— 2026-09-26 補：模板 441 行殘留 8 月舊值
        "25,538": _fmt(firstjin_div),      # 第一金本月領息
        "772,607": _fmt(cash),             # 現金（2026-08-31 補：8/30 template 值 → 777,767）
        "162,781": _fmt(expense),          # 月支出
    }
    # ── 雷達＋本週投資計劃（2026-08-29：模板寫死 8/23 舊版 → 讀 radar_state.json 動態）──
    try:
        import json as _json
        from pathlib import Path as _Path
        _rd_path = _Path(__file__).resolve().parent / "radar_state.json"
        if _rd_path.exists():
            _rd = _json.loads(_rd_path.read_text(encoding="utf-8"))
            _sig = _rd.get("signals", {}) or {}
            _signals_txt = "｜".join(
                f"{k}{v.get('color','')}" for k, v in _sig.items() if v.get("color")
            )
            _pn = _rd.get("policy_notes", {}) or {}
            _policy_txt = ""
            _titles = {"新聞1_華許升息": "華許放鷹（升息）", "新聞2_美委石油協議": "美委石油協議", "新聞3_伊朗戰爭SPR": "伊朗戰爭SPR"}
            for _k, _v in _pn.items():
                if isinstance(_v, dict):
                    _c = _v.get("內容", "")
                    _imp = _v.get("對資產影響", "")
                    _t = _titles.get(_k, _k)
                    if _c:
                        _policy_txt += (("｜" if _policy_txt else "") + f"{_t}：{_imp or _c[:30]}")
                elif isinstance(_v, str) and _v and _k in ("原油綜合判斷", "債券升息敏感度"):
                    _policy_txt += (("｜" if _policy_txt else "") + _v[:45])
            if not _policy_txt:
                _policy_txt = "無重大政策變動"
            # 本週計劃（同 institutional_flow 結論邏輯，精簡版）
            _pen2 = snap.get("penetration", {}).get("actual_pct", {}) or {}
            _tg2 = snap.get("penetration", {}).get("targets", {}) or {}
            # 2026-09-13：乾粉 = 台幣現金 − 生活底線（現算；原讀 乾粉執行_0926 的 8/22 舊值會與現金 % 矛盾）
            # 2026-09-25 INC cash_floor_two_calibers_unlabeled：現金口徑一律由 cash_caliber 派生
            _cw3 = cash_caliber(snap)
            # 2026-10-11 工單A：乾粉＝可動用現金 − 現金底線（有正負號）。移除「0 就回退
            #   snapshot.乾粉執行_0926 舊值（119,182）」的路徑——負值被 max(0,·) 夾成 0 後，
            #   falsy 判斷會把過期正值寫進下游報告（10/11 週報/eval 即此症狀）。
            _dry2 = _cw3["dry_signed"]
            _usd2 = snap.get("usd_exposure_monitor", {}).get("current", {}).get("合計", 0)
            from usd_advisory import cap as _usd_cap_fn   # 2026-10-07 裁決②：政策門檻單一來源
            _usd_cap2 = float(_usd_cap_fn(snap) or 60)
            # 2026-09-13：本週計劃改讀 radar_state.weekly_plan.rows（單一來源＝institutional_flow 產出）
            # 原為 7 行貼死文字（含「9/11簽約」「Fed 9/11 CPI / 9/16 FOMC」等過期日期）
            _plan = [f"{r.get('動作','')} {r.get('類別','')}：{r.get('內容','')}"
                     for r in ((_rd.get("weekly_plan", {}) or {}).get("rows") or []) if r.get("內容")]
            _plan.append(f"📊 台股穿透 {_pen2.get('台股市值型成長', 0):.1f}%（目標 {_tg2.get('台股市值型目標', 10)}%，缺口 {_tg2.get('台股市值型目標', 10) - _pen2.get('台股市值型成長', 0):+.1f}pp）")
            _plan.append(f"💰 {dry_display(_cw3, 'wan')}（現金 {_cw3['cash']:,.0f} − 現金底線 {_cw3['life']:,.0f} 守 "
                         + ("🟢 達標" if _cw3['life_ok'] else f"🔴 未達標（缺 {_cw3['life'] - _cw3['cash']:,.0f}）") + "）")
            if snap.get("usd_exposure_monitor", {}).get("advisory_only"):
                # 2026-10-07 裁決①③：美元曝險僅顯示、不觸發＋觀測線命名（門檻讀單一來源）
                from usd_advisory import tier_limit_text as _usd_tl
                _plan.append(f"🟡 美元曝險 {_usd2}%（{_usd_tl(snap)}）→ 僅顯示，不觸發美股減碼；政策門檻待 10 月戰略檢討")
            elif _usd2 > _usd_cap2:
                _plan.append(f"🔴 美元曝險 {_usd2}% 超標（目標值 ≤{_usd_cap2:.0f}%）→ 美股減碼")
            else:
                _plan.append(f"🟡 美元曝險 {_usd2}%（目標值 ≤{_usd_cap2:.0f}%）→ 續觀察")
            if not _plan:
                _plan = ["待雷達更新"]
            rep["__RADAR_DATE__"] = _rd.get("last_run", "2026-08-29")[:10]
            rep["__RISK_UPDATED__"] = rep["__RADAR_DATE__"]   # 風險提示標籤的資料日＝雷達資料日（不再寫死）

            # ── 風險提示區塊動態化（2026-09-13 INC-166：原為 8/23 寫死文字，已與現況矛盾）──
            _rows2 = ((_rd.get("weekly_plan", {}) or {}).get("rows") or [])
            def _row_of(_cat):
                for _r in _rows2:
                    if (_r.get("類別") or "").strip() == _cat:
                        return _r
                return {}
            _brief2 = lambda _t: ((_t or "").split("→")[0].strip())

            # ── 2026-10-15 TD-20261015-05（真 CIO 工作區審查 blocking②）──
            # 雷達週計畫（institutional_flow 週一/三產出）內寫死的桶位數字，在真值更新後會與同頁
            # CEO 卡（讀 snapshot.penetration 即時值）不一致 → 同頁兩個官方美股比例（36.4% vs 36.2%）。
            # 修法：顯示層把「桶位%／目標／偏差pp／分母／理論調整／以總資產為分母之比率／乾粉」
            # 一律改寫為 snapshot 即時推導值（單一來源）；政策文字與動作階梯完全不動。
            _lp = (snap.get("penetration", {}) or {}).get("actual_pct", {}) or {}
            _lt = (snap.get("penetration", {}) or {}).get("targets", {}) or {}
            _lta = float(snap.get("total_assets") or 0)
            _pk = {"台股": ("台股市值型成長", "台股市值型目標"),
                   "美股": ("美股市值型成長", "美股市值型目標"),
                   "防守": ("防守型配息", "配息型目標"),
                   "債券": ("債券", "債券型目標"),
                   "現金": ("現金/安全網", "現金目標")}

            def _live_row(_r):
                _cat = (_r.get("類別") or "").strip()
                _t = _r.get("內容") or ""
                _keys = _pk.get(_cat)
                if not (_keys and _lta > 0):
                    return _r
                _a = _lp.get(_keys[0])
                _g = _lt.get(_keys[1])
                if _a is None or _g is None:
                    return _r
                _a = float(_a)
                _g = float(_g)
                _d = _a - _g
                # ①（X.X% vs 目標Y%，超配/缺口 ±Z.Zpp）
                _t = re.sub(r"（\d+(?:\.\d+)?%\s*vs\s*目標\s*\d+(?:\.\d+)?%\s*，\s*(?:超配|缺口)\s*[+\-]\d+(?:\.\d+)?pp）",
                            f"（{_a:.1f}% vs 目標{_g:.0f}%，{'超配' if _d >= 0 else '缺口'} {_d:+.1f}pp）", _t)
                # ②X.X%（目標 Y%）
                _t = re.sub(r"(?<![\d.])-?\d+(?:\.\d+)?%（目標\s*\d+(?:\.\d+)?%）",
                            f"{_a:.1f}%（目標 {_g:.0f}%）", _t)
                # ③行首裸桶位百分比（如現金列「3.9% → 底線…」）
                _t = re.sub(r"^\s*-?\d+(?:\.\d+)?%", f"{_a:.1f}%", _t)
                # ④戰略偏差 ±Z.Zpp
                _t = re.sub(r"(戰略偏差\s*)[+\-]\d+(?:\.\d+)?pp",
                            lambda m: f"{m.group(1)}{_d:+.1f}pp", _t)
                # ⑤分母／理論調整（＝|偏差|÷100 × 分母）
                _t = re.sub(r"分母\s*[\d,]+", f"分母 {_lta:,.0f}", _t)
                if "理論調整" in _t:
                    _t = re.sub(r"理論調整\s*[\d,]+", f"理論調整 {abs(_d) / 100 * _lta:,.0f}", _t)
                    _t = re.sub(r"理論\s*[\d,]{7,}", f"理論 {abs(_d) / 100 * _lta:,.0f}", _t)
                # ⑥「配息資產合計 A ÷ 總資產 B = C%」：分子／分母／比率同一口徑、同一 as-of
                #    （2026-10-15 P1-1 修復）原版只換分母、保留 radar 舊分子 → 印出
                #    「配息資產合計 17,802,228 ÷ 總資產 26,992,475 = 66.0%」，與 CEO 卡
                #    「防守合併 65.9%（真值 17,774,779）」同頁互斥。修法：分子改讀
                #    sot_targets.defensive_caliber（配息資產合計真值，單一來源），比率由
                #    分子÷分母現算 → 三者自洽可核對；真值不可得則保留原文並留痕（fail-visible）。
                _dv = 0.0
                if "配息資產合計" in _t:
                    try:
                        _dv = float((defensive_caliber(snap) or {}).get("金額") or 0)
                    except Exception as _e:  # noqa: BLE001
                        print(f"⚠️ 配息資產合計真值不可得（{type(_e).__name__}: {_e}）→ 保留原文不重算（fail-visible）")
                    if _dv > 0 and _lta > 0:
                        _t = re.sub(
                            r"配息資產合計\s*[\d,]+\s*÷\s*總資產\s*[\d,]+\s*=\s*\d+(?:\.\d+)?%",
                            f"配息資產合計 {_dv:,.0f} ÷ 總資產 {_lta:,.0f} = {_dv / _lta * 100:.1f}%", _t)
                # 其餘「A ÷ 總資產 B = C%」若無可稽核的分子真值 → 一律不動並印出
                #    （禁印出「舊分子 ÷ live 分母」的跨 as-of 混合算式）
                _canon_num = f"{_dv:,.0f}" if _dv > 0 else None
                _unfixed = [m for m in re.findall(
                    r"[\d,]{7,}\s*÷\s*總資產\s*[\d,]{7,}\s*=\s*\d+(?:\.\d+)?%", _t)
                    if not (_canon_num and m.startswith(_canon_num))]
                if _unfixed:
                    print(f"⚠️ 未改寫的比例算式（無分子真值 → 保留原文，不與 live 分母混用）：{_unfixed}")
                # ⑦乾粉（＝可動用現金 − 生活底線）
                if "乾粉" in _t:
                    try:
                        _dr = cash_caliber(snap)["dry"]
                        _t = re.sub(r"乾粉\s*[\d.]+萬", f"乾粉 {_dr / 10000:.1f}萬", _t)
                    except Exception as _e_dr:
                        # 2026-10-15 CIO 複審：不得靜默放行舊值（行動列乾粉改寫失敗須可見）
                        print(f"⚠️ 行動列乾粉即時值不可得（{type(_e_dr).__name__}: {_e_dr}）→ 保留原文（fail-visible）")
                _n = dict(_r)
                _n["內容"] = _t
                return _n

            _rows2 = [_live_row(_r) for _r in _rows2]
            # 2026-10-15 P1-1（同頁一致性）：行動儀表板 JS 載入時會用 radar_state.json 重繪
            #   同一批 rows；餵原始內容 → 頁面載入後又冒出舊桶位（台股/美股/防守 皆會）。
            #   注入「已套用 live 規則」的同一份內容（規則仍只在本檔＝單一來源）；
            #   JS 端逐列以 類別+動作 嚴格比對後才採用，不符即回退原值（不錯位、不猜）。
            def _band_row(_cat: str, _c: str, _s: dict) -> str:
                """逐列套用與整頁同一道 band_filter（2026-10-15 P1-1）。

                band_filter 以「桶別別名」為錨點，單獨餵內容會完全 no-op（實測），
                故先補上類別前綴再套用、最後去錨 → 注入內容與伺服器端渲染逐字一致。
                """
                if not _cat:
                    return _c
                _out = _band_filter(_cat + _c, _s)
                return _out[len(_cat):] if _out.startswith(_cat) else _out

            tpl = tpl.replace("__LIVE_ROWS_JS__", json.dumps(
                [{"類別": r.get("類別") or "", "動作": r.get("動作") or "",
                  "內容": _band_row(r.get("類別") or "", r.get("內容") or "", snap)}
                 for r in _rows2], ensure_ascii=False))
            try:
                import pledge_status as _pf_d
                _pl2 = _pf_d.pledge_status_line(style="short")
            except Exception:
                _pl2 = "質押狀態未知"
            # 2026-10-01：國泰房貸利率/金額改讀 snapshot 真值（原寫死「1,200萬@2.6%」）
            try:
                _sn_db = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
            except Exception:
                _sn_db = {}
            # 2026-10-04 P0（CIO 五審 M5）：原 `or 0` → 缺真值時儀表板靜默顯示
            # 「國泰房貸繳款（大義街 0萬@0.0%寬限期） 0」＝ 1,200 萬房貸看起來歸零。缺鍵必須明示。
            _mc_p_raw = _sn_db.get("mortgage_cathay")
            _mc_r_raw = _sn_db.get("mortgage_cathay_rate")
            if _mc_p_raw in (None, "") or _mc_r_raw in (None, ""):
                _mc_miss = [k for k, v in (("mortgage_cathay", _mc_p_raw),
                                           ("mortgage_cathay_rate", _mc_r_raw))
                            if v in (None, "")]
                rep["__CATHAY_LOAN_LINE__"] = (
                    "國泰房貸繳款（大義街 ⚠️ 缺真值：" + "、".join(_mc_miss) + "）")
                print(f"⚠️ [dashboard] 國泰房貸真值缺（{'、'.join(_mc_miss)}）"
                      "→ 該列明示缺真值（不以 0萬@0.0% 頂替）")
            else:
                _mc_p_d = float(_mc_p_raw) / 10000
                _mc_r_d = float(_mc_r_raw) * 100
                # 2026-10-01：國泰房貸繳款列改由真值注入（原 index_template 寫死「1,200萬@2.6% 26,000」）
                rep["__CATHAY_LOAN_LINE__"] = (
                    f"國泰房貸繳款（大義街 {_mc_p_d:,.0f}萬@{_mc_r_d:.1f}%寬限期） "
                    f"{round(float(_mc_p_raw) * float(_mc_r_raw) / 12):,.0f}")
            # 2026-10-01：女友借款/還款列改由真值注入（原 index_template 靜態寫死「300,000」「09/05」）
            _gfi = ((_sn_db.get("personal_loans") or {}).get("女友借款") or {})
            _gf_bal = float(((_sn_db.get("receivables_breakdown") or {}).get("女友借款") or {}).get("本金") or 0) \
                or float((_sn_db.get("receivables") or {}).get("女友借款") or 0)
            _gf_m = int(float(_gfi.get("月還款") or 0))
            _gf_due = str(_gfi.get("最後清償") or "")
            try:
                _gf_due_txt = f"{int(_gf_due[5:7])}/{int(_gf_due[8:10])}"
            except Exception:
                _gf_due_txt = _gf_due or "—"
            rep["__GF_LOAN_LINE__"] = (
                f"⚠️ 還款中 女友借款（每月還 {_gf_m:,}，預計 {_gf_due_txt} 清償）餘本金 {_gf_bal:,.0f}"
                if _gf_m else "")
            _gf_payd = int("".join(ch for ch in str(_gfi.get("還款日") or "5") if ch.isdigit()) or 5)
            _gf_recs = _sn_db.get("girlfriend_repayment_records") or {}
            _t2 = date.today()
            _cand = []
            for _mo in (0, 1, 2):
                _y2 = _t2.year + (_t2.month - 1 + _mo) // 12
                _m2 = (_t2.month - 1 + _mo) % 12 + 1
                try:
                    _d2 = date(_y2, _m2, _gf_payd)
                except ValueError:
                    continue
                if f"{_y2}-{_m2:02d}" in _gf_recs or _d2 < _t2:
                    continue
                _cand.append(_d2)
            if _cand and _gf_m:
                rep["__GF_NEXT_DATE__"] = f"{_cand[0].month:02d}/{_cand[0].day:02d}"
                rep["__GF_NEXT_LINE__"] = f"🔄 還款中 女友還款（每月 {_gf_m:,}） {_gf_m:,}"
            else:
                rep["__GF_NEXT_DATE__"] = ""
                rep["__GF_NEXT_LINE__"] = ""
            rep["__RISK_FUNDS__"] = (
                f"— 美債殖利率高檔為主要風險；國泰 {_mc_p_d:,.0f}萬@{_mc_r_d:.1f}% 8/20 撥款"
                f"（配置：富達600＋聯博100＋貝萊德B11 500）；{_pl2}")
            _rules = [f"{_r.get('動作','')}{(_r.get('類別') or '').strip()}：{_brief2(_r.get('內容',''))}"
                      for _r in _rows2[:5]]
            _cw_r = cash_caliber(snap)
            _cash_rule = (
                f"；現金 {_cw_r['cash']:,.0f}：現金底線 {_cw_r['life']:,.0f} "
                + ("✅ 達標" if _cw_r["life_ok"] else "🔴 未達標")
                + (f"（餘裕/乾粉 {_cw_r['dry']:,.0f}）" if _cw_r["life_ok"]
                   else f"（缺 {_cw_r['life'] - _cw_r['cash']:,.0f}，配息導流補足、不新增買入）"))
            rep["__RISK_RULES__"] = (("操作規範：" + "；".join(_rules) + _cash_rule)
                                     if _rules else "操作規範：待雷達更新")
            try:
                _ev2 = json.loads((BASE / "schedule_events.json").read_text(encoding="utf-8"))
                _fut = []
                for _e in (_ev2 if isinstance(_ev2, list) else _ev2.get("events", [])):
                    _ds = str(_e.get("date", ""))[:10]
                    try:
                        _dd = date.fromisoformat(_ds)
                    except Exception:
                        continue
                    if _dd >= date.today():
                        _fut.append((_dd, str(_e.get("item", ""))[:38]))
                _fut.sort()
                _nodes = "｜".join(f"{_d.strftime('%m/%d')} {_t}" for _d, _t in _fut[:3]) or "無近期節點"
            except Exception as _e2n:
                _nodes = f"（schedule_events 讀取失敗：{_e2n}）"
            rep["__RISK_NODE__"] = ("凍結紅線：US30Y ≥5.30% 全面凍結債券配置、提高現金水位。"
                                    f"關鍵節點：{_nodes}")
            _chain = [x for x in [_row_of("保單轉換").get("內容", ""), _row_of("質押").get("內容", "")] if x]
            from sot_targets import restricted_breakdown as _rbk_d
            _rbk_txt = _rbk_d(snap)
            rep["__RISK_CHAIN__"] = ("📌 資金鏈現況：" + ("；".join(_chain) if _chain else "待雷達更新")
                                     + (f"｜{_rbk_txt}" if _rbk_txt else ""))
            rep["__RADAR_SIGNALS__"] = _signals_txt
            rep["__RADAR_PLAN__"] = "｜".join(_plan)
            rep["__RADAR_POLICY__"] = _policy_txt
        else:
            rep["__RADAR_DATE__"] = "—"
            rep["__RISK_UPDATED__"] = "—"
            rep["__RADAR_SIGNALS__"] = "雷達資料缺（radar_state.json 不存在）"
            rep["__RADAR_PLAN__"] = "待雷達更新"
            rep["__RADAR_POLICY__"] = "無"
    except Exception as _e:
        # 2026-09-16 修：原靜默吞例外 → __RISK_*__ 佔位符直接上線（使用者抓包「儀表板壞的」）
        import traceback as _tb
        print("  ⚠️ 雷達/風險區塊注入失敗（已用 fallback 文字）:", _e)
        _tb.print_exc()
        rep["__RADAR_DATE__"] = "—"
        rep["__RISK_UPDATED__"] = "—"
        rep["__RADAR_SIGNALS__"] = f"雷達讀取失敗: {_e}"
        rep["__RADAR_PLAN__"] = "待雷達更新"
        rep["__RADAR_POLICY__"] = "無"
        # 風險提示四段 fallback（嚴禁佔位符上線）
        _plf = "質押狀態未知"
        try:
            import pledge_status as _pf_f
            _plf = _pf_f.pledge_status_line(style="short")
        except Exception:
            pass
        rep.setdefault("__RISK_FUNDS__", f"— 風險區塊資料讀取失敗，請看日報；{_plf}")
        rep.setdefault("__RISK_RULES__", "操作規範：待雷達更新")
        rep.setdefault("__RISK_NODE__", "凍結紅線：US30Y ≥5.30% 全面凍結債券配置、提高現金水位。")
        rep.setdefault("__RISK_CHAIN__", "📌 資金鏈現況：待雷達更新")
    # ── 銀行水位（2026-08-26：模板寫死各銀行餘額 → 從 snapshot cash_detail 動態）──
    cd = snap.get("cash_detail", {}) or {}
    # 2026-09-28 修正（使用者指正：卡片「資料日期」永遠顯示 9/1）：
    #   舊寫法 glob moneybook/ 目錄（本機不存在）→ 永遠退回寫死的 "20260901"。
    #   正解＝讀 snapshot.cash_source.date（update_data.py --cash_detail 匯入 Moneybook 帳戶 CSV 時的匯入日，
    #   與 asset_diff_monitor「資料新鮮度」卡同源）；缺值才退回 CSV 檔名／snapshot.date。
    import glob as _glob_mb
    _csrc = snap.get("cash_source") or {}
    _cash_iso = _csrc.get("date") if isinstance(_csrc, dict) else _csrc
    _data_date = str(_cash_iso)[:10] if _cash_iso else ""
    if not _data_date:
        _mb_csv = sorted(_glob_mb.glob(str(BASE / "moneybook" / "Moneybook_帳戶_*.csv"))) + sorted(_glob_mb.glob(str(BASE / "Moneybook_帳戶_*.csv")))
        _data_date = (str(_mb_csv[-1]).replace(chr(92), "/").split("/")[-1]
                      .replace("Moneybook_帳戶_", "").replace(".csv", "")) if _mb_csv else str(snap.get("date") or "—")
    taiwan = (cd.get("敦南Richart子帳戶", 0) or 0) + (cd.get("文心綜活儲存款-薪轉", 0) or 0) + (cd.get("敦南Richart數位一般帳戶", 0) or 0) + (cd.get("敦南Richart外幣", 0) or 0)
    # 2026-09-28：模板管理費列已改寫（舊錨點兩分支皆死碼）→ 整段移除
    # 流動性調度 tab 銀行卡（2026-08-29 補：原 6 卡全寫死 → 動態）
    # 2026-09-28 使用者裁示：房貸扣款行安全線＝「自身房貸月繳×3」（國泰＝大義街、永豐＝洲際W）；
    #    其餘（台新薪轉帳戶）仍用月支出×3。值一律讀 snapshot，勿寫死。
    try:   # 2026-10-01：國泰房貸月繳改讀派生真值（rate×本金/12），利率一動安全線跟著動
        from mortgage_rate import cathay_monthly as _cg_mo_safe
        _cat_loan = float(_cg_mo_safe(snap) or 0)
    except Exception:
        _cat_loan = float(snap.get("mortgage_cathay_monthly") or 0)
    _sin_loan = float(snap.get("mortgage_sinopac_monthly") or 0)
    for _nm, _lv in (("mortgage_cathay_monthly", _cat_loan), ("mortgage_sinopac_monthly", _sin_loan)):
        if _lv <= 0:   # 2026-09-28（CIO 審查）：缺值不得退成 0 門檻（會把 🔴 誤判成 🟢）→ 退回月支出
            print(f"  ⚠️ {_nm} 缺值／為 0 → 該行庫安全線退回月支出口徑（{_fmt(expense)}×3）")
    _cat_loan = _cat_loan or float(expense)
    _sin_loan = _sin_loan or float(expense)
    rep["__SAFE_LINE_RAW__"] = str(int(expense) * 3)              # 台新（月支出×3；顯示值由下方 data-k="safe_line" 注入）
    rep["__SAFE_LINE_CATHAY_RAW__"] = str(int(_cat_loan) * 3)     # 國泰（房貸月繳×3＝3 個月扣款）
    rep["__SAFE_LINE_SINOPAC_RAW__"] = str(int(_sin_loan) * 3)    # 永豐（房貸月繳×3＝3 個月扣款）
    # 2026-08-28 修正：銀行水位全動態（Moneybook 8/27 帳戶）
    rep["20260829_1"] = _data_date      # 資料日期（2026-09-01 修正：動態，不再寫死 8/31）    # 現金合計卡「監控卡片合計」（2026-08-29 補：原寫死 799,612 殘留 → 動態算 cash_detail 正數，排除外幣 key）
    # ── 資產穿透卡五桶市值（2026-08-29 補：快照版 fallback 全部寫死舊值）──
    _ptwd = snap.get("penetration", {}).get("actual_twd", {}) or {}
    _ppct = snap.get("penetration", {}).get("actual_pct", {}) or {}
    _gaps = snap.get("penetration", {}).get("gaps", {}) or {}
    _tgt = snap.get("penetration", {}).get("targets", {}) or {}
    # 科技/非科技文字（⚠️ 必須在市值替換前，因整句 key 含市值數字，市值先被換掉就匹配不到）
    _tch = _ppct.get("美股市值型成長_科技", 0); _ntch = _ppct.get("美股市值型成長_非科技", 0)
    _tech_gap = _tch - 15
    _tech_txt_old = "🔬 科技 14.3%（3,735,174 TWD）｜非科技 29.6%（7,764,551 TWD）｜科技目標 ≤20%（缺口 -0.7pp）"
    _tech_txt_new = f"🔬 科技 {_tch:.1f}%（{_fmt(_ptwd.get('美股市值型成長_科技',0))} TWD）｜非科技 {_ntch:.1f}%（{_fmt(_ptwd.get('美股市值型成長_非科技',0))} TWD）｜科技目標 ≤20%（{'缺口' if _tech_gap<0 else '溢價'} {_tech_gap:+.1f}pp）"
    # 兩階段：先用 temp 佔位保護整句 → 再換市值 → 最後還原整句
    _TECH_PH = "@@TECH_TXT@@"
    tpl = tpl.replace(_tech_txt_old, _TECH_PH)
    _t_act = _ppct.get("台股市值型成長", 0); _t_tgt = _tgt.get("台股市值型目標", 10)
    _t_gap = _t_act - _t_tgt
    _t_col = "text-red-400" if _t_gap < 0 else "text-emerald-400"
    _u_act = _ppct.get("美股市值型成長", 0); _u_tgt = _tgt.get("美股市值型目標", 40)
    _u_gap = _u_act - _u_tgt
    _d_act = _ppct.get("防守型配息", 0); _d_tgt = _tgt.get("配息型目標", 20)
    _d_gap = _d_act - _d_tgt
    _b_act = _ppct.get("債券", 0); _b_tgt = _tgt.get("債券型目標", 25)
    _b_gap = _b_act - _b_tgt
    _c_act = _ppct.get("現金/安全網", 0); _c_tgt = _tgt.get("現金目標", 5)
    _c_gap = _c_act - _c_tgt
    # 科技/非科技文字
    _tch = _ppct.get("美股市值型成長_科技", 0); _ntch = _ppct.get("美股市值型成長_非科技", 0)
    _tech_gap = _tch - 15
    # 安聯配息卡（8/29 補：舊 62,969 → 76,931）
    # 2026-09-25 INC cash_floor_two_calibers_unlabeled：授信觀察期底線文案改由 SoT 派生（模板改為 __CASH_FLOOR_LINE__ 佔位符）
    _cw_t = cash_caliber(snap)
    # 2026-09-27：單一口徑（追繳緩衝取消）→ 不再輸出「合計含追繳緩衝」
    rep["__CASH_FLOOR_LINE__"] = f"現金 ≥{_cw_t['life']:,.0f}（單一口徑現金底線）"
    # 2026-09-29 使用者核准：Runway 卡改「可動用現金」口徑（扣指定清償款），並動態算 Runway
    # （原模板寫死「Runway 5 / 覆蓋倍數 5.0x」且把質押撥款 590 萬算成可動用現金）。
    _exp_m = float(snap.get("monthly_expense") or 0) or 1.0
    _rw_m = _cw_t["cash"] / _exp_m
    rep["__AVAILABLE_CASH_LINE__"] = (
        f'以可動用現金 {_cw_t["cash"]:,.0f}（Moneybook 真值 {_cw_t["cash_all"]:,.0f}'
        + (f' － 質押撥款指定清償款 {_cw_t["restricted"]:,.0f}' if _cw_t["restricted"] else '')
        + f'）進行除數運算。Runway {_rw_m:.1f} 個月 / 覆蓋倍數 {_rw_m:.1f}x（月支出 {_exp_m:,.0f}）。')
    # 保單A 現值（8/29 補：舊 5,103,722 → 5,083,230）

    hits = 0
    # 2026-09-28：死錨點自動現形（模板已全面 data-k 化 → 未命中的 rep 鍵＝靜默死碼）
    _dead_anchors = [k for k in rep if not k.startswith("__") and k not in tpl]
    if _dead_anchors:
        _KNOWN_DEAD = 0          # 2026-09-28 基線：死錨點全數清完（銀行區 11＋非銀行區 23）；超過基線＝模板改了、rep 沒跟
        if len(_dead_anchors) > _KNOWN_DEAD:
            print(f"  ⚠️ rep 未命中錨點 {len(_dead_anchors)} 個（基線 {_KNOWN_DEAD}）→ 模板已改、rep 未同步（死碼）："
                  + ", ".join(sorted(_dead_anchors)[:5]))
    for old, new in rep.items():
        if old in tpl:
            tpl = tpl.replace(old, new)
            hits += 1
    # 2026-09-21 INC-233：佔位符沒被取代＝模板與鍵名不一致，過去是「靜默留舊值」→ 改為當場大聲失敗。
    # 新增 rep 佔位符時，務必同步登錄這份清單（清單＝強制必須被消耗的佔位符）。
    _MUST_CONSUME = ("__SAFE_LINE_RAW__", "__SAFE_LINE_CATHAY_RAW__", "__SAFE_LINE_SINOPAC_RAW__", "__CASH_FLOOR_LINE__", "__AVAILABLE_CASH_LINE__")
    _leftover = [p for p in _MUST_CONSUME if p in tpl]
    if _leftover:
        raise RuntimeError(f"build_dashboard：佔位符未被取代 {_leftover}（注入失效，拒絕產出舊值儀表板）")

    # ── data-k 自動注入（2026-08-31 治本：template 的 <span data-k="KEY">顯示值</span> 直接對 snapshot，
    #    不再依賴 rep 舊值字串清單 — 8/31 血淚：cash_total 772,607 殘留只因 rep 沒列 772,607）──
    import re as _re
    # 2026-09-28：5 家行庫卡合計／其他帳戶／可動用乾粉（卡片合計口徑＝畫面上 5 張卡）
    _card_sum = ((cd.get("活期儲蓄存款", 0) or 0) + (cd.get("數位存款帳戶２類", 0) or 0) + taiwan
                 + (cd.get("營業部DAWHO活期儲蓄存款", 0) or 0) + (cd.get("市政分行活期儲蓄存款", 0) or 0)
                 + (cd.get("臺幣綜存", 0) or 0) + (cd.get("數位活儲", 0) or 0))
    _other_sum = max(0, float(snap.get("cash_total") or 0) - _card_sum)
    _dry = _cw_t["dry"]
    _data_k_map = {
        "cash_total": cash,        # 現金（snapshot.cash_total）
        "div_total": div_total,    # 配息實收
        "got_total2": got_total,   # 當月已收合計（說明欄）
        "got_total": got_total,    # 當月已收合計卡片（2026-08-31 補：template 用 data-k="got_total"）
        "rent_got": rent_got,      # 租金已收
        "salary_got": salary,      # 薪水已收（當月 salary_records；未入帳 = 0）
        # 2026-09-01 補齊：與 template JS V 表對齊（39 key 全注入 → 靜態 fallback 也是最新值）
        "ins_total": ins,
        "allianz_a": snap.get("allianz_policy_a_value", 0) or 0,
        "allianz_b": snap.get("allianz_policy_b_value", 0) or 0,
        "allianz_ab": allianz,
        "firstjin": firstjin,
        "cum_div": snap.get("allianz_cum_dividend", 0) or 0,
        "fj_cum": snap.get("firstjin_cum_dividend", 0) or 0,
        "az_div": az_div, "az_div2": az_div,
        "fj_div": firstjin_div,
        "div_ins": div_ins,
        "etf_div": sum(v for k, v in _dr.items() if any(t in k for t in ("ETF", "基金", "聯博")) and isinstance(v, (int, float))) or 0,
        "safe_line": int(expense) * 3,
        # 2026-09-28：現金合計卡（卡片合計 vs 其他帳戶）與可動用乾粉（現金 − 底線）
        "card_sum": _card_sum,
        "other_sum": _other_sum,
        "dry_powder": _dry,
        # 2026-10-11 工單A：分層註記需要的短少值（乾粉不足時 dry_powder=0，但短少＝60,339）
        "dry_powder_signed": _cw_t["dry_signed"],
        "cash_shortfall": _cw_t["shortfall"],
        "safe_line_cathay": int(_cat_loan) * 3,      # 2026-09-28：房貸扣款行各自口徑
        "safe_line_sinopac": int(_sin_loan) * 3,
        "cathay_loan": int(_cat_loan),
        "sinopac_loan": int(_sin_loan),
        "pen_tw": _ptwd.get("台股市值型成長", 0),
        "pen_us": _ptwd.get("美股市值型成長", 0),
        "pen_def": _ptwd.get("防守型配息", 0),
        "pen_bond": _ptwd.get("債券", 0),
        "pen_cash": _ptwd.get("現金/安全網", 0),
        "pen_tech": _ptwd.get("美股市值型成長_科技", 0),
        "pen_nontech": _ptwd.get("美股市值型成長_非科技", 0),
        "cathay": (cd.get("活期儲蓄存款", 0) or 0) + (cd.get("數位存款帳戶２類", 0) or 0),
        "cathay_d1": cd.get("活期儲蓄存款", 0) or 0,
        "cathay_d2": cd.get("數位存款帳戶２類", 0) or 0,
        "taiwan": (cd.get("敦南Richart子帳戶", 0) or 0) + (cd.get("文心綜活儲存款-薪轉", 0) or 0) + (cd.get("敦南Richart數位一般帳戶", 0) or 0),
        "richart_sub": cd.get("敦南Richart子帳戶", 0) or 0,
        "wenxin": cd.get("文心綜活儲存款-薪轉", 0) or 0,
        "richart_gen": cd.get("敦南Richart數位一般帳戶", 0) or 0,
        "sinopac": (cd.get("營業部DAWHO活期儲蓄存款", 0) or 0) + (cd.get("市政分行活期儲蓄存款", 0) or 0),
        "dawho": cd.get("營業部DAWHO活期儲蓄存款", 0) or 0,
        "shizheng": cd.get("市政分行活期儲蓄存款", 0) or 0,
        "yushan": cd.get("臺幣綜存", 0) or 0,
        "fubon": cd.get("數位活儲", 0) or 0,
        # 2026-09-28：index_template 的「被動月固定收入（常態）」「安全退休盈餘」原本是純文字寫死
        # （無 data-k、也不在 rep 對映內）→ 真值一動就靜默說舊話；改走注入。
        "passive_norm": float((snap.get("passive_income") or {}).get("total_conservative") or 0),
        "retire_surplus": float(snap.get("retirement_surplus") or 0),
    }
    for _dk, _dv in _data_k_map.items():
        _pat = _re.compile(r'(<span data-k="%s">)[^<]*(</span>)' % _dk)
        # 2026-10-12 資安處置（使用者裁決：保留憑證、優先清理公開資料）：
        #   行庫餘額／安全線／房貸月繳屬 4 類敏感項（帳號、餘額、資產分母）→ 公開頁只顯示 ●●●，
        #   狀態色與門檻比較仍用真值計算（功能不失、金額不公開）。真值層與內部報告不受影響。
        _show = public_mask.display_value(_dk, _dv)
        tpl, _n = _pat.subn(
            lambda m: m.group(1) + (_show if _show is not None else _fmt(_dv)) + m.group(2), tpl)
        if _n:
            hits += _n
    # ── 銀行水位卡片「靜態狀態」對齊門檻（2026-09-28：卡片顏色/🟢🔴字樣原本手寫，與實際門檻不一致）──
    #    JS 失敗時的離線快照版也必須說對話（國泰 78,000／永豐 197,205 為房貸口徑）。
    _bank_state = {
        "cathay":  ((cd.get("活期儲蓄存款", 0) or 0) + (cd.get("數位存款帳戶２類", 0) or 0), int(_cat_loan) * 3),
        "taiwan":  (taiwan, int(expense) * 3),
        "sinopac": ((cd.get("營業部DAWHO活期儲蓄存款", 0) or 0) + (cd.get("市政分行活期儲蓄存款", 0) or 0), int(_sin_loan) * 3),
        "yushan":  (cd.get("臺幣綜存", 0) or 0, 40000),
        "fubon":   (cd.get("數位活儲", 0) or 0, 40000),
    }
    for _bk, (_bv, _bm) in _bank_state.items():
        _ok = float(_bv or 0) >= float(_bm or 0)
        _card = "border-blue-500/20 bg-blue-500/10" if _ok else "border-red-500/20 bg-red-500/10"
        _txt = "text-blue-300" if _ok else "text-red-400"
        _bpat = re.compile(
            r'<div class="border-(?:red|blue)-500/20 bg-(?:red|blue)-500/10 (p-4 rounded-xl space-y-1)">'
            r'(<div class="flex justify-between text-xs font-bold )text-(?:red-400|blue-300)'
            r'("><span>[^<]*</span><span class="bank-status" data-val-k="' + _bk + r'"[^>]*>)[^<]*(</span>)')
        tpl, _n2 = _bpat.subn(
            lambda m, c=_card, x=_txt, ok=_ok: '<div class="%s %s">%s%s%s%s%s' % (
                c, m.group(1), m.group(2), x, m.group(3), "🟢 充裕" if ok else "🔴 警報", m.group(4)), tpl)
        if _n2 != 1:
            print(f"  ⚠️ 銀行卡狀態對齊異常：{_bk} 命中 {_n2} 次（預期 1）")
    # ── 2026-09-04：純文字/手動行事曆殘留值正規化（data-k 注入只涵蓋 span；公式行與事件列金額需隨 monthly_salary 自動更新）──
    _ms = int(snap["monthly_salary"])   # 2026-10-10：移除舊薪資退路 42,560（現行 39,777）；缺值 raise
    tpl = tpl.replace("39,727", f"{_ms:,}")
    _pi = snap.get("passive_income") or {}
    tpl = tpl.replace("219,827",
                      f"{_ms + float(_pi.get('fund_dividend_conservative') or 0) + float(_pi.get('rent_monthly') or 0):,.0f}")

    # ── 今日狀態列動態化（2026-08-27：今日 + 近3天 + 下一個；含保單轉換等決策事件）──
    try:
        _evs = json.loads((BASE / "schedule_events.json").read_text(encoding="utf-8"))
        if isinstance(_evs, dict):
            _evs = _evs.get("events", _evs.get("items", []))
        _td = date.today().isoformat()
        _wk = (date.today() + timedelta(days=7)).isoformat()
        # 2026-09-01 定案：優先級由資料欄位 importance 宣告（high=硬性要做 / medium=觀察 / low=例行），不再關鍵字猜
        _is_active = lambda e: str(e.get("importance", "")) == "high" and "✅" not in str(e.get("status", "")) and "已完成" not in str(e.get("status", ""))
        _today_act = [e for e in _evs if str(e.get("date","")) == _td and _is_active(e)]
        _soon3 = sorted([e for e in _evs if _td < str(e.get("date","")) <= (date.today() + timedelta(days=3)).isoformat() and _is_active(e)],
                        key=lambda x: str(x.get("date","")))
        _next = sorted([e for e in _evs if _td < str(e.get("date","")) <= _wk and _is_active(e)],
                       key=lambda x: str(x.get("date","")))
        _parts = []
        # 今日重點 = importance=high 且日期=今天（含已完成，讓使用者對照完成狀態）
        _today_key = [e for e in _evs if isinstance(e, dict) and str(e.get("date","")) == _td and str(e.get("importance","")) == "high" and str(e.get("item",""))]
        for e in _today_key[:3]:
            _st = str(e.get("status",""))
            _icon = "✅" if ("✅" in _st or "已完成" in _st) else ("🔄" if ("執行中" in _st or "待確認" in _st) else "⏳")
            _st_short = _st.lstrip("✅ ").strip()[:14]
            _parts.append(f"🔴 今日要做：{str(e.get('item',''))[:40]}（{_icon} {_st_short}）")
        if not _parts:
            _parts.append("🟢 今日無重點事項")
        if _soon3:
            _d3 = " ｜ ".join(f"{str(e.get('date',''))[5:]} {str(e.get('item',''))[:26]}" for e in _soon3[:3])
            _parts.append(f"📌 近 3 天：{_d3}")
        if _next:
            _n = next((e for e in _next if str(e.get("date","")) > (date.today() + timedelta(days=3)).isoformat()), None) or _next[0]
            _parts.append(f"⏭ 下一個：{str(_n.get('date',''))[5:]} {str(_n.get('item',''))[:44]}")
        tpl = tpl.replace("__TODAY_STATUS__", "<br>".join(_parts))
        tpl = tpl.replace("__TODAY__", _td)
    except Exception:
        tpl = tpl.replace("__TODAY_STATUS__", "🟢 今日狀態：無需人工操作")
        tpl = tpl.replace("__TODAY__", date.today().isoformat())

    # ── 決定卡＋決策核心卡（2026-10-02 裁示：首頁只看 GO/WAIT ＋ 今天有沒有事）──
    try:
        from report_components import render_decision_banner as _rdb, render_health_card as _rhc
        tpl = tpl.replace("__DECISION_BANNER__", _rdb(snap))
        tpl = tpl.replace("__HEALTH_CARD__", _rhc(snap))
    except Exception:
        tpl = tpl.replace("__DECISION_BANNER__", "")
        tpl = tpl.replace("__HEALTH_CARD__", "")

    # ── 戰略異常中心動態化（2026-09-01：雷達/交易計畫/政策面不再硬編碼 8/29 快照）──
    try:
        _rs = json.loads((BASE / "radar_state.json").read_text(encoding="utf-8"))
        _sig = _rs.get("signals", {}) or {}
        _sig_str = "｜".join(f"{k}{v.get('color', '⚪')} {v.get('note', '')}" for k, v in _sig.items())
        tpl = tpl.replace("__RADAR_SIG__", f"（雷達更新 {str(_rs.get('last_run', ''))[:10]}）{_sig_str}")
        _pn = _rs.get("policy_notes", {}) or {}
        _pol_items = []
        for _k in _pn:
            if str(_k).startswith("新聞"):
                _c = (_pn[_k].get("內容", "") or "")[:56]
                _imp = (_pn[_k].get("對資產影響", "") or "")[:42]
                _pol_items.append(f"{_c}（{_imp}）")
        _pol_str = "｜".join(_pol_items) if _pol_items else "無重大政策事件"
        _src = _pn.get("來源", "") or ""
        tpl = tpl.replace("__POLICY_NOTES__", f"🏛️ 政策面（{_src}）：{_pol_str}")
    except Exception as _e:
        tpl = tpl.replace("__RADAR_SIG__", "雷達暫無資料").replace("__POLICY_NOTES__", "政策面暫無資料")
    tpl = tpl.replace("__VOLATILITY_REPORT__", make_volatility_report())

    # ── 智慧審查：巴菲特配置哲學與實操（動態注入，2026-09-24）──
    try:
        import glob as _glob
        _candidates = sorted(BASE.glob("buffett_cto_report_*.md"))
        _buffett_md = _candidates[-1] if _candidates else BASE / f"buffett_cto_report_{date.today().isoformat()}.md"
        _buf_html = ""
        if _buffett_md.exists():
            _md_text = _buffett_md.read_text(encoding="utf-8")
            _buf_lines, _cto_lines = [], []
            _current = None
            for _line in _md_text.splitlines():
                _s = _line.strip()
                if _s.startswith("【Buffett") or _s.startswith("🧓 巴菲特"):
                    _current = "buffett"
                    continue
                elif _s.startswith("【CTO") or _s.startswith("CTO "):
                    _current = "cto"
                    continue
                elif _s.startswith("【"):
                    _current = None
                    continue
                if _current == "buffett" and _s:
                    _buf_lines.append(_s)
                elif _current == "cto" and _s:
                    _cto_lines.append(_s)
            _buf_content = "<br>".join(_buf_lines)
            _cto_content = "<br>".join(_cto_lines)
        else:
            _buf_content, _cto_content = "", ""
        # 穿透現況從 snapshot 讀
        _pen = snap.get("penetration", {})
        _ap = _pen.get("actual_pct", {})
        _gp = _pen.get("gaps", {})
        _tw = _pen.get("actual_twd", {})
        def _pen_li(label, key, target, emoji):
            _v = _ap.get(key, 0)
            _g = _v - target
            _cls = "text-emerald-400" if _g >= 0 else "text-red-400"
            _sign = "+" if _g >= 0 else ""
            return f'<li>{emoji} <strong>{label}</strong>：{_v:.1f}%（目標 {target}%，<span class="{_cls}">{_sign}{_g:.1f}pp</span>）</li>'
        _pen_html = (
            _pen_li("台股", "台股市值型成長", 10, "TW")
            + _pen_li("美股", "美股市值型成長", 30, "🇺🇸")
            + _pen_li("防守", "防守型配息", 30, "🛡️")
            + _pen_li("債券", "債券", 25, "💵")
            + _pen_li("現金", "現金/安全網", 5, "💰")
        )
        _buf_card = f'''<div class="bg-slate-900/40 p-4 rounded-xl border border-slate-800 space-y-2"><span class="text-xs font-bold text-teal-400">🎯 策略建議</span><ul class="text-xs text-slate-300 space-y-1.5 leading-relaxed"><li class='text-amber-300'><strong>🚨 指示卡（08/23 核心‑衛星保守成長版）：</strong>目標配置＝台股15/美股30/防守20/債券20/現金15，為中長期方向，容許數月階段偏離；債券鎖短中期投資等級（存續期1-5年，BBB-以上）；平衡基金僅限衛星≤防禦20%；兩條底線＝現金 ≥{cash_caliber(snap)['life']:,.0f}（單一口徑現金底線）、US30Y >5.20% 停新增長債；Lombard 橋接需手動開啟且借款≤擔保品4成</li></ul><div class="mt-3 pt-3 border-t border-slate-700"><span class="text-xs font-bold text-amber-400">📝 巴菲特視角</span><ul class="text-xs text-slate-300 space-y-1.5 list-disc pl-4 mt-2">{"".join(f"<li>{l}</li>" for l in _buf_lines[:4])}</ul></div></div>''' if _buf_lines else ""
        _cto_card = f'''<div class="bg-slate-900/40 p-4 rounded-xl border border-slate-800 space-y-2"><span class="text-xs font-bold text-red-400">⚡ CTO 技術視角</span><ul class="text-xs text-slate-300 space-y-1.5 list-disc pl-4">{"".join(f"<li>{l}</li>" for l in _cto_lines[:4])}</ul></div>''' if _cto_lines else ""
        _buf_html = f'''<div class="luxury-card p-6 space-y-4">
            <h3 class="text-md font-bold text-white">智慧審查：巴菲特配置哲學與實操</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4"><div class="bg-slate-900/40 p-4 rounded-xl border border-slate-800 space-y-2"><span class="text-xs font-bold text-blue-400">💡 穿透現況</span><ul class="text-xs text-slate-300 space-y-1.5 list-disc pl-4">{_pen_html}</ul></div>{_buf_card}</div>
            {_cto_card}
        </div>'''
        tpl = tpl.replace("__BUFFETT_ANALYSIS__", _buf_html)
    except Exception as _e:
        tpl = tpl.replace("__BUFFETT_ANALYSIS__", f"智慧審查載入失敗：{_e}")

    # ── 交易計畫（2026-10-23 修復：靜態 fallback 改讀 radar_state.weekly_plan 單一真值）
    #    原讀 pending_decisions.json（待處理/已確認）→ 把治理卡當交易計畫顯示（TD-20261011-01）。
    #    本段僅為 JS 未執行時的 fallback；即時版由頁尾「行動儀表板」JS 覆寫同一節點。
    try:
        _rd_tp = json.loads((BASE / "radar_state.json").read_text(encoding="utf-8"))
        _wp_tp = _rd_tp.get("weekly_plan") or {}
        _rows_tp = [r for r in (_wp_tp.get("rows") or [])
                    if isinstance(r, dict) and r.get("內容") and not str(r.get("動作", "")).startswith("↳")]
        if _rows_tp:
            _d_tp = str(_wp_tp.get("日期") or _rd_tp.get("last_run", "")[:10])
            _plan_items = [f"{r.get('動作', '')} {r.get('類別', '')}：{r.get('內容', '')}" for r in _rows_tp[:4]]
            _more = f"…共 {len(_rows_tp)} 條" if len(_rows_tp) > 4 else ""
            _plan_str = "｜".join(_plan_items) + _more + f"（靜態快照 {_d_tp}；即時版開頁後更新）"
        else:
            _plan_str = "⚠️ 投資計劃資料暫不可用（radar_state.weekly_plan 為空，勿引用為現行計劃）"
        tpl = tpl.replace("__TRADE_PLAN__", f"🎯 本週交易計畫（動態）：{_plan_str}")
    except Exception as _e_tp:
        tpl = tpl.replace("__TRADE_PLAN__", f"⚠️ 投資計劃資料暫不可用（radar_state 讀取失敗：{_e_tp}）")

    # ── 月度流入標題動態化（2026-09-01：原寫死「08月現金流入檢對核實」→ 當月）──
    tpl = tpl.replace("__INCOME_TITLE__", str(int(_today_m[5:])) + "月現金流入檢對核實")

    # ── 戰術任務動態化（2026-09-01：P0 任務 + 本週計畫從 pending_decisions 生成，非 8/29 快照）──
    try:
        _pd2 = json.loads((BASE / "pending_decisions.json").read_text(encoding="utf-8"))
        _lst = _pd2 if isinstance(_pd2, list) else []
        if _lst:
            # 2026-10-11：本段（P0 卡／戰術計畫／交易計畫）原直接吃檔案順序（_lst[0]、
            #   _lst[:6]）—— 狀態四態化與清單分流後，檔案第一筆即失去「P0」語意。
            #   統一改吃「未結案」子集（四態：待處理／已確認），P0 卡優先挑有 P0 標記者。
            _act = [x for x in _lst if str(x.get("status", "")) in ("待處理", "已確認")] or _lst
            _p0_c = [x for x in _act if "P0" in str(x.get("title", ""))]
            _p0 = (sorted(_p0_c, key=lambda x: str(x.get("date", "")))[0] if _p0_c
                   else sorted(_act, key=lambda x: str(x.get("date", "")))[0])
            _p0_st = str(_p0.get("status", "") or "")[:90]
            _p0_tt = str(_p0.get("title", "") or "")[:90]
            _p0_dt = str(_p0.get("detail", "") or "")[:150]
            _p0_html = (
                '<div class="luxury-card p-6 border-l-4 border-red-500 space-y-4">'
                '<div class="flex justify-between items-start">'
                '<div><span class="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded font-mono font-bold">P0 戰略任務</span>'
                f'<h3 class="text-md font-bold text-white mt-1">{"🔄" if _p0_st.startswith("待處理") else "✅"} {_p0_st}｜{_p0_tt}</h3></div>'
                f'<span class="text-xs text-slate-400 font-mono">{str(_p0.get("date", ""))[:10]}</span></div>'
                '<div class="bg-slate-900/60 p-4 rounded-xl space-y-2 border border-slate-800 text-xs">'
                f'<p class="font-bold text-yellow-500">執行狀態：{_p0_st[:60]}</p>'
                f'<p class="text-slate-300 leading-relaxed font-mono">{_p0_dt}</p></div></div>'
            )
            tpl = tpl.replace("__P0_TASK__", _p0_html)
            _tact_rows = []
            for _d in _act[:6]:
                _st = str(_d.get("status", "") or "").replace("：", ":")[:34]
                _tt = str(_d.get("title", "") or "")[:26]
                _tact_rows.append(
                    f'<div class="p-2 bg-slate-900/40 rounded border border-slate-800 flex justify-between">'
                    f'<span class="text-slate-300">{_tt}</span><span class="text-amber-400 font-mono">{_st}</span></div>'
                )
            tpl = tpl.replace("__TACTICAL_PLAN__",
                '<div class="luxury-card p-6 space-y-4"><h3 class="text-md font-bold text-white">🗓️ 本週計畫（動態）</h3>'
                '<div class="space-y-2 text-xs">' + "".join(_tact_rows) + '</div></div>')
        else:
            tpl = tpl.replace("__P0_TASK__", "").replace("__TACTICAL_PLAN__", "")
    except Exception:
        tpl = tpl.replace("__P0_TASK__", "").replace("__TACTICAL_PLAN__", "")

    # ── 穿透卡靜態渲染（2026-09-01：pen-card 不再依賴 JS「載入中」→ build 直接生成五桶，無 JS 也顯示）──
    _ptwd_p = snap.get("penetration", {}).get("actual_twd", {}) or {}
    _ppct_p = snap.get("penetration", {}).get("actual_pct", {}) or {}
    _tgt_p = snap.get("penetration", {}).get("targets", {}) or {}
    _defs_p = [
        ("台股市值型成長", "台股", "台股市值型目標", "#3b82f6"),
        ("美股市值型成長", "美股", "美股市值型目標", "#ef4444"),
        ("防守型配息", "防守", "配息型目標", "#22c55e"),
        ("債券", "債券", "債券型目標", "#f59e0b"),
        ("現金/安全網", "現金", "現金目標", "#94a3b8"),
    ]
    _pen_parts = [
        '<h3 class="text-md font-bold text-white">資產穿透（snapshot 真值）</h3>',
        f'<p class="text-xs text-slate-400">目標：台股 {_tgt_p.get("台股市值型目標", 10)}%｜美股 {_tgt_p.get("美股市值型目標", 40)}%｜防守 {_tgt_p.get("配息型目標", 20)}%｜債券 {_tgt_p.get("債券型目標", 25)}%｜現金 {_tgt_p.get("現金目標", 5)}%</p><div class="space-y-3 mt-3">',
    ]
    for _k, _lb, _tkey, _col in _defs_p:
        _act = _ppct_p.get(_k)
        if _act is None:
            continue
        _t = _tgt_p.get(_tkey, 0) or 0
        _twd = _ptwd_p.get(_k, 0) or 0
        _gap = _act - _t
        _gcls = "text-green-400" if abs(_gap) <= 2 else ("text-yellow-400" if abs(_gap) <= 5 else "text-red-400")
        _w = min(_act / 55 * 100, 100); _tw = min(_t / 55 * 100, 100)
        _pen_parts.append(
            f'<div><div class="flex justify-between text-xs"><span class="text-slate-300">{_lb}</span>'
            f'<span class="text-slate-100"><b>{_act:.1f}%</b> / 目標 {_t}% <span class="{_gcls}">({"+" if _gap > 0 else ""}{_gap:.1f}pp)</span></span></div>'
            f'<div class="relative h-2 bg-slate-800 rounded-full mt-1"><div class="absolute h-2 rounded-full" style="width:{_w:.0f}%;background:{_col}"></div>'
            f'<div class="absolute h-2 border-l-2 border-white/60" style="left:{_tw:.0f}%"></div></div>'
            f'<div class="text-[10px] text-slate-500 mt-0.5">市值：{_twd / 1e4:.0f} 萬 TWD</div></div>'
        )
    if _ppct_p.get("美股市值型成長_科技") is not None:
        # 2026-10-15 P1-1 附帶：科技目標紅線改讀 snapshot 真值
        #   （原寫死 ≤20%，與 SoT 科技曝險目標 15% 衝突 → 同頁兩個科技門檻）
        _tgt_p = snap.get("penetration", {}).get("targets", {}) or {}
        _tech_tgt_p = float(_tgt_p.get("科技曝險目標") or _tgt_p.get("科技") or 15)
        _pen_parts.append(
            f'<div class="text-[11px] text-slate-400 pt-2 border-t border-slate-700/50">🔬 美股科技 {_ppct_p.get("美股市值型成長_科技", 0):.1f}%（{(_ptwd_p.get("美股市值型成長_科技", 0) or 0) / 1e4:.0f}萬）｜非科技 {_ppct_p.get("美股市值型成長_非科技", 0):.1f}%（{(_ptwd_p.get("美股市值型成長_非科技", 0) or 0) / 1e4:.0f}萬）｜科技目標 ≤{_tech_tgt_p:.0f}%</div>'
        )
    _pen_parts.append("</div>")
    tpl = tpl.replace("__PEN_CARD__", "".join(_pen_parts))

    # ── 月度流入核對清單靜態生成（2026-09-01 定案：✅已入帳 + ⏳待入帳兩段，build 生成 + JS 開頁同邏輯）──
    _inc_parts = []
    _inc_row = (
        '<div class="flex justify-between items-center p-3 bg-slate-900/50 rounded-xl border border-slate-800">'
        '<div class="flex items-center gap-2 text-xs"><span class="text-emerald-400">✅ 已收</span>'
        '<span class="text-slate-300">{label}</span></div>'
        '<span class="text-xs font-mono text-emerald-400 font-bold">{amt}</span></div>'
    )
    _pend_row = (
        '<div class="flex justify-between items-center p-3 bg-slate-900/50 rounded-xl border border-slate-800">'
        '<div class="flex items-center gap-2 text-xs"><span class="text-amber-400">⏳ 待收</span>'
        '<span class="text-slate-300">{label}</span></div>'
        '<span class="text-xs font-mono text-amber-400 font-bold">{amt}</span>'
        '<span class="text-[10px] text-slate-500">{note}</span></div>'
    )
    _inc_parts.append('<div class="text-xs font-bold text-emerald-400 mb-1 mt-1">✅ 已入帳</div>')
    _has_inc = False
    _inc_total = 0
    if salary > 0:
        _inc_parts.append(_inc_row.format(label="台電薪水", amt=f"{_fmt(salary)} TWD")); _has_inc = True; _inc_total += salary
    for _k, _v in _dr.items():
        if isinstance(_v, (int, float)) and _v > 0:
            _inc_parts.append(_inc_row.format(label=_k, amt=f"{_fmt(_v)} TWD")); _has_inc = True; _inc_total += _v
    # 當月房租已收明細（rent_received_records）
    _rent_recv = {}
    for _d, _v in (snap.get("rent_received_records", {}) or {}).items():
        if str(_d).startswith(_today_m):
            if isinstance(_v, dict):
                for _k2, _v2 in _v.items():
                    _rent_recv[_k2] = _rent_recv.get(_k2, 0) + (_v2 or 0)
            elif isinstance(_v, (int, float)):
                _rent_recv["房租"] = _rent_recv.get("房租", 0) + _v
    for _k3, _v3 in _rent_recv.items():
        if _v3 > 0:
            _inc_parts.append(_inc_row.format(label=_k3 + "房租", amt=f"{_fmt(_v3)} TWD")); _has_inc = True; _inc_total += _v3
    _gf_inc = sum((v.get("amount", 0) if isinstance(v, dict) else v)
                  for k, v in (snap.get("girlfriend_repayment_records", {}) or {}).items()
                  if str(k).startswith(_today_m)) or 0
    if _gf_inc > 0:
        _inc_parts.append(_inc_row.format(label="女友還款", amt=f"{_fmt(_gf_inc)} TWD")); _has_inc = True; _inc_total += _gf_inc
    if not _has_inc:
        _inc_parts = ['<div class="text-slate-400">本月尚無入帳</div>']
    else:
        _inc_parts[0] = f'<div class="text-xs font-bold text-emerald-400 mb-1 mt-1">✅ 已收（{_fmt(_inc_total)} TWD）</div>'
    # 待入帳段
    _pend2 = []
    if salary <= 0:
        # 2026-09-15：原 fallback 寫死 39,727（8 月值）→ 改讀 snapshot.monthly_salary；
        # 缺值顯示「金額待確認」而非舊薪資
        _sal_pend = int(snap.get("monthly_salary") or 0)
        _sal_lbl = "本月入帳" if _sal_pend > 0 else "金額待確認（snapshot.monthly_salary 缺失）"
        _pend2.append(("台電薪水", _sal_pend, _sal_lbl))
    if _gf_inc <= 0:
        # 2026-10-01：原寫死 ("女友還款", 6000, "9/5 入帳") → 改讀 snapshot（月還款＋還款日）
        #   否則每月都會停在同一個舊入帳日（使用者 10/1 反映「已入帳但儀表板沒更新」）
        _gfl = ((snap.get("personal_loans") or {}).get("女友借款") or {})
        _gfa = int(float(_gfl.get("月還款") or 0))
        if _gfa > 0:
            _pend2.append(("女友還款", _gfa, str(_gfl.get("還款日") or "每月5號")))
    # 當月應收明細（2026-09-23 INC-241）：逐項待收必須用「當月應收」而非常態 rent_breakdown，
    # 否則一次性折讓（2026-09 洲際W 維修費 −3,000）會變成幽靈待收（26,100 vs 真值 23,100）。
    # 真值來源：snapshot.rent_receivable_by_month[本月]；缺本月 → fallback 常態 rent_breakdown。
    _rrb = (snap.get("rent_receivable_by_month", {}) or {}).get(_today_m) or (snap.get("rent_breakdown", {}) or {})
    for _k4, _v4 in _rrb.items():
        _g4 = _rent_recv.get(_k4, 0)
        if _g4 < _v4:
            _pend2.append((_k4 + "房租", _v4 - _g4, ""))
    if _pend2:
        _pend_total = sum(x[1] for x in _pend2)
        _inc_parts.append(f'<div class="text-xs font-bold text-amber-400 mt-2 mb-1">⏳ 待收（{_fmt(_pend_total)} TWD）</div>')
        for _pl, _pv, _pn in _pend2:
            _inc_parts.append(_pend_row.format(label=_pl, amt=f"{_fmt(_pv)} TWD", note=_pn))
    # 第一金配息（2026-09-01：FA81 8/31 基準日 → 9 月入帳；App 應收推估，待確認）
    _fj_exp = (snap.get("firstjin_dividend_expected", {}) or {}).get(_today_m, {}) or {}
    _fj_amt = _fj_exp.get("amount", 0) or 0
    if _fj_amt > 0 and not any("第一金" in str(x[0]) for x in _pend2):
        _fj_note = _fj_exp.get("note", "")[:40]
        _inc_parts.append(_pend_row.format(label="第一金 FA81 配息", amt=f"{_fmt(_fj_amt)} TWD", note=_fj_note))
        _inc_parts[0 if not _has_inc else -1] = _inc_parts[0 if not _has_inc else -1]  # noop 保留
        # 更新待收段標題合計
        for _k_i, _p in enumerate(_inc_parts):
            if "⏳ 待收（" in _p:
                _inc_parts[_k_i] = _inc_parts[_k_i].replace("）</div>", "）</div>").replace(
                    f"{_fmt(_pend_total)} TWD", f"{_fmt(_pend_total + _fj_amt)} TWD")
                break
    tpl = tpl.replace("__INCOME_LIST__", "".join(_inc_parts))

    # ── 執行中決策追蹤靜態生成（2026-09-01：decision-track 不再硬編碼 8/21 快照 → 讀 pending_decisions）──
    try:
        _pd3 = json.loads((BASE / "pending_decisions.json").read_text(encoding="utf-8"))
        _dt_html = []
        # 2026-09-12：原取「清單前 6 筆」（=最舊 6 筆）→ 新裁決永遠看不到儀表板。
        # 改為：剔除已結案 → 依日期新→舊 → 取最新 8 筆（日報第5章仍列全部）。
        # 2026-09-13：閉環判定與前端 JS 對齊（單一口徑），否則靜態層與即時層顯示不同筆數。
        # 2026-10-11：狀態單一口徑＝pending_engine 四態（待處理／已確認／已完成／關案）。
        # 原白名單在 2026-10-06 狀態正規化後失效 → 「關案」被靜態層當成執行中（與前端 JS 不一致）。
        _open_status = ("待處理", "已確認")
        _closed_kw = ("✅", "☑", "已完成", "已結案", "已定案", "閉環", "已送出", "已核定", "關案")
        def _is_active_r(_r):
            _s = str(_r.get("status", ""))
            if _s in _open_status:
                return True
            if _s in ("已完成", "關案"):
                return False
            return not any(_kw in _s for _kw in _closed_kw)
        _pd3_rows = [r for r in (_pd3 if isinstance(_pd3, list) else [])
                     if isinstance(r, dict) and _is_active_r(r)]
        _pd3_rows.sort(key=lambda r: str(r.get("date", "")), reverse=True)
        for _d in _pd3_rows[:8]:
            _d_date = str(_d.get("date", ""))[5:].replace("-", "/")
            _d_tt = str(_d.get("title", "") or "")[:44]
            _d_st = str(_d.get("status", "") or "")[:64]
            # 2026-09-12：pending 條目可帶 "card" 欄位（決策卡檔名）→ 標題變可點連結
            _d_card = str(_d.get("card", "") or "").strip()
            if _d_card:
                _tt_html = (f'<a href="{_d_card}" target="_blank" '
                            f'class="text-white font-bold flex-1 underline decoration-sky-400/60 '
                            f'hover:text-sky-300">📑 {_d_tt}</a>')
            else:
                _tt_html = f'<span class="text-white font-bold flex-1">{_d_tt}</span>'
            _dt_html.append(
                f'<div class="flex items-center gap-3 p-2 bg-slate-900/30 rounded border border-red-500/30">'
                f'<span class="text-amber-400 font-mono font-bold w-14">{_d_date}</span>'
                f'{_tt_html}'
                f'<span class="text-slate-300 font-mono">{_d_st}</span></div>'
            )
        tpl = tpl.replace("__DECISION_TRACK__", "".join(_dt_html) if _dt_html else '<div class="text-slate-400">無執行中決策</div>')
    except Exception:
        tpl = tpl.replace("__DECISION_TRACK__", '<div class="text-slate-400">決策追蹤暫無資料</div>')

    # ── CIO 戰略審查靜態 fallback（2026-09-07：讀 cio_review.json 最新一則；JS 開頁即時覆蓋）──
    try:
        import html as _html
        _cio = json.loads((BASE / "cio_review.json").read_text(encoding="utf-8"))
        _crl = sorted([r for r in (_cio.get("reviews") or []) if r.get("date")],
                      key=lambda r: str(r["date"]), reverse=True)
        if _crl:
            _c0 = _crl[0]
            _st = _c0.get("structured") or {}
            def _cio_sec(ico, title, color, items):
                if not items:
                    return ""
                _body = "".join(
                    f'<div style="padding:3px 0 3px 10px;border-left:2px solid {color}55;color:#e2e8f0;line-height:1.65">{_html.escape(str(s))}</div>'
                    for s in items
                )
                return f'<div style="margin-top:9px"><div class="cio-h" style="color:{color};margin-top:0">{ico} {_html.escape(title)}（{len(items)}）</div>{_body}</div>'
            _h = f'<div class="cio-card"><div class="text-white font-bold text-[13px]">📅 {_c0.get("date")}（{_c0.get("weekday", "")}）最近一次審查（結構化快照）</div>'
            _h += _cio_sec("✅", "已核准", "#34d399", _st.get("approved"))
            _h += _cio_sec("⏳", "已核准待執行", "#fbbf24", _st.get("pending_exec"))
            _h += _cio_sec("⏸️", "延後 / 凍結", "#94a3b8", _st.get("frozen"))
            _h += _cio_sec("📌", "Pending 關鍵", "#93c5fd", _st.get("pending_notes"))
            _objs = _st.get("objections") or []
            if _objs:
                _ob = "".join(
                    f'<div style="padding:5px 8px;margin-top:5px;background:rgba(15,23,42,0.5);border:1px solid rgba(255,255,255,0.06);border-radius:8px;color:#e2e8f0;line-height:1.65"><span style="display:inline-block;font-size:10px;font-weight:800;padding:1px 7px;border-radius:99px;background:{"#f87171" if (o.get("type")=="質疑") else ("#fb7185" if (o.get("type")=="風險") else ("#fbbf24" if (o.get("type")=="提醒") else "#60a5fa"))}22;color:{"#f87171" if (o.get("type")=="質疑") else ("#fb7185" if (o.get("type")=="風險") else ("#fbbf24" if (o.get("type")=="提醒") else "#60a5fa"))};border:1px solid {"#f87171" if (o.get("type")=="質疑") else ("#fb7185" if (o.get("type")=="風險") else ("#fbbf24" if (o.get("type")=="提醒") else "#60a5fa"))}55;margin-right:6px">{_html.escape(str(o.get("type","意見")))}</span>{_html.escape(str(o.get("text","")))}</div>'
                    for o in _objs
                )
                _h += f'<div style="margin-top:10px"><div class="cio-h cio-h2" style="margin-top:0">🧠 Part B：對策反抗</div>{_ob}</div>'
            if _st.get("conclusion"):
                _h += f'<div style="margin-top:10px;padding:8px 10px;background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.3);border-radius:8px;color:#d1fae5;line-height:1.7">📌 <b>結論</b>：{_html.escape(str(_st.get("conclusion")))}</div>'
            _full = _html.escape(str(_c0.get("text", "")))
            _full = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", _full).replace("\n", "<br>")
            _h += f'<details class="cio-old" style="margin-top:8px"><summary>📄 看全文（{len(_full)} 字）</summary><div class="cio-body" style="margin-top:4px">{_full}</div></details>'
            _h += '</div>'
            tpl = tpl.replace("__CIO_REVIEW__", _h)
        else:
            tpl = tpl.replace("__CIO_REVIEW__", '<div class="text-slate-400">CIO 審查資料尚未產生（每週一/三 18:30 後出現）</div>')
    except Exception:
        tpl = tpl.replace("__CIO_REVIEW__", '<div class="text-slate-400">CIO 審查資料尚未產生（每週一/三 18:30 後出現）</div>')

    # ── 下週工作清單（2026-09-06：讀 schedule_events 未來 7 天，每天自動滑動）──
    try:
        import datetime as _dt_nw
        _se = json.loads((BASE / "schedule_events.json").read_text(encoding="utf-8"))
        _today = _dt_nw.date.today()
        _cutoff = _today + _dt_nw.timedelta(days=7)
        _imp_color = {"high": "#f87171", "medium": "#fbbf24", "low": "#94a3b8"}
        _wd = "一二三四五六日"
        _nw_rows = []
        for _e in sorted(_se, key=lambda x: str(x.get("date", ""))):
            _dstr = str(_e.get("date", ""))[:10]
            try:
                _d = _dt_nw.date.fromisoformat(_dstr)
            except Exception:
                continue
            if not (_today <= _d <= _cutoff):
                continue
            _imp = _e.get("importance", "medium")
            _c = _imp_color.get(_imp, "#94a3b8")
            _label = f"{_d.month}/{_d.day} ({_wd[_d.weekday()]})"
            _item = str(_e.get("item", "")).replace("｜", " ｜ ")
            _nw_rows.append(
                f'<div style="display:flex;gap:8px;padding:5px 0;border-bottom:1px dashed #1f2937;font-size:12px;line-height:1.55">'
                f'<span style="color:{_c};font-weight:800;white-space:nowrap;min-width:74px">{_label}</span>'
                f'<span style="color:#e2e8f0;flex:1">{_item}</span></div>'
            )
        if _nw_rows:
            _nw_html = "".join(_nw_rows)
        else:
            _nw_html = '<div style="color:#9ca3af;font-size:12px">下週暫無排定事項</div>'
        tpl = tpl.replace("__NEXT_WEEK__", _nw_html)
    except Exception as _e:
        tpl = tpl.replace("__NEXT_WEEK__", f'<div style="color:#9ca3af;font-size:12px">下週清單載入失敗（{_e}）</div>')

    # ── 八大連結動態化（2026-08-26：模板連結寫死 8/21-23 → glob 最新檔名）──
    import glob as _glob
    # 2026-09-22：連結設定改由 links_config.py 單一來源提供
    # （原本與 update_dashboard_links._LINK_PATTERNS 各存一份 → 新增按鈕漏改一邊就永遠停在舊檔）
    import sys as _sys, pathlib as _pl
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
    import links_config as _lc
    _link_map = _lc.build_link_map()
    _link_hits = 0
    for _ph, _pat in _link_map.items():
        if _ph in tpl:
            # 2026-10-20：改以「檔名中的日期」挑最新（原 sorted() 取字母序最後一個，
            # 導致 *_card_*.html 這種檔名不固定的圖樣永遠指向字母序較大的舊卡，
            # 例：investment_structure_plan_card_2026-10-20 輸給 policyB_conversion_card_2026-09-12）。
            # 無日期者維持字母序，行為不變。
            def _fdate_key(_p):
                # 年月日可缺日（如 dynamic_monthly_review_2026-09.html）：缺日視為該月 31 日，
                # 否則「2026-09」會因抓不到三段日期而排到「2026-08-31」之前（倒退選舊檔）。
                _m = re.search(r"(20\d{2})[-_]?(\d{2})(?:[-_]?(\d{2}))?",
                               str(_p).replace("\\", "/").split("/")[-1])
                return (_m.group(1) + _m.group(2) + (_m.group(3) or "31")) if _m else "00000000"
            _fs = sorted(_glob.glob(str(BASE / _pat)), key=lambda _x: (_fdate_key(_x), str(_x)))
            if _fs:
                _new = str(_fs[-1]).replace("\\", "/").split("/")[-1]  # Windows glob 回傳 str
                tpl = tpl.replace(_ph, _new)
                _link_hits += 1
            else:
                # 2026-08-27 fallback：找不到檔案 → 指向儀表板首頁（不留死佔位符）
                tpl = tpl.replace(_ph, "index.html")
                _link_hits += 1
    # ── 本週完成清單（2026-09-13：work_log.json「完成」近 7 天 — 原本是寫死靜態清單，永不更新）
    #    2026-09-15（使用者核准）：併入「修正」並以 🔧 區分；項目文字做 HTML 轉義（item 可能含 <p> 等標籤字面）──
    try:
        import datetime as _dtm
        import html as _html
        _wlog = json.loads((BASE / "work_log.json").read_text(encoding="utf-8"))
        _td = _dtm.date.today()
        _lo = _td - _dtm.timedelta(days=6)
        _CAT_ICON = {"完成": "✅", "修正": "🔧", "更正": "📝"}  # 2026-10-02：加「更正」與模板 JS CLOSED_CAT 同步（兩層語義一致）
        _done = []
        for _e in _wlog:
            _ic = _CAT_ICON.get(str(_e.get("category", "")))
            if not _ic:
                continue
            try:
                _ed = _dtm.date.fromisoformat(str(_e.get("date", ""))[:10])
            except ValueError:
                continue
            if _lo <= _ed <= _td:
                _done.append((_ed, _ic, str(_e.get("item", ""))))
        _done.reverse()  # 同日：後登錄者較新
        _done.sort(key=lambda x: x[0], reverse=True)
        _wd_rows = [f'<div class="text-slate-300">{_ic} {d.month}/{d.day} {_html.escape(it, quote=False)}</div>'
                    for d, _ic, it in _done]
        _wd_inner = "".join(_wd_rows[:10])
        if len(_wd_rows) > 10:
            _wd_inner += (f'<details><summary style="cursor:pointer;color:#6ee7b7;font-weight:700">顯示其餘 {len(_wd_rows) - 10} 項</summary>'
                          f'<div class="grid grid-cols-1 gap-1.5" style="margin-top:6px">{"".join(_wd_rows[10:])}</div></details>')
        if not _wd_inner:
            _wd_inner = '<div class="text-slate-400">近 7 天無完成紀錄</div>'
        _n_fix = sum(1 for _d, _i, _t in _done if _i == "🔧")
        tpl = tpl.replace("__WEEK_DONE__", _wd_inner)
        tpl = tpl.replace("__WEEK_DONE_RANGE__",
                          f"近 7 天 {_lo.month}/{_lo.day}–{_td.month}/{_td.day}｜{len(_done)} 項（✅ {len(_done) - _n_fix}｜🔧 {_n_fix}）")
    except Exception as _wde:
        tpl = tpl.replace("__WEEK_DONE__", f'<div class="text-slate-400">完成清單載入失敗（{_wde}）</div>')
        tpl = tpl.replace("__WEEK_DONE_RANGE__", "")

    # ── 被動收入結構條（2026-09-14：模板寫死值移除，改由 snapshot 動態計算；INC 對策）──
    try:
        _pi = snap.get("passive_income", {}) or {}
        # 2026-10-06 使用者裁決（口徑錯置修正）：本區塊是「常態模型」——與配息保守
        # （fund_dividend_conservative）、房租常態（rent_monthly）並列，且覆蓋率以此為底線，
        # 因此薪資必須取常態 monthly_salary。
        # 原 `_sal = salary`（當月實收 salary_records[當月]）有兩個病：
        #   ①月初尚未補記 → 常態線顯示薪水 0（實例：10/01–10/05 為 180,100）
        #   ②單月因素（連假等）波動被當成常態（實例：10/06 補記後 39,777）
        # 當月實收的呈現不受影響：data-k="salary_got"／"got_total2" 由 _data_k_map
        # 靜態注入（L434/L432）並於開頁由 JS 以 salary_records[當月] 覆寫。
        _sal = float(snap.get("monthly_salary") or 0)
        if not snap.get("monthly_salary"):
            print("[WARN] 儀表板：snapshot.monthly_salary 缺值：常態薪資以 0 計（不以當月實收冒充）")
        # 2026-09-23 INC-248：保守口徑鍵缺值時不得靜默退到「當月實收」——
        # 原 `or div_total（當月實收）` 會讓圖例的「覆蓋 X%（保守底線）」偷偷變成實收口徑；
        # 房租同理（rent_got＝當月已收）。缺值一律 WARN 並以 0 計（寧可低估，不得偷換口徑）。
        _div = float(_pi.get("fund_dividend_conservative", 0) or 0)
        if "fund_dividend_conservative" not in _pi:
            print("[WARN] 儀表板：passive_income.fund_dividend_conservative 缺值：配息保守以 0 計（不以當月實收冒充）")
        _div_act = float(snap.get("dividend_month_actual") or snap.get("monthly_dividend_total") or 0)   # 當月實收：成對顯示用（2026-09-23）
        _rent = float(_pi.get("rent_monthly", 0) or 0)
        if "rent_monthly" not in _pi:
            print("[WARN] 儀表板：passive_income.rent_monthly 缺值：房租常態以 0 計（不以當月已收冒充）")
        _exp = float(expense or 0)
        _inc_tot = _sal + _div + _rent
        if _inc_tot <= 0:
            raise ValueError("income total <= 0")
        _pc = lambda x: x / _inc_tot * 100.0
        _bar = "".join(
            f'<div style="width: {_pc(v):.1f}%" class="shadow-none flex flex-col text-center whitespace-nowrap text-white justify-center {cls} font-bold" title="{lab}">{lab} {_pc(v):.0f}%</div>'
            for lab, v, cls in (("薪水", _sal, "bg-yellow-600"), ("配息", _div, "bg-blue-600"), ("房租", _rent, "bg-teal-600")))
        _cov = (_div + _rent) / _exp * 100.0
        # 2026-09-27：實收口徑與 FI 跑道改由 passive_caliber 單一來源計算。
        # 原本這條結構條自算一份 → 房租實收校正（80,100→77,100）後僅日報生效，
        # 儀表板仍顯示常態值，形成兩份數字。
        _sc = _pcal.scenarios(snap)
        _cov_act = _sc["act"]["coverage"]   # 當月實收覆蓋（配息實收＋房租實收）
        _mr = snap.get("metrics_registry") or {}
        _mv = _mr.get("metric_version")
        _metric_note = ""
        if _mv:
            _stress_hist = ((_mr.get("影響") or {}).get("壓力情境覆蓋率") or {}).get("歷史值")
            _metric_note = (f'<span class="text-slate-400">｜口徑 v{_mv}「度量修正」'
                            f'（壓力情境 {_stress_hist}%→{_sc["stress"]["coverage"]:.1f}%，非資產變動）</span>')
        _cl = snap.get("cash_layers") or {}
        _cash_note = ""
        if _cl:
            # 2026-10-11 工單A：原本乾粉直接讀 snapshot.cash_layers.dry_powder（不足時被夾成 0
            #   → 顯示「＋乾粉 0」，與報告的「短少 60,339」矛盾）。改走 SoT 現算並保留正負號。
            from sot_targets import dry_powder as _dp_fn
            _dpx = _dp_fn(snap)
            _dry_txt = dry_display(_dpx)
            _cash_note = (f'<span class="text-slate-400">｜現金分層：總 {_cl.get("cash_total", 0):,.0f}'
                          f'／可動用 {_cl.get("available", _cl.get("unrestricted_cash", 0)):,.0f}'
                          f'（底線 {( _cl.get("emergency_cash") or {}).get("金額", 0):,.0f}'
                          f'＋{_dry_txt}）'
                          f'／指定還債 {( _cl.get("restricted_cash") or {}).get("debt_repayment_reserve", 0):,.0f}'
                          f'（不得當普通現金）</span>')
        _legend = (f'<div class="flex gap-3 text-[10px] text-slate-400 mt-1">'
                   f'<span class="text-yellow-400">▮ 薪水 {_pc(_sal):.0f}%</span>'
                   f'<span class="text-blue-400">▮ 配息 {_pc(_div):.0f}%</span>'
                   f'<span class="text-teal-400">▮ 房租 {_pc(_rent):.0f}%</span>'
                   f'<span class="text-slate-500">▮ 覆蓋 {_cov:.1f}%（保守底線）</span>'
                   f'<span class="text-slate-300">｜當月實收 {_cov_act:.1f}%'
                   f'（配息 {_sc["div_act"]:,.0f} ＋ 房租 {_sc["rent_act"]:,.0f}）</span>'
                   # 2026-10-15 使用者裁決：新增常態層並列（基金常態 80,000＋保單常態 97,072；
                   # 保單值為暫定規劃值）。與實收／保守互不覆寫。
                   f'<span class="text-amber-300">｜常態 {_sc["norm"]["coverage"]:.1f}%'
                   f'（配息 {_sc["div_norm"]:,.0f} ＋ 房租 {_sc["rent_norm"]:,.0f}）</span></div>'
                   f'<div class="flex flex-wrap gap-3 text-[10px] mt-1">'
                   f'<span class="text-emerald-400">💰 月盈餘：保守 {_pcal.surplus_text(_sc["con"]["surplus"])}'
                   f'／實收 {_pcal.surplus_text(_sc["act"]["surplus"])}'
                   f'／常態 {_pcal.surplus_text(_sc["norm"]["surplus"])}</span>'
                   f'<span class="text-amber-400">🏁 FI 跑道（極端情境口徑）：{_pcal.runway_text(_sc["extreme"]["runway_days"])}'
                   f'、實收情境 {_pcal.runway_text(_sc["act"]["runway_days"])}</span>'
                   f'<span class="text-amber-300">｜壓力情境覆蓋 {_sc["stress"]["coverage"]:.1f}%'
                   f'（留停判準 ≥100%）</span>'
                   f'{_metric_note}'
                   f'{_cash_note}</div>')
        tpl = tpl.replace("__INC_BAR__", _bar)
        tpl = tpl.replace("__INC_LEGEND__", _legend)
        tpl = tpl.replace("__INC_COV__", f"{_cov:.1f}% 覆蓋（保守底線）｜實收 {_cov_act:.1f}%"
                                       f"｜常態 {_sc['norm']['coverage']:.1f}%")
        tpl = tpl.replace("__INC_SUMMARY__", f"薪水 {_fmt(_sal)} + 配息保守 {_fmt(_div)} + 房租 {_fmt(_rent)} = {_fmt(_inc_tot)} TWD")
        tpl = tpl.replace("__INC_EXPENSE__", _fmt(_exp))
        tpl = tpl.replace("__INC_SALARY__", _fmt(_sal))
        tpl = tpl.replace("__INC_DIV__", _fmt(_div))
        tpl = tpl.replace("__INC_RENT__", _fmt(_rent))
        # 2026-10-06：此佔位符只出現在 data-k="got_total2" 的 span（當月實際已收），
        # 靜態 fallback 必須與 JS 的 gotTotal（_salaryA + divTotal + rentGot）同口徑，
        # 不得放常態總計（_inc_tot）。正常情況該 span 會被 L481 的 data-k 注入覆寫。
        tpl = tpl.replace("__INC_TOTAL__", _fmt(got_total))
        print(f"  💰 被動收入結構條：薪水 {_fmt(_sal)} / 配息 {_fmt(_div)}（保守） / 房租 {_fmt(_rent)}｜覆蓋 {_cov:.1f}%（保守底線）｜當月實收 {_cov_act:.1f}%｜常態 {_sc['norm']['coverage']:.1f}%（配息 {_sc['div_norm']:,.0f}）")
    except Exception as _ince:
        for _ph in ("__INC_BAR__", "__INC_LEGEND__", "__INC_COV__", "__INC_SUMMARY__",
                    "__INC_EXPENSE__", "__INC_SALARY__", "__INC_DIV__", "__INC_RENT__", "__INC_TOTAL__"):
            tpl = tpl.replace(_ph, "—")
        print("  ⚠️ 被動收入結構條注入失敗:", _ince)

    # ── 被動收入基準觀察小卡（2026-09-23 使用者指示：以 9 月完整估計為基準，走 3 個月再修正）──
    try:
        _rec = snap.get("dividend_records", {}) or {}
        _base_m = "2026-09"                                    # 基準月（使用者 9/23 指定）
        _obs_n = 3                                             # 觀察月數
        _all_m = sorted([m for m in _rec if re.match(r"^\d{4}-\d{2}$", m)])
        _ms = _all_m[-_obs_n:]
        if _base_m in _all_m and _base_m not in _ms:      # 2026-09-28：基準月一律留在窗口內
            _ms = sorted(set(_ms) | {_base_m})            # （原取「最近 N 個月」，2026-12 起基準月掉出 → 基準列消失、合計歸零）

        def _bucket_of(_n):
            return dividend_bucket(_n)

        _rows = []
        _base_tot = 0.0
        for _m in _ms:
            _d = _rec.get(_m) or {}
            _sum = {"ins": 0.0, "etf": 0.0, "fund": 0.0, "other": 0.0}
            for _n, _v in _d.items():
                if isinstance(_v, (int, float)):
                    _sum[_bucket_of(_n)] += _v
            _i, _e, _f, _tot = _sum["ins"], _sum["etf"], _sum["fund"], _sum["ins"] + _sum["etf"] + _sum["fund"]
            if _m == _base_m:
                _base_tot = _tot
                _rows.append(f'<tr class="border-b border-slate-900 font-bold text-teal-400">'
                             f'<td class="text-left py-1">{_m}（基準）</td><td class="text-right">{_fmt(_i)}</td>'
                             f'<td class="text-right">{_fmt(_e)}</td><td class="text-right">{_fmt(_f)}</td>'
                             f'<td class="text-right">{_fmt(_tot)}</td></tr>')
            else:
                _rows.append(f'<tr class="border-b border-slate-900 text-slate-300">'
                             f'<td class="text-left py-1">{_m}</td><td class="text-right">{_fmt(_i)}</td>'
                             f'<td class="text-right">{_fmt(_e)}</td><td class="text-right">{_fmt(_f)}</td>'
                             f'<td class="text-right">{_fmt(_tot)}</td></tr>')
        _mi = (int(_today_m[:4]) - int(_base_m[:4])) * 12 + (int(_today_m[5:7]) - int(_base_m[5:7])) + 1
        _ci = min(max(_mi, 1), _obs_n)
        _end_m = f"{int(_base_m[:4]) + (int(_base_m[5:7]) - 1 + _obs_n) // 12}-{(int(_base_m[5:7]) - 1 + _obs_n) % 12 + 1:02d}"
        _floor = float((snap.get("passive_income", {}) or {}).get("fund_dividend_conservative", 0) or 0)
        tpl = tpl.replace("__DIVBASE_TABLE__", "".join(_rows) or '<tr><td colspan="5" class="py-2 text-slate-500">無 dividend_records 資料</td></tr>')
        tpl = tpl.replace("__DIVBASE_BASE_M__", _base_m)
        tpl = tpl.replace("__DIVBASE_N__", str(_obs_n))
        tpl = tpl.replace("__DIVBASE_STATUS__", f"⏳ 第 {_ci}/{_obs_n} 個月")
        tpl = tpl.replace("__DIVBASE_FLOOR__", _fmt(_floor))
        # 其他項（一次性，不計入三桶）動態列出，勿在模板寫死名稱
        _other_items = [f"{_m} {_n} {_v:,.0f}" for _m in _ms for _n, _v in (_rec.get(_m) or {}).items()
                        if isinstance(_v, (int, float)) and _v and _bucket_of(_n) == "other"]
        _other_txt = "、".join(_other_items) if _other_items else "無（本期僅三桶配息）"
        tpl = tpl.replace("__DIVBASE_NOTE__",
                          f"基準月 {_base_m} 三桶合計 {_fmt(_base_tot)}（內含安聯一次性補入，常態口徑見 monthly_dividend_breakdown）。"
                          f"觀察期 {_base_m}～{_end_m}，檢視點 {_end_m}-01 真值日 → 依三個月逐月實收修正保守底線（現行 {_fmt(_floor)}）。"
                          f"期間判準層不動（使用者 2026-09-23 指示：以 9 月完整估計為基準，走 3 個月再修正）。"
                          f"註：不計入三桶之其他項＝{_other_txt}。")
        print(f"  🗓️ 被動收入基準觀察卡：基準 {_base_m} 三桶 {_fmt(_base_tot)}｜觀察 {_ci}/{_obs_n} 個月")
    except Exception as _dbe:
        for _ph in ("__DIVBASE_TABLE__", "__DIVBASE_STATUS__", "__DIVBASE_FLOOR__", "__DIVBASE_NOTE__",
                    "__DIVBASE_BASE_M__", "__DIVBASE_N__"):
            tpl = tpl.replace(_ph, "—")
        print("  ⚠️ 被動收入基準觀察卡注入失敗:", _dbe)

    # ── 配息接力戰略時序（三站卡片）動態化（2026-10-10：原寫死於模板，每月停在舊月）──
    try:
        tpl = tpl.replace("__RELAY_SCHEDULE__", relay_schedule_html(snap.get("relay_stations", {})))
    except Exception as _rse:
        tpl = tpl.replace("__RELAY_SCHEDULE__", '<p class="text-xs text-slate-400">接力資料待更新</p>')
        print("  ⚠️ 接力時序注入失敗:", _rse)

    # ── 投資績效卡（2026-10-31 使用者裁決：四分類，只列可算項；缺成本基礎不宣稱報酬）──
    try:
        _perf_html, _perf_asof = build_perf_card(snap)
        tpl = tpl.replace("__PERF_CARD__", _perf_html)
        tpl = tpl.replace("__PERF_ASOF__", _perf_asof)
    except Exception as _pfe:
        tpl = tpl.replace("__PERF_CARD__", '<div class="p-2 text-xs text-red-400">投資績效卡注入失敗</div>')
        tpl = tpl.replace("__PERF_ASOF__", "—")
        print("  ⚠️ 投資績效卡注入失敗:", _pfe)

    # ── 本月投資績效＋資金成本（2026-10-31 使用者要求）──
    try:
        tpl = tpl.replace("__PERF_MONTH_CARD__", build_perf_month_card(snap))
    except Exception as _pme:
        tpl = tpl.replace("__PERF_MONTH_CARD__", "")
        print("  ⚠️ 本月投資績效卡注入失敗:", _pme)

    # ── 每月收入與獲利總覽（2026-10-31 規格 v2：只增不動其他區塊）──
    try:
        _mio_hist = json.loads((BASE / "asset_diff_history.json").read_text(encoding="utf-8"))
    except Exception as _mhe:
        _mio_hist = {}
        print("  ⚠️ 每月總覽：asset_diff_history 讀取失敗，期初一律以「資料不足」處理:", _mhe)
    try:
        _mio_card, _mio_trace, _mio_status = build_monthly_overview(snap, _mio_hist)
        tpl = tpl.replace("__MIO_CARD__", _mio_card)
        tpl = tpl.replace("__MIO_TRACE__", _mio_trace)
        tpl = tpl.replace("__MIO_STATUS__", _mio_status)
        tpl = tpl.replace("__MIO_MONTH__", str(snap.get("date") or "")[:7] or "—")
    except Exception as _moe:
        tpl = tpl.replace("__MIO_CARD__", '<div class="text-xs text-red-400">每月總覽產生失敗</div>')
        tpl = tpl.replace("__MIO_TRACE__", "")
        tpl = tpl.replace("__MIO_STATUS__", "")
        tpl = tpl.replace("__MIO_MONTH__", "—")
        print("  ⚠️ 每月收入與獲利總覽產生失敗:", _moe)

    # 2026-10-12 資安處置：輸出前最後一道——遮罩帳號識別碼與安全線門檻（唯一實作在 public_mask）

    tpl = public_mask.scrub(tpl)

    # 2026-10-15 P1-1：__LIVE_ROWS_JS__ 若因雷達週計畫缺失而未注入 → 以空清單收尾
    #   （JS 端逐列比對不符即回退原值），絕不留裸佔位符進 index.html（否則整段 JS 語法錯誤）。
    tpl = tpl.replace("__LIVE_ROWS_JS__", "[]")
    (BASE / "index.html").write_text(_band_filter(tpl), encoding="utf-8", newline="\n")  # 2026-10-12：鎖 LF，避免每次重建產生整檔 CRLF 假 diff
    print(f"✅ 儀表板注入完成（{hits} 組值 + {_link_hits} 連結動態化）｜現金 {_fmt(cash)} / 保單 {_fmt(ins)} / 配息 {_fmt(div_total)} / 租金 {_fmt(rent_got)}")

if __name__ == "__main__":
    main()
