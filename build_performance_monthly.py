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
    out.append(("報酬率", _pct(m["rate"]), _cls(m["rate"])))
    if m["usable"] == pc.USE_COMPLETE:
        out.append(("日均（÷%d 天）" % m["days"], _f(m["net_per_day"]), _cls(m["net_per_day"])))
    elif m["usable"] == pc.USE_IN_PROGRESS:
        out.append(("期間", f"{m['label']}/01 起 {m['days']} 天（進行中）", "flat"))
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


def build(today: dt.date | None = None, out_path: Path | str | None = None) -> str:
    today = today or dt.date.today()
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    adjust = json.loads(ADJ.read_text(encoding="utf-8"))
    db = sqlite3.connect(DB)
    try:
        months_keys = sorted(k for k in adjust if len(k) == 7 and k[4] == "-")
        cur = today.strftime("%Y-%m")
        if cur not in months_keys:
            months_keys.append(cur)
        h = pc.monthly_history(months_keys, snap=snap, adjust_all=adjust, db=db, today=today)
    finally:
        db.close()

    months = h["months"]
    by_role = {}
    for m in months:
        by_role.setdefault(m["role"], []).append(m)
    baseline = next((m for m in months if m["role"] == pc.ROLE_CAPITAL_BASELINE), None)
    post = by_role.get(pc.ROLE_POST_BASELINE, [])
    refs = by_role.get(pc.ROLE_REFERENCE, [])
    legacies = by_role.get(pc.ROLE_LEGACY, [])
    post_acc = h["post_accum"]

    # ── 基準後累計（只計完整基準後月份）──
    if post_acc["n"]:
        acc_txt = (f'基準後累計（{post_acc["start"]} 完成月起）：<b class="{_cls(post_acc["sum"])}">'
                   f'{_f(post_acc["sum"])}</b>｜完整基準後月份平均：'
                   f'<b>{_f(post_acc["avg"])}</b>／月（{post_acc["n"]} 個月）')
    else:
        acc_txt = (f'基準後累計：<b>尚無完整基準後月份</b>'
                   f'（基準月 {h["baseline_month"] or "—"}；'
                   f'{"、".join(m["label"] for m in post) or "無"} 進行中，不列入累計）')

    baseline_txt = (f'{baseline["label"]}（{baseline["usable_label"]}）淨投資績效 '
                    f'<b class="{_cls(baseline["net"])}">{_f(baseline["net"])}</b>'
                    f'｜角色＝建立新資本基準，<b>不列入基準後累計</b>') if baseline else "未宣告基準月"

    html = PAGE.format(
        ts=f"{dt.datetime.now():%Y-%m-%d %H:%M}",
        baseline_txt=baseline_txt,
        acc_txt=acc_txt,
        baseline_card=_month_card(baseline) if baseline else "",
        post_cards="".join(_month_card(m) for m in post) or '<div class="empty">目前無基準後月份</div>',
        ref_cards="".join(_month_card(m) for m in (refs + legacies)) or '<div class="empty">無</div>',
        breakdown=_class_breakdown(months),
        trend=_trend(months),
        payload=json.dumps(h, ensure_ascii=False, separators=(",", ":")),
        n_months=len(months),
    )
    target = Path(out_path) if out_path else OUT_HTML
    target.write_text(html, encoding="utf-8")
    return str(target)


