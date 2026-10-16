#!/usr/bin/env python3
"""財務結構健檢報告（Structural Health Check）

用途：把「近幾個月的結構調整是否讓財務結構更穩定」變成一份可定期檢核的報告，
      由儀表板按鈕「🏥 結構健檢」固定取用。

資料源（單一真值，禁寫死）：
  - 現值  = snapshot.json（全部現算；配合 sot_targets 的單一 accessor）
  - 定錨  = structural_health_baseline.json（僅放快照備份才有的過去值）

輸出：structural_health_YYYYMMDD.html
"""
import json
import re
import html as _html
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
BL = json.loads((BASE / "structural_health_baseline.json").read_text(encoding="utf-8"))["baseline"]
TODAY = date.today().isoformat()

import sot_targets as S


# ───────────────────────── 格式化工具 ─────────────────────────
def fmt(v):
    if v is None:
        return "—"
    return f"{int(round(float(v))):,}"


def wan(v, d=1):
    if v is None:
        return "—"
    return f"{float(v) / 10000:,.{d}f}"


def pctf(v, d=1):
    if v is None:
        return "—"
    return f"{float(v):.{d}f}%"


def esc(s):
    return _html.escape(str(s), quote=False)


# ───────────────────────── 現值：負債 ─────────────────────────
mort = snap.get("mortgages") or []
def _is_cathay(m):
    return "國泰" in str(m.get("bank", ""))
yy_mort = sum(float(m.get("balance", 0)) for m in mort if not _is_cathay(m))
ct_mort = sum(float(m.get("balance", 0)) for m in mort if _is_cathay(m))
mort_total = yy_mort + ct_mort

cc = snap.get("credit_card") or {}
cc_unpaid = sum(-float(v) for v in cc.values() if isinstance(v, (int, float)) and v < 0)

policy_loan = float(snap.get("policy_pledge_loan") or 0)
broker_loan = float(snap.get("pledge_loan") or 0)
fund_pledge = float(snap.get("fund_pledge_loan") or 0)
fund_rate = snap.get("fund_pledge_rate")
policy_rate = snap.get("policy_pledge_rate")
broker_rate = snap.get("pledge_loan_rate")
cathay_rate = snap.get("mortgage_cathay_rate")
total_liab = float(snap.get("total_liabilities") or 0)
high_cost_debt = policy_loan + broker_loan  # 保單＋券商＝高息（≥3.9%）


def _yf_rate():
    """永豐房貸利率：優先明確欄位，其次 debt_schedule 文字；找不到回 None（禁預設值頂替）。"""
    for k in ("mortgage_yongfeng_rate", "mortgage_yy_rate"):
        v = snap.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    for it in snap.get("debt_schedule") or []:
        t = str(it.get("項目", ""))
        if "永豐" in t:
            m = re.search(r"@(\d+(?:\.\d+)?)%", t)
            if m:
                return float(m.group(1)) / 100
    return None


yf_rate = _yf_rate()

_num = _den = 0.0
_rate_missing = []
if yy_mort and yf_rate:
    _num += yy_mort * yf_rate
    _den += yy_mort
elif yy_mort:
    _rate_missing.append("永豐房貸")
if ct_mort and cathay_rate:
    _num += ct_mort * float(cathay_rate)
    _den += ct_mort
elif ct_mort:
    _rate_missing.append("國泰房貸")
if fund_pledge and fund_rate:
    _num += fund_pledge * float(fund_rate)
    _den += fund_pledge
elif fund_pledge:
    _rate_missing.append("基金質押")
wa_rate = (_num / _den * 100) if _den else None

li = S.liability_interest(snap)
monthly_interest = li.get("合計")

mfe = snap.get("monthly_fixed_expense") or {}
mort_monthly = float(mfe.get("房貸_永豐") or 0) + float(mfe.get("房貸_國泰") or 0)

