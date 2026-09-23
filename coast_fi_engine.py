#!/usr/bin/env python3
"""coast_fi_engine.py — Coast FI 離職控管引擎（Coast FI Exit Engine）v1
2026-09-23 建立：使用者提供規格（4 大指標＋紅黃綠矩陣），落地為單一真值引擎。

設計原則
  1. 全部讀 snapshot.json（單一真值），本檔不含任何寫死金額／門檻。
     門檻優先序：snapshot.coast_fi_config > DEFAULT_CONFIG（僅為首次預設）。
  2. 質押數據一律走 pledge_status.pledge_facts()（既有唯一來源），不自行重算。
  3. 與既有「留停驗收表」口徑對齊：被動收入用 passive_income.total_conservative、
     支出用 monthly_expense、配息壓力用 haircut 0.8 + 洲際W 空置（既有壓力情境口徑）。
  4. 本檔預設 dry-run（只印不寫）；--write 才寫回 snapshot.coast_fi_engine。

用法
  python coast_fi_engine.py            # dry-run：印出日報區塊＋診斷
  python coast_fi_engine.py --write    # 寫回 snapshot.coast_fi_engine（附歷史）
"""
import json
import sys
import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"

# ── 首次預設（經使用者核准後會固化進 snapshot.coast_fi_config，之後以此為準）──────
DEFAULT_CONFIG = {
    "version": "v1-2026-09-23",
    "swr_pct": 4.0,            # FI 目標 = 年支出 ÷ 4%（保守底線口徑）
    "yield_fi_pct": 5.0,       # 配息型 FI 目標 = 年支出 ÷ 配息率（本戶模型口徑）
    "real_return_pct": 5.0,    # Coast 複利：實質年化報酬假設
    "target_date": "2027-02-01",   # 目標日＝留停生效日（使用者 2026-09-23 定調：已在規劃退休）
    "years_to_target": None,   # 若要直接給年數（覆蓋 target_date）在此填數字
    "cash_caliber": "net_of_reserve",   # net_of_reserve（扣追繳緩衝，正式口徑）| cash_total
    "stress_dividend_haircut": 0.8,     # 配息壓力砍 20%（沿用既有壓力情境口徑）
    "light_work_incomes": [0, 20000, 30000],  # 退休後「簡單工作」月收敏感度
    "targets": {
        "coast_fi_ratio_pct": 100,
        "pccr_pct": 120,
        "runway_days": 540,
        "maintenance_pct": 180,
    },
}


def years_to_target(c, today):
    """距目標日年數（Coast FI 的複利期）。直接給 years_to_target 時以它為準。"""
    if c.get("years_to_target") is not None:
        return float(c["years_to_target"])
    td = c.get("target_date")
    if not td:
        return 0.0
    try:
        d = (datetime.date.fromisoformat(str(td)[:10]) - today).days / 365.25
    except ValueError:
        return 0.0
    return max(round(d, 2), 0.0)


def load():
    return json.loads(SNAP.read_text(encoding="utf-8"))


def cfg(snap):
    c = dict(DEFAULT_CONFIG)
    c["targets"] = dict(DEFAULT_CONFIG["targets"])
    u = snap.get("coast_fi_config") or {}
    for k, v in u.items():
        if k == "targets" and isinstance(v, dict):
            c["targets"].update(v)
        else:
            c[k] = v
    return c


def growth_assets(snap):
    """成長資產（Coast FI 本金）= 全穿透市值型部位 ＋ 不動產淨值（僅扣房貸）。
    為什麼只扣房貸：保單借貸/券商質押是金融資產擔保，扣在房產淨值會重複計提。"""
    pen = (snap.get("penetration") or {}).get("actual_twd") or {}
    tw = float(pen.get("台股市值型成長") or 0)
    us = float(pen.get("美股市值型成長") or 0)
    re_v = float(snap.get("real_estate") or 0)
    mort = float(snap.get("mortgage_balance") or 0)
    fin_debt = float(snap.get("policy_pledge_loan") or 0) + float(
        (snap.get("liabilities_build_up") or {}).get("券商質押") or 0)
    return {
        "tw_growth": tw, "us_growth": us, "re_value": re_v, "mortgage": mort,
        "re_net": re_v - mort, "fin_debt": fin_debt,
        "total": tw + us + (re_v - mort),
        "net_after_fin_debt": tw + us + (re_v - mort) - fin_debt,
    }


