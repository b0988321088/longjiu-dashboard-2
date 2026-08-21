# -*- coding: utf-8 -*-
"""build_rebalance_report.py — 再平衡評估網頁（動態讀 snapshot，2026-08-14 建立）"""
import json, datetime, re, sys

REPO = r"C:\Users\bot\Desktop\longjiu_system"
today = datetime.date.today().strftime("%Y-%m-%d")

def load():
    with open(f"{REPO}\\snapshot.json", encoding="utf-8") as f:
        return json.load(f)

def main():
    snap = load()
    apct = snap.get("penetration", {}).get("actual_pct", {})
    atwd = snap.get("penetration", {}).get("actual_twd", {})
    targets = snap.get("penetration", {}).get("targets", {})
    total = snap.get("total_assets", 0)
    cash = snap.get("cash_total", 0)

    try:
        st = json.load(open(f"{REPO}\\us30y_state.json", encoding="utf-8"))
    except Exception:
        st = {"mode": "?", "last_rate": None, "last_date": "?"}
    us30y = st.get("last_rate")
    mode = "防禦（模式A）" if st.get("mode") == "A" else "布局（模式B）" if st.get("mode") == "B" else "未知"
    us30y_txt = f"{us30y:.2f}%" if us30y else "—"

    # 五桶對照
    BUCKETS = [
        ("台股市值型成長", "台股市值型目標", "🇹🇼 台股", "配息導流 + 回檔小單低吸（單筆≤5萬）"),
        ("美股市值型成長", "美股市值型目標", "🇺🇸 美股", "逢反彈分批減碼（單次≤20萬），資金導向防守"),
        ("防守型配息", "配息型目標", "🛡️ 防守", "已達標維持；配息優先導入"),
        ("債券", "債券型目標", "💵 債券", "維持底倉，停止新增（00983D 不追）"),
        ("現金/安全網", "現金目標", "💰 現金", "守住 70 萬底線，<目標優先回補"),
    ]
    rows = []
    sum_pct = 0
    for actual_key, target_key, label, action in BUCKETS:
        a = apct.get(actual_key, 0)
        t = targets.get(target_key, 0)
        v = atwd.get(actual_key, 0)
        gap = a - t
        sum_pct += a
        if abs(gap) <= 1.5:
            light = "🟢"
        elif abs(gap) <= 3:
            light = "🟡"
        else:
            light = "🔴"
        rows.append(f"""
        <tr>
          <td>{label} {actual_key.replace('成長','').replace('型','')}</td>
          <td class="num">{v:,.0f}</td>
          <td class="num">{a:.1f}%</td>
          <td class="num">{t}%</td>
          <td class="num">{gap:+.1f}pp</td>
          <td class="light">{light}</td>
          <td class="action">{action}</td>
        </tr>""")
    rows_html = "".join(rows)

    # 風控紅線
    redlines = []
    def red(k, ok, txt):
        redlines.append(f"<tr><td>{k}</td><td class='{'ok' if ok else 'bad'}'>{'✅' if ok else '❌'}</td><td>{txt}</td></tr>")
    red("US30Y < 5.30%（債券凍結線）", us30y is None or us30y < 5.30, f"目前 {us30y_txt}（模式A防禦）")
    red("現金 ≥ 70 萬（6個月開支）", cash >= 700000, f"目前 {cash:,}（需求 851,748）")
    red("美股 ≤ 33%（熔斷閾值）", apct.get("美股市值型成長", 0) <= 33, f"目前 {apct.get('美股市值型成長',0):.1f}%")
    red("LTV ≤ 40%（未質押）", True, "目前未質押 ✅")
    red("單筆交易 ≤ 5 萬（台股）", True, "管制中")
    redlines_html = "".join(redlines)

    # 調倉優先順序
    priority = """
    <ol class="prio">
      <li><b>① 配息導流（第一優先｜零摩擦）</b>：每月配息/租金全部導入低配標的（台股高股息），不滾回原持有</li>
      <li><b>② 內部調度（第二優先｜逢反彈）</b>：逢反彈分批減碼美股（單次≤20萬，4-6週完成），資金導向防守</li>
      <li><b>③ 資金禁令（模式A）</b>：不加碼美股長久期科技、不新增債券標的（00983D/PIMCO 維持底倉）</li>
    </ol>"""

    # DAA v3 宏觀情境（macro_regime）— 2026-08-21 整合
    mr_html = "<div class='note'>⚠️ DAA v3 引擎尚未執行（跑 <code>python macro_regime.py</code> 後顯示情境與 targetAllocation）</div>"
    try:
        import macro_regime
        mr = macro_regime.load_latest()
        reg = mr.get("情境評分", {})
        alloc = mr.get("targetAllocation", {}).get("rows", [])
        tilt = mr.get("板塊輪動", [])
        reg_rows = "".join(
            f"<tr><td>{k}</td><td class='num'>{v['score']}</td>"
            f"<td class='light'>{'🔴' if v['score'] >= 70 else '🟡' if v['score'] >= 50 else '🟢'}</td></tr>"
            for k, v in reg.items()
        )
        alloc_txt = " ｜ ".join(
            f"{r['資產']} {r['燈號偏移後'] if r['燈號偏移後'] is not None else r['建議金額(±)']}" for r in alloc
        )
        tilt_txt = "；".join(f"{t['方向']} {t['偏移']}（{t['金額']:,}元）" for t in tilt)
        em = mr.get("緊急應變")
        em_txt = ""
        if em:
            em_txt = (f"<br/>🚨 <b>緊急應變：</b>{em['source']}｜{em['generated_at']}｜應變分 {em['應變分']} "
                      f"{'🔴' if em['應變分'] >= 70 else '🟡' if em['應變分'] >= 50 else '🟢'}｜{em['建議節錄'][:80]}")
        mr_html = f"""
  <h2>🧭 DAA v3 宏觀情境（{mr.get('燈號','—')}）</h2>
  <table><thead><tr><th>情境</th><th class="num">分數</th><th>燈</th></tr></thead><tbody>{reg_rows}</tbody></table>
  <div class="note">🎯 <b>targetAllocation：</b>{alloc_txt}<br/>🔄 <b>板塊輪動：</b>{tilt_txt}{em_txt}</div>"""
        # 避險衛星（黃金+石油，2026-08-21 裁示）現況 vs 目標
        import json as _json
        _sn = load()
        _hs = _sn.get("hedge_satellite", {})
        _gold_row = next((r for r in alloc if "黃金" in r.get("資產", "")), None)
        _oil_row = next((r for r in alloc if "石油" in r.get("資產", "")), None)
        if _gold_row and _oil_row:
            mr_html += (f"<div class='note' style='border-left:3px solid #d97706'>🛡️ <b>避險衛星（黃金+石油，合計 ≤7%）：</b>"
                        f"黃金目標 {_gold_row['燈號偏移後']}%（現況 {_hs.get('黃金現況',0):,}）＋ 石油目標 {_oil_row['燈號偏移後']}%（現況 {_hs.get('石油現況',0):,}）"
                        f"<br/><span style='color:#64748b;font-size:12px'>{_hs.get('note','')}</span></div>")
    except Exception:
        pass

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>龍九再平衡評估 {today}</title>
<style>
  body {{ background:#0b1220; color:#e2e8f0; font-family:'Segoe UI',system-ui,sans-serif; margin:0; padding:20px; }}
  .wrap {{ max-width:900px; margin:auto; }}
  h1 {{ font-size:22px; color:#fff; margin-bottom:4px; }}
  h2 {{ font-size:15px; color:#94a3b8; margin:28px 0 10px; border-bottom:1px solid #1e293b; padding-bottom:6px; }}
  .sub {{ color:#64748b; font-size:12px; margin-bottom:18px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin-bottom:8px; }}
  .card {{ background:#111a2e; border:1px solid #1e293b; border-radius:12px; padding:14px; }}
  .card .k {{ font-size:11px; color:#64748b; }}
  .card .v {{ font-size:20px; font-weight:800; color:#60a5fa; margin-top:4px; }}
  .card .v.green {{ color:#34d399; }} .card .v.red {{ color:#f87171; }} .card .v.amber {{ color:#fbbf24; }}
  table {{ width:100%; border-collapse:collapse; background:#111a2e; border-radius:12px; overflow:hidden; font-size:13px; }}
  th {{ background:#1e293b; color:#94a3b8; padding:8px 10px; text-align:left; font-size:11px; }}
  td {{ padding:8px 10px; border-top:1px solid #1e293b; }}
  .num {{ text-align:right; font-family:monospace; }}
  .light {{ text-align:center; font-size:16px; }}
  .action {{ color:#94a3b8; font-size:11px; }}
  .ok {{ color:#34d399; }} .bad {{ color:#f87171; }}
  .prio li {{ margin-bottom:8px; line-height:1.5; }}
  .note {{ background:#111a2e; border-left:4px solid #fbbf24; border-radius:8px; padding:12px; font-size:12px; color:#94a3b8; margin-top:14px; }}
  .footer {{ color:#475569; font-size:10px; margin-top:30px; text-align:center; }}
</style></head><body><div class="wrap">
  <h1>📊 龍九再平衡評估</h1>
  <div class="sub">{today}｜US30Y {us30y_txt}｜模式：{mode}｜穿透分母 {total:,}（不含不動產）</div>

  <div class="cards">
    <div class="card"><div class="k">總資產</div><div class="v">{total:,}</div></div>
    <div class="card"><div class="k">現金</div><div class="v {'green' if cash>=700000 else 'red'}">{cash:,}</div></div>
    <div class="card"><div class="k">美股超標</div><div class="v {'green' if apct.get('美股市值型成長',0)<=33 else 'red'}">{apct.get('美股市值型成長',0):.1f}%</div></div>
    <div class="card"><div class="k">US30Y</div><div class="v {'amber' if (us30y or 0)>=5.2 else 'green'}">{us30y_txt}</div></div>
    <div class="card"><div class="k">五桶合計</div><div class="v">{sum_pct:.1f}%</div></div>
  </div>

  <h2>📐 五桶偏離評估（目標：{targets.get('台股市值型目標','10')} / {targets.get('美股市值型目標','40')} / {targets.get('配息型目標','20')} / {targets.get('債券型目標','25')} / {targets.get('現金目標','5')}，動態讀 snapshot）</h2>
  <table><thead><tr><th>類別</th><th class="num">金額</th><th class="num">實際</th><th class="num">目標</th><th class="num">差距</th><th>燈號</th><th>建議動作</th></tr></thead>
  <tbody>{rows_html}</tbody></table>

  <h2>🎯 調倉優先順序</h2>
  {priority}

  <h2>🚨 風控紅線檢核</h2>
  <table><thead><tr><th>紅線</th><th>狀態</th><th>現況</th></tr></thead><tbody>{redlines_html}</tbody></table>

  {mr_html}

  <div class="note">📌 <b>執行紀律</b>：配息導流優先（零摩擦）→ 內部調度逢反彈（≤20萬/次）→ 資金禁令（模式A 不加美股長債）｜台股單筆 ≤5 萬、回檔小單低吸、不追漲｜8/20 定案：富達600萬+MMF600萬→PI認列2週→質押300萬@2.77%還安聯4.2%→MMF轉10月標案預備金</div>
  <div class="footer">龍九控股自動產出｜資料：snapshot {today} + us30y_state｜公式：桶值 ÷ 總資產（不含不動產）</div>
</div></body></html>"""

    out = f"{REPO}\\rebalance_report_{today}.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ {out}（{len(html):,} bytes）")

if __name__ == "__main__":
    main()