# ───────────────────────── 現值：資產 ─────────────────────────
ins = float(snap.get("insurance_total") or 0)
sec = float(snap.get("securities_total") or 0)
funds = float(snap.get("funds_total") or 0)
cash = float(S.total_cash(snap))
re_val = float(snap.get("real_estate") or 0)
fin_assets = ins + sec + funds + cash
net_fin = fin_assets - total_liab
net_all = fin_assets + re_val - total_liab
allowable = float(S.allowable_cash(snap))
restricted = float(S.restricted_cash(snap))
dp = S.dry_powder(snap)
dp_dry = dp.get("dry")
dp_floor = dp.get("floor")
dp_goal = dp.get("long_term_goal")

# ───────────────────────── 現值：配置 ─────────────────────────
pen = (snap.get("penetration") or {}).get("actual_pct") or {}
tgt = (snap.get("thresholds_2026_0915") or {}).get("桶目標_pct") or {}
T = {
    "台股市值型": tgt.get("台股市值型", 10),
    "美股市值型": tgt.get("美股市值型", 30),
    "科技": tgt.get("科技", 15),
    "防守型配息": tgt.get("防守型配息", 30),
    "債券": tgt.get("債券", 25),
    "現金": tgt.get("現金", 5),
}
A = {
    "台股市值型": pen.get("台股市值型成長"),
    "美股市值型": pen.get("美股市值型成長"),
    "科技": pen.get("美股市值型成長_科技"),
    "防守型配息": pen.get("防守型配息"),
    "債券": pen.get("債券"),
    "現金": pen.get("現金/安全網"),
}
usd = snap.get("usd_exposure_pct")
usd_cfg = (snap.get("thresholds_2026_0915") or {}).get("美元曝險_pct") or {}
ltv = S.pledge_ltv_detail(snap)
rv = S.repayment_valve(snap)
gate = S.us30y_gate(snap)

# ───────────────────────── 現值：現金流 ─────────────────────────
pi = snap.get("passive_income") or {}
exp = float(S.sot_monthly_expense(snap))
income = float(S.sot_monthly_income(snap))
cons = float(pi.get("total_conservative") or 0)
norm = float(pi.get("total_normal") or 0)
cov_cons = (cons / exp * 100) if exp else None
cov_norm = (norm / exp * 100) if exp else None
surplus = income - exp

# ───────────────────────── 趨勢判定 ─────────────────────────
def trend(b, c, better):
    """回 (符號, css class, 變化文字)。better: down/up/near0"""
    if b is None or c is None:
        return ("•", "na", "無同期基準")
    d = float(c) - float(b)
    if better == "down":
        good, bad = d < -0.05, d > 0.05
    elif better == "up":
        good, bad = d > 0.05, d < -0.05
    else:
        good, bad = abs(float(c)) < abs(float(b)) - 0.05, abs(float(c)) > abs(float(b)) + 0.05
    cls = "good" if good else ("bad" if bad else "flat")
    sign = "▲" if d > 0 else ("▼" if d < 0 else "▬")
    return (sign, cls, f"{d:+,.1f}" if abs(d) < 1000 else f"{d:+,.0f}")


def _kpi(label, value, note, cls=""):
    return (f'<div class="kpi"><div class="lbl">{label}</div>'
            f'<div class="val {cls}">{value}</div><div class="note">{note}</div></div>')


def _bar(name, actual, target, unit="%"):
    if actual is None:
        return ""
    _a, _t = float(actual), float(target)
    over = _a > _t
    scale = max(_a, _t) * 1.15
    w = max(0.0, min(_a / scale * 100, 100))
    w_t = max(0.0, min(_t / scale * 100, 100))
    gap = _a - _t
    gap_cls = "good" if abs(gap) <= 3 else ("warn" if abs(gap) <= 8 else "bad")
    return (f'<div class="bl"><div class="bl-top"><span class="bl-n">{esc(name)}</span>'
            f'<span class="bl-v">{pctf(actual)} <em>／ 目標 {pctf(target, 0)}</em> '
            f'<b class="{gap_cls}">{gap:+.1f}pp</b></span></div>'
            f'<div class="bar"><div class="fill{" over" if over else ""}" style="width:{w:.1f}%"></div>'
            f'<span class="mk" style="left:{w_t:.1f}%"></span></div></div>')


def _alarm(title, value, desc, level):
    return (f'<div class="alarm {level}"><div class="a-t">{esc(title)}</div>'
            f'<div class="a-v">{value}</div><div class="a-d">{desc}</div></div>')


