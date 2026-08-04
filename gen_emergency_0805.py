# -*- coding: utf-8 -*-
"""美股緊急應變 2026-08-05 00:15 (台北) — 美股 8/4 盤中更新（美東 12:16 ET）
LLM 分析 JSON + Railway/GitHub 雙版 HTML"""
import json, datetime, os

TODAY = "2026-08-05"
NOW = "2026-08-05 00:15"

FULL_REPORT = """【一、市場概況】美股週二(8/4)延續週一大漲、盤中續創歷史新高（台北 8/5 00:15 擷取，美東 12:16 盤中）：道瓊 54,067.11(+1.67%)、S&P 500 7,709.95(+1.44%，盤中觸及歷史新高 7,713.62)、納指 26,445.72(+2.05%)、費城半導體 12,124.54(+6.07%，全場最強訊號，週一 +1.05% 後兩日累計逾 +7%)。盤前期貨同步強勢：道瓊期 54,207(+1.64%)、標普期 7,738.25(+1.44%)、那指期 29,686.25(+2.75%)；VIX 16.27(+2.6%) 仍在低位、情緒偏多。個股：TSM ADR 415.96(+2.43%)、NVDA 210.63(+1.93%)、TSLA 325.03(+0.91%)、AAPL 306.27(+0.94%)、META 582.88(-1.25%，週一 +6% 後連兩日回吐)、AMZN 278.23(-2.04%，財報後獲利了結)。商品與債市：黃金 4,142.50(+1.27%)、WTI 原油 75.92(-5.50%，兩日累計 -10.3%)、10Y 4.627%(-5.9bp)、30Y 5.191%(-4.0bp，正式跌破 5.20% 防禦門檻)。台股 8/4 收盤：加權 43,360.66(-0.06%)、台積電 2,320(-2.11%)，盤中一度跌破 43,000、震盪逾千點；惟費半大漲將挹注週三(8/5)台股半導體補漲動能。

【二、重大事件分析】(1) 美伊停火談判＋油價崩跌：Bessent 稱「荷莫茲協議在望」、卡達證實美伊談判有進展、川普高調宣稱談判進行中；惟 NBC 報導荷莫茲海峽仍有貨輪遭襲、WSJ 警告談判不確定性未除。WTI 75.92(-5.50%)、兩日累計 -10.3%，油價崩跌＝通膨降溫路徑成形，Investing.com 指伊朗停火後市場對年底降息押注明顯升溫。(2) Fed 按兵不動、通膨處三年高點：本週 FOMC 維持利率不變（ABC），AOL 指會議出現十年未見的訊號令華爾街憂心（鷹派傾斜）；惟油價回落＋7 月非農待公布，市場定價反而轉向年內降息。(3) 半導體/AI 財報點火：Palantir Q2 商業營收「otherworldly」、股價單日 +20%，緩解 OpenAI/Anthropic 威脅疑慮；TSMC 擴大外包封裝產能應對 Nvidia AI 需求（盤前 +3%）、Druckenmiller 續抱 TSM；Citadel Securities 稱「夏季殘酷回檔已結束、該重新買進」，費半 +6.07% 直接驗證 AI 資本開支未變。(4) 台股結構：8/4 加權跌破 43,000 後收斂，台積電受英特爾 EMIB-T 封裝（宣稱良率 90%、成本僅 CoWoS 一半）消息壓抑 -2.11%，處置股冷卻期規則放寬；費半 +6.07%＋TSM ADR +2.43% 為週三台股提供強力補漲催化。

【三、持倉關聯分析】① 0050（2,000股/成本84.9/+18.55%）：台積電權重約五成，8/4 台積電 -2.11% 拖累、加權僅 -0.06%；惟 TSM ADR +2.43%＋費半 +6.07%，週三補漲機率高，續小單低吸。② 006208（+16.89%）：與 0050 同邏輯，台股低配 -14.1pp 屬既定架構，逢回小單（單筆≤5萬）。③ 00878（16,000股/+19.99%）：高股息防禦屬性，8 月除權息旺季，續建 4 週為本階段唯一明確增持。④ 00919（6,000股/-0.12%）：平盤、殖利率保護，持有。⑤ 00983D（20,000股/+0.05%）：8/4 已按方案B執行最後 10,000 單位 @10.12（101,200 元，使用者核准超額單）；流動性觀察期內暫緩新增，待 US30Y 連3日 <5.20% 解除。⑥ 00646 元大S&P500（+8.52%）：S&P 創高直接受惠，美股超配 +5.7pp 不追高。⑦ 貝萊德世界科技（保單連結）：NVDA +1.93%＋費半 +6.07%，淨值直接受惠，AI 長線邏輯強化。⑧ 安聯AI收益成長（保單連結）：AI 半導體全面上漲、受益明確。⑨ 保單基金（安聯 A/B 合計 764.5 萬＋第一金 FL65 已轉 FJ33 摩根多重收益 193.4 萬）：美股創高推升帳戶價值，配息 SOP 維持 hold；另台新美日台半導體基金 13.4 萬直接受惠費半大漲。

【四、資產配置透視】依 snapshot penetration.actual_twd（2026-08-04 自動校準，總投資 16,220,311 TWD）對照臨時階段目標（美股30/台股23.5/防守19/債券13/現金14.5）：台股市值型成長 152.2 萬(9.4%) vs 23.5%＝-14.1pp（嚴重低配、唯一大缺口）；美股市值型成長 578.7 萬(35.7%) vs 30%＝+5.7pp（超標）；防守型配息 305.0 萬(18.8%) vs 19%＝-0.2pp（幾乎達標）；債券 294.6 萬(18.2%) vs 13%＝+5.2pp（超標）；現金/安全網 291.5 萬(18.0%) vs 14.5%＝+3.5pp（超標）。結構解讀：美股/債券/現金超標合計 +14.4pp，以「暫緩新增＋配息導流」自然收斂；安全網（債券+現金）合計 36.1%，緩衝極度充足；唯一動作面仍是台股朝 23.5% 逐步架構回補。

【五、巴菲特/蒙格式建議】依臨時階段規則給出清單：✅ 增持：00878 續建 4 週（每筆<5 萬小額分批，8 月除權息旺季）；台股市值型（0050/006208）逢回小單低吸、單筆≤5 萬，朝 23.5% 前進。⏸️ 暫緩：00983D 新增（流動性觀察期，8/4 最後一筆已執行完畢；解除條件＝US30Y 連3日 <5.20%＋負債穩定＋現金充足）；債券 18.2% 超標 5.2pp 不新增；單筆≥5 萬元買單全數暫停。🧘 持有：00646/00919/0056/00713 等高息族；保單基金（安聯/第一金-FJ33）hold；美股超配靠配息導流自然降槓、不追高。⚠️ 減碼：美股 35.7% vs 30% 超標 +5.7pp——費半 +6.07% 強勢日不急於砍倉，採每週≤5 萬等價分批逢高收斂。💰 現金紀律：現金 291.5 萬＝6 個月生活費底線（約 85 萬）之 3.4 倍，runway 充足；ETF 擁擠交易新規（8/4 上線）：熱門 ETF 禁追漲大額、僅回檔小單。巴菲特視角：指數創高＋半導體暴漲的順風日，最忌追高與改變既定紀律——00878 續建、台股低吸照舊執行，美股超配不因大漲心動加碼，反視為收斂視窗。

【六、風控檢查】① US30Y 現值 5.191%（Yahoo ^TYX 即時，前收 5.231%）：<5.20% 防禦門檻→模式A防禦解除計數 Day 1/3（連3日 <5.20% 即解除流動性觀察期）；距 5.30% 債券凍結紅線尚有 10.9bp 緩衝，未觸發凍結；惟 Fed 按兵不動＋通膨三年高點，殖利率易反彈，不預設單邊。② 國泰核貸：snapshot(8/4) cathay_refinance_amount 仍為 null、原訂 8/4 撥款未見更新紀錄，第一階段審查至 9/25 到期；流程＝資金停泊→清償保單借貸 400 萬→提高信用分數→台銀築巢優利貸 2.185%（10/1 生效）佈局；審查期內 00983D 暫緩、單筆≥5 萬暫停維持。③ 其他風險：7 月非農將公布（Fed 路徑關鍵）；荷莫茲貨輪遇襲顯示談判反覆、油價恐報復性反彈；英特爾封裝競爭消息反覆；META/AMZN 連日走弱＝AI 巨頭資金輪動至半導體，留意獲利了結擴散；AAPL/AMZN 財報後波動未止。④ 結論：費半 +6.07% 續爆發＋S&P 觸歷史新高，多頭確立但已處高位，防禦紀律照舊——00878 續建 4 週、台股小單低吸、00983D 暫緩、單筆≥5 萬暫停、現金底線充足；US30Y 能否連續 3 日收於 5.20% 下方為未來三日首要監控指標。"""

