# -*- coding: utf-8 -*-
"""build_performance_monthly.py — 投資績效｜月度比較（歷史視圖）

產出：`performance_monthly.html`（固定檔名，與 mtd_performance.html 同層）

## 鐵則（使用者 2026-10-03 裁示）
1. **唯一真值來源＝`performance_core.monthly_history()`**；本檔不得出現任何績效公式或寫死的績效數字。
2. 每月「角色／可用性」（Baseline 不可比／歷史參考／資本基準月／基準後／進行中）**由 core 決定**，
   報表端不得用月份字串自行判斷。
3. 累計只計「基準月之後且已完成」的月份；基準月本身、歷史參考月、Baseline 不可比月、進行中月一律不列入。
4. 沒有可靠期初市值 → 報酬率顯示「—」，禁止反推。

資料源：snapshot.json／investment_performance_adjust.json（含 `角色` 宣告）／dragon_assets.db
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import performance_core as pc  # noqa: E402

OUT_HTML = BASE / "performance_monthly.html"
SNAP = BASE / "snapshot.json"
ADJ = BASE / "investment_performance_adjust.json"
DB = BASE / "dragon_assets.db"
LOG = BASE / "logs" / "performance_monthly.log"

log = logging.getLogger("perf_monthly")


def _f(v) -> str:
    return f"{v:+,.0f}" if v is not None else "—"


def _pct(v) -> str:
    return f"{v * 100:+.3f}%" if v is not None else "—"


def _cls(v) -> str:
    return "up" if (v or 0) > 0 else ("down" if (v or 0) < 0 else "flat")


def _mkt_sum(m: dict) -> float:
    return sum(r["mkt"] for r in m["rows"])


def _rows_html(m: dict) -> str:
    """單月明細列（手機優先：純列式，不用橫向捲動表格）。"""
    out = [
        ("投資損益（三類合計）", _f(m["grand"]), _cls(m["grand"])),
        ("　配息實收", _f(m["div"]), "up"),
    ]
    if m["usable"] == pc.USE_NOT_COMPARABLE:
        out.append(("　市值變化", "—（市值不可靠，不計）", "flat"))
    else:
        out.append(("　市值變化", _f(_mkt_sum(m)), _cls(_mkt_sum(m))))
    if m["fee"]:
        out.append(("　手續費", _f(-m["fee"]), "down"))
    if m["interest_registered"]:
        out.append(("　投資利息", _f(-m["interest"]), "down"))
    elif m["interest_est"] is not None:
        out.append(("　投資利息", f"—（未登錄；暫估 {m['interest_est']:,.0f}／月）", "flat"))
    else:
        out.append(("　投資利息", "—（未登錄）", "flat"))
    out.append(("淨投資績效", _f(m["net"]), _cls(m["net"])))
    if m["interest_est"] is not None:
        out.append(("　同口徑暫估", _f(m["net_same_caliber"]), _cls(m["net_same_caliber"])))
    twr = (m.get("twr") or {}).get("twr")
    if twr is not None and m.get("twr_reliable"):
        out.append(("報酬率（TWR）", _pct(twr), _cls(twr)))
    else:
        why = (m.get("twr_reason") or "無法可靠計算").split("；")[0]
        out.append(("報酬率（TWR）", f"—（{why}）", "flat"))
    if m.get("rate_total") is not None:
        out.append(("淨值報酬（含配息）", _pct(m["rate_total"]), _cls(m["rate_total"])))
    if m["usable"] == pc.USE_COMPLETE:
        out.append(("日均（÷%d 天）" % m["days"], _f(m["net_per_day"]), _cls(m["net_per_day"])))
    elif m["usable"] == pc.USE_IN_PROGRESS:
        end = (m.get("asof") or "")[5:] or "最新"
        out.append(("期間", f"{m['label'][5:]}/01–{end[:2]}/{end[3:]}（{m['days']} 天，MTD）", "flat"))
    else:
        out.append(("期間", f"{m['label']}/01 起 {m['days']} 天（不可比）", "flat"))
    html = "".join(f'<tr><th>{k}</th><td class="{c}">{v}</td></tr>' for k, v, c in out)
    return f'<table class="kv">{html}</table>'


def _status_chip(m: dict) -> str:
    cls = {"legacy": "chip-grey", "reference": "chip-slate",
           "capital_baseline": "chip-amber", "post_baseline": "chip-teal"}[m["role"]]
    use = "chip-live" if m["usable"] == pc.USE_IN_PROGRESS else ""
    return (f'<span class="chip {cls}">{m["role_label"]}</span>'
            f'<span class="chip {use}">{m["usable_label"]}</span>')


def _month_card(m: dict, title_extra: str = "") -> str:
    return (f'<div class="mcard">'
            f'<div class="mhead"><span class="mlabel">{m["label"]}</span>{_status_chip(m)}'
            f'<span class="mnet {_cls(m["net"])}">{_f(m["net"])}</span></div>'
            f'{title_extra}{_rows_html(m)}</div>')


def _class_breakdown(months) -> str:
    rows = []
    for m in months:
        cells = "".join(
            f'<tr><th>{r["c"]}</th><td class="{_cls(r["mkt"])}">{_f(r["mkt"])}</td>'
            f'<td class="up">{_f(r["div"])}</td><td class="{_cls(r["pnl"])}">{_f(r["pnl"])}</td>'
            f'<td class="basis">{r["basis"]}</td></tr>' for r in m["rows"])
        rows.append(
            f'<div class="bgroup"><div class="btitle">{m["label"]}'
            f'<span class="chip {_chip_of(m)}">{m["role_label"]}</span></div>'
            f'<table class="bt"><thead><tr><th>類別</th><th>市值變化</th><th>配息</th>'
            f'<th>損益</th><th>來源</th></tr></thead><tbody>{cells}</tbody></table></div>')
    return "".join(rows)


def _chip_of(m: dict) -> str:
    return {"legacy": "chip-grey", "reference": "chip-slate",
            "capital_baseline": "chip-amber", "post_baseline": "chip-teal"}[m["role"]]


def _trend(months) -> str:
    mx = max((abs(m["net"]) for m in months), default=1) or 1
    out = []
    for m in months:
        w = max(2, round(abs(m["net"]) / mx * 100))
        bar_cls = _chip_of(m) + (" live" if m["usable"] == pc.USE_IN_PROGRESS else "")
        out.append(
            f'<div class="trow"><span class="tlbl">{m["label"]}</span>'
            f'<span class="tbarwrap"><span class="tbar {bar_cls}" style="width:{w}%"></span></span>'
            f'<span class="tval {_cls(m["net"])}">{_f(m["net"])}</span></div>')
    return "".join(out)


def _hero(cur: dict, base_mv: float, asof: str) -> str:
    """本月判讀卡：①淨損益 ②報酬率 ③配息/市值變化 ④利息 ⑤資料日。"""
    net_same = cur["net_same_caliber"]
    est = cur["interest_est"]
    twr = (cur.get("twr") or {}).get("twr")
    twr_ok = bool(cur.get("twr_reliable")) and twr is not None
    twr_txt = _pct(twr) if twr_ok else "無法可靠計算"
    if twr_ok:
        twr_note = (f'日頻時間加權報酬率（TWR）；起算 {cur.get("twr_start") or "—"}（首個有效估值日），'
                    f'截至 {cur.get("twr_end") or "—"}。資金流於日初計入；資料涵蓋範圍與配息時點依完整度判讀。')
    else:
        twr_note = cur.get("twr_reason") or "缺日估值"
    rt = cur.get("rate_total")
    mkt = _mkt_sum(cur)
    int_line = (f"−{cur['interest']:,.0f}（已登錄）" if cur["interest_registered"]
                else (f"−{est:,.0f}（暫估，10 月未登錄）" if est is not None else "未登錄"))
    fee_line = f"−{cur['fee']:,.0f}" if cur["fee"] else "0（未登錄）"
    return f"""