# ───────────────────────── 組裝 ─────────────────────────
BL_D = BL["date"]
CUR_D = TODAY

# 1) 六維度對照列
rows = [
    ("成本", "加權負債成本", BL["weighted_debt_rate_pct"], wa_rate, "down", "%",
     f"7/20 為 2.91%（含保單 4.0%、券商 3.92%）"),
    ("成本", "高息負債（≥3.9%）", BL["high_cost_debt"], high_cost_debt, "down", "元",
     "保單借貸＋券商質押；現已全數清償"),
    ("成本", "月利息支出", BL["monthly_interest"], monthly_interest, "down", "元",
     "保單息＋券商息＋基金質押息（房貸另計於月支出）"),
    ("成本", "房貸月付", BL["mortgage_monthly"], mort_monthly, "down", "元",
     "現值含國泰大義街 3 年寬限期（只繳息＝本金延後，非全為降息效果）"),
    ("配置", "美股桶", BL["us_bucket_pct"], A["美股市值型"], "down", "%",
     "目標 30%（7 月口徑目標 40%）"),
    ("配置", "台股桶", BL["tw_bucket_pct"], A["台股市值型"], "up", "%", "目標 10%（7 月口徑目標 40%）"),
    ("配置", "科技曝險", BL["tech_pct"], A["科技"], "down", "%", "單桶硬上限 25%、目標 ≤15%"),
    ("現金流", "被動收入覆蓋（保守）", BL["coverage_conservative_pct"], cov_cons, "up", "%",
     f"保守配息 {fmt(cons)}＋房租 {fmt(pi.get('rent_monthly'))} ÷ 月支出 {fmt(exp)}"),
    ("緩衝", "可動用現金", BL["cash_available"], allowable, "up", "元",
     f"總現金 {fmt(cash)}＝可動用 {fmt(allowable)}＋指定款 {fmt(restricted)}"),
    ("風險", "美元曝險", BL["usd_exposure_pct"], usd, "down", "%",
     f"門檻 目標 {usd_cfg.get('目標', 60)}／黃 {usd_cfg.get('黃', 65)}／紅 {usd_cfg.get('紅', 70)}"),
    ("風險", "質押 LTV", BL["pledge_ltv_pct"], ltv.get("LTV_pct"), "down", "%",
     f"政策停止線 {ltv.get('政策停止線_pct')}%、追繳 {ltv.get('追繳參考_pct')}%（內部判定，非銀行追繳線）"),
]

row_html = []
_last_grp = None
for grp, name, b, c, better, unit, note in rows:
    if grp != _last_grp:
        row_html.append(f'<tr class="grp"><td colspan="3">{esc(grp)}</td></tr>')
        _last_grp = grp
    sign, cls, dtext = trend(b, c, better)
    if unit == "%":
        b_txt, c_txt = (pctf(b) if b is not None else "—"), (pctf(c) if c is not None else "—")
    else:
        b_txt, c_txt = (fmt(b) if b is not None else "—"), (fmt(c) if c is not None else "—")
    _u = "pp" if unit == "%" else ""
    if sign == "•":
        d_cell = f'<span class="d na">{esc(dtext)}</span>'
    else:
        d_cell = f'<span class="d {cls}">{sign} {esc(dtext)}{_u}</span>'
    row_html.append(
        f'<tr><td class="nm">{esc(name)}<span class="nt">{esc(note)}</span></td>'
        f'<td class="cur">{c_txt}<span class="was">{esc(BL_D)} {b_txt}</span></td>'
        f'<td class="dc">{d_cell}</td></tr>'
    )
rows_table = "\n".join(row_html)

# 2) 負債明細
def _debt_line(name, bal, rate, monthly, tag=""):
    r = f"{float(rate) * 100:.2f}%" if isinstance(rate, (int, float)) else "—"
    m = f"{fmt(monthly)}" if monthly else "—"
    return (f'<tr><td class="nm">{esc(name)}{f"<span class=lite>{esc(tag)}</span>" if tag else ""}</td>'
            f'<td class="cur">{fmt(bal)}</td><td>{r}</td><td>{m}</td></tr>')