def coast_metric(snap, c, ga, today):
    exp = float(snap.get("monthly_expense") or 0)
    annual = exp * 12
    fi_swr = annual / (c["swr_pct"] / 100.0) if c["swr_pct"] else 0
    fi_yield = annual / (c["yield_fi_pct"] / 100.0) if c["yield_fi_pct"] else 0
    n = years_to_target(c, today)
    r = c["real_return_pct"] / 100.0
    growth_mult = (1 + r) ** n
    fin_only = ga["tw_growth"] + ga["us_growth"]   # 純金融（經典 Coast FI 的資本）
    out = {"fi_target_swr": fi_swr, "fi_target_yield": fi_yield, "years_to_target": n,
           "target_date": c.get("target_date"), "real_return_pct": c["real_return_pct"],
           "fin_only_capital": fin_only}
    for tag, fi in (("swr", fi_swr), ("yield", fi_yield)):
        thr = fi / growth_mult if growth_mult else 0
        out[f"coast_threshold_{tag}"] = thr
        out[f"coast_fi_ratio_{tag}_pct"] = round(ga["total"] / thr * 100, 1) if thr else 0
        # 純金融口徑（不含房產淨值）＝正式判準：經典 Coast FI 只看可複利資本
        out[f"coast_fi_ratio_fin_only_{tag}_pct"] = round(fin_only / thr * 100, 1) if thr else 0
        out[f"coast_gap_fin_only_{tag}"] = max(thr - fin_only, 0)
        # 不投入新資金的情況：A×growth_mult = 未來值 → 缺口與每月需投入額
        fv = ga["total"] * growth_mult
        gap_fv = max(fi - fv, 0)
        out[f"fv_no_contrib_{tag}"] = fv
        out[f"gap_fv_{tag}"] = gap_fv
        mr = r / 12.0
        if gap_fv > 0 and mr > 0 and n > 0:
            m = round(n * 12)
            out[f"monthly_needed_{tag}"] = gap_fv * mr / ((1 + mr) ** m - 1)
        else:
            out[f"monthly_needed_{tag}"] = 0.0
    return out


def pccr_metric(snap, c):
    """PCCR 三軌（2026-09-23 使用者質疑後修正）：
    原本只有「保守底線」一軌，會讓人把下限誤讀成現況。改三軌並列：
      ① 正式判準＝常態配息×0.8＋租金（規格口徑，也是實際會收到的量）
      ② 保守底線＝配息基本值＋租金（留停驗收表/健康度口徑，是下緣不是現況）
      ③ 當月實收＝dividend_month_actual＋租金（當期真值，隨月浮動）
    女友還款 6,000 與利息 2,858 不併入：前者非被動且 12/5 結清，後者非經常。"""
    pi = snap.get("passive_income") or {}
    exp = float(snap.get("monthly_expense") or 0)
    div_c = float(pi.get("fund_dividend_conservative") or 0)          # 保守基本值
    div_n = float(snap.get("monthly_dividend_total")
                  or pi.get("fund_dividend_monthly") or 0)            # 常態月配（9月 147,975）
    div_a = float(snap.get("dividend_month_actual") or div_n)          # 當月實收
    rent = float(pi.get("rent_monthly") or 0)
    h = c["stress_dividend_haircut"]

    def cov(x):
        return round(x / exp * 100, 1) if exp else 0

    return {
        "expense": exp, "rent": rent,
        "dividend_conservative": div_c, "dividend_normal": div_n, "dividend_actual": div_a,
        "pccr_pct": cov(div_n * h + rent),              # 正式判準（規格口徑）
        "pccr_conservative_pct": cov(div_c + rent),     # 下緣（留停驗收表口徑）
        "pccr_actual_pct": cov(div_a + rent),           # 當月實收
        "pccr_normal_headroom": round((div_n * h + rent) / exp * 100, 1) if exp else 0,
        "nonpassive": {"girlfriend_repayment": float(pi.get("girlfriend_repayment") or 0)},
        "canonical_source": "monthly_dividend_total（常態）／passive_income.fund_dividend_conservative（保守）",
    }