<section class="card hero">
  <div class="klabel">本月淨投資損益（已扣投資利息）</div>
  <div class="kval {_cls(net_same)}">{_f(net_same)}</div>
  <div class="ksub">未扣息 <b>{_f(cur['net'])}</b>｜投資利息 {int_line}｜手續費 {fee_line}</div>
  <div class="kgrid">
    <div class="kpi"><div class="klabel">報酬率（TWR）</div>
      <div class="kval2 {_cls(twr) if twr_ok else 'flat'}">{twr_txt}</div>
      <div class="ksub">{twr_note}</div></div>
    <div class="kpi"><div class="klabel">淨值報酬（含配息）</div>
      <div class="kval2 {_cls(rt)}">{_pct(rt) if rt is not None else '—'}</div>
      <div class="ksub">淨投資損益 ÷ 月初三類市值 {base_mv:,.0f}</div></div>
  </div>
  <table class="kv" style="margin-top:10px">
    <tr><th>配息實收</th><td class="up">{_f(cur['div'])}</td></tr>
    <tr><th>市值變化（已排除已登錄資金流）</th><td class="{_cls(mkt)}">{_f(mkt)}</td></tr>
    <tr><th>統計期間</th><td class="flat">{cur['label'][5:]}/01–{asof[5:7]}/{asof[8:]}（{cur['days']} 天，MTD 未結束）</td></tr>
  </table>
