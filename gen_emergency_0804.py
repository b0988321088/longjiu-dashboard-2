# -*- coding: utf-8 -*-
"""美股緊急應變 2026-08-04 21:30 (美股開盤) — LLM 分析 JSON + Railway/GitHub 雙版 HTML"""
import json, datetime

TODAY = "2026-08-04"
NOW = "2026-08-04 21:40"

# ============ 完整六大章節 LLM 分析（>1500 字元） ============
FULL_REPORT = """【一、市場概況】美股週二(8/4)開盤續創歷史新高，延續週一(8/3)大漲氣勢。週一收盤：道瓊 53,178.41(+1.32%)、納指 25,913.90(+2.13%)、S&P 500 7,600.50(+1.48%)、費半 11,430.35(+1.05%)；週二開盤(21:30 TW)進一步走高：道瓊 53,775.52(+1.12%)、納指 26,231.32(+1.22%)、S&P 500 7,644.81(+0.58%，距歷史高點 7,647.86 僅 3 點)、費城半導體指數 12,005.07(+5.03%，單日暴漲，為全場最強訊號)。盤前期貨同步走強：道瓊期 54,078(+1.39%)、標普期 7,666.50(+0.50%)、那斯達克期 29,305.75(+1.43%)。VIX 15.56(-1.9%) 續降，市場情緒偏樂觀。個股：TSM ADR 414.43(+2.05%)、NVDA 211.13(+2.17%，續創高)、TSLA 323.00(+0.29%)、AAPL 303.13(-0.10%，連日弱勢)、META 584.80(-0.92%，週一+6%後回吐)、AMZN 277.38(-2.34%，獲利了結)。商品與匯率：黃金 4,134.20(+2.49%)、WTI 原油 76.36(-4.95%)、10Y 美債 4.641%、30Y 美債 5.202%、USDJPY 157.26、比特幣 63,984。台股 8/4 收盤：加權 43,360.66(-0.06%)，台積電 2,320(-2.11%)，受英特爾封裝消息壓抑。

【二、重大事件分析】(1) 伊朗戰爭暫停＋荷莫茲海峽重開談判：NYT/WSJ/MarketWatch 報導卡達與美國財長 Bessent 提及重開荷莫茲海峽會談，川普宣稱伊朗談判進行中，WTI 單日再跌 -4.95% 至 76.36 美元（兩日累計 -10%）。意涵：油價崩跌＝通膨降溫＋消費成本減輕，直接利多股市與債券；惟談判反覆風險仍在，地緣主軸未完全解除。(2) 半導體全面爆發：ON Semiconductor 財報與展望優於預期，Citi 喊買半導體（AMAT 入觀察名單），Citadel Securities 稱「夏季殘酷回檔已結束、該重新買進」，費半開盤 +5.03%，TSM/NVDA 同步創高，直接驗證 AI 資本開支與半導體基本面未變。(3) 債市與 Fed：10Y 4.641%(-0.96%)、30Y 5.202%(-0.55%) 回落；近期 6 月 CPI 3.5% 低於預期（Core 2.6%）強化降息預期，惟 Barron's 警告「殖利率正測試 Fed 信譽」，關鍵就業數據（7 月非農）即將公布，Axios 並報導日圓干預疑雲（USDJPY 157.26）。(4) 台股結構消息：英特爾宣稱 EMIB-T 先進封裝良率 90%、成本僅 CoWoS 一半，台積電 8/4 大跌 -2.11%；MarketWatch 稱「全球最熱股市（台股今年+14,397 點）淪為放空獵場」，但 TSMC 2nm 年底月產 10 萬片、熊本廠地震後復原等利多仍在。

【三、持倉關聯分析】① 0050（2000股/成本84.9/+18.55%）：台積電權重約五成，今日台股 -0.06% 收平、台積電 -2.11%，短期承壓；但費半 +5.03% 與 TSM ADR +2.05% 強勢，週三台股半導體有望反彈補漲，持倉受惠。② 006208（+16.89%）：與 0050 同邏輯，台股市值型低配 -14.1pp 屬預期內，逢回小單分批即可。③ 00878（16000股/+19.99%）：高股息防禦屬性，8 月除權息旺季，續建 4 週策略不受美股影響，為本階段唯一明確增持標的。④ 00919（6000股/-0.12%）：平盤、殖利率保護，持有。⑤ 00983D（20000股/+0.05%）：主動複合收益，US30Y 5.202% 仍在 5.20% 防禦門檻上方，核貸審查期暫緩新增（8/4 最後一筆 10,000 單位@10.12 已執行完畢）。⑥ 00646 元大S&P500（+8.52%）：S&P 續創新高直接受惠，美股超配 +5.9pp 不追高。⑦ 貝萊德世界科技（保單連結）：NVDA +2.17%、費半 +5.03%，淨值直接受惠，AI 長線邏輯強化。⑧ 安聯AI收益成長（保單連結）：AI 半導體全面上漲，NVDA 續創高，受益明確。⑨ 保單基金（安聯 A/B 合計 764.5 萬、第一金 FL65 193.4 萬）：連結美股科技與多重收益，美股創高推升帳戶價值，配息 SOP 維持 hold。另台新美日台半導體基金 13.4 萬直接受惠費半大漲。

【四、資產配置透視】依 snapshot penetration.actual_twd（2026-08-04 自動校準，總投資 1,624 萬 TWD），對照臨時階段目標（美股30/台股23.5/防守19/債券13/現金14.5）：台股市值型成長 152.2 萬(9.4%) vs 23.5%＝-14.1pp（嚴重低配）；美股市值型成長 583.0 萬(35.9%) vs 30%＝+5.9pp（超標）；防守型配息 305.0 萬(18.8%) vs 19%＝-0.2pp（幾乎達標）；債券 292.6 萬(18.0%) vs 13%＝+5.0pp（超標）；現金/安全網 291.5 萬(17.9%) vs 14.5%＝+3.4pp（超標）。結構解讀：唯一大缺口仍是台股 -14.1pp（屬預期、逐步架構回補）；美股/債券/現金三項超標合計 +14.3pp，以「暫緩新增＋配息導流」自然收斂；安全網（債券+現金）合計 35.9%，緩衝極度充足。

【五、巴菲特/蒙格式建議】依臨時階段規則給出清單：✅ 增持：00878 續建 4 週（每筆<5 萬小額分批，8 月除權息旺季＋高股息防禦驗證）；台股市值型（0050/006208）逢回小單低吸、單筆≤5 萬，逐步朝 23.5% 前進。⏸️ 暫緩：00983D 新增（核貸審查期，8/4 撥款後重新評估）；債券類 18.0% 已超標 5pp 不新增；單筆≥5 萬元買單全數暫停。🧘 持有：00646/009823/009824（美股超配靠配息導流自然降槓，不追高）；00919/0056/00713 等高息族；保單基金（安聯/第一金）hold。⚠️ 減碼：美股 35.9% vs 30% 超標 5.9pp——今天費半 +5.03% 屬強勢反彈，不急於單日砍倉，採分批小額（每週≤5 萬等價）逢高收斂。💰 現金紀律：高利活存 220.0 萬＝6 個月生活費底線（85.2 萬）之 2.6 倍，runway 充足；現金降至 15% 以下即停止補碼。巴菲特視角：指數創高＋半導體暴漲的順風日，最忌追高與改變既定紀律——00878 續建、台股低吸照舊執行，美股超配部分不因大漲而心動加碼，反而視為收斂視窗。

【六、風控檢查】① US30Y 現值 5.202%（Yahoo ^TYX 即時，前收 5.231%）：5.202% > 5.20% 防禦門檻→模式 A 防禦持續（差距僅 0.2bp、幾乎貼線，連 3 日 <5.20% 未成立，大額進場仍不開放）；距 5.30% 債券凍結紅線尚有 9.8bp 緩衝，未觸發凍結。② 國泰核貸階段：第一階段審查進行中（9/25 到期），資金先轉停泊帳戶避免列管→清償保單借貸 400 萬→提高信用分數→為台銀築巢優利貸 2.185%（10/1 生效）佈局；snapshot 顯示 cathay_refinance_amount 尚未撥款（null），核貸審查期內 00983D 暫緩、單筆≥5 萬暫停。③ 其他風險：7 月非農就業數據將公布（Fed 路徑關鍵）、英特爾封裝競爭消息反覆、AAPL/AMZN 財報後波動未止、伊朗談判若破局油價恐報復性反彈。④ 結論：費半 +5.03% 與指數創高確立風險偏好多頭延續，防禦紀律照舊——00878 續建 4 週、台股小單低吸、00983D 暫緩、單筆≥5 萬暫停、現金底線充足；30Y 貼線 5.20% 為明日首要監控指標。"""

