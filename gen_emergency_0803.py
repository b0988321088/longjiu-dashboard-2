#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_emergency_0803.py — 台股緊急應變 13:30 完整六大章節分析
產出: data/emergency_llm_analysis.json + emergency_report_2026-08-03.html (Railway) + emergency_taiex_report_2026-08-03.html (GitHub)
"""
import json, datetime, html
from pathlib import Path

BASE = Path(__file__).resolve().parent
TODAY = "2026-08-03"
NOW = "2026-08-03 13:30"

# ── 市場數據（8/3 午盤，來源: Yahoo Finance 即時 + 系統 daily_analysis）──
MARKET = {
    "twii": "43,436.17 (+0.73%)",
    "twii_note": "早盤一度下探 -339 點後翻紅震盪（7/31 歷史最大漲點 +3,186 點後的獲利了結）",
    "tsm": "2,375.00 (-2.06%)",
    "sox": "11,311.08 (+0.07%)",
    "us": "道瓊 52,485.03 (+0.53%) / 納指 25,373.85 (+1.00%) / S&P 7,489.72 (+0.70%)",
    "cpi": "美國 6 月 CPI YoY 3.5% (預期 3.8%)；Core 2.6% (預期 2.8%)",
    "foreign": "7日淨流無即時數據；7/31 外資+投信大舉掃貨半導體/封測，今日轉調節觀望（7/24 曾單日賣超約600億）",
}

# 持倉即時漲跌（Yahoo Finance 8/3 vs 7/31 收盤）
HOLDINGS = [
    ("0050", "元大台灣50", "102.05", "-0.78%", "台積電權重約五成，直接受 TSM -2.06% 拖累；大盤翻紅略收斂。帳面 +21%（成本84.9）", "持有"),
    ("006208", "富邦台50", "233.30", "-0.87%", "與0050同邏輯，跌幅主要來自台積電權重；帳面 +19%", "持有"),
    ("00878", "國泰永續高股息", "32.65", "+0.68%", "逆勢上漲！高股息防禦屬性在震盪中獲資金流入；8月除權息旺季，續建4週策略不受影響", "增持"),
    ("00919", "群益台灣精選高息", "29.54", "-0.10%", "平盤，殖利率保護；帳面 +0.1% 微幅正報酬", "持有"),
    ("00983D", "主動富邦複合收益", "10.10", "-0.20%", "複合收益型；US30Y 5.21% 防禦模式下維持底倉、暫緩新增（臨時階段規則）", "暫緩"),
    ("00646", "元大S&P500", "76.70", "+0.66%", "美股 7/31 收高（納指+1.00%），受惠 CPI 降溫與降息預期", "持有"),
    ("009823", "群益S&P500", "10.33", "≈0.0%", "美股寬基，跟隨美股走升；美股佔比超標不追高", "持有"),
    ("00924", "群益美國科技巨頭", "32.90", "+1.29%", "美股科技今日最強；但模式A禁令：不加碼美股長久期科技", "減碼候選"),
    ("00713", "元大台灣高息低波", "61.00", "-0.33%", "低波高息，防守補碼候選（小額分批）", "持有"),
    ("保單基金", "安聯/第一金 保單", "—", "—", "配息 SOP 維持 hold；保單 relay 最晚申請日才轉換，無 30 分鐘轉換風險", "持有"),
]

# 資產配置（snapshot penetration.actual_twd，總投資 15,975,619）
ALLOC = [
    ("台股市值型成長", "3,281,225", "20.5%", "23.5%", "-3.0pp", "略低"),
    ("美股市值型成長", "5,152,391", "32.3%", "30.0%", "+2.3pp", "超標"),
    ("防守型配息", "1,881,453", "11.8%", "19.0%", "-7.2pp", "嚴重不足"),
    ("債券", "2,723,627", "17.0%", "13.0%", "+4.0pp", "超標"),
    ("現金/安全網", "2,936,923", "18.4%", "14.5%", "+3.9pp", "超標"),
]

NEWS = [
    ("7/31 台股暴漲 3,186 點創歷史最大漲點，重返 4.3 萬大關；投信與外資大舉掃貨半導體/封測族群",
     "sinotrade 豐雲學堂 / ETtoday", "高", "今日為漲多後技術性換手，非趨勢反轉"),
    ("台積電跌 50 元至 2,375，台股跌 339 點後翻紅震盪",
     "ETtoday 財經雲", "高", "賣出訊號主因：漲多回吐 + 英特爾先進封裝消息"),
    ("英特爾先進封裝良率直逼 90%、成本低 5 成（CoWoS 潛在競爭）",
     "自由財經 / ETtoday", "中高", "消息面短線干擾；高盛同步釋出台積電 2027 漲價近 10% 利多"),
    ("高盛：台積電 2027 年或漲價近 10%，AI ASIC 將超越 GPU",
     "鉅亨網 news.cnyes.com", "中高", "基本面未壞，長線動能仍在"),
    ("大摩上調韓股至增持，目標 9,000 點（+36% 空間）",
     "Yahoo奇摩股市", "中高", "亞洲科技股評價外溢利多，對台股半導體正面"),
    ("美國 6 月 CPI 3.5%（預期3.8%）、核心 2.6%（預期2.8%）雙低於預期",
     "系統情報源", "高", "降息預期升溫，美股週五收高；US30Y 5.21% 仍在防禦門檻上方"),
    ("印度達拉街本週聚焦 RBI 貨幣政策與 Q1 財報，外資流向牽動市場",
     "商傳媒 / Yahoo奇摩股市", "中", "新興市場資金流動本週波動加大，間接影響外資動向"),
]

# ── 六大章節全文（>1500 字元）──
REPORT = f"""🚨 龍九控股 — 台股緊急應變報告（{TODAY} 13:30 午盤）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【一、市場概況】
• 加權指數：{MARKET['twii']}；{MARKET['twii_note']}。盤中成交量維持破兆元常態水準，市場情緒偏多但波動明顯放大。
• 台積電：{MARKET['tsm']}（跌50元），為今日唯一重大賣出訊號。
• 費城半導體指數：{MARKET['sox']}，AI 半導體盤勢平穩。
• 美股（7/31 收）：{MARKET['us']}。
• 外資動向：{MARKET['foreign']}。
【二、重大事件分析】
1. 7/31 台股暴漲 3,186 點創歷史最大漲點：加權指數重返 4.3 萬大關，台積電與大盤同創單日最大漲勢，投信外資大舉回補半導體與封測族群。今日（8/3）早盤一度 -339 點屬漲多後的獲利了結與技術性換手，屬正常整理而非趨勢反轉。
2. 台積電 -2.06%（跌50元至2,375）：雙重壓力——(a) 短線漲多回吐；(b) 傳英特爾先進封裝良率直逼 90%、成本低 5 成，市場憂心 CoWoS 壟斷地位受挑戰。但高盛同步發布「台積電 2027 年可望漲價近 10%、AI ASIC 將超越 GPU」利多，基本面並未惡化，屬消息面短線干擾。
3. 大摩上調韓股至「增持」、目標 9,000 點（+36% 空間）：韓股自 6 月底高點回跌逾 30%、36 萬個保證金帳戶強平後估值重置，外資開始回補亞洲科技股；對台股半導體評價具外溢利多。
4. 美國 6 月 CPI 3.5%（預期3.8%）、核心 2.6%（預期2.8%）雙雙低於預期：降息預期升溫，美股週五收高；美債殖利率回落至 US30Y 5.21%，仍在 5.20% 防禦門檻上方。
5. 印度達拉街本週迎 RBI 貨幣政策決策與 Q1 財報（8/5 前後）：新興市場資金流向本週波動加大，對台股外資動向有間接影響，列為觀察項。
（新聞來源與可信度標記：ETtoday／sinotrade 豐雲學堂／自由財經／經濟日報／鉅亨網／Yahoo奇摩股市／商傳媒；主流財經媒體即時報導，可信度 高~中高）
【三、持倉關聯分析】（即時報價為 8/3 午盤 vs 7/31 收盤）
• 0050 元大台灣50：102.05（-0.78%）— 台積電權重約五成，直接受 TSM -2.06% 拖累；大盤翻紅略收斂跌幅。帳面 +21%（成本84.9），持有不砍倉。
• 006208 富邦台50：233.30（-0.87%）— 與 0050 同邏輯，跌幅主要來自台積電權重，帳面 +19%，持有。
• 00878 國泰永續高股息：32.65（+0.68%）— 逆勢上漲！高股息防禦屬性在震盪中獲資金流入；8 月除權息旺季，續建 4 週策略不受影響。
• 00919 群益精選高息：29.54（-0.10%）— 平盤，殖利率保護，帳面微幅正報酬，持有。
• 00983D 主動富邦複合收益：10.10（-0.20%）— 複合收益型；US30Y 5.21% 防禦模式下維持底倉、暫緩新增（依臨時階段規則）。
• 美股 ETF：00646 S&P500 76.70（+0.66%）、009823 S&P500 10.33（持平）、00924 美股科技 32.90（+1.29%）— 受惠 CPI 降溫與降息預期；但美股佔比已超標，不追高。
• 台股高息衛星（00713 -0.33%／0056／00918／00888／00984A）：多數抗跌，防守型配息組合表現穩健。
• 保單基金（安聯、第一金）：配息 SOP 維持 hold，保單 relay 最晚申請日才轉換，無 30 分鐘轉換風險。
【四、資產配置透視】（snapshot penetration.actual_twd；總投資 15,975,619 TWD；臨時階段目標：美股30／台股23.5／防守19／債券13／現金14.5）
• 台股市值型成長 3,281,225（20.5%）vs 23.5% → -3.0pp 略低
• 美股市值型成長 5,152,391（32.3%）vs 30.0% → +2.3pp 超標
• 防守型配息 1,881,453（11.8%）vs 19.0% → -7.2pp ⚠️ 最大偏離
• 債券 2,723,627（17.0%）vs 13.0% → +4.0pp 超標
• 現金/安全網 2,936,923（18.4%）vs 14.5% → +3.9pp 超標
關鍵結論：防守型配息嚴重不足（-7.2pp）為唯一結構性缺口；債券+現金合計安全網 35.4%，緩衝充足。現金 2,936,923 為 6 個月生活費底線（141,958×6=851,748）之 3.4 倍，安全邊際穩健（runway 27.1 個月）。
【五、巴菲特/蒙格式建議】（臨時階段規則：00878 續建4週、00983D 暫緩、單筆≥5萬暫停、現金底線6個月）
• 增持：00878 依計畫續建 4 週（今日逆勢 +0.68% 驗證防禦屬性）；防守型配息（00878/00713/0056 等）以每筆 <5 萬元分批補碼，逐步將防守 11.8% 補向 19%，優先處理最大偏離。
• 持有：0050/006208（台股核心，跌勢屬台積電權重拖累，不砍倉）；00919（配息保護）；美股 ETF（超標不追高，靠配息導流自然降槓）。
• 減碼：美股 32.3% > 30% 目標 — 依模式A策略「逢反彈分批減碼美股科技（00924 為候選）」，資金轉往台股高股息；受限單筆≥5萬暫停令，改分批小額執行。
• 暫緩：00983D 新增（防禦模式+複合債券）；債券類 17.0% 已超標 4pp，不新增；單筆 ≥5 萬元買單全數暫停；不加碼美股長久期科技。
• 現金紀律：現金 18.4% > 14.5% 目標，但高於 6 個月生活費底線 3.4 倍，緩衝充足；若防守補碼使現金降至 15% 以下即停止補碼。
巴菲特視角：不因單日 -339 點或 +3,186 點改變紀律；用配息導流而非砍倉來再平衡，符合「別人恐懼我貪婪」精神，惟受單筆≥5萬暫停令約束，採小額分批、以時間換空間。
【六、風控檢查】
• US30Y 現值：5.21%（2026-07-30 最新，FRED DGS30）
  – 5.20% 防禦門檻：✅ 已觸發（7/29=5.20%、7/30=5.21% 連續2日達標 → 模式A 防禦，streak=1）
  – 5.30% 凍結紅線：✅ 未觸發（5.21% < 5.30%）→ 長期債券未被永久凍結；惟依模式A禁令「不新增債券、00983D/PIMCO 維持底倉」
  – 10年期美債 4.68%，長短天期利差結構正常
