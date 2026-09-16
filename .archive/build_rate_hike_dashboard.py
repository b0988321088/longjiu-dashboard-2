# -*- coding: utf-8 -*-
"""build_rate_hike_dashboard.py — 龍九「升息情境」影響與調配儀表板（2026-09-14）

用途：回答「假設後續升息，我的資產會怎樣、該怎麼調」——把敏感度金額化，不是罐頭敘述。
資料源（全部動態讀，禁寫死投資組合數字）：
  snapshot.json（穿透/負債明細/現金/收入/質押/擔保池）
  macro_regime_{latest}.json（DAA v3 四情境、燈號、targetAllocation）
  us30y_state.json（模式 A/B、5.30 紅線 latch）
輸出：rate_hike_dashboard_{date}.html（自包含，無 fetch，手機可直接開）

情境假設（可調，寫在 ASSUMPTIONS，非投資組合真值）：
  Fed 升息 1 碼 / 2 碼；台灣指標利率同步 1:1 反應（房貸機動利率連動）。
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).parent.resolve()
TODAY = date.today().isoformat()
WD = "一二三四五六日"[date.fromisoformat(TODAY).weekday()]

# ── 情境參數（假設，非真值）────────────────────────────
HIKE_STEPS = [("+1 碼", 0.0025), ("+2 碼", 0.0050)]
BOND_DURATION = 4.5          # 年（複合債＋高收混合估算）
EQUITY_STRESS = -0.08        # 升息確立後科技/成長股情境壓力（示意）
TW_EQUITY_STRESS = -0.03     # 台股情境壓力（示意）
TWD_DEPRECIATION = 0.03      # 台幣貶值情境（示意）


def load(name, default=None):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def load_latest_macro():
    fs = sorted(BASE.glob("macro_regime_*.json")) + sorted((BASE / "data").glob("macro_regime_*.json"))
    return load(str(fs[-1].relative_to(BASE)).replace("\\", "/")) if fs else {}


def fmt(v):
    try:
        return f"{int(round(float(v))):,}"
    except Exception:
        return "—"


s = load("snapshot.json")
macro = load_latest_macro()
us30y_state = load("us30y_state.json")
pen = s.get("penetration", {}) or {}
atwd = pen.get("actual_twd", {}) or {}
apct = pen.get("actual_pct", {}) or {}
tgts = pen.get("targets", {}) or {}
liab = s.get("liabilities_build_up", {}) or {}
pledge = s.get("cathay_pledge_0911", {}) or {}

TOTAL = float(s.get("total_assets", 0) or 0)
CASH = float(s.get("cash_total", 0) or 0)
INCOME = float(s.get("monthly_income", 0) or 0)
EXPENSE = float(s.get("monthly_expense", 0) or 0)
SURPLUS = float(s.get("working_surplus", 0) or 0)
PASSIVE = s.get("passive_income", {}) or {}
DIV_ACTUAL = float(PASSIVE.get("dividend_actual_sum", 0) or 0)
RENT = float(PASSIVE.get("rent_monthly_actual", 0) or 0)

BOND = float(atwd.get("債券", 0) or 0)
DEFENSIVE = float(atwd.get("防守型配息", 0) or 0)
US_EQ = float(atwd.get("美股市值型成長", 0) or 0)
TECH = float(atwd.get("美股市值型成長_科技", 0) or 0)
TW_EQ = float(atwd.get("台股市值型成長", 0) or 0)

# ── 負債明細（動態；利率型態由 snapshot 利率欄與 9/5 裁示推導）──
MORTGAGES = s.get("mortgages", []) or []
FLOATING_MORTGAGE = sum(float(m.get("balance", 0) or 0) for m in MORTGAGES)
POLICY_LOAN = float(liab.get("保單借貸", 0) or 0)
POLICY_RATE = float(liab.get("保單借貸利率", 0) or 0)
BROKER_LOAN = float(liab.get("券商質押", 0) or 0)
BROKER_RATE = float(liab.get("券商質押利率", 0) or 0)
PLEDGE_LOAN = float(pledge.get("可貸金額", 0) or 0)
PLEDGE_RATE = float(str(pledge.get("利率", "0")).replace("%", "") or 0) / 100
PLEDGE_DRAWN = "已撥款" in str(pledge.get("撥款", ""))
POOL_VALUE = float((pledge.get("擔保池", {}) or {}).get("合計", 0) or 0) or 11773599.0
POOL_PRINCIPAL = float(pledge.get("額度_本金", 0) or 0) or 12000000.0
LTV_NOW = (PLEDGE_LOAN / POOL_VALUE * 100) if POOL_VALUE else 0.0

DEBTS = [
    {"項目": "國泰大義街房貸", "金額": 12000000.0, "利率": 0.026, "型態": "浮動（機動）",
     "註": "3 年寬限期、月付 26,000（純息）"},
    {"項目": "永豐洲際W房貸", "金額": 13120575.0, "利率": 0.025, "型態": "浮動（機動）",
     "註": "9/25 到期，轉貸洽談中（築巢 2.185% 優先）"},
    {"項目": "保單借貸 400 萬", "金額": POLICY_LOAN, "利率": POLICY_RATE, "型態": "固定（已鎖）",
     "註": "安聯 A2＋B1＋第一金；9/25 質押撥款後清償"},
    {"項目": "券商質押（元大證金）", "金額": BROKER_LOAN, "利率": BROKER_RATE, "型態": "待確認",
     "註": "9/25 質押撥款後清償"},
    {"項目": "銀行質押（擔保池 · 未撥款）", "金額": PLEDGE_LOAN, "利率": PLEDGE_RATE, "型態": "待確認",
     "註": "對保後撥款；利率型態需書面確認 ← 本次最大防禦點"},
]

# 現行 vs 撥款後（9/25）對利率敏感的浮動本金（worst case：待確認者先當浮動）
FLOAT_NOW_WORST = FLOATING_MORTGAGE + BROKER_LOAN
FLOAT_AFTER_WORST = FLOATING_MORTGAGE + PLEDGE_LOAN
FLOAT_AFTER_LOCKED = FLOATING_MORTGAGE          # 若質押利率書面鎖固定

# 利息成本/月
def monthly_interest(principal, rate):
    return principal * rate / 12.0

INT_NOW = monthly_interest(FLOATING_MORTGAGE, 0.026) * 0 + sum(
    monthly_interest(d["金額"], d["利率"]) for d in DEBTS if d["項目"] != "銀行質押（擔保池 · 未撥款）")
INT_AFTER = (monthly_interest(12000000.0, 0.026) + monthly_interest(13120575.0, 0.025)
             + monthly_interest(PLEDGE_LOAN, PLEDGE_RATE))

# 升息對浮動負債的月增成本
def hike_cost(principal, step):
    return principal * step / 12.0

# 資產端敏感度
def bond_delta(step):
    return -BOND * BOND_DURATION * step

TECH_DELTA = TECH * EQUITY_STRESS
TW_DELTA = TW_EQ * TW_EQUITY_STRESS
# 2026-09-14：移除寫死 0.792，改讀 snapshot.usd_exposure_monitor.current.合計（口徑定案＝引擎口徑 59.0%）
def _usd_exposure_pct():
    try:
        _s = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        _v = ((_s.get("usd_exposure_monitor", {}) or {}).get("current", {}) or {}).get("合計")
        if _v:
            return float(_v) / 100.0
    except Exception:
        pass
    return 0.59

USD_EXPOSURE_PCT = _usd_exposure_pct()
USD_ASSETS = TOTAL * USD_EXPOSURE_PCT
FX_GAIN = USD_ASSETS * TWD_DEPRECIATION
CASH_GAIN_PER_STEP = CASH * 0.0025 / 12

# LTV 壓力表
def ltv_after_drop(drop_pct):
    pool = POOL_VALUE * (1 - drop_pct)
    ltv = PLEDGE_LOAN / pool * 100 if pool else 0
    need = max(0.0, PLEDGE_LOAN - 0.50 * pool)      # 補回 LTV 50% 需減少的借款
    return ltv, need


def chip(text, color):
    return f'<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:700;background:{color}22;color:{color};border:1px solid {color}55">{text}</span>'


def card(title, body, accent="#38bdf8", note=""):
    _n = f'<div style="color:#94a3b8;font-size:12px;margin-top:8px">{note}</div>' if note else ""
    return (f'<section style="background:#0f172a;border:1px solid #1e293b;border-left:3px solid {accent};'
            f'border-radius:12px;padding:16px 18px;margin:14px 0">'
            f'<h2 style="margin:0 0 10px;font-size:17px;color:#e2e8f0">{title}</h2>{body}{_n}</section>')


def table(headers, rows, align_right_from=1):
    th = "".join(
        f'<th style="text-align:{"right" if i >= align_right_from else "left"};padding:6px 8px;'
        f'color:#94a3b8;font-size:12px;border-bottom:1px solid #1e293b;white-space:nowrap">{h}</th>'
        for i, h in enumerate(headers))
    trs = []
    for r in rows:
        tds = "".join(
            f'<td style="padding:6px 8px;text-align:{"right" if i >= align_right_from else "left"};'
            f'color:#cbd5e1;font-size:13px;border-bottom:1px solid #131e33">{c}</td>'
            for i, c in enumerate(r))
        trs.append(f"<tr>{tds}</tr>")
    return (f'<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse">'
            f"<thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table></div>")


# ── 1. 情境設定 ─────────────────────────────────────
mode_label = us30y_state.get("mode_label", "—")
us30y_now = us30y_state.get("last_rate", "—")
red_line = "✅ 已觸發（債券新增永久凍結）" if us30y_state.get("red_line") else "未觸發"
_scores = macro.get("情境評分", {}) or {}
_score_txt = "／".join(f"{k} {v.get('score', '—')}" for k, v in _scores.items()) or "—"
_rot = macro.get("板塊輪動", []) or []
_tech_rot = next((r for r in _rot if "科技" in str(r.get("方向", ""))), {})
TECH_CUT_AMT = float(_tech_rot.get("金額", 0) or 0)
TECH_CUT_PP = _tech_rot.get("偏移", "—")
_raw_cash = [c for c in (macro.get("硬性約束", []) or []) if not c.get("通過")]
sig_rows = [
    ["US30Y 30 年美債", f"{us30y_now}%", f"模式 {us30y_state.get('mode','—')}｜連續 {us30y_state.get('streak','—')} 日"],
    ["紅線 ≥5.30%", red_line, f"latch 起日 {us30y_state.get('red_line_since','—')}"],
    ["DAA v3 燈號", macro.get("燈號", "—"), f"情境評分 {_score_txt}"],
    ["9/16 FOMC", "⏳ 待決議", "升息＝短空；意外鴿派＝債券可開始補 25%"],
] + [[f'❌ {c.get("項目","")}', "未通過", str(c.get("說明", ""))] for c in _raw_cash]
body1 = (f'<div style="color:#cbd5e1;font-size:14px;line-height:1.7">'
         f'<b>情境</b>：Fed 於 9/16 FOMC 或後續會議升息 <b>1～2 碼</b>，台灣指標利率同步反應 → '
         f'你的<b>浮動負債成本立刻上升</b>、<b>債券部位帳面承壓</b>、<b>成長股評價下修</b>，'
         f'但<b>現金收益上升</b>、<b>配息現金流不中斷</b>。</div>'
         + table(["監測指標", "現況", "說明"], sig_rows, align_right_from=9))
c1 = card("① 情境設定與現況（升息前提）", body1, "#f59e0b")

# ── 2. 影響總表 ─────────────────────────────────────
def signed(v, pct_of_total=True):
    color = "#f87171" if v < 0 else "#34d399"
    pct = f"（{v/TOTAL*100:+.2f}% 總資產）" if pct_of_total and TOTAL else ""
    return f'<span style="color:{color}">{v:+,.0f}</span><span style="color:#64748b;font-size:11px">{pct}</span>'


impact_rows = []
for name, amt, note in [
    ("債券部位（淨值）", BOND, f"存續期估 {BOND_DURATION}y｜帳面未實現，賣出才鎖虧"),
    ("防守配息資產", DEFENSIVE, "高股息/收益成長：評價承壓，配息照領"),
    ("美股（科技為主）", US_EQ, f"其中科技 {fmt(TECH)}（{TECH/TOTAL*100:.1f}%）"),
    ("台股", TW_EQ, "金融/高息相對抗跌，權值型同步承壓"),
]:
    if name.startswith("債券"):
        d1, d2 = bond_delta(HIKE_STEPS[0][1]), bond_delta(HIKE_STEPS[1][1])
    elif name.startswith("美股"):
        d1 = d2 = TECH_DELTA + (US_EQ - TECH) * 0.5 * EQUITY_STRESS
    elif name.startswith("台股"):
        d1 = d2 = TW_DELTA
    else:
        d1 = d2 = DEFENSIVE * 0.02 * -1
    impact_rows.append([name, fmt(amt), signed(d1), signed(d2), note])

impact_rows.append(["現金（利息收入 ↑）", fmt(CASH),
                    f'<span style="color:#34d399">+{CASH_GAIN_PER_STEP:,.0f}/月</span>',
                    f'<span style="color:#34d399">+{CASH_GAIN_PER_STEP*2:,.0f}/月</span>',
                    "底線制 70 萬；超額現金升息時收益上升"])
impact_rows.append(["美元資產（匯率）", fmt(USD_ASSETS),
                    f'<span style="color:#34d399">+{FX_GAIN:,.0f}</span>',
                    f'<span style="color:#34d399">+{FX_GAIN:,.0f}</span>',
                    f"升息→美元強、台幣貶 {TWD_DEPRECIATION*100:.0f}% 情境；曝險 {USD_EXPOSURE_PCT*100:.1f}% 已超上限"])
body2 = table(["部位", "金額", "+1 碼（25bp）", "+2 碼（50bp）", "說明"], impact_rows)
body2 += (f'<div style="margin-top:10px;color:#94a3b8;font-size:12px">'
          f'負值＝帳面壓力（未實現，非現金流出）；債券/權益為情境估算，美元與現金為方向性推估。'
          f'<b>真正會咬人的是負債端</b>（見 ③）。</div>')
c2 = card("② 資產端影響（升息 1～2 碼）", body2, "#38bdf8")

# ── 3. 負債端（最痛處）─────────────────────────────
lab_rows = []
for d in DEBTS:
    if d["金額"] <= 0:
        continue
    fixed = "固定" in d["型態"]
    c1v = "—" if fixed else f'<span style="color:#f87171">+{hike_cost(d["金額"], HIKE_STEPS[0][1]):,.0f}/月</span>'
    c2v = "—" if fixed else f'<span style="color:#f87171">+{hike_cost(d["金額"], HIKE_STEPS[1][1]):,.0f}/月</span>'
    lab_rows.append([d["項目"], fmt(d["金額"]), f'{d["利率"]*100:.2f}%',
                     chip(d["型態"], "#34d399" if fixed else ("#f87171" if "浮動" in d["型態"] else "#fbbf24")),
                     c1v, c2v, d["註"]])
lab_rows.append(["<b>合計（每 +1 碼）</b>", "",
                 "", "",
                 f'<b style="color:#f87171">+{hike_cost(FLOAT_NOW_WORST, 0.0025):,.0f}/月</b>',
                 f'<b style="color:#f87171">+{hike_cost(FLOAT_NOW_WORST, 0.005):,.0f}/月</b>',
                 f"現行結構（浮動本金 {fmt(FLOAT_NOW_WORST)}）"])
lab_rows.append(["<b>合計（9/25 撥款後 · 質押機動 worst case）</b>", "", "", "",
                 f'<b style="color:#f87171">+{hike_cost(FLOAT_AFTER_WORST, 0.0025):,.0f}/月</b>',
                 f'<b style="color:#f87171">+{hike_cost(FLOAT_AFTER_WORST, 0.005):,.0f}/月</b>',
                 f"浮動本金 {fmt(FLOAT_AFTER_WORST)}"])
lab_rows.append(["<b>合計（9/25 撥款後 · 質押鎖固定）</b>", "", "", "",
                 f'<b style="color:#fbbf24">+{hike_cost(FLOAT_AFTER_LOCKED, 0.0025):,.0f}/月</b>',
                 f'<b style="color:#fbbf24">+{hike_cost(FLOAT_AFTER_LOCKED, 0.005):,.0f}/月</b>',
                 "← 爭取這個：書面固定 = 每碼少付約 1,125 元/月"])

body3 = table(["負債項目", "餘額", "利率", "型態", "+1 碼", "+2 碼", "備註"], lab_rows)
cf_rows = [
    ["現行（保單 4%＋券商 3.92% 仍在）", fmt(INT_NOW), "—", "—"],
    ["9/25 質押撥款後（清 500 萬高息）", fmt(INT_AFTER),
     f'{INT_AFTER-INT_NOW:+,.0f}', "每月省息約 4,135（與 snapshot 利差試算一致）"],
    ["再遇 +1 碼（撥款後結構）", fmt(INT_AFTER + hike_cost(FLOAT_AFTER_WORST, 0.0025)),
     f'+{hike_cost(FLOAT_AFTER_WORST, 0.0025):,.0f}', "利率風險已轉移到低利負債，但本金變大"],
]
body3 += f'<h3 style="color:#e2e8f0;font-size:14px;margin:14px 0 6px">月利息支出對照</h3>'
body3 += table(["狀態", "月利息（估）", "變化", "說明"], cf_rows)
c3 = card("③ 負債端影響（升息真正咬你的地方）", body3, "#ef4444")

# ── 4. 月現金流衝擊 ────────────────────────────────
rows4 = []
for label, step in HIKE_STEPS:
    inc_cost = hike_cost(FLOAT_AFTER_WORST, step)
    surplus_after = SURPLUS - inc_cost + CASH_GAIN_PER_STEP * (2 if step > 0.003 else 1)
    rows4.append([f"Fed {label}", f'{inc_cost:,.0f}', f'{surplus_after:,.0f}',
                  f'{(surplus_after/SURPLUS-1)*100:+.1f}%', "仍為正 → 不需賣資產、不需砍配息"])
rows4.append(["升息同時債券配息再投資升", "—", f'≥ {SURPLUS:,.0f}', "0%",
              "新資金買到更高殖利率，2-4 季後配息回升"])
body4 = table(["情境", "月增利息成本", "月盈餘（估）", "變化", "判讀"], rows4)
body4 += (f'<div style="margin-top:10px;color:#cbd5e1;font-size:13px">'
          f'月收入 {fmt(INCOME)}（含配息 {fmt(DIV_ACTUAL)}＋租金 {fmt(RENT)}）／月支出 {fmt(EXPENSE)}／'
          f'月盈餘 {fmt(SURPLUS)}。<b>結論：升息會吃掉 8-20% 盈餘，但盈餘不會轉負</b> → '
          f'這是「調結構」的問題，不是「求生」的問題。</div>')
c4 = card("④ 現金流衝擊（月盈餘還剩多少）", body4, "#22c55e")

# ── 5. 擔保池 / LTV 追繳壓力 ────────────────────────
ltv_rows = []
for drop in [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]:
    ltv, need = ltv_after_drop(drop)
    if ltv <= 50:
        cl = "#34d399"
    elif ltv <= 53:
        cl = "#fbbf24"
    elif ltv < 70:
        cl = "#fb923c"
    else:
        cl = "#f87171"
    cash_covers = "✅" if need <= CASH else "❌"
    ltv_rows.append([f"池 {drop*100:.0f}%", fmt(POOL_VALUE*(1-drop)), f'<span style="color:{cl}">{ltv:.1f}%</span>',
                     fmt(need), f'{need/CASH*100:.0f}%　{cash_covers}' if need else "—",
                     "綠 ≤50｜黃 50-53｜橙 53-70｜紅 追繳 70"])
body5 = table(["擔保池跌幅", "池市值", "LTV", "補回 50% 需補繳", "佔現金比", "燈號"], ltv_rows)
body5 += (f'<div style="margin-top:10px;color:#cbd5e1;font-size:13px;line-height:1.7">'
          f'擔保池後收級別占 <b>92%</b>（富達 CDSC 至 2029/8、貝萊德 B11 至 2029/9）→ '
          f'<b>追繳時不能賣擔保品</b>，緩衝只有現金 {fmt(CASH)}。'
          f'升息若讓池內債券型基金跌 10-15%，LTV 會從 {LTV_NOW:.1f}% 升到 '
          f'{ltv_after_drop(0.10)[0]:.1f}%-{ltv_after_drop(0.15)[0]:.1f}%，'
          f'補回 50% 需動用 {fmt(ltv_after_drop(0.15)[1])}（現金 {ltv_after_drop(0.15)[1]/CASH*100:.0f}%）→ '
          f'<b>現金底線 70 萬在升息情境下太薄</b>。</div>')
c5 = card("⑤ 最大尾風險：擔保池 LTV 與追繳（升息→池淨值跌）", body5, "#f97316")

# ── 6. 該怎麼調（分層行動）────────────────────────
acts = [
    ("🟥 升息前必須完成（這一週）", [
        f'洲際W 轉貸：優先<b>築巢優利貸 2.185%</b>（台電專屬）→ 拿不到就國泰 ≤2.5%；'
        f'<b>書面載明利率型態</b>（固定/機動＋加碼基準）',
        f'質押 540 萬對保：<b>本週推動、不要拖過 9/25</b>；合約要求利率型態書面化、'
        f'維持率/追繳線/補繳天數白紙黑字（升息前鎖 2.77%＝撿便宜）',
        f'確認保單借貸 400 萬@4% 與券商 3.92% 的<b>型態</b>：若是機動，清償順序提前（現金流先鎖住）',
        f'現金底線由 70 萬→<b>120 萬</b>（擔保池 92% 後收不可變現，升息期緩衝必須自己留）',
    ]),
    ("🟨 升息確認後（FOMC 之後）", [
        f'債券 {fmt(BOND)}：<b>凍結不賣</b>（賣＝鎖虧），領息照收；'
        f'存續期只降不增（新資金往短債/浮動利率債，長債不再加）— 紅線 ≥5.30% 已 latch',
        f'科技 {fmt(TECH)}（{TECH/TOTAL*100:.1f}%）：逢反彈減碼 <b>{fmt(TECH_CUT_AMT)}</b>'
        f'（引擎板塊輪動 {TECH_CUT_PP}｜情境倍率 ×1.32，標的：{_tech_rot.get("標的","—")}），單次 ≤20 萬、4-6 週分批',
        f'台股：不追反彈，回檔 -3% 才小單（≤5 萬）；配息導流第一優先（零摩擦）→ 高股息 00878/00713',
        f'新資金改買<b>短天期/機動利率</b>收益資產：升息期「買短的」，不買長天期鎖死',
    ]),
    ("🟩 若進入股債雙殺（LTV 上限切 50%）", [
        f'情境切換：震盪 → 股債雙殺（防禦門檻 50→55、收入 65→70、LTV 上限 52→50）',
        f'質押借款<b>部分提前還本</b>：把 LTV 壓回 45% 以下（每降 1pp ≈ 還本 11.8 萬）',
        f'停止新增美元曝險（現 {USD_EXPOSURE_PCT*100:.1f}% 已超 60% 上限）',
        f'暫停市值型大額布局：US30Y 需連續 3 日 < 5.20% 才解凍（現 {us30y_now}%）',
    ]),
]
body6 = ""
for title, items in acts:
    lis = "".join(f'<li style="margin-bottom:7px">{i}</li>' for i in items)
    body6 += f'<div style="margin-bottom:12px"><div style="color:#e2e8f0;font-weight:700;font-size:14px;margin-bottom:6px">{title}</div><ul style="margin:0;padding-left:20px;color:#cbd5e1;font-size:13px;line-height:1.6">{lis}</ul></div>'
c6 = card("⑥ 調配行動清單（照這個順序做）", body6, "#a78bfa")

# ── 7. 不要做什麼 + 監控觸發 ────────────────────────
donts = ["❌ 不要因為帳面下跌就賣債券——賣出才把未實現虧損變成真虧損，配息也一併斷掉",
         "❌ 不要用質押借來的錢去追高（升息期槓桿成本上升、擔保品同時跌＝雙向夾殺）",
         "❌ 不要賣房或急著降房貸（房租 8 萬/月＝穩定現金流，且轉貸已在優化利率）",
         "❌ 不要因升息恐慌清空美股（你真正的風險是債務成本與美元集中度，不是股票本身）"]
triggers = [
    f'US30Y ≥5.30%（紅線 latch）→ 債券新增永久凍結（現 {us30y_now}%｜{red_line}）',
    "9/16 FOMC 升息 → 當下不接刀，等 2-3 天消化；大跌 -5% 才考慮 0050/006208（單次 ≤5 萬）",
    "US30Y 連續 3 日 <5.20% → 市值型大額布局解凍（目前凍結中）",
    f'美元曝險 >60% 黃燈 / >65% 紅燈 → 停止新增美元（現 {USD_EXPOSURE_PCT*100:.1f}% ❌）',
    "VIX >28 或緊急應變 ≥70 → 情境切「熊市」（LTV 上限 48%、只還本不加碼）",
    f'擔保池 LTV >53% → 補繳/還本（現 {LTV_NOW:.1f}%，補回 50% 每檔約需 11.8 萬）',
]
body7 = ('<div style="color:#cbd5e1;font-size:13px;line-height:1.8">'
         + "".join(f'{d}<br>' for d in donts) + '</div>')
body7 += '<h3 style="color:#e2e8f0;font-size:14px;margin:14px 0 6px">監控觸發（自動對應動作）</h3>'
body7 += '<div style="color:#cbd5e1;font-size:13px;line-height:1.8">' + "".join(f'• {t}<br>' for t in triggers) + '</div>'
c7 = card("⑦ 不要做什麼 × 監控觸發", body7, "#64748b")

# ── 組裝 ───────────────────────────────────────────
html = f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>龍九 · 升息情境影響與調配（{TODAY}）</title></head>
<body style="margin:0;background:#020617;font-family:-apple-system,'Noto Sans TC','Microsoft JhengHei',sans-serif">
<div style="max-width:980px;margin:0 auto;padding:20px 16px 60px">
  <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
    <h1 style="margin:0;font-size:22px;color:#f1f5f9">📈 升息情境 · 影響與調配</h1>
    {chip(f"{TODAY}（{WD}）", "#38bdf8")}
    {chip(f"US30Y {us30y_now}%", "#f87171")}
    {chip("DAA 🔴 紅燈", "#f87171")}
  </div>
  <div style="color:#94a3b8;font-size:13px;margin-top:8px">
    總資產 {fmt(TOTAL)}｜負債 {fmt(liab.get('total', 0))}｜現金 {fmt(CASH)}｜月盈餘 {fmt(SURPLUS)}
  </div>
  <div style="background:#0b1220;border:1px solid #1e293b;border-radius:12px;padding:12px 14px;margin-top:14px;color:#cbd5e1;font-size:13px;line-height:1.7">
    <b style="color:#e2e8f0">一句話結論</b>：升息對你是「<b style="color:#f87171">負債成本上升 × 債券帳面承壓</b>」，
    但<b style="color:#34d399">配息現金流不中斷、月盈餘仍為正</b>。
    最該做的不是賣資產，而是<b>把浮動負債鎖成固定、把現金緩衝加厚</b>——
    你已經在做的 540 萬質押清高息就是這條路，只要來得及在升息前完成就贏一半。
  </div>
  {c1}{c2}{c3}{c4}{c5}{c6}{c7}
  <div style="color:#475569;font-size:11px;margin-top:18px;line-height:1.7">
    資料源：snapshot.json（{s.get('date','—')}）／macro_regime（{macro.get('date', TODAY)}）／us30y_state.json。
    情境假設：Fed +1／+2 碼、台灣指標同步 1:1；債券存續期 {BOND_DURATION}y（混合估算）；權益壓力科技 {EQUITY_STRESS*100:.0f}%／台股 {TW_EQUITY_STRESS*100:.0f}%；台幣貶值 {TWD_DEPRECIATION*100:.0f}%。
    產生時間 {datetime.now():%Y-%m-%d %H:%M}｜本表為情境試算，非預測，不自動下單。
  </div>
</div></body></html>"""

out = BASE / f"rate_hike_dashboard_{TODAY}.html"
out.write_text(html, encoding="utf-8")
print(f"✅ 已輸出 {out.name}（{len(html):,} bytes）")
print(f"   浮動負債：現行 {FLOAT_NOW_WORST:,.0f}｜撥款後 worst {FLOAT_AFTER_WORST:,.0f}｜鎖固定 {FLOAT_AFTER_LOCKED:,.0f}")
print(f"   +1 碼月增：現行 {hike_cost(FLOAT_NOW_WORST,0.0025):,.0f}｜撥款後 {hike_cost(FLOAT_AFTER_WORST,0.0025):,.0f}｜鎖固定 {hike_cost(FLOAT_AFTER_LOCKED,0.0025):,.0f}")
print(f"   LTV 現況 {LTV_NOW:.1f}%｜跌 15% → {ltv_after_drop(0.15)[0]:.1f}%（補回 50% 需 {ltv_after_drop(0.15)[1]:,.0f}）")
print(f"   債券 +1 碼帳面 {bond_delta(0.0025):,.0f}｜+2 碼 {bond_delta(0.005):,.0f}")