debt_rows = []
if yy_mort:
    debt_rows.append(_debt_line("永豐房貸（洲際W，3 筆）", yy_mort, yf_rate,
                                mfe.get("房貸_永豐"), "每月 27 扣款"))
if ct_mort:
    debt_rows.append(_debt_line("國泰房貸（大義街）", ct_mort, cathay_rate,
                                mfe.get("房貸_國泰"), "3 年寬限期・只繳息"))
if fund_pledge:
    debt_rows.append(_debt_line("國泰基金質押", fund_pledge, fund_rate,
                                li.get("基金質押利息"), "擔保池＝國泰直購基金"))
if policy_loan:
    debt_rows.append(_debt_line("保單借貸", policy_loan, policy_rate, li.get("保單借貸利息")))
if broker_loan:
    debt_rows.append(_debt_line("券商質押", broker_loan, broker_rate, li.get("券商質押利息")))
if cc_unpaid:
    debt_rows.append(_debt_line("信用卡（當期未繳・全額扣繳）", cc_unpaid, None, None))
debt_table = "\n".join(debt_rows)

# 3) 風險哨兵
ltv_lvl = "ok" if (ltv.get("LTV_pct") or 0) <= (ltv.get("政策停止線_pct") or 53) else "bad"
usd_pct_val = usd if usd is not None else 0
if usd is None:
    usd_lvl, usd_desc = "warn", "無同期基準（9/14 才定案口徑）"
elif usd_pct_val >= usd_cfg.get("紅", 70):
    usd_lvl, usd_desc = "bad", f"已觸紅線 {usd_cfg.get('紅', 70)}% → 停止新增美元資產"
elif usd_pct_val >= usd_cfg.get("黃", 65):
    usd_lvl, usd_desc = "warn", f"黃色觀察區 {usd_cfg.get('黃', 65)}~{usd_cfg.get('紅', 70)}%（僅顯示，不觸發調整）"
else:
    usd_lvl, usd_desc = "ok", f"低於黃線 {usd_cfg.get('黃', 65)}%"

valve_ok = bool(rv.get("已證實")) and not rv.get("轉負情境")
valve_lvl = "ok" if valve_ok else "bad"
valve_value = "已證實" if rv.get("已證實") else "未證實"
valve_desc = (f"月盈餘 {fmt(rv.get('月盈餘'))}；轉負情境 {len(rv.get('轉負情境') or [])} 個"
              f"（{esc('、'.join((rv.get('轉負情境') or [])[:2]))}{'…' if len(rv.get('轉負情境') or []) > 2 else ''}）"
              f"｜待銀行書面確認還本方式")

gate_lvl = "bad" if gate.get("risk_warning") else "ok"
gate_desc = f"警戒線 {gate.get('red_line')}%；連續 {gate.get('streak_days')} 日在上方（模式 {gate.get('mode')}）"

alarms = "".join([
    _alarm("美元曝險", pctf(usd), usd_desc, usd_lvl),
    _alarm("質押 LTV", pctf(ltv.get("LTV_pct")), 
           f"政策停止線 {pctf(ltv.get('政策停止線_pct'))}；池值可跌 {pctf(ltv.get('池值可跌_pct'))} 觸停止線", ltv_lvl),
    _alarm("還本安全閥", valve_value, valve_desc, valve_lvl),
    _alarm("US30Y 長端利率", pctf(gate.get("value"), 3), gate_desc, gate_lvl),
])

# 4) 配置進度
bars = "".join([
    _bar("台股市值型", A["台股市值型"], T["台股市值型"]),
    _bar("美股市值型", A["美股市值型"], T["美股市值型"]),
    _bar("科技曝險", A["科技"], T["科技"]),
    _bar("債券", A["債券"], T["債券"]),
    _bar("現金／安全網", A["現金"], T["現金"]),
])