def light_work_sensitivity(snap, c, ga):
    """退休後「簡單工作」月收 → 所需金融本金與缺口（配息率口徑）。
    為什麼要有這塊：使用者 2026-09-23 定調「已在規劃退休，但退休後會繼續做一個簡單的工作」，
    正是規格裡的黃燈情境 → 本金門檻會下降，必須量化，不能只寫一句『可搭配輕量收入』。
    只用金融資本（不含房產）：輕量工作在退休當下吃飯，需要的是現金流對應的本金。"""
    exp = float(snap.get("monthly_expense") or 0)
    y = c["yield_fi_pct"] / 100.0
    fin = ga["tw_growth"] + ga["us_growth"]
    rows = []
    for inc in c.get("light_work_incomes") or []:
        inc = float(inc)
        need_m = max(exp - inc, 0)
        need_cap = need_m * 12 / y if y else 0
        rows.append({
            "月收": inc,
            "所需年現金流": round(need_m * 12),
            "所需本金": round(need_cap),
            "缺口": round(max(need_cap - fin, 0)),
            "達成_pct": round(fin / need_cap * 100, 1) if need_cap else 100.0,
        })
    return {"rows": rows, "fin_capital": fin, "yield_pct": c["yield_fi_pct"], "expense": exp}


def runway_metric(snap, c):
    """跑道＝現金 / 壓力情境月缺口 × 30。
    為什麼用壓力情境：正常情境下被動收入已 > 支出（分母為負）→ 指標恆為無限大而失效。"""
    pi = snap.get("passive_income") or {}
    exp = float(snap.get("monthly_expense") or 0)
    div_c = float(pi.get("fund_dividend_conservative") or 0)
    rent = float(pi.get("rent_monthly") or 0)
    rb = snap.get("rent_breakdown") or {}
    vacancy = float(rb.get("洲際W") or 0)          # 洲際W 空置壓力
    income_stress = div_c * c["stress_dividend_haircut"] + rent - vacancy
    gap = max(exp - income_stress, 0)
    thr = snap.get("thresholds_2026_0915") or {}
    cw = thr.get("現金_twd") or {}
    reserve = float(cw.get("追繳緩衝") or 0)
    floor = float(cw.get("合計底線") or 0) or (float(cw.get("生活底線") or 0) + reserve)
    cash_full = float(snap.get("cash_total") or 0)
    cash = cash_full - reserve if c["cash_caliber"] == "net_of_reserve" else cash_full
    days = round(cash / gap * 30) if gap > 0 else 999
    return {"income_stress": income_stress, "gap": gap, "vacancy": vacancy,
            "cash_full": cash_full, "reserve": reserve, "floor": floor, "cash_used": cash,
            "cash_below_floor": cash_full < floor and floor > 0,
            "runway_days": days, "cash_caliber": c["cash_caliber"],
            "runway_days_full_cash": round(cash_full / gap * 30) if gap > 0 else 999,
            "runway_days_net_reserve": round(max(cash_full - reserve, 0) / gap * 30) if gap > 0 else 999}


def stress_metric(snap, c, facts):
    pool = float((snap.get("cathay_pledge_0911") or {}).get("擔保池", {}).get("合計") or 0)
    loan = float(facts.get("可貸") or 0)
    if pool <= 0:
        return {"pool": 0, "loan": loan, "ltv_now_pct": 0, "maintenance_now_pct": 0,
                "maintenance_minus30_pct": 0, "drop_to_call_pct": 0}
    ltv_now = loan / pool * 100
    pool30 = pool * 0.7
    ltv30 = loan / pool30 * 100
    # 銀行追繳線（thresholds.ltv分級_pct.追繳）
    thr = (snap.get("thresholds_2026_0915") or {}).get("ltv分級_pct") or {}
    call = float(thr.get("追繳") or 70)
    drop_to_call = (1 - (loan / (call / 100.0)) / pool) * 100
    return {
        "pool": pool, "loan": loan, "disbursed": bool(facts.get("已撥款")),
        "ltv_now_pct": round(ltv_now, 1),
        "maintenance_now_pct": round(100 / ltv_now * 100, 1),
        "pool_minus30": pool30, "ltv_minus30_pct": round(ltv30, 1),
        "maintenance_minus30_pct": round(100 / ltv30 * 100, 1),
        "call_line_pct": call, "drop_to_call_pct": round(drop_to_call, 1),
    }