# ============ 寫入 JSON ============
os.makedirs("data", exist_ok=True)
d = {"generated_at": NOW, "source": "美股緊急應變", "full_report": FULL_REPORT}
with open("data/emergency_llm_analysis.json", "w", encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, indent=2)
print("JSON len:", len(FULL_REPORT))

# ============ HTML 模板 ============
CSS = """:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--tx:#e6edf3;--mut:#8b949e;
--red:#f85149;--grn:#3fb950;--yel:#d29922;--blu:#58a6ff;--pur:#bc8cff}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font-family:'Segoe UI','Noto Sans TC','Microsoft JhengHei',sans-serif;line-height:1.65;padding:24px}
.wrap{max-width:980px;margin:0 auto}
header{border:1px solid var(--line);border-radius:12px;padding:22px 26px;background:linear-gradient(135deg,#1a2332,#161b22);margin-bottom:20px}
header h1{font-size:26px;letter-spacing:1px}
header .sub{color:var(--mut);margin-top:6px;font-size:14px}
.alert-bar{margin:14px 0 4px;padding:10px 16px;border-radius:8px;background:rgba(63,185,80,.12);border:1px solid rgba(63,185,80,.4);font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 24px;margin-bottom:18px}
.card h2{font-size:19px;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--line);color:var(--blu)}
.card h2 .tag{float:right;font-size:12px;color:var(--mut);font-weight:400}
ul{padding-left:22px} li{margin:5px 0}
table{width:100%;border-collapse:collapse;margin-top:10px;font-size:14px}
th,td{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
th{background:#21262d;font-size:13px;white-space:nowrap}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pos{color:var(--grn)} .neg{color:var(--red)}
.badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600;white-space:nowrap}
.badge.buy{background:rgba(63,185,80,.15);color:var(--grn);border:1px solid var(--grn)}
.badge.hold{background:rgba(88,166,255,.12);color:var(--blu);border:1px solid var(--blu)}
.badge.pause{background:rgba(210,153,34,.12);color:var(--yel);border:1px solid var(--yel)}
.badge.over{background:rgba(248,81,73,.12);color:var(--red);border:1px solid var(--red)}
.badge.warn{background:rgba(248,81,73,.15);color:var(--red);border:1px solid var(--red)}
.badge.ok{background:rgba(63,185,80,.12);color:var(--grn);border:1px solid var(--grn)}
.kpi{display:flex;flex-wrap:wrap;gap:12px;margin-top:12px}
.kpi .box{flex:1;min-width:150px;background:#21262d;border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpi .box .lbl{font-size:12px;color:var(--mut)} .kpi .box .val{font-size:20px;font-weight:700;margin-top:2px}
.risk-line{padding:8px 12px;border-radius:8px;margin:6px 0;background:#21262d;border-left:4px solid var(--blu)}
.risk-line.warn{border-left-color:var(--yel)}
.risk-line.ok{border-left-color:var(--grn)}
pre.report{white-space:pre-wrap;word-break:break-word;font-family:inherit;font-size:14px;line-height:1.75}
footer{color:var(--mut);font-size:12px;text-align:center;margin-top:24px}"""