# 5) 三階段
p1_done = high_cost_debt == 0
p3_need = -net_fin if net_fin < 0 else 0
phase_rows = [
    ("第一階段", "債務優化", "2026–2027",
     ("✅ 高息債清零" if p1_done else f"⏳ 高息債 {fmt(high_cost_debt)}"),
     ("完成" if p1_done else "進行中")),
    ("第二階段", "留職停薪測試", "2027/02",
     f"Gate {'綠燈' if gate.get('unfreeze_allowed') else '未通過'}（"
     f"{sum(1 for c in (gate.get('unfreeze_conditions') or {}).get('conditions', []) if c.get('通過'))}"
     f"/{len((gate.get('unfreeze_conditions') or {}).get('conditions', []))} 條件成立）",
     "待執行"),
    ("第三階段", "扣房產後淨資產 ≥ 0", "2029–2030",
     f"金融淨值 {fmt(net_fin)}（需改善 {wan(p3_need)}）",
     "待執行"),
]
phase_html = "\n".join(
    f'<tr><td class="nm">{esc(a)}<span class="nt">{esc(b)}｜{esc(c)}</span></td>'
    f'<td class="cur">{d}</td><td class="st">{esc(e)}</td></tr>' for a, b, c, d, e in phase_rows
)

# 6) 本次檢核重點（動態：只列當下真的卡住的項目）
focus = []
if not rv.get("已證實"):
    focus.append(("🔴", "還本安全閥未證實",
                  f"質押 {fmt(fund_pledge)} 的還本方式待銀行書面；"
                  f"轉負情境 {len(rv.get('轉負情境') or [])} 個（{esc('、'.join((rv.get('轉負情境') or [])[:2]))}…）"
                  f"→ 這是留停 Gate 唯一卡點"))
if usd is not None and usd >= (usd_cfg.get("黃") or 65):
    focus.append(("🟡", "美元曝險導流",
                  f"現 {pctf(usd)}（黃區 {usd_cfg.get('黃')}~{usd_cfg.get('紅')}%）→ "
                  f"新增資金往台幣資產；不追高、不賣後收級別（避免摩擦成本）"))
if (dp_dry or 0) < (dp_goal or 0):
    focus.append(("🟡", "乾粉回補",
                  f"現 {wan(dp_dry)}（底線 {wan(dp_floor)} 之上）→ 長期目標 {wan(dp_goal)}；"
                  f"以配息導流回補，不賣資產"))
if A["美股市值型"] and A["美股市值型"] > T["美股市值型"] + 5:
    focus.append(("🟡", "美股桶收斂",
                  f"現 {pctf(A['美股市值型'])} → 目標 {pctf(T['美股市值型'], 0)}；"
                  f"擔保池 92% 後收（CDSC 至 2029）→ 只能停新增＋配息導流"))
if gate.get("risk_warning"):
    focus.append(("🟡", "US30Y 高檔警示",
                  f"{pctf(gate.get('value'), 3)}（連續 {gate.get('streak_days')} 日 ≥ {gate.get('red_line')}%）→ "
                  f"長天期債券新增凍結、科技部位不擴大"))
if not focus:
    focus.append(("🟢", "無待辦紅黃燈", "各項指標均在門檻內，維持現行紀律即可"))
focus_html = "".join(
    f'<div class="fb {("r" if ic == "🔴" else ("y" if ic == "🟡" else "g"))}">'
    f'<div class="fb-t">{esc(t)}</div><div class="fb-d">{d}</div></div>'
    for ic, t, d in focus
)

# 7) 總評
_green = sum(1 for _, _, b, c, better, _u, _n in rows if trend(b, c, better)[1] == "good")
_red = sum(1 for _, _, b, c, better, _u, _n in rows if trend(b, c, better)[1] == "bad")
_worse = [n for _g, n, b, c, better, _u, _n in rows if trend(b, c, better)[1] == "bad"]
verdict = (f"<b>結構改善 {_green} 項、惡化 {_red} 項（共 {len(rows)} 項，其餘持平或無同期基準）。</b><br>"
           f"三個月的主軸是「可控的事做好」—— 把 4.0%／3.92% 的高息負債清零，換成加權 {pctf(wa_rate, 2)} 的低息結構，"
           f"資產配置同時向目標收斂；代價是流動性變薄"
           f"（可動用現金 {wan(BL['cash_available'])} → {wan(allowable)}）與新槓桿的還本不確定性。"
           + (f"<br>唯一惡化項：<b>{esc('、'.join(_worse))}</b>。"
              if _worse else "")
           + f"<br><b>結論：結構比三個月前穩定，但穩定 ≠ 安全</b> —— 目前最該處理的是"
             f"「質押還本方式取得銀行書面」與「美元曝險 {pctf(usd)} 的導流」。")