</section>"""


def _verdict(cur: dict) -> str:
    """一句話判讀：賺賠多少／是不是投資本身造成／最大來源／賣出有沒有被誤記。"""
    net = cur["net_same_caliber"]
    rows = sorted(cur["rows"], key=lambda r: -abs(r["pnl"]))
    top = rows[0] if rows else None
    invested = sum(r["invest"] for r in cur["rows"])
    fout = sum(r["flow_out"] for r in cur["rows"])
    fin = sum(r["flow_in"] for r in cur["rows"])
    bits = [f'本月{"賺" if net >= 0 else "賠"} <b class="{_cls(net)}">{abs(net):,.0f}</b>']
    bits.append("沒有新增投入，數字全部來自投資本身（市值＋配息−利息）" if not invested
                else f'含新增投入 {invested:,.0f}（已排除，不當獲利）')
    if top:
        bits.append(f'最大來源：{top["c"]} <b>{_f(top["pnl"])}</b>（其中配息 {top["div"]:,.0f}）')
    if fout:
        bits.append(f'已排除賣出回流 {fout:,.0f}（若未排除會虛增虧損）')
    if fin:
        bits.append(f'已排除買進投入 {fin:,.0f}（若未排除會虛增獲利）')
    if not cur["interest_registered"]:
        bits.append("利息為暫估，尚未核實")
    return '<p class="verdict">' + "；".join(bits) + "。</p>"


def _cmp_row(label: str, a: str, b: str, cls: str = "") -> str:
    return f'<tr><th>{label}</th><td class="{cls}">{a}</td><td class="{cls}">{b}</td></tr>'


def _pct4(v) -> str:
    return f"{v * 100:+.4f}%" if v is not None else "—"


def _period_compare(prev_m: dict, cur_m: dict) -> str:
    """9 月（完整月）vs 10 月（MTD）同口徑比較；資料不足時明示不補。"""
    def rp(m):
        return _pct4(m.get("rate_price"))

    def rt(m):
        return _pct4(m.get("rate_total"))

    def twr_cell(m):
        t = (m.get("twr") or {}).get("twr")
        if t is not None and m.get("twr_reliable"):
            return f'{_pct(t)}（{m.get("twr_start") or ""}–{m.get("twr_end") or ""}）'
        why = (m.get("twr_reason") or "缺日估值").split("；")[0]
        why = (why.replace("（TWR ", "（").replace("（db 缺月初估值）", "，db 缺月初估值")
               .replace("TWR 僅涵蓋", "僅涵蓋"))
        return f'無法可靠計算（{why}）'

    def interest_cell(m):
        if m["interest_registered"]:
            return f'已扣利息 {m["interest"]:,.0f}（已登錄）'
        return (f'已扣利息 {m["interest_est"]:,.0f}（暫估）'
                if m["interest_est"] is not None else "利息未登錄")

    def quality_cell(m):
        bits = []
        bits.append("利息已登錄" if m["interest_registered"] else "利息暫估")
        bits.append("TWR 可算" if m.get("twr_reliable") else "TWR 缺")
        bits.append(f'資金流 {m.get("flow_count", 0)} 筆' if m.get("flow_count") else "無資金流")
        bits.append("手續費未登錄" if not m["fee"] else f'手續費 {m["fee"]:,.0f}')
        return "；".join(bits)

    def period_cell(m):
        if m["usable"] == pc.USE_COMPLETE:
            end = pc.month_bounds(m["month"])[1].isoformat()[5:].replace("-", "/")
            return f'{m["label"][5:]}/01–{end}（{m["days"]} 天，完整月）'
        end = (m.get("asof") or "")[5:]
        end = f'{end[:2]}/{end[3:]}' if "-" in end else end
        return f'{m["label"][5:]}/01–{end}（{m["days"]} 天，MTD）'

    rows = [
        _cmp_row("統計期間", period_cell(prev_m), period_cell(cur_m)),
        _cmp_row("未扣息投資損益", _f(prev_m["grand"]), _f(cur_m["grand"]),
                 _cls(cur_m["grand"])),
        _cmp_row("扣息後損益", f'{_f(prev_m["net_same_caliber"])}'
                 f'<br><span class="basis">{interest_cell(prev_m)}</span>',
                 f'{_f(cur_m["net_same_caliber"])}'
                 f'<br><span class="basis">{interest_cell(cur_m)}</span>',
                 _cls(cur_m["net_same_caliber"])),
        _cmp_row("純價格報酬", rp(prev_m), rp(cur_m), _cls(cur_m.get("rate_price"))),
        _cmp_row("含配息報酬", rt(prev_m), rt(cur_m), _cls(cur_m.get("rate_total"))),
        _cmp_row("TWR", twr_cell(prev_m), twr_cell(cur_m)),
        _cmp_row("配息實收", _f(prev_m["div"]), _f(cur_m["div"]), "up"),
        _cmp_row("資料品質", quality_cell(prev_m), quality_cell(cur_m)),
    ]
    # 一句話：只比「已標準化」的報酬率，不比金額
    tail = ""
    a, b_ = prev_m.get("rate_total"), cur_m.get("rate_total")
    if a is not None and b_ is not None:
        win = cur_m["label"] if b_ > a else prev_m["label"]
        tail = (f'<p class="verdict">以已標準化的報酬率比較：<b>{win}</b> 含息報酬較高'
                f'（{prev_m["label"]} {rt(prev_m)} vs {cur_m["label"]} {rt(cur_m)}）。'
                f'但 {cur_m["label"]} 為 MTD（{cur_m["days"]} 天）、'
                f'{"利息暫估" if not cur_m["interest_registered"] else "利息已登錄"}，'
                f'金額不可與完整月直接比。</p>')
    # 同期間比較：需要前期「月初到第 N 日」的每日估值
    gap_note = ""
    ps = prev_m.get("twr_start")
    if prev_m.get("twr_reliable") and ps and ps[8:] > "01":
        gap_note = f'{prev_m["label"]} 每日估值起於 {ps}，同期間比較可做'
    elif ps:
        import datetime as _d
        last_gap = (_d.date.fromisoformat(ps) - _d.timedelta(days=1)).isoformat()
        gap_note = (f'{prev_m["label"]} 每日估值起於 {ps}，'
                    f'缺 {prev_m["label"][5:]}/01–{last_gap[5:]} 每日估值 → '
                    f'<b>同期間比較資料不足，不補推估</b>')
    else:
        gap_note = f'{prev_m["label"]} 無每日估值 → <b>同期間比較資料不足</b>'
    return (f'<section class="card"><h2>◆ {prev_m["label"]} vs {cur_m["label"]}（同一口徑）</h2>'
            f'<table class="bt"><thead><tr><th>項目</th><th>{prev_m["label"]}</th>'
            f'<th>{cur_m["label"]}</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
            f'{tail}<p class="note">同期間比較（{prev_m["label"][5:]}/01–{prev_m["label"][5:]}/20 vs '
            f'{cur_m["label"][5:]}/01–{cur_m["label"][5:]}/20）：{gap_note}。</p></section>')


def _source_table(cur: dict) -> str:
    rows = "".join(
        f'<tr><th>{r["c"]}</th><td class="{_cls(r["mkt"])}">{_f(r["mkt"])}</td>'
        f'<td class="up">{_f(r["div"])}</td><td class="{_cls(r["pnl"])}">{_f(r["pnl"])}</td>'
        f'<td class="basis">{r["basis"]}</td></tr>'
        for r in cur["rows"])
    return (f'<table class="bt"><thead><tr><th>類別</th><th>市值變化</th><th>配息</th>'
            f'<th>損益</th><th>算法</th></tr></thead><tbody>{rows}</tbody></table>')


def _flow_table(cur: dict) -> str:
    items = []
    for r in cur["rows"]:
        for f in (r.get("flow_detail") or []):
            tag = "（日期推定）" if f.get("推定") else ""
            items.append((f.get("date", ""), r["c"], f.get("金額") or 0,
                          (f.get("來源") or "") + tag))
    if not items:
        return '<p class="empty">本月無已登錄資金流（買賣／申贖）；若有交易未登錄，市值變化會誤判為損益。</p>'
    rows = "".join(f'<tr><th>{d}　{c}</th><td class="{_cls(amt)}">{_f(amt)}</td>'
                   f'<td class="basis">{s}</td></tr>' for d, c, amt, s in items)
    return f'<table class="kv">{rows}</table>'


def _quality(cur: dict, asof_info: dict, extra: list[str]) -> str:
    ok = "up"
    items = [f'資料日 <b>{asof_info.get("newest") or "—"}</b>'
             f'（{len(asof_info.get("by_source") or {})} 個來源，'
             f'{"全部同步" if not asof_info.get("warnings") else "有落後"}）']
    items.append(f'資金流已登錄 <b>{cur.get("flow_count", 0)}</b> 筆'
                 + ("（金額可證實、部分日期推定）" if cur.get("flow_count") else ""))
    if cur["interest_registered"]:
        items.append("投資利息：已登錄")
    else:
        items.append(f"投資利息：<b>{cur['label']} 未登錄</b> → 以同口徑暫估，"
                     "「已扣息」數字為暫估值")
    if cur["fee"]:
        items.append(f'手續費：已登錄 {cur["fee"]:,.0f}')
    else:
        items.append("手續費：未登錄（視為 0，可能低估成本）")
    twr = (cur.get("twr") or {})
    items.append("TWR：" + ("可算（{segs} 段、缺 {gaps} 日）".format(
        segs=twr.get("segments", 0), gaps=twr.get("gaps", 0)) if cur.get("twr_reliable")
        else f'不可靠 → {cur.get("twr_reason") or "缺資料"}'))
    items += extra
    lis = "".join(f'<li>{i}</li>' for i in items)
    return f'<ul class="qlist">{lis}</ul>'


def _balance_snapshot(snap: dict) -> str:
    """資產／負債／淨值／現金：與投資報酬分開列示（不同口徑，不得相加比較）。"""
    def g(k):
        v = snap.get(k)
        return f"{v:,.0f}" if isinstance(v, (int, float)) else "—"
    return (f'<table class="kv">'
            f'<tr><th>總資產（含指定用途款）</th><td>{g("total_assets")}</td></tr>'
            f'<tr><th>總負債</th><td class="down">{g("total_liabilities")}</td></tr>'
            f'<tr><th>淨值</th><td class="{_cls(snap.get("net_worth"))}">{g("net_worth")}</td></tr>'
            f'<tr><th>可動用現金</th><td>{g("cash")}</td></tr>'
            f'</table><p class="note">此區為資產負債快照（時點值），'
            f'<b>不是投資報酬</b>；負債變動、質押撥款、房貸攤還都會改變淨值但不屬於投資績效。</p>')


def build(today: dt.date | None = None, out_path: Path | str | None = None) -> str:
    today = today or dt.date.today()
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    adjust = json.loads(ADJ.read_text(encoding="utf-8"))
    db = sqlite3.connect(DB)
    try:
        asof_info = pc.latest_asof(snap, db)
        asof = asof_info.get("asof") or today.isoformat()
        eff_today = dt.date.fromisoformat(asof)
        months_keys = sorted(k for k in adjust if len(k) == 7 and k[4] == "-")
        cur = eff_today.strftime("%Y-%m")
        if cur not in months_keys:
            months_keys.append(cur)
        h = pc.monthly_history(months_keys, snap=snap, adjust_all=adjust, db=db,
                               today=eff_today, asof=asof)
    finally:
        db.close()

    # 資產／負債快照（時點值，與績效分開）→ 一併進 payload，讓頁面數字可追溯、不寫死
    h["balance"] = {k: snap.get(k) for k in
                    ("total_assets", "total_liabilities", "net_worth", "cash")}
    months = h["months"]
    by_role = {}
    for m in months:
        by_role.setdefault(m["role"], []).append(m)
    baseline = next((m for m in months if m["role"] == pc.ROLE_CAPITAL_BASELINE), None)
    post = by_role.get(pc.ROLE_POST_BASELINE, [])
    refs = by_role.get(pc.ROLE_REFERENCE, [])
    legacies = by_role.get(pc.ROLE_LEGACY, [])
    post_acc = h["post_accum"]
    cur_m = next((m for m in months if m["usable"] == pc.USE_IN_PROGRESS), None)
    done = [m for m in months if m["usable"] == pc.USE_COMPLETE]

    # ── 基準後累計（只計完整基準後月份）──
    if post_acc["n"]:
        acc_txt = (f'基準後累計（{post_acc["start"]} 完成月起）：<b class="{_cls(post_acc["sum"])}">'
                   f'{_f(post_acc["sum"])}</b>｜平均 <b>{_f(post_acc["avg"])}</b>／月（{post_acc["n"]} 個月）')
    else:
        acc_txt = (f'<b>尚無完整基準後月份</b>（基準月 {h["baseline_month"] or "—"}；'
                   f'{"、".join(m["label"] for m in post) or "無"} 為 MTD，不列入累計）')

    baseline_txt = (f'{baseline["label"]}（{baseline["usable_label"]}）淨投資績效 '
                    f'<b class="{_cls(baseline["net"])}">{_f(baseline["net"])}</b>'
                    f'｜角色＝建立新資本基準，<b>不列入基準後累計</b>') if baseline else "未宣告基準月"

    prev_m = baseline or next((m for m in reversed(done)
                              if m["month"] != (cur_m or {}).get("month")), None)
    hero = _hero(cur_m, cur_m["mv_total0"] or 0, asof) if cur_m else '<p class="empty">本月無資料</p>'
    quality = _quality(cur_m, asof_info, []) if cur_m else ""
    flow_tbl = _flow_table(cur_m) if cur_m else ""
    src_tbl = _source_table(cur_m) if cur_m else ""

    body = f"""