def row(name, price, pct, extra=""):
    cls = "pos" if pct >= 0 else "neg"
    sign = "+" if pct >= 0 else ""
    return f"<tr><td>{name}</td><td class='num'>{price}</td><td class='num {cls}'>{sign}{pct:.2f}%</td><td>{extra}</td></tr>"

market_rows = "".join([
    row("道瓊工業 DJI", "54,067.11", 1.67, "盤中觸及 54,108 歷史高點"),
    row("S&P 500", "7,709.95", 1.44, "盤中創歷史新高 7,713.62"),
    row("納斯達克 IXIC", "26,445.72", 2.05, "科技領漲"),
    row("費城半導體 SOX", "12,124.54", 6.07, "全場最強，兩日累計逾 +7%"),
    row("VIX 恐慌指數", "16.27", 2.6, "仍處低位，情緒偏多"),
    row("TSM ADR", "415.96", 2.43, "擴外包封裝＋Druckenmiller 續抱"),
    row("NVDA", "210.63", 1.93, "AI 需求強勁，8 月財報前觀望"),
    row("TSLA", "325.03", 0.91, "跟漲"),
    row("AAPL", "306.27", 0.94, "連日弱勢後反彈"),
    row("META", "582.88", -1.25, "週一 +6% 後連兩日回吐"),
    row("AMZN", "278.23", -2.04, "財報後獲利了結"),
    row("黃金 GC", "4,142.50", 1.27, "避險＋降息預期"),
    row("WTI 原油", "75.92", -5.50, "美伊談判進展，兩日累計 -10.3%"),
    row("美債 10Y", "4.627%", -1.26, "-5.9bp"),
    row("美債 30Y (US30Y)", "5.191%", -0.76, "-4.0bp，跌破 5.20% 防禦門檻"),
    row("道瓊期 ES", "54,207", 1.64, "盤前"),
    row("標普期 ES", "7,738.25", 1.44, "盤前"),
    row("那指期 NQ", "29,686.25", 2.75, "盤前"),
])