• 國泰核貸狀態：核貸進行中，順延至 8/4（下週二）撥款，利率 2.6%；撥款前不預支加碼，撥款後依防守補碼計畫小額分批執行。
• 其他：三筆永豐房貸正常繳納；大義街房貸已清償 ✅；四大信用卡列管正常；配息 SOP hold、無 30 分鐘轉換風險。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
結論：今日為 7/31 歷史大漲後的技術性整理，台積電因英特爾封裝消息 -2.06% 為主要賣出訊號，惟基本面（高盛漲價論、CPI 降溫）未變。最大結構問題仍是防守型配息 -7.2pp 缺口；依臨時階段規則：00878 續建 4 週、小額分批補防守、00983D 與單筆≥5萬暫緩、現金安全網充足。整體維持「防禦為先、分批再平衡」總基調。數據來源：Yahoo Finance 即時報價、FRED DGS30/DGS10、snapshot.json、daily_analysis.json。"""


def build_html() -> str:
    alloc_rows = "".join(
        f"<tr><td>{a}</td><td class='num'>{v}</td><td class='num'>{p}</td>"
        f"<td class='num'>{t}</td><td class='num {'neg' if '-' in g else 'pos'}'>{g}</td>"
        f"<td><span class='badge {'warn' if '不足' in s else 'ok' if s=='略低' else 'over'}'>{s}</span></td></tr>"
        for a, v, p, t, g, s in ALLOC
    )
    hold_rows = "".join(
        f"<tr><td><b>{t}</b><br><small>{n}</small></td><td class='num'>{px}</td>"
        f"<td class='num {'pos' if chg.startswith('+') else 'neg'}'>{chg}</td><td>{note}</td>"
        f"<td><span class='badge {'buy' if act=='增持' else 'hold' if act=='持有' else 'pause' if act=='暫緩' else 'over'}'>{act}</span></td></tr>"
        for t, n, px, chg, note, act in HOLDINGS
    )
    news_rows = "".join(
        f"<tr><td>{t}</td><td>{src}</td><td><span class='badge cred'>{cred}</span></td><td>{imp}</td></tr>"
        for t, src, cred, imp in NEWS
    )
    return f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>龍九控股｜台股緊急應變報告 {TODAY}</title>
<style>
:root{{--bg:#0d1117;--card:#161b22;--line:#30363d;--tx:#e6edf3;--mut:#8b949e;
--red:#f85149;--grn:#3fb950;--yel:#d29922;--blu:#58a6ff;--pur:#bc8cff}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--tx);font-family:'Segoe UI','Noto Sans TC','Microsoft JhengHei',sans-serif;line-height:1.65;padding:24px}}
.wrap{{max-width:980px;margin:0 auto}}
header{{border:1px solid var(--line);border-radius:12px;padding:22px 26px;background:linear-gradient(135deg,#1a2332,#161b22);margin-bottom:20px}}
header h1{{font-size:26px;letter-spacing:1px}}
header .sub{{color:var(--mut);margin-top:6px;font-size:14px}}
.alert-bar{{margin:14px 0 4px;padding:10px 16px;border-radius:8px;background:rgba(248,81,73,.12);border:1px solid rgba(248,81,73,.4);font-weight:600}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 24px;margin-bottom:18px}}
.card h2{{font-size:19px;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--line);color:var(--blu)}}
.card h2 .tag{{float:right;font-size:12px;color:var(--mut);font-weight:400}}
ul{{padding-left:22px}} li{{margin:5px 0}}
table{{width:100%;border-collapse:collapse;margin-top:10px;font-size:14px}}
th,td{{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}}
th{{background:#21262d;font-size:13px;white-space:nowrap}}
.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
.pos{{color:var(--grn)}} .neg{{color:var(--red)}}
.badge{{display:inline-block;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:600;white-space:nowrap}}
.badge.buy{{background:rgba(63,185,80,.15);color:var(--grn);border:1px solid var(--grn)}}
.badge.hold{{background:rgba(88,166,255,.12);color:var(--blu);border:1px solid var(--blu)}}
.badge.pause{{background:rgba(210,153,34,.12);color:var(--yel);border:1px solid var(--yel)}}
.badge.over{{background:rgba(248,81,73,.12);color:var(--red);border:1px solid var(--red)}}
.badge.warn{{background:rgba(248,81,73,.15);color:var(--red);border:1px solid var(--red)}}
.badge.ok{{background:rgba(63,185,80,.12);color:var(--grn);border:1px solid var(--grn)}}
.badge.cred{{background:rgba(188,140,255,.12);color:var(--pur);border:1px solid var(--pur)}}
.kpi{{display:flex;flex-wrap:wrap;gap:12px;margin-top:12px}}
.kpi .box{{flex:1;min-width:150px;background:#21262d;border:1px solid var(--line);border-radius:10px;padding:12px 14px}}
.kpi .box .lbl{{font-size:12px;color:var(--mut)}} .kpi .box .val{{font-size:20px;font-weight:700;margin-top:2px}}
.risk-line{{padding:8px 12px;border-radius:8px;margin:6px 0;background:#21262d;border-left:4px solid var(--blu)}}
footer{{color:var(--mut);font-size:12px;text-align:center;margin-top:24px}}
</style></head><body><div class="wrap">

<header>
<h1>🐉 龍九控股 — 台股緊急應變報告</h1>
<div class="sub">📅 {TODAY} 13:30 午盤｜Chief Reporter + 台股危機應變官｜六大章節完整版</div>
<div class="alert-bar">⚠️ 賣出訊號：台積電 -2.06%（跌50元至2,375）｜🛡️ 結構缺口：防守型配息 -7.2pp｜🌡️ US30Y 5.21%（模式A 防禦，未觸及 5.30% 紅線）</div>
</header>

<div class="kpi">
<div class="box"><div class="lbl">加權指數</div><div class="val">{MARKET['twii'].split(' ')[0]}</div><div class="lbl">{MARKET['twii']}</div></div>
<div class="box"><div class="lbl">台積電</div><div class="val neg">2,375.00</div><div class="lbl">-2.06%</div></div>
<div class="box"><div class="lbl">費城半導體</div><div class="val">{MARKET['sox'].split(' ')[0]}</div><div class="lbl">{MARKET['sox']}</div></div>
<div class="box"><div class="lbl">總投資部位</div><div class="val">15,975,619</div><div class="lbl">TWD（snapshot）</div></div>
<div class="box"><div class="lbl">US30Y</div><div class="val" style="color:var(--yel)">5.21%</div><div class="lbl">防禦 5.20% / 紅線 5.30%</div></div>
</div>

<div class="card"><h2>一、市場概況 <span class="tag">Yahoo Finance 即時 + 系統情報</span></h2>
<ul>
<li><b>加權指數：{MARKET['twii']}</b> — {MARKET['twii_note']}。成交量維持破兆元常態水準。</li>
<li><b>台積電：{MARKET['tsm']}</b>（跌50元），今日唯一重大賣出訊號。</li>
<li><b>費半：{MARKET['sox']}</b>｜<b>美股（7/31收）：{MARKET['us']}</b></li>
<li><b>外資動向：</b>{MARKET['foreign']}</li>
</ul></div>

<div class="card"><h2>二、重大事件分析 <span class="tag">5 大驅動事件</span></h2>
<table><tr><th style="width:34%">事件</th><th>來源／可信度</th><th style="width:38%">對龍九持倉之意涵</th></tr>
{news_rows}
</table>
<p style="margin-top:10px;font-size:13px;color:var(--mut)">核心判斷：8/3 為 7/31 歷史最大漲點（+3,186）後的技術性整理；台積電受英特爾封裝消息短線干擾，基本面（高盛 2027 漲價論、CPI 降溫）未變。</p>
</div>

<div class="card"><h2>三、持倉關聯分析 <span class="tag">即時報價 vs 7/31 收盤</span></h2>
<table><tr><th>標的</th><th>現價</th><th>今日</th><th>關聯分析</th><th>動作</th></tr>
{hold_rows}
</table></div>

<div class="card"><h2>四、資產配置透視 <span class="tag">snapshot penetration.actual_twd｜臨時階段目標</span></h2>
<table><tr><th>類別</th><th>金額 (TWD)</th><th>實際</th><th>目標</th><th>偏離</th><th>狀態</th></tr>
{alloc_rows}
</table>
<ul style="margin-top:10px">
<li>⚠️ 唯一結構缺口：<b>防守型配息 -7.2pp</b>（11.8% vs 19%），優先處理最大偏離。</li>
<li>✅ 安全網（債券+現金）合計 35.4%，緩衝充足；現金為 6 個月生活費底線（851,748）之 <b>3.4 倍</b>，runway 27.1 個月。</li>
<li>美股 +2.3pp、債券 +4.0pp、現金 +3.9pp 超標 → 以「配息導流 + 暫緩新增」自然收斂，不主動砍倉。</li>
</ul></div>

<div class="card"><h2>五、巴菲特／蒙格式建議 <span class="tag">臨時階段規則：00878續建4週｜00983D暫緩｜單筆≥5萬暫停｜現金底線6個月</span></h2>
<ul>
<li><span class="badge buy">增持</span> <b>00878 續建 4 週</b>（今日逆勢 +0.68% 驗證防禦屬性）；防守型配息（00878/00713/0056）以每筆 &lt;5 萬元分批補碼，11.8% → 19%。</li>
<li><span class="badge hold">持有</span> 0050／006208（台股核心，跌勢為台積電權重拖累，不砍倉）；00919（配息保護）；美股 ETF（超標不追高）。</li>
<li><span class="badge over">減碼</span> 美股 32.3% &gt; 30% — 依模式A「逢反彈分批減碼美股科技（00924 候選）」，資金轉台股高股息。</li>
<li><span class="badge pause">暫緩</span> 00983D 新增、債券類新增（17.0% 已超標 4pp）、單筆 ≥5 萬元買單、美股長久期科技加碼。</li>
<li>💰 現金紀律：現金 18.4% 高於目標但為底線 3.4 倍；防守補碼使現金降至 15% 以下即停止。</li>
<li>🧓 巴菲特視角：不因單日 ±3,000 點級波動改變紀律；以配息導流而非砍倉再平衡，小額分批、以時間換空間。</li>
</ul></div>

<div class="card"><h2>六、風控檢查 <span class="tag">US30Y 防禦/凍結 + 國泰核貸</span></h2>
<div class="risk-line" style="border-left-color:var(--yel)">🌡️ <b>US30Y 現值 5.21%</b>（2026-07-30，FRED DGS30）— <b>已觸發 5.20% 防禦門檻</b>（7/29=5.20%、7/30=5.21% 連續2日 → 模式A 防禦，streak=1）</div>
<div class="risk-line" style="border-left-color:var(--grn)">✅ <b>5.30% 凍結紅線：未觸發</b>（5.21% &lt; 5.30%）— 長期債券未被永久凍結；惟依模式A禁令：不新增債券、00983D/PIMCO 維持底倉。10Y 4.68%，利差結構正常。</div>
<div class="risk-line" style="border-left-color:var(--blu)">🏦 <b>國泰核貸：核貸進行中，順延至 8/4（下週二）撥款，利率 2.6%</b> — 撥款前不預支加碼；撥款後依防守補碼計畫小額分批執行。</div>
<div class="risk-line" style="border-left-color:var(--blu)">✅ 三筆永豐房貸正常；大義街房貸已清償；四大信用卡列管正常；配息 SOP hold、無 30 分鐘轉換風險。</div>
</div>

<footer>🐉 龍九控股 Chief Reporter｜台股緊急應變｜{TODAY} 13:30｜數據來源：Yahoo Finance、FRED DGS30/DGS10、snapshot.json、daily_analysis.json（tw.stock.yahoo.com 新聞附來源/可信度標記）</footer>
</div></body></html>"""


def main():
    # 1) JSON
    d = {"generated_at": NOW, "source": "台股緊急應變", "full_report": REPORT}
    (BASE / "data" / "emergency_llm_analysis.json").write_text(
        json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(REPORT)
    print(f"[OK] emergency_llm_analysis.json written, full_report length = {n} chars")
    assert n > 1500, "full_report too short!"

    # 2) Railway + GitHub HTML
    h = build_html()
    (BASE / f"emergency_report_{TODAY}.html").write_text(h, encoding="utf-8")
    (BASE / f"emergency_taiex_report_{TODAY}.html").write_text(h, encoding="utf-8")
    print(f"[OK] emergency_report_{TODAY}.html + emergency_taiex_report_{TODAY}.html written ({len(h)} bytes each)")


if __name__ == "__main__":
    main()