<h1>📈 本月投資績效</h1>
<p class="sub">先看結論，再看拆解。口徑唯一計算層 <b>performance_core.py</b>；
產出 {dt.datetime.now():%Y-%m-%d %H:%M}</p>
{hero}
{_verdict(cur_m) if cur_m else ""}

{_period_compare(prev_m, cur_m) if (prev_m and cur_m) else ""}

<section class="card"><h2>◆ 損益來源（股票／基金／保單）</h2>
  {src_tbl}
  <p class="note">市值變化已扣掉「已登錄的買賣／申贖」：買進不算獲利、賣出不算虧損。
  配息為獨立列示，來自 Moneybook 入帳與配息紀錄。</p>
</section>

<section class="card"><h2>◆ 本月資金流（唯一可證實者才登錄）</h2>
  {flow_tbl}
</section>

<section class="card"><h2>◆ 資料完整度（決定數字能不能信）</h2>
  {quality}
</section>

<section class="card"><h2>◆ 資產／負債快照（與投資報酬分開）</h2>
  {_balance_snapshot(snap)}
</section>

<section class="card" data-zone="post"><h2>◆ 基準後累計</h2>
  <p class="note" style="margin:0 0 8px">{acc_txt}</p>
  {"".join(_month_card(m) for m in post) or '<div class="empty">目前無基準後完整月份</div>'}