PAGE = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>📈 龍九投資績效｜月度比較</title>
<style>
:root{{--bg:#0b1220;--card:#121c2e;--line:rgba(148,163,184,.18);--txt:#e2e8f0;--sub:#94a3b8;
--up:#16a34a;--down:#dc2626;--flat:#64748b;--amber:#f59e0b;--teal:#14b8a6}}
*{{box-sizing:border-box}}
body{{margin:0;padding:14px;background:var(--bg);color:var(--txt);
font-family:-apple-system,'PingFang TC','Microsoft JhengHei',sans-serif;font-size:14px;line-height:1.55}}
.wrap{{max-width:760px;margin:0 auto}}
h1{{font-size:19px;margin:2px 0 4px}}
h2{{font-size:15px;margin:0 0 10px;color:#cbd5e1}}
.sub{{color:var(--sub);font-size:11.5px;margin:0 0 14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin-bottom:12px}}
.chip{{display:inline-block;font-size:10.5px;padding:1px 7px;border-radius:999px;margin-left:5px;
border:1px solid var(--line);color:var(--sub)}}
.chip-grey{{color:#94a3b8}}.chip-slate{{color:#cbd5e1}}.chip-amber{{color:var(--amber);border-color:rgba(245,158,11,.45)}}
.chip-teal{{color:var(--teal);border-color:rgba(20,184,166,.45)}}.chip-live{{color:#f97316;border-color:rgba(249,115,22,.5)}}
.mcard{{border:1px solid var(--line);border-radius:10px;padding:10px;margin-bottom:10px;background:#0f1829}}
.mhead{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:6px}}
.mlabel{{font-weight:700;font-size:15px}}
.mnet{{margin-left:auto;font-weight:800}}
.up{{color:var(--up)}}.down{{color:var(--down)}}.flat{{color:var(--flat)}}
table.kv{{width:100%;border-collapse:collapse}}
table.kv th{{text-align:left;font-weight:400;color:var(--sub);font-size:12.5px;padding:3px 0}}
table.kv td{{text-align:right;padding:3px 0;font-variant-numeric:tabular-nums;font-weight:600}}
.bt{{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}}
.bt th{{text-align:right;color:var(--sub);font-weight:500;padding:3px 4px;border-bottom:1px solid var(--line)}}
.bt th:first-child,.bt td:first-child{{text-align:left}}
.bt td{{text-align:right;padding:3px 4px;border-bottom:1px solid rgba(148,163,184,.08);
font-variant-numeric:tabular-nums}}
.basis{{color:#64748b;font-size:10.5px}}
.bgroup{{margin-bottom:10px}}.btitle{{font-weight:700;font-size:13.5px}}
.trow{{display:flex;align-items:center;gap:8px;margin:5px 0}}
.tlbl{{width:62px;color:var(--sub);font-size:12px}}
.tbarwrap{{flex:1;background:rgba(148,163,184,.12);border-radius:5px;height:14px;overflow:hidden}}
.tbar{{display:block;height:100%;border-radius:5px}}
.tbar.chip-grey{{background:#475569}}.tbar.chip-slate{{background:#64748b}}
.tbar.chip-amber{{background:var(--amber)}}.tbar.chip-teal{{background:var(--teal)}}
.tbar.live{{background:repeating-linear-gradient(45deg,#f97316,#f97316 5px,#7c2d12 5px,#7c2d12 10px)}}
.tval{{width:96px;text-align:right;font-variant-numeric:tabular-nums;font-weight:600}}
.note{{color:var(--sub);font-size:11px;margin-top:8px}}
.empty{{color:var(--sub);font-size:12px}}
details{{margin-top:6px}}summary{{color:var(--sub);font-size:11.5px;cursor:pointer}}
pre{{white-space:pre-wrap;word-break:break-all;font-size:10px;color:#64748b}}
</style></head><body><div class="wrap">
<h1>📈 投資績效｜月度比較</h1>
<p class="sub">口徑：Σ市值變化 ＋ Σ配息實收 − Σ投資利息 − Σ手續費｜唯一計算層 <b>performance_core.py</b>
（本頁 {n_months} 個月；產出 {ts}）</p>

<section class="card"><h2>◆ 資本基準月</h2>
  <p class="note" style="margin:0 0 8px">{baseline_txt}</p>
  {baseline_card}
</section>

<section class="card"><h2>◆ 基準後累計</h2>
  <p class="note" style="margin:0 0 8px">{acc_txt}</p>
  {post_cards}
</section>

<section class="card"><h2>◆ 歷史參考區（不列入累計）</h2>
  {ref_cards}
  <p class="note">7 月＝Baseline／不可比（市值不可靠，僅現金型）；8 月＝歷史參考月（9 月底資金到位前，資本基數不同）。
  兩者僅供回顧，不得與基準後月份混算。</p>
</section>

<section class="card"><h2>◆ 損益來源（類別拆解）</h2>
  {breakdown}
  <p class="note">來源：校正檔指定＝校正檔登錄之市值變化；推導＝帳面變化 − 新增投入 − 估值更新；
  無月初基準＝不計（不得視為 0 報酬）。</p>
</section>

<section class="card"><h2>◆ 月度趨勢</h2>
  {trend}
  <p class="note">長條長度＝該月淨投資績效（相對最大者）。斜紋＝進行中月份；灰色＝不可比月份。</p>
</section>

<section class="card"><h2>◆ 資料（供閘門比對）</h2>
  <details><summary>展開 core 原始輸出</summary>
  <pre id="pm-data-json">{payload}</pre></details>
</section>
</div>
<script id="pm-data" type="application/json">{payload}</script>
</body></html>
"""


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    path = build()
    log.info("✅ 已產出 %s", Path(path).name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