# ============ CSS（沿用既有樣式） ============
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
.badge.cred{background:rgba(188,140,255,.12);color:var(--pur);border:1px solid var(--pur)}
.kpi{display:flex;flex-wrap:wrap;gap:12px;margin-top:12px}
.kpi .box{flex:1;min-width:150px;background:#21262d;border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpi .box .lbl{font-size:12px;color:var(--mut)} .kpi .box .val{font-size:20px;font-weight:700;margin-top:2px}
.risk-line{padding:8px 12px;border-radius:8px;margin:6px 0;background:#21262d;border-left:4px solid var(--blu)}
footer{color:var(--mut);font-size:12px;text-align:center;margin-top:24px}"""

def posneg(pct):
    return f"<span class='{'pos' if pct >= 0 else 'neg'}'>{'+' if pct >= 0 else ''}{pct:.2f}%</span>"

kpi = [
    ("道瓊", "53,775.52", "+1.12%", "pos"), ("S&P 500", "7,644.81", "+0.58%", "pos"),
    ("納斯達克", "26,231.32", "+1.22%", "pos"), ("費城半導體", "12,005.07", "+5.03%", "pos"),
    ("US30Y", "5.202%", "防禦5.20/紅線5.30", "yel"), ("WTI原油", "76.36", "-4.95%", "neg"),
]

sec1 = """<ul>
<li><b>道瓊 53,775.52（+597.11，+1.12%）</b>— 開盤續創歷史新高，週一 +1.32% 後強勢延續。</li>
<li><b>S&P 500 7,644.81（+44.31，+0.58%）</b>— 距歷史高點 7,647.86 僅 3 點，隨時再創新高。</li>
<li><b>納斯達克 26,231.32（+317.42，+1.22%）</b>— 科技權值領漲。</li>
<li><b>費城半導體 12,005.07（+574.72，+5.03%）</b>🚀 單日暴漲，全場最強訊號——ON Semi 財報優於預期 + Citi 喊買 + Citadel「夏季重置結束」。</li>
<li><b>盤前期貨：</b>道瓊期 +1.39% / 標普期 +0.50% / 那斯達克期 +1.43%。</li>
<li><b>VIX 15.56（-1.9%）</b>— 恐慌指數續降，風險偏好回溫。</li>
<li><b>黃金 4,134.20（+2.49%）</b>；<b>WTI 原油 76.36（-4.95%）</b>⚠️ 兩日累計 -10%，伊朗戰爭暫停 + 荷莫茲海峽重開談判。</li>
<li><b>美債：</b>10Y 4.641%（-0.96%）、30Y 5.202%（-0.55%，前收 5.231%）。</li>
<li><b>重要個股：</b>TSM ADR 414.43（+2.05%）、NVDA 211.13（+2.17% 續創高）、TSLA 323.00（+0.29%）、AAPL 303.13（-0.10%）、META 584.80（-0.92%）、AMZN 277.38（-2.34%）；USDJPY 157.26、BTC 63,984。</li>
<li><b>台股（8/4 收盤）：</b>加權 43,360.66（-0.06%）；台積電 2,320.00（-2.11%，英特爾 EMIB-T 封裝良率消息壓抑）。</li>
</ul>"""

events = [
    ("伊朗戰爭暫停、油價崩跌（地緣主軸）", "NYT / WSJ / MarketWatch / Al Jazeera", "高",
     "卡達與美財長 Bessent 提及重開荷莫茲海峽會談，川普宣稱伊朗談判進行中，WTI 再跌 -4.95% 至 76.36（兩日 -10%）。意涵：油價崩跌＝通膨降溫＋消費成本減輕，直接利多股市債券；惟談判反覆風險仍在，地緣主軸未完全解除。"),
    ("半導體全面爆發（今日最強訊號）", "Yahoo Finance / IBD / MarketWatch / Barron's", "高",
     "ON Semiconductor 財報與展望優於預期；Citi 喊買半導體（AMAT 入觀察名單）；Citadel Securities 稱「夏季殘酷回檔已結束、該重新買進」。費半開盤 +5.03%，TSM/NVDA 創高，驗證 AI 資本開支與半導體基本面未變，直接利多 00646/貝萊德科技/安聯AI 與台新美日台半導體基金。"),
    ("債市與 Fed：殖利率回落但就業數據將公布", "CNBC / Barron's / Axios", "中高",
     "10Y 4.641%、30Y 5.202% 回落；6 月 CPI 3.5% 低於預期（Core 2.6%）強化降息預期；惟 Barron's 警告殖利率正測試 Fed 信譽，7 月非農就業數據將公布為 Fed 路徑關鍵；Axios 報導日圓干預疑雲（USDJPY 157.26）。"),
    ("台股結構消息：英特爾挑戰台積電＋放空獵場", "Focus Taiwan / MarketWatch / TweakTown", "中",
     "英特爾宣稱 EMIB-T 先進封裝良率 90%、成本僅 CoWoS 一半，台積電 8/4 大跌 -2.11%（台股收平）；MarketWatch 稱全球最熱股市（台股今年+14,397 點）淪為放空獵場；惟 TSMC 2nm 年底月產 10 萬片、熊本廠地震後復原等利多仍在，費半大漲將於週三台股反映。"),
]

holdings = [
    ("0050 元大台灣50", "100.65", "—", "台積電權重約五成，今日台股 -0.06%、台積電 -2.11% 壓抑；但費半 +5.03% + TSM ADR +2.05%，週三半導體有望反彈補漲；帳面 +18.55%", "hold", "持有"),
    ("006208 富邦台50", "230.15", "—", "與 0050 同邏輯；台股市值型低配 -14.1pp 屬預期，逢回小單分批（單筆≤5萬）", "buy", "增持"),
    ("00878 國泰永續高股息", "32.57", "—", "高股息防禦＋8 月除權息旺季；續建 4 週策略照舊，為本階段唯一明確增持標的", "buy", "增持"),
    ("00919 群益精選高息", "29.51", "—", "平盤、殖利率保護，帳面 -0.12% 微幅波動", "hold", "持有"),
    ("00983D 富邦複合收益", "10.11", "—", "US30Y 5.202% 仍在 5.20% 防禦門檻上方；核貸審查期暫緩新增（8/4 最後一筆 10,000 單位@10.12 已執行）", "pause", "暫緩"),
    ("00646 元大S&P500", "77.70", "—", "S&P 續創高直接受惠（+8.52%）；美股超配 +5.9pp，不追高", "hold", "持有"),
    ("貝萊德世界科技（保單）", "—", "—", "NVDA +2.17% 續創高、費半 +5.03% → 淨值直接受惠，AI 長線邏輯強化", "hold", "持有"),
    ("安聯AI收益成長（保單）", "—", "—", "AI 半導體全面上漲、NVDA 續創高 → 受益明確；台新美日台半導體基金 13.4 萬同受惠", "hold", "持有"),
    ("保單基金（第一金/安聯）", "—", "—", "安聯 A/B 合計 764.5 萬 + 第一金 FL65 193.4 萬：美股創高推升帳戶價值；配息 SOP 維持 hold", "hold", "持有"),
]

alloc = [
    ("台股市值型成長", "1,522,144", "9.4%", "23.5%", "-14.1pp", "warn", "嚴重低配"),
    ("美股市值型成長", "5,830,436", "35.9%", "30.0%", "+5.9pp", "over", "超標"),
    ("防守型配息", "3,050,365", "18.8%", "19.0%", "-0.2pp", "ok", "接近達標"),
    ("債券", "2,925,827", "18.0%", "13.0%", "+5.0pp", "over", "超標"),
    ("現金/安全網", "2,914,655", "17.9%", "14.5%", "+3.4pp", "over", "超標"),
]

sec5 = """<ul>
<li><b>增持：</b><span class='badge buy'>00878 續建 4 週</span>（8 月除權息旺季＋高股息防禦驗證，每筆 &lt;5 萬小額分批）；台股市值型（0050/006208）逢回小單低吸（單筆≤5 萬），逐步朝 23.5% 前進。</li>
<li><b>持有：</b>00646/009823/009824（美股超配靠配息導流自然降槓，不追高）；00919/0056/00713 等高息族；貝萊德科技、安聯AI、保單基金（hold，費半大漲直接受益）。</li>
<li><b>減碼：</b>美股 35.9% &gt; 30% 目標（+5.9pp）— 今日費半 +5.03% 屬強勢反彈，不急於單日砍倉，採分批小額（每週≤5 萬等價）逢高收斂至 30%。</li>
<li><b>暫緩：</b><span class='badge pause'>00983D 新增</span>（核貸審查期，8/4 撥款後重新評估）；債券類 18.0% 已超標 5pp，不新增；單筆 ≥5 萬元買單全數暫停。</li>
<li><b>現金紀律：</b>高利活存 220.0 萬 = 6 個月生活費底線（85.2 萬）之 <b>2.6 倍</b>，runway 充足；現金降至 15% 以下即停止補碼。</li>
<li><b>巴菲特視角：</b>指數創高＋半導體暴漲的順風日最忌追高——00878 續建、台股低吸照既定紀律執行；美股超配不因大漲心動加碼，反而視為收斂視窗；「別人貪婪我恐懼」此時體現在不加碼美股、守住現金底線與單筆≥5萬暫停令。</li>
</ul>"""

sec6 = """<div class="risk-line"><b>US30Y 現值 5.202%</b>（Yahoo ^TYX 即時，前收 5.231%）</div>
<div class="risk-line" style="border-left-color:var(--yel)">⚠️ <b>5.20% 防禦門檻：仍觸發</b>（5.202% &gt; 5.20%，差距僅 <b>0.2bp</b>、幾乎貼線）→ 模式 A 防禦持續；「連 3 日 &lt;5.20%」未成立，大額進場仍不開放</div>
<div class="risk-line" style="border-left-color:var(--grn)">✅ <b>5.30% 凍結紅線：未觸發</b>（5.202% &lt; 5.30%，緩衝 9.8bp）；若伊朗談判破局或 Fed 轉鷹，30Y 可能快速越線 → 明日首要監控指標</div>
<div class="risk-line">📉 10Y 4.641%；油價崩跌推升降息預期，殖利率回落支撐股市評價</div>
<div class="risk-line" style="border-left-color:var(--blu)">🏦 <b>國泰核貸狀態：</b>第一階段審查進行中（9/25 到期）——資金先轉停泊帳戶避免列管→清償保單借貸 400 萬→提高信用分數→為台銀築巢優利貸 2.185%（10/1 生效）佈局；cathay_refinance_amount 尚未撥款（null），核貸審查期內 00983D 暫緩、單筆≥5 萬暫停</div>
<div class="risk-line">📊 其他風險：7 月非農就業數據將公布（Fed 路徑關鍵）、英特爾封裝競爭消息反覆、AAPL/AMZN 財報後波動未止、伊朗談判若破局油價恐報復性反彈</div>"""

def build(title, filename, subtitle):
    kpi_html = "".join(
        f"<div class='box'><div class='lbl'>{l}</div><div class='val' style='color:var(--{c})'>{v}</div><div class='lbl'>{s}</div></div>"
        for l, v, s, c in kpi)
    ev_rows = "".join(
        f"<tr><td><b>{e}</b></td><td>{src}</td><td><span class='badge cred'>{cred}</span></td><td>{imp}</td></tr>"
        for e, src, cred, imp in events)
    hd_rows = "".join(
        f"<tr><td><b>{n}</b></td><td class='num'>{p}</td><td class='num'>{chg}</td><td>{note}</td><td><span class='badge {b}'>{act}</span></td></tr>"
        for n, p, chg, note, b, act in holdings)
    al_rows = "".join(
        f"<tr><td>{n}</td><td class='num'>{v}</td><td class='num'>{a}</td><td class='num'>{t}</td><td class='num {'pos' if '+' in g else 'neg'}'>{g}</td><td><span class='badge {b}'>{s}</span></td></tr>"
        for n, v, a, t, g, b, s in alloc)
    html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{CSS}</style></head><body><div class="wrap">

<header>
<h1>🐉 龍九控股 — 美股緊急應變報告</h1>
<div class="sub">📅 {subtitle}｜Chief Reporter + 美股危機應變官｜六大章節完整版</div>
<div class="alert-bar">🚀 費半 +5.03% 全面爆發（ON Semi 財報＋Citi 喊買）｜🛢️ 油價 -4.95%（伊朗戰爭暫停＋荷莫茲海峽重開談判）｜🌡️ US30Y 5.202%（貼線 5.20% 防禦門檻）｜📊 S&P 距歷史高點僅 3 點</div>
</header>

<div class="kpi">{kpi_html}</div>

<div class="card"><h2>一、市場概況 <span class="tag">Yahoo Finance 即時 21:40 TW（開盤）</span></h2>{sec1}</div>

<div class="card"><h2>二、重大事件分析 <span class="tag">4 大驅動事件</span></h2>
<table><tr><th style="width:26%">事件</th><th style="width:16%">來源</th><th>可信度</th><th>對龍九持倉之意涵</th></tr>{ev_rows}</table>
<p style="margin-top:10px;font-size:13px;color:var(--mut)">核心判斷：油價崩跌（伊朗戰爭暫停）＋殖利率回落＋半導體財報利多三線共振，確立風險偏好多頭延續；惟 7 月非農就業數據與英特爾封裝競爭消息為兩大變數，防禦紀律（00878 續建 4 週、00983D 暫緩、單筆≥5萬暫停）維持不變。</p></div>

<div class="card"><h2>三、持倉關聯分析 <span class="tag">逐檔檢視</span></h2>
<table><tr><th>標的</th><th>現價</th><th>今日</th><th>關聯分析</th><th>動作</th></tr>{hd_rows}</table></div>

<div class="card"><h2>四、資產配置透視 <span class="tag">snapshot penetration.actual_twd｜臨時階段目標：美股30/台股23.5/防守19/債券13/現金14.5</span></h2>
<table><tr><th>類別</th><th>金額 (TWD)</th><th>實際</th><th>目標</th><th>偏離</th><th>狀態</th></tr>{al_rows}</table>
<ul style="margin-top:10px">
<li>⚠️ 唯一大缺口：<b>台股市值型成長 -14.1pp</b>（9.4% vs 23.5%）— 屬預期低配，逐步架構回補、不強迫貼齊。</li>
<li>✅ 防守型配息 -0.2pp 幾乎達標；安全網（債券+現金）合計 35.9%，緩衝極度充足；現金為 6 個月生活費底線（851,748）之 <b>2.6 倍</b>。</li>
<li>美股 +5.9pp、債券 +5.0pp、現金 +3.4pp 超標 → 以「暫緩新增＋配息導流」自然收斂，不主動砍倉。</li>
</ul></div>

<div class="card"><h2>五、巴菲特/蒙格式建議 <span class="tag">臨時階段規則：00878續建4週｜00983D暫緩｜單筆≥5萬暫停｜現金底線6個月</span></h2>{sec5}</div>

<div class="card"><h2>六、風控檢查 <span class="tag">US30Y 防禦/凍結紅線｜國泰核貸</span></h2>{sec6}
<p style="margin-top:10px;font-size:13px;color:var(--mut)">結論：費半 +5.03% 與指數創高確立多頭延續，但 US30Y 5.202% 貼線 5.20% 防禦門檻、7 月非農將公布，防禦紀律照舊——00878 續建 4 週、台股小單低吸、00983D 暫緩、單筆≥5 萬暫停、現金底線 2.6 倍充足；30Y 殖利率與國泰核貸進度為兩大監控焦點。整體維持「防禦為先、分批再平衡」總基調。</p></div>

<footer>🐉 龍九控股 emergency response ｜ generated {subtitle} ｜ 數據來源：Yahoo Finance 即時（^GSPC/^IXIC/^DJI/^SOX/^TYX/TSM/NVDA...）、Google News RSS（NYT/WSJ/CNBC/Barron's/IBD）、snapshot.json（penetration.actual_twd）</footer>
</div></body></html>"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    print("written:", filename, len(html), "bytes")

# ============ 1. 寫入 LLM 分析 JSON ============
d = {"generated_at": NOW, "source": "美股緊急應變", "full_report": FULL_REPORT}
with open("data/emergency_llm_analysis.json", "w", encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, indent=2)
print("written: data/emergency_llm_analysis.json, full_report chars =", len(FULL_REPORT))

# ============ 2/3. 雙版 HTML ============
build("龍九控股｜美股緊急應變報告 2026-08-04", f"emergency_report_{TODAY}.html", f"{TODAY} 21:40 美股開盤")
build("龍九控股｜美股緊急應變報告 2026-08-04（GitHub 同步版）", f"emergency_taiex_report_{TODAY}.html", f"{TODAY} 21:40 美股開盤（GitHub Pages 同步）")