</section>

<section class="card" data-zone="baseline"><h2>◆ 資本基準月</h2>
  <p class="note" style="margin:0 0 8px">{baseline_txt}</p>
  {_month_card(baseline) if baseline else ""}
</section>

<section class="card"><h2>◆ 歷史月份（完整月 → 可比較；MTD／不可比 → 僅參考）</h2>
  {"".join(_month_card(m) for m in done if m["role"] == pc.ROLE_POST_BASELINE) or '<div class="empty">目前只有 MTD，完整月份待月底結算</div>'}
  <details data-zone="ref"><summary>歷史參考區（不列入累計）｜7、8 月</summary>
  {"".join(_month_card(m) for m in (refs + legacies)) or "無"}</details>
</section>

<section class="card"><h2>◆ 月度趨勢</h2>
  {_trend(months)}
  <p class="note">長條＝該月淨投資績效；斜紋＝MTD；灰色＝不可比。不同資本基數月份不應直接比大小。</p>
</section>

<section class="card"><h2>◆ 資料（供閘門比對）</h2>
  <details><summary>展開 core 原始輸出</summary>
  <pre id="pm-data-json">{json.dumps(h, ensure_ascii=False, separators=(",", ":"))}</pre></details>
</section>
<script id="pm-data" type="application/json">{json.dumps(h, ensure_ascii=False, separators=(",", ":"))}</script>
"""
    html = PAGE.replace("__BODY__", body)
    target = Path(out_path) if out_path else OUT_HTML
    target.write_text(html, encoding="utf-8")
    return str(target)


PAGE = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>📈 龍九投資績效｜本月判讀</title>
<style>
:root{--bg:#0b1220;--card:#121c2e;--line:rgba(148,163,184,.18);--txt:#e2e8f0;--sub:#94a3b8;
--up:#16a34a;--down:#dc2626;--flat:#64748b;--amber:#f59e0b;--teal:#14b8a6}
*{box-sizing:border-box}
body{margin:0;padding:14px;background:var(--bg);color:var(--txt);
font-family:-apple-system,'PingFang TC','Microsoft JhengHei',sans-serif;font-size:14px;line-height:1.55}
.wrap{max-width:760px;margin:0 auto}
h1{font-size:19px;margin:2px 0 4px}
h2{font-size:15px;margin:0 0 10px;color:#cbd5e1}
.sub{color:var(--sub);font-size:11.5px;margin:0 0 14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin-bottom:12px}
.hero{background:linear-gradient(180deg,#132038 0%,#101a2b 100%);border-color:rgba(20,184,166,.35)}
.klabel{color:var(--sub);font-size:11.5px;margin-bottom:2px}
.kval{font-size:31px;font-weight:800;letter-spacing:-.6px;line-height:1.15}
.kval2{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}
.ksub{color:var(--sub);font-size:11px;margin-top:4px}
.kgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}
.kpi{background:#0f1829;border:1px solid var(--line);border-radius:10px;padding:10px}
.verdict{margin:0 0 12px;padding:10px 12px;border-left:3px solid var(--teal);
background:rgba(20,184,166,.08);border-radius:0 8px 8px 0;font-size:12.5px;color:#cbd5e1}
.qlist{margin:0;padding-left:18px;font-size:12px;color:#cbd5e1}
.qlist li{margin:4px 0}
.chip{display:inline-block;font-size:10.5px;padding:1px 7px;border-radius:999px;margin-left:5px;
border:1px solid var(--line);color:var(--sub)}
.chip-grey{color:#94a3b8}.chip-slate{color:#cbd5e1}.chip-amber{color:var(--amber);border-color:rgba(245,158,11,.45)}
.chip-teal{color:var(--teal);border-color:rgba(20,184,166,.45)}.chip-live{color:#f97316;border-color:rgba(249,115,22,.5)}
.mcard{border:1px solid var(--line);border-radius:10px;padding:10px;margin-bottom:10px;background:#0f1829}
.mhead{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:6px}
.mlabel{font-weight:700;font-size:15px}
.mnet{margin-left:auto;font-weight:800}
.up{color:var(--up)}.down{color:var(--down)}.flat{color:var(--flat)}
table.kv{width:100%;border-collapse:collapse}
table.kv th{text-align:left;font-weight:400;color:var(--sub);font-size:12.5px;padding:3px 0}
table.kv td{text-align:right;padding:3px 0;font-variant-numeric:tabular-nums;font-weight:600}
.bt{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}
.bt th{text-align:right;color:var(--sub);font-weight:500;padding:3px 4px;border-bottom:1px solid var(--line)}
.bt th:first-child,.bt td:first-child{text-align:left}
.bt td{text-align:right;padding:3px 4px;border-bottom:1px solid rgba(148,163,184,.08);
font-variant-numeric:tabular-nums}
.basis{color:#64748b;font-size:10.5px;text-align:right}
.note{color:var(--sub);font-size:11px;margin-top:8px}
.empty{color:var(--sub);font-size:12px}
details{margin-top:6px}summary{color:var(--sub);font-size:11.5px;cursor:pointer}
pre{white-space:pre-wrap;word-break:break-all;font-size:10px;color:#64748b}
</style></head><body><div class="wrap">
__BODY__
</div>
</body></html>
"""


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    path = build()
    log.info("✅ 已產出 %s", Path(path).name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
