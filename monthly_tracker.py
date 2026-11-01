#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""monthly_tracker.py — 月度追蹤（資產變化 ＋ 現金流），每月 1 日自動累積。

為什麼要有這支
--------------
原本的「大轉向簡報」是事件式敘事（9/11 CPI → 9/25 到期 → 10 月標案），
事件一過整份就過期，且內容與日報/儀表板高度重疊。使用者 2026-11-01 指正：
「我看不出來這個簡報對我有什麼幫助」「我想整理成 9/10/11 月的績效評估跟分析」
「這樣至少可以方便我去追蹤每個月的變化跟現金流」。

→ 改成「月度追蹤」：固定欄位、逐月累積、可直接比較。不寫敘事、不寫日曆事件。

資料源（全部動態，禁寫死）
------------------------
- 資產／負債／淨值：asset_diff_history.json（逐日快照，10/01 起）
- 配息：snapshot.dividend_records[YYYY-MM]（逐筆加總）
- 租金：snapshot.rent_received_records（逐筆日期 → 月加總）
- 薪資：snapshot.salary_records[YYYY-MM].amount
- 支出：snapshot.monthly_fixed_expense.合計（常態值；實際支出需 Moneybook 月別匯入）
- 9 月以前：沒有逐日 history → 從既有 monthly_report_YYYY-MM.html 解析，並標口徑斷點

輸出
----
- monthly_tracker.html（人看：每月一張卡 ＋ 變化）
- data/monthly_tracker.json（機器讀：逐月累積，供後續比較/圖表）

用法
----
  python monthly_tracker.py            # 產出 HTML + JSON
  python monthly_tracker.py --print    # 只印摘要，不寫檔
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
HIST = BASE / "asset_diff_history.json"
SNAP = BASE / "snapshot.json"
OUT_HTML = BASE / "monthly_tracker.html"
OUT_JSON = BASE / "data" / "monthly_tracker.json"


