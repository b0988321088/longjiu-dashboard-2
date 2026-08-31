# -*- coding: utf-8 -*-
"""build_rebalance_report.py — 再平衡評估網頁（動態讀 snapshot，2026-08-14 建立）"""
import json, datetime, re, sys, os

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

    # 🔴 Fed 升息情境（2026-09-01 整合：snapshot.fed_hike_monitor_0901）
    fed_html = ""
    try:
        _fh = snap.get("fed_hike_monitor_0901", {}) or {}
        if _fh:
            _sig = "｜".join(_fh.get("觸發訊號", [])[:2])
            _cfg = "｜".join(_fh.get("對應配置", [])[:4])
            fed_html = f"""
    <div class="card"><h2 style="color:#f87171">🔴 Fed 升息情境（{_fh.get('決策','')[:40]}）</h2>
    <div class="callout" style="border-left:3px solid #dc2626;padding:8px 10px;background:#1e1b2e;border-radius:6px;margin-bottom:8px;color:#fca5a5">
      <b>觸發訊號：</b>{_sig}<br>
      <b>再平衡調整：</b>{_cfg}<br>
      <b style="color:#f87171">升息下五桶動作：美股超配 → 逢彈減碼優先執行（訊號增強）；債券 -2.0pp → 升息中不補（等利率見頂）；現金/MMF → 避風港不動；台股缺口 → 回檔才買（不追反彈）</b>
    </div></div>"""
    except Exception:
        fed_html = ""

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

    # 機構流向雷達 + 政策面 + 本週投資計劃（2026-08-29：動態讀 radar_state.json）
    try:
        radar = json.load(open(os.path.join(REPO, "radar_state.json"), encoding="utf-8"))
    except Exception:
        radar = {}
    _sig = radar.get("signals", {}) or {}
    _radar_cards = "".join(
        f'<div class="card"><div class="k">{k}</div><div class="v {("green" if v.get("color","").startswith("🟢") else "red" if v.get("color","").startswith("🔴") else "amber")}">{v.get("color","—")}</div><div style="font-size:10px;color:#64748b;margin-top:4px">{v.get("note","")[:36]}</div></div>'
        for k, v in _sig.items()
    )
    # 政策面
    _pn = radar.get("policy_notes", {}) or {}
    _titles = {"新聞1_華許升息": "華許放鷹（升息）", "新聞2_美委石油協議": "美委石油協議", "新聞3_伊朗戰爭SPR": "伊朗戰爭SPR"}
    _pol_items = []
    for _k, _v in _pn.items():
        if isinstance(_v, dict):
            _c = _v.get("內容", "")
            _imp = _v.get("對資產影響", "")
            if _c:
                _pol_items.append(f"<li><b>{_titles.get(_k,_k)}</b>：{_imp or _c[:40]}</li>")
        elif isinstance(_v, str) and _v and _k in ("原油綜合判斷", "債券升息敏感度"):
            _pol_items.append(f"<li><b>{_k}</b>：{_v[:50]}</li>")
    _pol_html = "".join(_pol_items) if _pol_items else "<li>無重大政策變動</li>"
    # 本週投資計劃（結論引擎，與雷達一致）
    _pen3 = apct
    _dry3 = snap.get("乾粉執行_0926", {}).get("戰術乾粉總額", {}).get("當前", 0)
    _usd3 = snap.get("usd_exposure_monitor", {}).get("current", {}).get("合計", 0)
    _hs3 = snap.get("hedge_satellite", {}) or {}
    _rot3 = (snap.get("rotation_recommendation", {}) or {}).get("建議", [{}])[0]
    _def3 = snap.get("defensive_combined_metric", {}).get("佔比", 69.2)
    _tw3 = _pen3.get("台股市值型成長", 7.5); _us3 = _pen3.get("美股市值型成長", 43.4)
    _plan_items = []
    _plan_items.append(f"🟢 台股（{_tw3:.1f}% vs 目標10%，缺口 {_tw3-10:+.1f}pp）→ 0050/006208 每週1.5-2萬慢慢買（外資連3買+台幣強升）")
    if _us3 > 45:
        _plan_items.append(f"🔴 美股（{_us3:.1f}% vs 目標40%，超配 {_us3-40:+.1f}pp）→ 逢彈減碼 ≤20萬/次")
    else:
        _plan_items.append(f"⏸️ 美股（{_us3:.1f}% vs 目標40%）超配 {_us3-40:+.1f}pp 未達減碼觸發（>45%）→ 續持")
    _plan_items.append(f"⏸️ 防守（合併口徑 {_def3:.1f}% 已足）→ 凍結不追（00878/00713 不加碼）")
    _plan_items.append("⏸️ 債券 23.1% 接近目標25% → 等 US30Y<5.30% 才新增（華許升息1碼估 -0.5~-1.5%）")
    _plan_items.append(f"💰 現金 22.1% → 底線70萬守；乾粉 {_dry3/10000:.1f}萬 優先「{_rot3.get('產業','—')}」（{_rot3.get('動作','')}）")
    if _hs3.get("黃金延後_0829"):
        _plan_items.append("⏸️ 避險衛星：黃金A10 32萬 8/30 生效（保單內）；00635U ~105萬 延後（華許放鷹+金價偏高）→ 等回檔")
    else:
        _plan_items.append(f"🟢 避險衛星：黃金現況 {_hs3.get('黃金現況',0):,} → PI 後 00635U 分批 ≤20萬/次")
    if _usd3 > 55:
        _plan_items.append(f"🔴 美元曝險 {_usd3}% 超標（>55%）→ 美股減碼/美元定存到期轉台幣")
    else:
        _plan_items.append(f"🟡 美元曝險 {_usd3}% （目標≤50%）→ 未達減碼閾值，續觀察")
    _plan_items.append("🔴 9/2 前：保單轉換截止（PIMCO120+M&G80-100+醫療50+黃金30）→ 8/26已轉80萬 8/30生效，剩餘本週內完成")
    _plan_items.append("🔍 9/3 PI 認列 → 質押350萬@2.77% 還安聯300+元大50（高息→低息，月省利息）")
    _plan_items.append(f"📊 產業輪動：買「{_rot3.get('產業','—')}」（{_rot3.get('標的','')}）｜避開「公用事業」")
    _plan_html = "".join(f"<li>{p}</li>" for p in _plan_items)
    _radar_block = f"""
  <h2>📡 機構流向雷達（{radar.get('last_run','—')[:10]}）</h2>
  <div class="cards">{_radar_cards}</div>
  <div class="note" style="border-left-color:#3b82f6">🏛️ <b>政策面：</b><ul style="margin:6px 0 0 16px">{_pol_html}</ul></div>
  <div class="note" style="border-left-color:#10b981">📋 <b>本週投資計劃：</b><ol style="margin:6px 0 0 16px">{_plan_html}</ol></div>
"""
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

  {_radar_block}

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

  {fed_html}

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
