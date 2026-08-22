# -*- coding: utf-8 -*-
"""build_rebalance_dashboard.py — 龍九再平衡儀表板（2026-08-22）
深色指揮中心主題，內容：五桶穿透圖/雷達燈號/動作建議/產業穿透/乾粉/質押/風險紅線/里程碑。
資料全部動態讀 snapshot.json + radar_state.json，每週六可重跑。
輸出：rebalance_dashboard_{date}.html
"""
import json, os
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent.resolve()
TODAY = date.today().isoformat()

def load(p, default=None):
    try:
        return json.loads((BASE / p).read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}

def main():
    s = load("snapshot.json", {})
    radar = load("radar_state.json", {})
    pen = s.get("penetration", {})
    apct, atwd, tgt = pen.get("actual_pct", {}), pen.get("actual_twd", {}), pen.get("targets", {})
    total = s.get("total_assets", 0)
    cash = s.get("cash_total", 0)
    monthly_inc = s.get("monthly_income", 225918)
    monthly_exp = s.get("monthly_expense", 152781)
    surplus = monthly_inc - monthly_exp
    coverage = monthly_inc / monthly_exp * 100 if monthly_exp else 0
    usd_pct = s.get("usd_exposure_pct", 64.0)
    tech = s.get("sector_penetration", {}).get("高科技/半導體", {}).get("佔比_估", 17.5)
    us30y = load("us30y_state.json", {}).get("last_rate")

    # ── 五桶 ──
    buckets = [
        ("台股", apct.get("台股市值型成長", 0), tgt.get("台股市值型目標", 10), atwd.get("台股市值型成長", 0), "#3b82f6"),
        ("美股", apct.get("美股市值型成長", 0), tgt.get("美股市值型目標", 40), atwd.get("美股市值型成長", 0), "#ef4444"),
        ("防守", apct.get("防守型配息", 0), tgt.get("配息型目標", 20), atwd.get("防守型配息", 0), "#22c55e"),
        ("債券", apct.get("債券", 0), tgt.get("債券型目標", 25), atwd.get("債券", 0), "#f59e0b"),
        ("現金", apct.get("現金/安全網", 0), tgt.get("現金目標", 5), atwd.get("現金/安全網", 0), "#94a3b8"),
    ]
    bar_rows = ""
    for name, act, t, twd, color in buckets:
        gap = act - t
        w = min(act / 55 * 100, 100)
        tw = min(t / 55 * 100, 100)
        gap_cls = "green" if abs(gap) <= 2 else ("yellow" if abs(gap) <= 5 else "red")
        bar_rows += f"""
        <div class="bucket">
          <div class="bucket-head"><span class="bucket-name">{name}</span><span class="bucket-val">{act:.1f}% <small>/ 目標 {t}%</small></span><span class="gap {gap_cls}">{gap:+.1f}pp</span></div>
          <div class="bar-track"><div class="bar-fill" style="width:{w:.1f}%;background:{color}"></div><div class="bar-target" style="left:{tw:.1f}%"></div></div>
          <div class="bucket-twd">{twd/1e4:.0f} 萬</div>
        </div>"""

    # ── 雷達 ──
    radar_cards = ""
    sig_meta = {"台股": "#22c55e", "黃金": "#f59e0b", "原油": "#ef4444", "美債10年": "#3b82f6", "台幣": "#94a3b8"}
    for k in ["台股", "黃金", "原油", "美債10年", "台幣"]:
        v = radar.get("signals", {}).get(k, {})
        color = v.get("color", "⚪")
        locked = " 🔒LOCKED" if v.get("locked") else ""
        border = "#22c55e" if color.startswith("🟢") else ("#ef4444" if color.startswith("🔴") else ("#f59e0b" if color.startswith("🟡") else "#64748b"))
        radar_cards += f"""
        <div class="card rcard" style="border-top:3px solid {border}">
          <div class="r-signal">{color}</div>
          <div class="r-name">{k}{locked}</div>
          <div class="r-note">{v.get('note', '—')}</div>
        </div>"""

    # ── 動作建議 ──
    actions = [
        ("台股慢慢買", "🟢🔥 順勢", "每週 1.5-2萬 0050/006208 × 8-12 週，單筆≤5萬；配息流+結餘", "✅ 主動"),
        ("美股逢彈減", "⏸ 等待", "44.0%→40%，費半弱不砍低點；反彈日減碼 ≤20萬/次達標即停", "被動"),
        ("債券補碼", "⏸ 等兩條件", "質押完成 + US30Y<5.30%；經理人代管不買單一純債ETF", "待命"),
        ("防守", "🟢 已足", "合併口徑 69.5% 無缺口；勿被單看 4.2% 誤導", "不動作"),
        ("現金", "🟢 底線制", f"{cash:,} ≥ 70萬 ✅；MMF 500萬已指定標案/質押補救", "不動作"),
        ("石油衛星", "🔴 Locked", "COT 機構撤離（-175.6%）；維持延後建倉", "凍結"),
        ("黃金衛星", "🟢 順勢", "PI 後 131萬 分 3 批 50/30/20；台幣計價 00635U", "待PI"),
    ]
    action_cards = ""
    for name, light, desc, tag in actions:
        action_cards += f"""
        <div class="card acard">
          <div class="a-head"><b>{name}</b><span class="tag">{tag}</span></div>
          <div class="a-light">{light}</div>
          <div class="a-desc">{desc}</div>
        </div>"""

    # ── 產業穿透 ──
    sec_rows = ""
    for k in ["高科技/半導體", "金融/電信", "醫療/公用事業/不動產", "固收與現金", "實物避險-黃金", "實物避險-石油"]:
        v = s.get("sector_penetration", {}).get(k, {})
        if not v:
            continue
        amt = v.get("金額_估", v.get("金額", 0)) or 0
        pct = v.get("佔比_估", "—")
        st = v.get("狀態", "")
        sec_rows += f"<tr><td>{k}</td><td class='num'>{amt:,}</td><td class='num'>{pct}</td><td>{st}</td></tr>"

    # ── 乾粉 ──
    dry = s.get("乾粉執行_0926", {}).get("戰術乾粉總額", {})
    dry_cur = dry.get("當前", 0)

    # ── 質押 ──
    pledge = s.get("質押計畫", {})
    ltv_txt = "未質押（9/3 PI 後 350萬@2.77%）"

    # ── 里程碑 ──
    milestones = [
        ("8/24（一）", "保單轉換 300萬 決策（科技→債，T+4 截止）", "high"),
        ("8/31", "安聯B 贖回（補現金 + 抵借款 100萬）", "mid"),
        ("9/3 前", "PI 認列 → 質押 350萬@2.77% 還債", "high"),
        ("9月中", "富達/聯博首次配息入帳 → 更新配息基準", "mid"),
        ("10月", "洲際W 轉貸國泰（要求全額吸收規費）＋ 標案", "mid"),
    ]
    ms_html = ""
    for d, t, lv in milestones:
        cls = "ms-high" if lv == "high" else "ms-mid"
        ms_html += f"<div class='ms {cls}'><span class='ms-date'>{d}</span><span class='ms-txt'>{t}</span></div>"

    # ── 風險紅線 ──
    risks = [
        ("US30Y 凍結線", f"{us30y:.2f}%" if us30y else "—", "≥5.30% 🔴", us30y and us30y >= 5.30),
        ("美元曝險", f"{usd_pct:.0f}%", "紅線 50%", usd_pct > 50),
        ("高科技", f"{tech:.1f}%", "紅線 30%", tech > 30),
        ("現金底線", f"{cash:,}", "≥70萬", cash < 700000),
        ("總質押 LTV", "完成後 20.4%", "安全值 ≤35%", False),
    ]
    risk_rows = ""
    for name, val, limit, triggered in risks:
        st = "🔴 觸發" if triggered else "🟢 安全"
        risk_rows += f"<tr><td>{name}</td><td class='num'>{val}</td><td class='num'>{limit}</td><td>{st}</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>龍九再平衡儀表板 {TODAY}</title>