def _num(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except Exception:
        return None


def _fmt(v, dash="—"):
    return f"{int(round(v)):,}" if _num(v) is not None else dash


def _pct(v, d=1, dash="—"):
    return f"{v:,.{d}f}%" if _num(v) is not None else dash


# ── 1. 逐日 history → 每月最後一筆 ────────────────────────────────
def month_ends_from_history():
    if not HIST.exists():
        return {}
    h = json.loads(HIST.read_text(encoding="utf-8"))
    last = {}
    for d, v in sorted(h.items()):
        if not re.match(r"\d{4}-\d{2}-\d{2}", d):
            continue
        last[d[:7]] = (d, v)
    return last


# ── 2. 舊月報解析（9 月以前沒有逐日資料）────────────────────────
def parse_monthly_report(ym):
    """從 monthly_report_YYYY-MM.html 取首末資產負債（表格前 5 列）。"""
    p = BASE / f"monthly_report_{ym}.html"
    if not p.exists():
        return None
    t = p.read_text(encoding="utf-8")
    t = re.sub(r"<(script|style).*?</\1>", "", t, flags=re.S)
    cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", t, flags=re.S)]

    def grab(label):
        for i, c in enumerate(cells):
            if c == label and i + 3 < len(cells):
                try:
                    return float(cells[i + 1].replace(",", "")), float(cells[i + 2].replace(",", ""))
                except Exception:
                    return None
        return None

    liq = grab("流動資產合計")
    liab = grab("總負債")
    net = grab("淨資產(流動-負債)")
    if not (liq and liab):
        return None
    return {"first": {"assets": liq[0], "liabilities": liab[0]},
            "last": {"assets": liq[1], "liabilities": liab[1]},
            "net_first": net[0] if net else None, "net_last": net[1] if net else None,
            "source": p.name}


# ── 3. 現金流（收入三源 ＋ 常態支出）──────────────────────────────
def income_by_month(snap):
    div = {}
    for ym, items in (snap.get("dividend_records") or {}).items():
        if not re.match(r"\d{4}-\d{2}$", str(ym)) or not isinstance(items, dict):
            continue
        vals = [_num(x) for x in items.values()]
        vals = [v for v in vals if v is not None]
        if vals:
            div[ym] = sum(vals)

    rent = defaultdict(float)
    for d, items in (snap.get("rent_received_records") or {}).items():
        if not re.match(r"\d{4}-\d{2}", str(d)) or not isinstance(items, dict):
            continue
        vals = [_num(x) for x in items.values()]
        vals = [v for v in vals if v is not None]
        if vals:
            rent[str(d)[:7]] += sum(vals)

    sal = {}
    for ym, v in (snap.get("salary_records") or {}).items():
        if re.match(r"\d{4}-\d{2}$", str(ym)) and isinstance(v, dict):
            a = _num(v.get("amount"))
            if a is not None:
                sal[ym] = a

    exp = _num((snap.get("monthly_fixed_expense") or {}).get("合計")) or _num(snap.get("monthly_expense"))
    return div, rent, sal, exp


# ── 4. 組月度序列 ────────────────────────────────────────────────
def build():
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    hist = month_ends_from_history()
    div, rent, sal, exp = income_by_month(snap)

    months = sorted(set(list(hist) + list(div) + list(rent) + list(sal)))
    rows = []
    for ym in months:
        row = {"month": ym, "assets": None, "liabilities": None, "net": None,
               "cash": None, "securities": None, "insurance": None, "funds": None,
               "dividend": div.get(ym), "rent": rent.get(ym), "salary": sal.get(ym),
               "expense": exp, "partial": False, "note": "", "source": ""}
        if ym in hist:
            d, v = hist[ym]
            row.update({
                "as_of": d,
                "assets": _num(v.get("total_assets")),
                "liabilities": _num(v.get("total_liabilities")),
                "cash": _num(v.get("cash")),
                "securities": _num(v.get("securities_market")),
                "insurance": _num(v.get("insurance_total") or v.get("insurance_current")),
                "funds": _num(v.get("fund_market")),
                "source": "asset_diff_history.json",
            })
            row["net"] = (row["assets"] - row["liabilities"]) if row["assets"] is not None and row["liabilities"] is not None else None
            # 當月最後一筆不是月底 → 進行中
            if d[8:10] != _last_day(ym)[8:10]:
                row["partial"] = True
                row["note"] = f"進行中（截至 {d}）"
        else:
            rep = parse_monthly_report(ym)
            if rep:
                row.update({
                    "as_of": _last_day(ym),
                    "assets": rep["last"]["assets"],
                    "liabilities": rep["last"]["liabilities"],
                    "net": rep["net_last"] if rep["net_last"] is not None else rep["last"]["assets"] - rep["last"]["liabilities"],
                    "source": rep["source"],
                })
                row["note"] = "由月報解析；無逐日 history"
        if ym == "2026-09":
            row["caliber_break"] = True   # 9 月底負債含保單借貸 400 萬未沖銷 → 跨月不可相減
        rows.append(row)

    # 月變化
    prev = None
    for r in rows:
        _ok = prev and not prev.get("caliber_break") and not r.get("caliber_break")
        r["assets_chg"] = (r["assets"] - prev["assets"]) if _ok and r["assets"] is not None and prev.get("assets") is not None else None
        r["net_chg"] = (r["net"] - prev["net"]) if _ok and r["net"] is not None and prev.get("net") is not None else None
        prev = r

    # ── 口徑註記（不寫死金額：跨月斷點一律用相鄰月差額動態描述）──
    by_ym = {r["month"]: r for r in rows}
    for r in rows:
        ym = r["month"]
        if ym == "2026-07":
            r["note"] = (r["note"] + "｜" if r["note"] else "") + "月報口徑：僅流動資產，與 8 月起口徑不同，不可與後續月份直接比較"
        if ym == "2026-09":
            nxt = by_ym.get("2026-10") or {}
            gap = None
            if r.get("liabilities") is not None and nxt.get("liabilities") is not None:
                gap = r["liabilities"] - nxt["liabilities"]
            r["note"] = (r["note"] + "｜" if r["note"] else "") + (
                "負債含一次性未沖銷項（保單借貸於 10/01 入帳沖銷）"
                + (f"，9→10 月負債差 {_fmt(gap)}" if gap else "")
                + "→ 淨值偏低、跨月不可直接相減")

    # 收入合計與現金流
    for r in rows:
        inc = sum(v for v in (r["dividend"], r["rent"], r["salary"]) if v is not None)
        r["income_total"] = inc if inc or r["dividend"] is not None else None
        passive = sum(v for v in (r["dividend"], r["rent"]) if v is not None)
        r["passive"] = passive
        r["net_cash"] = (inc - r["expense"]) if r["expense"] and inc else None
        r["cover_pct"] = (passive / r["expense"] * 100) if r["expense"] and passive else None

    # ── Moneybook 實際支出（有匯入才顯示；缺失＝明示「未匯入」，不以估算冒充）──
    cum = 0.0
    have_any = False
    for r in rows:
        f = BASE / "data" / f"mb_expense_{r['month']}.json"
        r["mb"] = None
        if f.exists():
            try:
                m = json.loads(f.read_text(encoding="utf-8"))
                r["mb"] = {"expense": m.get("expense_actual"), "non_recurring": m.get("expense_non_recurring"),
                           "holds": m.get("holds") or [], "source": (m.get("source") or {}).get("file")}
                have_any = True
            except Exception:
                r["mb"] = None
        if r["mb"] and r["mb"]["expense"] is not None:
            r["expense_actual"] = r["mb"]["expense"]
            r["net_cash_actual"] = (r["income_total"] or 0) - r["expense_actual"]
            r["budget_diff"] = r["expense_actual"] - r["expense"] if r["expense"] else None
            r["passive_left"] = (r["passive"] or 0) - r["expense_actual"]
            cum += r["net_cash_actual"]
            r["cum_cash"] = cum
        else:
            r["expense_actual"] = r["net_cash_actual"] = r["budget_diff"] = r["passive_left"] = None
            r["cum_cash"] = cum if have_any else None
    return rows, exp


def _last_day(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    nxt = f"{y + 1}-01-01" if m == 12 else f"{y}-{m + 1:02d}-01"
    import datetime as _dt
    d = _dt.date.fromisoformat(nxt) - _dt.timedelta(days=1)
    return d.isoformat()


# ── 5. 輸出 ─────────────────────────────────────────────────────
def render_html(rows, exp):
    css = """
    :root{--bg:#0b0d1a;--card:#151a2e;--line:#27304d;--txt:#e8ebf2;--dim:#8a8fa0;--gold:#f7a01c;--green:#34d399;--red:#ff5c5c;--blue:#60a5fa}
    *{box-sizing:border-box}
    body{margin:0;padding:16px;background:var(--bg);color:var(--txt);font-family:-apple-system,"Segoe UI","Noto Sans TC",sans-serif;line-height:1.5}
    h1{font-size:20px;margin:0 0 4px}
    .sub{color:var(--dim);font-size:12px;margin-bottom:16px}
    .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:12px}
    .hd{display:flex;justify-content:space-between;align-items:baseline;gap:8px;margin-bottom:10px}
    .ym{font-size:17px;font-weight:800}
    .tag{font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);color:var(--dim)}
    .tag.wip{border-color:#6b5a1f;color:var(--gold)}
    .grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
    .kv{padding:6px 8px;background:#0f1424;border-radius:8px}
    .kv .k{font-size:11px;color:var(--dim)}
    .kv .v{font-size:15px;font-weight:700}
    .kv .d{font-size:11px;margin-top:2px}
    .up{color:var(--green)} .down{color:var(--red)} .dim{color:var(--dim)}
    .sec{margin-top:10px;padding-top:10px;border-top:1px dashed var(--line);font-size:12px;color:var(--dim)}
    .sec b{color:var(--txt);font-weight:600}
    .warn{background:#2a1f12;border:1px solid #6b5a1f;color:#f5c26b;font-size:12px;padding:8px 10px;border-radius:8px;margin-bottom:12px}
    """
    cards = []
    prev_break = False
    for r in rows:
        chg = r.get("net_chg")
        chg_cls = "up" if (chg or 0) > 0 else ("down" if (chg or 0) < 0 else "dim")
        chg_txt = f"{'+' if (chg or 0) > 0 else ''}{_fmt(chg)}" if chg is not None else "—"
        tag = '<span class="tag wip">進行中</span>' if r.get("partial") else '<span class="tag">已結算</span>'
        items = [
            ("金融資產", _fmt(r["assets"]), f"月變 {_fmt(r.get('assets_chg'))}" if r.get("assets_chg") is not None else ("口徑斷點，不比月變" if prev_break else r.get("note", ""))),
            ("總負債", _fmt(r["liabilities"]), ""),
            ("金融淨值", _fmt(r["net"]), f'月變 <span class="{chg_cls}">{chg_txt}</span>' if chg is not None else ""),
            ("被動覆蓋", _pct(r.get("cover_pct")), f"支出基準 {_fmt(exp)}"),
        ]
        kvs = "".join(
            f'<div class="kv"><div class="k">{k}</div><div class="v">{v}</div><div class="d">{d}</div></div>'
            for k, v, d in items
        )
        if r.get("expense_actual") is not None:
            _nr = (r.get("mb") or {}).get("non_recurring") or 0
            act = (f'實際支出 <b>{_fmt(r["expense_actual"])}</b>'
                   f'（MB 明細；含非經常性 {_fmt(_nr)}）｜實際淨現金流 <b>{_fmt(r["net_cash_actual"])}</b><br>'
                   f'預算差異 <b>{_fmt(r["budget_diff"])}</b>（對常態 {_fmt(r["expense"])}）'
                   f'｜被動結餘 <b>{_fmt(r["passive_left"])}</b>'
                   f'｜累積現金流 <b>{_fmt(r["cum_cash"])}</b>')
        else:
            act = (f'支出（常態，未匯入實際）：<b>{_fmt(r["expense"])}</b>'
                   f'｜淨現金流（估）：<b>{_fmt(r["net_cash"])}</b>')
        flow = f'''<div class="sec">
          收入：薪資 <b>{_fmt(r["salary"], "本月未入帳")}</b>｜配息 <b>{_fmt(r["dividend"], "本月未入帳")}</b>｜租金 <b>{_fmt(r["rent"], "本月未入帳")}</b>
          ＝ <b>{_fmt(r["income_total"])}</b><br>
          {act}
          {f'<br>資產明細：現金 {_fmt(r["cash"])}｜證券 {_fmt(r["securities"])}｜保單 {_fmt(r["insurance"])}｜基金 {_fmt(r["funds"])}' if r.get("cash") is not None else ''}
          <br><span style="opacity:.7">來源：{r.get("source") or "—"}{("｜" + r["note"]) if r.get("note") else ""}</span>
        </div>'''
        cards.append(f'<div class="card"><div class="hd"><div class="ym">{r["month"]}</div>{tag}</div><div class="grid">{kvs}</div>{flow}</div>')
        prev_break = bool(r.get("caliber_break"))

    has_act = any(r.get("expense_actual") is not None for r in rows)
    warn = ('<div class="warn">口徑：有 Moneybook 匯入的月份用<b>實際支出</b>；'
            '未匯入月份沿用常態'
            f'（{_fmt(exp)}）並標示「估」，不以估算冒充實際。'
            '實際支出已排除帳戶互轉／信用卡繳款／投資買賣／貸款本金。</div>'
            if has_act else
            '<div class="warn">口徑提醒：目前尚無 Moneybook 實際支出，支出採常態'
            f'（{_fmt(exp)}）。每月 1 日匯入後才有真值。</div>')
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>龍九控股 · 月度追蹤</title><style>{css}</style></head><body>
<h1>📅 龍九控股 · 月度追蹤</h1>
<div class="sub">每月變化與現金流｜資產負債以月底快照為準｜資料源 snapshot.json ＋ asset_diff_history.json</div>
{warn}
{''.join(cards)}
<div class="sub" style="margin-top:16px">唯一寫入者 monthly_tracker.py｜產生於 {__import__('datetime').date.today().isoformat()}</div>
</body></html>"""


def main(argv):
    rows, exp = build()
    if "--print" in argv:
        for r in rows:
            print(f'{r["month"]}｜資產 {_fmt(r["assets"])}｜負債 {_fmt(r["liabilities"])}｜淨值 {_fmt(r["net"])}'
                  f'｜配息 {_fmt(r["dividend"])}｜租金 {_fmt(r["rent"])}｜薪資 {_fmt(r["salary"])}'
                  f'｜覆蓋 {_pct(r.get("cover_pct"))}{"（進行中）" if r.get("partial") else ""}')
        return 0
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
                                    "expense_base": exp, "months": rows}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    OUT_HTML.write_text(render_html(rows, exp), encoding="utf-8")
    print(f"✅ 已產出 {OUT_HTML.name}（{len(rows)} 個月）＋ {OUT_JSON.relative_to(BASE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