kpis = "".join([
    _kpi("加權負債成本", pctf(wa_rate, 2), f"7/20：{pctf(BL['weighted_debt_rate_pct'], 2)}", "good" if (wa_rate or 9) < (BL['weighted_debt_rate_pct'] or 0) else ""),
    _kpi("高息負債", fmt(high_cost_debt), "保單 4.0%＋券商 3.92%（已清償 500萬）", "good" if high_cost_debt == 0 else "bad"),
    _kpi("被動收入覆蓋", pctf(cov_cons), f"常態 {pctf(cov_norm)}（月支出 {fmt(exp)}）", "good" if (cov_cons or 0) >= 100 else "bad"),
    _kpi("可動用現金", wan(allowable), f"乾粉 {wan(dp_dry)}（底線 {wan(dp_floor)}）", "warn" if (dp_dry or 0) < (dp_goal or 0) else "good"),
])

CSS = """
:root{--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--good:#059669;--warn:#d97706;--bad:#dc2626;--blue:#2563eb}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#eef2f7;color:var(--ink);font-size:16px;line-height:1.6;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans TC","Microsoft JhengHei",sans-serif;
 -webkit-text-size-adjust:100%}
.wrap{max-width:920px;margin:0 auto;padding:16px 14px 56px}
.hero{background:linear-gradient(140deg,#0f172a 0%,#1e293b 48%,#0f766e 135%);color:#fff;
 border-radius:20px;padding:22px 20px;box-shadow:0 14px 34px -18px rgba(15,23,42,.65)}
.hero-top{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
.hero h1{font-size:21px;font-weight:900;letter-spacing:.4px}
.badge{font-size:11px;font-weight:800;background:rgba(45,212,191,.16);color:#5eead4;
 border:1px solid rgba(45,212,191,.35);border-radius:999px;padding:3px 10px;white-space:nowrap}
.hero .sub{font-size:11.5px;color:#94a3b8;margin-top:8px;line-height:1.6}
.verdict{margin-top:14px;background:rgba(255,255,255,.07);border-left:3px solid #2dd4bf;
 border-radius:10px;padding:12px 14px;font-size:13px;line-height:1.85;color:#e2e8f0}
.verdict b{color:#fff}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:10px;margin-top:14px}
.kpi{background:#fff;border:1px solid var(--line);border-radius:14px;padding:13px 14px;
 box-shadow:0 3px 10px -8px rgba(15,23,42,.4)}
.kpi .lbl{font-size:11.5px;font-weight:800;color:var(--muted)}
.kpi .val{font-size:22px;font-weight:900;letter-spacing:-.6px;margin-top:3px;font-variant-numeric:tabular-nums}
.kpi .val.good{color:var(--good)}.kpi .val.warn{color:var(--warn)}.kpi .val.bad{color:var(--bad)}
.kpi .note{font-size:10.5px;color:#94a3b8;margin-top:2px}
section{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px 15px;
 margin-top:13px;box-shadow:0 3px 12px -10px rgba(15,23,42,.5)}
h2{font-size:16px;font-weight:900;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
h2 .hint{font-size:10.5px;font-weight:700;color:#94a3b8}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin-top:8px}
th{font-size:11px;font-weight:800;color:var(--muted);text-align:right;padding:7px 5px;
 border-bottom:2px solid var(--line);white-space:nowrap}
th:first-child{text-align:left}
td{padding:9px 5px;border-bottom:1px solid #f1f5f9;text-align:right;
 font-variant-numeric:tabular-nums;vertical-align:top}
td:first-child{text-align:left}
tr:last-child td{border-bottom:none}
tr.grp td{background:#f8fafc;font-size:11px;font-weight:900;color:#475569;
 letter-spacing:.6px;padding:5px 5px;border-bottom:1px solid var(--line)}
td.nm{font-weight:800;line-height:1.45}
td.nm .nt{display:block;font-size:10.5px;font-weight:600;color:#94a3b8;margin-top:1px}
td.nm .lite{display:block;font-size:10.5px;font-weight:600;color:#94a3b8;margin-top:1px}
td.old{color:#94a3b8}
td.cur{font-weight:900;color:var(--ink);white-space:nowrap}
td.cur .was{display:block;font-size:10.5px;font-weight:700;color:#9aa8bb;margin-top:1px;white-space:nowrap}
td.dc{white-space:nowrap;width:1%}
.d{font-weight:900;font-size:12.5px;white-space:nowrap}
.d.good{color:var(--good)}.d.bad{color:var(--bad)}.d.flat{color:#64748b}.d.na{color:#cbd5e1;font-weight:700;font-size:11.5px}
td.st{white-space:nowrap;font-weight:800;font-size:12px}
.fbs{display:grid;gap:9px;margin-top:10px}
.fb{border:1px solid var(--line);border-left-width:4px;border-radius:12px;padding:11px 13px;background:#f8fafc}
.fb.r{border-left-color:var(--bad);background:#fef2f2}
.fb.y{border-left-color:var(--warn);background:#fffbeb}
.fb.g{border-left-color:var(--good);background:#f0fdf4}
.fb-t{font-size:13.5px;font-weight:900}
.fb-d{font-size:11.5px;color:#475569;line-height:1.7;margin-top:3px}
.foot-note{font-size:11.5px;color:var(--muted);line-height:1.75;margin-top:10px;
 border-top:1px dashed #e2e8f0;padding-top:8px}
.foot-note b{color:var(--ink)}
.bars{margin-top:10px}
.bl{margin-bottom:13px}
.bl-top{display:flex;justify-content:space-between;align-items:baseline;gap:8px;font-size:12.5px;flex-wrap:wrap}
.bl-n{font-weight:800}
.bl-v{font-variant-numeric:tabular-nums;color:#475569;font-size:12px}
.bl-v em{color:#94a3b8;font-style:normal;font-size:11px}
.bl-v b{font-weight:900;margin-left:2px}
.bl-v b.good{color:var(--good)}.bl-v b.warn{color:var(--warn)}.bl-v b.bad{color:var(--bad)}
.bar{position:relative;height:9px;background:#f1f5f9;border-radius:999px;margin-top:6px;overflow:hidden}
.bar .fill{height:100%;border-radius:999px;background:linear-gradient(90deg,#3b82f6,#2563eb)}
.bar .fill.over{background:linear-gradient(90deg,#f59e0b,#d97706)}
.bar .mk{position:absolute;top:-3px;width:2px;height:15px;background:#0f172a;border-radius:2px;opacity:.55}
.alarms{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-top:10px}
.alarm{border-radius:13px;padding:12px 13px;border:1px solid var(--line);background:#f8fafc;
 border-left-width:4px}
.alarm.ok{border-left-color:var(--good);background:#f0fdf4}
.alarm.warn{border-left-color:var(--warn);background:#fffbeb}
.alarm.bad{border-left-color:var(--bad);background:#fef2f2}
.a-t{font-size:11px;font-weight:900;color:var(--muted);letter-spacing:.3px}
.a-v{font-size:20px;font-weight:900;letter-spacing:-.5px;margin-top:2px;font-variant-numeric:tabular-nums}
.alarm.ok .a-v{color:var(--good)}.alarm.warn .a-v{color:var(--warn)}.alarm.bad .a-v{color:var(--bad)}
.a-d{font-size:10.5px;color:#64748b;line-height:1.6;margin-top:4px}
footer{margin-top:16px;padding:14px 15px;background:#0f172a;color:#cbd5e1;border-radius:14px;
 font-size:11.5px;line-height:1.85}
footer b{color:#fff}
@media (max-width:640px){
 body{font-size:15px}
 .hero h1{font-size:19px}
 table{font-size:12.5px}
 td{padding:8px 4px}th{padding:6px 4px;font-size:10.5px}
 .kpi .val{font-size:20px}
 .a-v{font-size:18px}
}
"""