def credit_locked(snap, facts):
    items = []
    ref = snap.get("refinance_plan_2026") or {}
    dy = ref.get("大義街") or {}
    items.append({"項目": "大義街轉貸（國泰 1,200萬@2.6%）",
                  "完成": "撥款已入帳" in str(dy.get("狀態") or "")})
    xz = ref.get("洲際W") or {}
    items.append({"項目": f"洲際W 轉貸（永豐 1,312萬，9/25 到期）",
                  "完成": any(k in str(xz.get("狀態") or "") for k in ("完成", "已撥款", "已入帳"))})
    items.append({"項目": f"整池質押 {facts.get('可貸萬', '')}@{facts.get('利率文字', '')}（撥款後清償 500萬高息）",
                  "完成": bool(facts.get("已撥款"))})
    items.append({"項目": "理財型房貸清償",
                  "完成": float(snap.get("financial_mortgage") or 0) == 0})
    return {"locked": all(i["完成"] for i in items), "items": items}


def decide(c, coast, pccr, runway, stress, credit):
    t = c["targets"]
    coast_pct = coast["coast_fi_ratio_fin_only_swr_pct"]   # 正式判準＝純金融（經典 Coast FI）
    st = {
        "coast": coast_pct >= t["coast_fi_ratio_pct"],
        "pccr": pccr["pccr_pct"] >= t["pccr_pct"],
        "runway": runway["runway_days"] >= t["runway_days"],
        "maintenance": stress["maintenance_minus30_pct"] >= t["maintenance_pct"],
        "credit": credit["locked"],
    }
    blocks = []
    if not st["coast"]:
        blocks.append(f"Coast FI 本金滑行（純金融）{coast_pct}% < {t['coast_fi_ratio_pct']}%"
                      f"（含房產 {coast['coast_fi_ratio_swr_pct']}%）")
    if not st["pccr"]:
        blocks.append(f"現金流覆蓋 PCCR {pccr['pccr_pct']}% < {t['pccr_pct']}%")
    if not st["runway"]:
        blocks.append(f"無薪跑道 {runway['runway_days']} 天 < {t['runway_days']} 天")
    if not st["maintenance"]:
        blocks.append(f"跌30% 維持率 {stress['maintenance_minus30_pct']}% < {t['maintenance_pct']}%")
    if not st["credit"]:
        pend = "、".join(i["項目"] for i in credit["items"] if not i["完成"])
        blocks.append(f"授信未鎖定（{pend}）")
    if all(st.values()):
        light = "🟢 綠燈"
    elif st["coast"] and pccr["pccr_pct"] >= 100:
        light = "🟡 黃燈"
    else:
        light = "🔴 紅燈"
    return light, st, blocks


def build(snap, today=None):
    today = today or datetime.date.today()
    c = cfg(snap)
    import pledge_status as _pf
    facts = _pf.pledge_facts(snap)
    ga = growth_assets(snap)
    coast = coast_metric(snap, c, ga, today)
    pccr = pccr_metric(snap, c)
    runway = runway_metric(snap, c)
    stress = stress_metric(snap, c, facts)
    credit = credit_locked(snap, facts)
    lightwork = light_work_sensitivity(snap, c, ga)
    light, st, blocks = decide(c, coast, pccr, runway, stress, credit)
    return {
        "asof": today.isoformat(),
        "config_used": c,
        "growth_assets": ga,
        "coast": coast,
        "light_work": lightwork,
        "pccr": pccr,
        "runway": runway,
        "stress": stress,
        "credit": credit,
        "status": st,
        "light": light,
        "blockers": blocks,
    }