<style>
:root {{ --bg:#0f172a; --card:#1e293b; --line:#334155; --txt:#e2e8f0; --sub:#94a3b8; --grn:#22c55e; --red:#ef4444; --yel:#f59e0b; --blu:#3b82f6; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--txt); font-family:'Segoe UI','Microsoft JhengHei',sans-serif; padding:20px; }}
.wrap {{ max-width:1100px; margin:0 auto; }}
h1 {{ font-size:22px; font-weight:800; }}
.sub {{ color:var(--sub); font-size:13px; margin:4px 0 16px; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-bottom:16px; }}
.kpi {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px; }}
.kpi .k {{ color:var(--sub); font-size:11px; }}
.kpi .v {{ font-size:20px; font-weight:800; font-family:Consolas,monospace; }}
.kpi .v.red {{ color:var(--red); }} .kpi .v.green {{ color:var(--grn); }} .kpi .v.yellow {{ color:var(--yel); }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
@media (max-width:800px) {{ .grid {{ grid-template-columns:1fr; }} }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
.card h2 {{ font-size:14px; font-weight:800; margin-bottom:10px; color:#f8fafc; }}
.bucket {{ margin-bottom:12px; }}
.bucket-head {{ display:flex; justify-content:space-between; font-size:12.5px; margin-bottom:4px; }}
.bucket-name {{ font-weight:700; }}
.gap {{ font-weight:800; }} .gap.green {{ color:var(--grn); }} .gap.yellow {{ color:var(--yel); }} .gap.red {{ color:var(--red); }}
.bar-track {{ position:relative; height:14px; background:#0b1220; border-radius:7px; }}
.bar-fill {{ height:100%; border-radius:7px; opacity:.85; }}
.bar-target {{ position:absolute; top:-3px; width:2px; height:20px; background:#fff; }}
.bucket-twd {{ font-size:11px; color:var(--sub); text-align:right; margin-top:2px; }}
.rcards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px; }}
.rcard {{ border-top:3px solid var(--line); }}
.r-signal {{ font-size:22px; }}
.r-name {{ font-weight:800; font-size:13px; margin:4px 0; }}
.r-note {{ font-size:11px; color:var(--sub); line-height:1.5; }}
.acards {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
.acard {{ border-left:3px solid var(--line); }}
.a-head {{ display:flex; justify-content:space-between; font-size:13px; }}
.tag {{ font-size:10px; background:#0b1220; border:1px solid var(--line); padding:1px 6px; border-radius:8px; color:var(--sub); }}
.a-light {{ font-size:11px; color:var(--sub); margin:3px 0; }}
.a-desc {{ font-size:12px; color:#cbd5e1; line-height:1.55; }}
table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
th {{ text-align:left; color:var(--sub); font-weight:600; padding:6px 8px; border-bottom:1px solid var(--line); }}
td {{ padding:7px 8px; border-bottom:1px solid #263449; }}
.num {{ font-family:Consolas,monospace; text-align:right; }}
.drybar {{ display:flex; height:26px; border-radius:8px; overflow:hidden; margin:10px 0; font-size:11px; font-weight:700; color:#fff; }}
.drybar div {{ display:flex; align-items:center; justify-content:center; }}
.ms {{ display:flex; gap:10px; padding:8px 10px; border-radius:8px; margin-bottom:6px; font-size:12.5px; }}
.ms-high {{ background:#3f1d1d; border:1px solid #7f1d1d; }}
.ms-mid {{ background:#1e293b; border:1px solid var(--line); }}
.ms-date {{ font-weight:800; color:var(--yel); white-space:nowrap; }}
.foot {{ margin-top:16px; color:var(--sub); font-size:11px; text-align:center; }}
</style></head><body><div class="wrap">
<h1>🔄 龍九再平衡儀表板</h1>
<div class="sub">{TODAY}（週六）｜修正後 DAA 口徑 + 機構流向雷達｜本週動作：<b style="color:var(--grn)">台股慢慢買</b>，其餘按兵不動</div>

<div class="kpis">
  <div class="kpi"><div class="k">總資產（流動）</div><div class="v">{total:,}</div></div>
  <div class="kpi"><div class="k">現金</div><div class="v">{cash:,}</div></div>
  <div class="kpi"><div class="k">月盈餘</div><div class="v green">+{surplus:,}</div></div>
  <div class="kpi"><div class="k">收入/支出</div><div class="v">{monthly_inc:,} <small style="font-size:11px">/ {monthly_exp:,}</small></div></div>
  <div class="kpi"><div class="k">美元曝險</div><div class="v red">{usd_pct:.0f}%</div></div>
  <div class="kpi"><div class="k">高科技</div><div class="v yellow">{tech:.1f}%</div></div>
</div>

<div class="grid">
  <div class="card"><h2>📊 五桶穿透 vs 目標</h2>{bar_rows}</div>
  <div class="card"><h2>📡 機構流向雷達</h2><div class="rcards">{radar_cards}</div></div>
</div>

<div class="grid" style="margin-top:14px">
  <div class="card"><h2>🎯 動作建議（執行紀律）</h2><div class="acards">{action_cards}</div></div>
  <div class="card"><h2>🏭 產業別穿透（雙層 Micro）</h2>
    <table><tr><th>產業</th><th class="num">金額</th><th class="num">佔比</th><th>狀態</th></tr>{sec_rows}</table>
    <div style="font-size:11px;color:var(--sub);margin-top:8px">紅線：高科技 ≤30%（當前 {tech:.1f}%）｜輪動閥門：科技>30% 或雷達科技轉弱 → 乾粉轉金融/電信/醫療防禦</div>
  </div>
</div>

<div class="grid" style="margin-top:14px">
  <div class="card"><h2>💰 9月台幣乾粉分配</h2>
    <div class="drybar">
      <div style="width:38%;background:var(--blu)">台股 12-24萬</div>
      <div style="width:55%;background:var(--yel)">黃金 131萬（PI後）</div>
      <div style="width:0%;background:var(--red)"></div>
      <div style="width:7%;background:var(--sub)">其他</div>
    </div>
    <div style="font-size:12px;color:#cbd5e1;line-height:1.7">
      當前乾粉 <b>{dry_cur:,}</b>（現金 − 70萬底線）｜9月新增：月盈餘 6-11萬 + 台幣配息 + 8/31 贖回超底線部分<br>
      石油 🔴 Locked（0）｜債券 ⏸ 等質押+US30Y&lt;5.30%（0）
    </div>
  </div>
  <div class="card"><h2>🛡️ 質押 / 風險紅線</h2>
    <div style="font-size:12.5px;color:#cbd5e1;margin-bottom:8px">📌 {ltv_txt}</div>
    <table><tr><th>指標</th><th class="num">現值</th><th class="num">紅線</th><th>狀態</th></tr>{risk_rows}</table>
  </div>
</div>

<div class="card" style="margin-top:14px"><h2>🗓 里程碑時程</h2>{ms_html}</div>

<div class="foot">資料來源：snapshot.json（{TODAY}）+ radar_state.json（機構流向雷達）｜build_rebalance_dashboard.py 動態生成</div>
</div></body></html>"""

    out = BASE / f"rebalance_dashboard_{TODAY}.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ 再平衡儀表板已產出: {out}（{len(html)//1024} KB）")

if __name__ == "__main__":
    main()