_now = f"{snap.get('date', TODAY)}"
_report = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>財務結構健檢 · {esc(_now)}</title>
<style>
{CSS}
</style>
</head>
<body>
<div class="wrap">

  <div class="hero">
    <div class="hero-top">
      <h1>🏥 財務結構健檢</h1>
      <span class="badge">資料快照 {esc(_now)}</span>
    </div>
    <p class="sub">對照基準：{esc(BL_D)}（{esc(BL.get('label','調整前'))}）→ 今日 · 建議檢核頻率：每週六（再平衡評估同日）或每月真值日</p>
    <div class="verdict">{verdict}</div>
  </div>

  <div class="kpis">{kpis}</div>

  <section>
    <h2>① 結構指標對照<span class="hint">7/20 → 今日 · 方向以「越好越好」判定</span></h2>
    <table>
      <thead><tr><th>指標</th><th>今日 ／ 對照</th><th>變化</th></tr></thead>
      <tbody>{rows_table}</tbody>
    </table>
    <p class="foot-note">※ 7/20 基準有多處口徑尚未建檔（國泰直購基金、大義街轉貸、美元曝險、質押），標「—」者代表無同期可比基準，不代表示當時為零；負值變化代表下降。</p>
  </section>

  <section>
    <h2>② 負債結構明細<span class="hint">總負債 {fmt(total_liab)}</span></h2>
    <table>
      <thead><tr><th>項目</th><th>餘額</th><th>利率</th><th>月付／月息</th></tr></thead>
      <tbody>{debt_table}</tbody>
    </table>
    <p class="foot-note">加權平均負債成本 <b>{pctf(wa_rate, 2)}</b>（房貸＋質押）{'；' + esc('、'.join(_rate_missing)) + ' 利率缺真值，未計入加權' if _rate_missing else ''}。房貸月付合計 {fmt(mort_monthly)}，其中國泰大義街為 3 年寬限期只繳息。</p>
  </section>

  <section>
    <h2>③ 資產配置 vs 目標<span class="hint">偏離 ≤3pp 綠／≤8pp 黃／&gt;8pp 紅</span></h2>
    <div class="bars">{bars}</div>
    <p class="foot-note">單桶硬上限：美股 40%／科技 25%／台股 15%；防守合併口徑 {pctf(S.defensive_caliber(snap).get('佔比'))}（門檻 60%）。</p>
  </section>

  <section>
    <h2>④ 風險哨兵<span class="hint">四條紅線即時狀態</span></h2>
    <div class="alarms">{alarms}</div>
  </section>

  <section>
    <h2>⑤ 三階段目標進度</h2>
    <table>
      <thead><tr><th>階段</th><th>現況</th><th>狀態</th></tr></thead>
      <tbody>{phase_html}</tbody>
    </table>
  </section>

  <section>
    <h2>⑥ 本次檢核重點<span class="hint">依當前數據動態產生，未卡住則自動消失</span></h2>
    <div class="fbs">{focus_html}</div>
  </section>

  <footer>
    <p>金融資產 {fmt(fin_assets)}（證券 {fmt(sec)}・基金 {fmt(funds)}・保單 {fmt(ins)}・現金 {fmt(cash)}）</p>
    <p>金融淨值 <b>{fmt(net_fin)}</b>（金融資產 − 負債）｜含不動產淨值 <b>{fmt(net_all)}</b>（不動產 {fmt(re_val)}）</p>
    <p>資料源：snapshot.json（現值）＋ structural_health_baseline.json（{esc(BL_D)} 定錨）｜產生時間 {date.today().isoformat()}｜唯一寫入者 build_structural_health.py</p>
  </footer>

</div>
</body>
</html>
"""



out = BASE / f"structural_health_{TODAY.replace('-', '')}.html"
out.write_text(_report, encoding="utf-8")
print(f"✅ 產出 {out.name}")
print(f"   加權負債成本 {pctf(wa_rate, 2)}｜高息負債 {fmt(high_cost_debt)}｜LTV {pctf(ltv.get('LTV_pct'))}｜美元曝險 {pctf(usd)}｜覆蓋 {pctf(cov_cons)}")
if _rate_missing:
    print(f"   ⚠️ 利率缺真值：{'、'.join(_rate_missing)}")