alloc_rows = "".join([
    "<tr><th>類別</th><th class='num'>實際 TWD</th><th class='num'>實際%</th><th class='num'>臨時目標%</th><th class='num'>偏離(pp)</th><th>狀態</th></tr>",
    "<tr><td>台股市值型成長</td><td class='num'>1,522,144</td><td class='num'>9.4%</td><td class='num'>23.5%</td><td class='num neg'>-14.1</td><td><span class='badge over'>嚴重低配</span></td></tr>",
    "<tr><td>美股市值型成長</td><td class='num'>5,787,079</td><td class='num'>35.7%</td><td class='num'>30.0%</td><td class='num pos'>+5.7</td><td><span class='badge over'>超標</span></td></tr>",
    "<tr><td>防守型配息</td><td class='num'>3,050,365</td><td class='num'>18.8%</td><td class='num'>19.0%</td><td class='num'>-0.2</td><td><span class='badge ok'>達標</span></td></tr>",
    "<tr><td>債券</td><td class='num'>2,946,068</td><td class='num'>18.2%</td><td class='num'>13.0%</td><td class='num pos'>+5.2</td><td><span class='badge over'>超標</span></td></tr>",
    "<tr><td>現金/安全網</td><td class='num'>2,914,655</td><td class='num'>18.0%</td><td class='num'>14.5%</td><td class='num pos'>+3.5</td><td><span class='badge over'>超標</span></td></tr>",
    "<tr><td>合計</td><td class='num'>16,220,311</td><td class='num'>100%</td><td class='num'>100%</td><td class='num'>—</td><td>安全網(債券+現金) 36.1% 緩衝充足</td></tr>",
])

hold_rows = "".join([
    "<tr><th>標的</th><th>狀態</th><th>說明</th></tr>",
    "<tr><td>00878（16,000股 +19.99%）</td><td><span class='badge buy'>增持</span></td><td>續建 4 週，8 月除權息旺季，每筆&lt;5萬</td></tr>",
    "<tr><td>0050/006208（台股市值型）</td><td><span class='badge buy'>增持</span></td><td>逢回小單低吸、單筆≤5萬，朝 23.5% 回補</td></tr>",
    "<tr><td>00983D（20,000股 +0.05%）</td><td><span class='badge pause'>暫緩</span></td><td>流動性觀察期；8/4 最後10,000單位@10.12已執行</td></tr>",
    "<tr><td>債券類（18.2%）</td><td><span class='badge pause'>暫緩</span></td><td>超標 5.2pp 不新增</td></tr>",
    "<tr><td>單筆≥5萬元買單</td><td><span class='badge pause'>暫停</span></td><td>國泰核貸審查期管制</td></tr>",
    "<tr><td>00646 S&P500（+8.52%）</td><td><span class='badge hold'>持有</span></td><td>美股超配 +5.7pp 不追高</td></tr>",
    "<tr><td>00919/0056/00713 高息族</td><td><span class='badge hold'>持有</span></td><td>殖利率保護</td></tr>",
    "<tr><td>貝萊德世界科技/安聯AI（保單）</td><td><span class='badge hold'>持有</span></td><td>NVDA＋費半大漲直接受惠</td></tr>",
    "<tr><td>保單基金（安聯A/B 764.5萬＋FJ33 193.4萬）</td><td><span class='badge hold'>持有</span></td><td>配息 SOP hold</td></tr>",
    "<tr><td>美股超配部位（35.7% vs 30%）</td><td><span class='badge warn'>減碼</span></td><td>強勢日不砍倉，每週≤5萬分批逢高收斂</td></tr>",
])

def render(suffix):
    return f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>龍九控股｜美股緊急應變報告 {TODAY}</title>
<style>{CSS}</style></head><body><div class="wrap">