def render(r):
    c = r["config_used"]["targets"]
    co, pc, rw, st, cr = r["coast"], r["pccr"], r["runway"], r["stress"], r["credit"]

    def tri(ok, warn=False):
        return "🟢" if ok else ("🟡" if warn else "🔴")

    pccr_warn = 100 <= pc["pccr_pct"] < c["pccr_pct"]
    yp = r["config_used"]["yield_fi_pct"]
    L = []
    L.append("📊 【Coast FI 離職準備度】" + f"（{r['asof']}）")
    L.append(f"• 本金滑行（純金融）：{co['coast_fi_ratio_fin_only_swr_pct']}% "
             f"{tri(r['status']['coast'])}（目標 {c['coast_fi_ratio_pct']}%；"
             f"含房產另計 {co['coast_fi_ratio_swr_pct']}%）")
    L.append(f"  4%法則門檻 {co['coast_threshold_swr']:,.0f}｜配息率{yp:.0f}%門檻 "
             f"{co['coast_threshold_yield']:,.0f} → 純金融比率 {co['coast_fi_ratio_fin_only_yield_pct']}%")
    L.append(f"• 離職現金覆蓋率 PCCR：{pc['pccr_pct']}% {tri(r['status']['pccr'], pccr_warn)}"
             f"（目標 {c['pccr_pct']}%；常態配息 {pc['dividend_normal']:,.0f}×0.8＋租金 {pc['rent']:,.0f}）")
    L.append(f"  保守底線 {pc['pccr_conservative_pct']}%（配息基本值 {pc['dividend_conservative']:,.0f}；"
             f"留停驗收表口徑，是下緣不是現況）｜當月實收 {pc['pccr_actual_pct']}%")
    L.append(f"• 無薪安全跑道：{rw['runway_days']} 天 {tri(r['status']['runway'])}"
             f"（目標 {c['runway_days']} 天 ≈18個月；全現金口徑 {rw['runway_days_full_cash']} 天）")
    L.append(f"• 跌30% 維持率：{st['maintenance_minus30_pct']}% {tri(r['status']['maintenance'])}"
             f"（目標 {c['maintenance_pct']}%；追繳線 LTV {st['call_line_pct']}%，"
             f"再跌 {st['drop_to_call_pct']}% 觸線{'；撥款後口徑' if not st.get('disbursed') else ''}）")
    L.append(f"• 離職前信用鎖定：{'✅ 已鎖定' if cr['locked'] else '❌ 未完成'} {tri(r['status']['credit'])}")
    L.append(f"• 現金水位：{rw['cash_full']:,.0f}／底線 {rw['floor']:,.0f} "
             f"{'🔴 已低於底線' if rw['cash_below_floor'] else '🟢'}")
    L.append("")
    L.append(f"🧩 退休後「簡單工作」分擔（配息率{yp:.0f}%口徑，僅計金融資本 "
             f"{r['light_work']['fin_capital']:,.0f}）：")
    for row in r["light_work"]["rows"]:
        L.append(f"  · 月收 {row['月收']:,.0f} → 需本金 {row['所需本金']:,.0f}"
                 f"（缺口 {row['缺口']:,.0f}；達成 {row['達成_pct']}%）")
    L.append("")
    L.append(f"🎯 裁決：{r['light']}")
    if r["blockers"]:
        L.append("⛔ 擋下原因：" + "；".join(r["blockers"]))
    L.append("")
    note = ("距目標不足 1 年 → 複利期 ≈0，Coast 門檻≈FI 目標（此指標此時等同『資本 vs FI 目標』）"
            if co["years_to_target"] < 1 else
            f"距目標 {co['years_to_target']} 年、實質報酬 {r['config_used']['real_return_pct']}% → 複利倍數 "
            f"{co['fv_no_contrib_swr'] / max(r['growth_assets']['total'], 1):.2f}x")
    L.append(f"（目標日 {co.get('target_date')}｜{note}；"
             f"FI 目標 {co['fi_target_swr']:,.0f}＝年支出÷{r['config_used']['swr_pct']}%）")
    return "\n".join(L)