<header>
<h1>🐉 龍九控股 — 美股緊急應變報告</h1>
<div class="sub">📅 {NOW} 美股盤中（美東 8/4 12:16 ET）{suffix}｜Chief Reporter + 美股危機應變官｜六大章節完整版</div>
<div class="alert-bar">🚀 費半 +6.07% 續爆發（Palantir「otherworldly」＋TSMC 擴外包封裝）｜🛢️ 油價 -5.5%（美伊談判進展、荷莫茲仍傳遇襲）｜🌡️ US30Y 5.191% 跌破 5.20% 防禦門檻（解除計數 Day 1/3）｜📊 S&P 7,709.95 觸歷史新高 7,713.62</div>
</header>

<div class="kpi"><div class='box'><div class='lbl'>道瓊</div><div class='val pos'>54,067.11</div><div class='lbl'>+1.67%</div></div><div class='box'><div class='lbl'>S&P 500</div><div class='val pos'>7,709.95</div><div class='lbl'>+1.44% 歷史新高</div></div><div class='box'><div class='lbl'>納斯達克</div><div class='val pos'>26,445.72</div><div class='lbl'>+2.05%</div></div><div class='box'><div class='lbl'>費城半導體</div><div class='val pos'>12,124.54</div><div class='lbl'>+6.07% 🔥</div></div><div class='box'><div class='lbl'>US30Y</div><div class='val' style='color:var(--yel)'>5.191%</div><div class='lbl'>-4.0bp 破 5.20% 門檻</div></div><div class='box'><div class='lbl'>WTI 原油</div><div class='val neg'>75.92</div><div class='lbl'>-5.50% 兩日 -10.3%</div></div></div>

<div class="card"><h2>📊 即時市場數據 <span class="tag">Yahoo Finance 8/4 12:16 ET 盤中</span></h2>
<table>{market_rows}</table></div>

<div class="card"><h2>🧩 資產配置透視 <span class="tag">snapshot.json penetration.actual_twd（8/4 校準）</span></h2>
<table>{alloc_rows}</table>
<p style='margin-top:10px;font-size:13px;color:var(--mut)'>結構解讀：唯一大缺口＝台股 -14.1pp（屬預期、逐步架構回補）；美股/債券/現金超標合計 +14.4pp，以「暫緩新增＋配息導流」自然收斂；安全網（債券+現金）合計 36.1%，緩衝極度充足。</p></div>

<div class="card"><h2>📋 巴菲特/蒙格式建議清單 <span class="tag">臨時階段規則</span></h2>
<table>{hold_rows}</table></div>

<div class="card"><h2>🛡️ 風控檢查 <span class="tag">US30Y vs 5.20% / 5.30%</span></h2>
<div class="risk-line ok">✅ US30Y 現值 <b>5.191%</b>（前收 5.231%）&lt; <b>5.20%</b> 防禦門檻 → 解除計數 <b>Day 1/3</b>（連3日 &lt;5.20% 解除流動性觀察期）</div>
<div class="risk-line ok">✅ 距 <b>5.30%</b> 債券凍結紅線尚有 <b>10.9bp</b>，未觸發凍結</div>
<div class="risk-line warn">⚠️ 國泰核貸：cathay_refinance_amount 仍 null、原訂 8/4 撥款未見更新；第一階段審查至 9/25；流程＝停泊→清償保單借貸400萬→信用評分→台銀築巢 2.185%（10/1）；審查期內 00983D 暫緩、單筆≥5萬暫停</div>
<div class="risk-line warn">⚠️ 其他風險：7月非農將公布；荷莫茲貨輪遇襲（談判反覆、油價恐反彈）；英特爾封裝競爭；META/AMZN 連日走弱＝AI 資金輪動至半導體</div></div>

<div class="card"><h2>📄 完整六大章節分析 <span class="tag">LLM 深度分析</span></h2>
<pre class="report">{FULL_REPORT}</pre></div>

<footer>🐉 龍九控股 emergency response ｜ generated {NOW} 美股盤中{suffix} ｜ 數據來源：Yahoo Finance 即時（^GSPC/^IXIC/^DJI/^SOX/^TYX/TSM/NVDA...）、Google News RSS（CNBC/WSJ/Reuters/Barron's/IBD）、snapshot.json（penetration.actual_twd）</footer>
</div></body></html>"""

with open(f"emergency_report_{TODAY}.html", "w", encoding="utf-8") as f:
    f.write(render(""))
with open(f"emergency_taiex_report_{TODAY}.html", "w", encoding="utf-8") as f:
    f.write(render("（GitHub Pages 同步）"))

print("HTML OK:", f"emergency_report_{TODAY}.html", f"emergency_taiex_report_{TODAY}.html")