def main():
    snap = load()
    r = build(snap)

    # --notify：cron no_agent 用；與上次寫入的燈號相同 → 完全靜默（不推訊息、不寫檔）
    if "--notify" in sys.argv:
        prev = ((snap.get("coast_fi_engine") or {}).get("current") or {}).get("light")
        if prev == r["light"]:
            return
        print(f"⚠️ Coast FI 燈號變化：{prev or '（無前值）'} → {r['light']}")
        print(render(r))
        return

    print(render(r))
    print("\n── 診斷 ──")
    ga = r["growth_assets"]
    print(f"成長資產：台股 {ga['tw_growth']:,.0f} + 美股 {ga['us_growth']:,.0f} "
          f"+ 房產淨值 {ga['re_net']:,.0f}（房產 {ga['re_value']:,.0f} − 房貸 {ga['mortgage']:,.0f}）"
          f" = {ga['total']:,.0f}")
    print(f"  （再扣保單借貸+券商質押 {ga['fin_debt']:,.0f} → 淨成長資產 {ga['net_after_fin_debt']:,.0f}）")
    co = r["coast"]
    if co["years_to_target"] < 1:
        print(f"配息率口徑（含房產）：門檻 {co['coast_threshold_yield']:,.0f} → 比率 "
              f"{co['coast_fi_ratio_yield_pct']}%；一次性缺口 {co['gap_fv_yield']:,.0f}"
              f"（複利期 {co['years_to_target']} 年，不做月攤）")
    else:
        print(f"配息率口徑（含房產）：門檻 {co['coast_threshold_yield']:,.0f} → 比率 "
              f"{co['coast_fi_ratio_yield_pct']}%；年缺口 {co['gap_fv_yield']:,.0f} → "
              f"每月需投入 {co['monthly_needed_yield']:,.0f}")
    print(f"跑道口徑：壓力月收入 {r['runway']['income_stress']:,.0f}"
          f"（配息 {r['pccr']['dividend_conservative']:,.0f}×0.8 + 租金 − 洲際W空置 {r['runway']['vacancy']:,.0f}）"
          f" → 月缺口 {r['runway']['gap']:,.0f}")
    print(f"  現金可用 {r['runway']['cash_used']:,.0f}（{r['runway']['cash_caliber']}："
          f"{r['runway']['cash_full']:,.0f} − 追繳緩衝 {r['runway']['reserve']:,.0f}）"
          f" → {r['runway']['runway_days']} 天；全現金口徑 {r['runway']['runway_days_full_cash']} 天")
    for it in r["credit"]["items"]:
        print(f"  授信：{it['項目']} → {'✅' if it['完成'] else '❌ 未完成'}")
    if "--write" in sys.argv:
        snap["coast_fi_config"] = r["config_used"]
        hist = snap.setdefault("coast_fi_engine", {})
        hist["asof"] = r["asof"]
        hist["current"] = {k: r[k] for k in
                           ("growth_assets", "coast", "light_work", "pccr", "runway", "stress",
                            "credit", "status", "light", "blockers")}
        h = hist.setdefault("history", {})
        h[r["asof"]] = {"light": r["light"],
                        "coast_fin_only_pct": r["coast"]["coast_fi_ratio_fin_only_swr_pct"],
                        "coast_with_re_pct": r["coast"]["coast_fi_ratio_swr_pct"],
                        "pccr_pct": r["pccr"]["pccr_pct"], "runway_days": r["runway"]["runway_days"],
                        "maintenance_pct": r["stress"]["maintenance_minus30_pct"],
                        "credit_locked": r["credit"]["locked"],
                        "light_work_cap_2w": next((x["缺口"] for x in r["light_work"]["rows"]
                                                    if x["月收"] == 20000), None)}
        hist["history"] = {k: h[k] for k in sorted(h)[-90:]}
        SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n✅ 已寫回 snapshot.coast_fi_engine（{r['asof']}）")
    else:
        print("\n（dry-run：未寫檔；加 --write 才寫回 snapshot.coast_fi_engine）")


if __name__ == "__main__":
    main()
