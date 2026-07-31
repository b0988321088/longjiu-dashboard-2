# -*- coding: utf-8 -*-
"""美股緊急應變 2026-07-31 — 產出 JSON + Railway/GitHub 雙版 HTML"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
TODAY = "2026-07-31"

full_report = """🚨 龍九控股 — 美股緊急應變深度分析（21:30 美股開盤）
📅 2026-07-31 21:30 ET ｜ Chief Reporter / 美股危機應變官

【一、市場概況｜AI 財報行情續航：費半兩日強彈 +13.6%，三大指數開盤齊漲】
• 開盤即時（21:33 ET）：道瓊 52,396.78（+0.36%／+188.7）、納指 25,408.17（+1.14%／+286.0）、S&P 500 7,483.41（+0.62%／+45.8）— 連續第二日收復 7/29 Fed 鷹派重挫（道瓊單日 -1,100 點，2025/4 以來最差）
• 費城半導體 11,858.19（+4.91%）：7/30 大漲 +8.19% 後續強，兩日累計 +13.6%（10,447 → 11,858）；TSMC ADR 417.50（+3.53%）、NVDA 198.70（+1.88%）
• 個股強烈分化：AMZN 267.32（+13.51%，財報噴發）vs AAPL 301.69（-9.52%，賣事實）；META 554.83（+2.93%，自 7/30 -8% 反彈）；TSLA 313.93（+1.64%）
• 盤前期貨：ES 7,494.75（+0.30%）、NQ 28,546.5（+1.09%）— 科技領漲結構明確
• 避險/商品：VIX 17.06（-0.2%）風險偏好回歸；黃金 4,101（-1.43%）回落；原油 WTI 85.69（+2.51%）— 中東衝突溢價再起，通膨反轉風險未解
• 債市：10Y 4.704%（+0.88%）走升；30Y（US30Y）最新官方值 5.20%（7/29）恰觸防禦門檻（詳見第六章）

【二、重大事件分析｜四大驅動事件】
1. 🏛️ Fed 7/29 按兵不動但鷹派分裂：連續第 5 次維持 5.25%-5.50%，3 位委員異議（市場一度 price-in 升息風險）；主席 Warsh 面對債市「紅旗」（長債殖利率走高）。7/31 公布 6 月 PCE 3.7%（核心 3.3%）降溫，為盤前期貨提供支撐 — 短期「更高更久」定調，估值靠盈餘撐、不靠降息
2. 💻 科技財報超級週：MSFT 業績爆發（+15%，史上單日最大市值增幅，雲端+AI 加速）；盤後 AMZN Q2 大超預期（雲端銷售強勁、2026 資本開支上調至 $2,200 億、AI/晶片業務 $250 億 run rate）→ 今日 +13.5%；AAPL Q3 營收 $1,094 億/獲利 $298 億雖優於預期，但服務收入未達標＋AI 成本上揚、供應鏈拖累展望 → 「sell the news」-9.5%；META 獲利失望 -8% 後今日反彈
3. 🔥 半導體報復性反彈：AMD/Micron 大漲、Lam Research 單日 +17%；TSMC 利多簇擁（1.4nm 廠 2027/4 完工、AI 先進封裝對抗 Intel、亞利桑那再加碼 $1,000 億）— 大廠 AI 資本開支「不見放緩」是最強支撐
4. ⚠️ 地緣與油價：中東衝突升溫推 WTI 至 85.69（+2.51%），6 月通膨回落恐難延續；川普新一輪關稅（7/24 期限）持續壓抑企業利潤率 — 通膨黏著正是 Fed 鷹派分裂的主因

【三、持倉關聯分析｜逐檔影響】
台股部位（穿透 276.7 萬 TWD，昨收大漲 +8.15%，今日影響待週一 8/3 反映）：
• 0050（+21.1% 未實現）／006208（+19.2%）：台股權值與費半高度連動，費半兩日 +13.6% 為 8/3 開盤提供順風；但 AAPL -9.5% 對蘋概鏈是雜音，權值指數開高後防震盪
• 00878／00919／00713（防守型配息）：與美股連動低、配息現金流穩定，續建 4 週計畫不受影響；台股若週一高開，依鐵律暫停當週買單、回檔再承接
• 00983D（質押套利底倉）：波動極低，與美股風險脫鉤，維持底倉、不加碼
• 00646（元大 S&P500）：直接連動 S&P +0.62%，持倉受益，核貸期不加碼
美股部位（穿透 552.1 萬 TWD）：
• 貝萊德世界科技／安聯 AI 收益成長（美元基金）：直接暴露美股科技/AI，費半 +4.9%、納指 +1.1% 正面；但 AAPL 單日 -9.5% 顯示「財報驗證期」個股波動放大，基金淨值短線震盪難免
• 保單基金（合計 957.5 萬）：安聯 A 499.8 萬＋安聯 B 264.7 萬＋第一金連結安聯 AI 收益成長 193.0 萬 — 連動美股 AI/科技，屬長期持有，波動不影響現金流與核貸，續抱
• 衛星基金（貝萊德能源/黃金/多重收益等）：能源基金受惠油價 +2.5%，黃金基金隨金價 -1.4% 小回檔，佔比極小、不影響大局

【四、資產配置透視｜結構失衡：美股超標、台股與防守不足】（穿透 actual_twd，總資產 15,921,385 TWD）
• 美股 34.7%（5,521,150）vs 臨時目標 30% → +4.7pp ➖ 超標；核貸期暫緩減碼（避免帳戶流水震盪影響 8/4 撥款授信）
• 台股 17.4%（2,766,920）vs 23.5% → -6.1pp ⬆️ 最優先補強缺口，8/3-8/4 回檔分批小額承接
• 防守 12.4%（1,974,200）vs 19% → -6.6pp ⬆️ 00878 續建 4 週＋00919/00713 小額跟進
• 債券 17.1%（2,723,627）vs 13% → +4.1pp ⛔ 超標暫緩（00983D 暫緩、債券備用金維持現金）
• 現金 18.4%（2,935,488）vs 14.5% → +3.9pp 💰 保留（6 個月支出底線約 85-119 萬，現金為底線 2.5-3.5 倍；另為核貸撥款緩衝）

【五、巴菲特/蒙格式建議｜臨時階段紀律：分批、小額、不追高】
✅ 增持（維持原節奏）：00878 續建 4 週（每週小額、配息再投入）；台股 -6.1pp 缺口於 8/3-8/4 回檔時小額承接 0050/006208（每筆 <5 萬）
➖ 持有（不動）：美股 34.7% 已超標，今日開盤大漲不追高，8/4 核貸撥款前零新增；00646／貝萊德科技／安聯AI／保單基金全數續抱 — 巴菲特原則：不因單日波動賣出優質資產；AAPL 式單日 -9.5% 正是「持有指數/基金而非個股」的意義
⛔ 暫緩：00983D 暫緩新增（質押標的維持底倉）；債券類（PIMCO/00983D）於 US30Y ≥5.20% 防禦模式期間不新增
🚫 禁令：單筆 ≥5 萬申購全面暫停；現金 6 個月支出底線（約 85-119 萬）不可動用 — 目前 293.5 萬，安全邊際充足
🎯 蒙格式提醒：AMZN 資本開支 $2,200 億＋微軟/谷歌軍備競賽 → AI 利多出盡風險在 9 月後（Truist 亦警告 5-8% 下行空間）；趁波動分批、保留子彈，勝過單筆重押

【六、風控檢查｜US30Y 警戒升級、核貸倒數計時】
• US30Y 現值 5.20%（7/29 官方值）＝ 5.20% 防禦門檻「恰觸及」：7/28 為 5.09% → 目前僅 1 日達標，模式A（連續 2 交易日 ≥5.20%）尚未確立；7/30 官方值未公布，盤中 10Y 4.70%（+0.88%）走升、30Y 估 5.20-5.25% → 若連續確認即正式進入模式A：配息導流 → 逢反彈分批減碼美股科技 → 轉台股高股息
• 5.30% 債券凍結紅線：未觸及 → 債券新增未被「永久凍結」，但債券 17.1% 已超標，實務上持續暫緩（25% 債券備用金維持現金）
• 國泰核貸階段：核貸進行中、利率 2.6%、順延至 8/4（下週二）撥款＋舊貸清償（排程 🔴 重要）→ 撥款前維持帳戶流水穩定：零大額申購（≥5 萬）、零大額轉帳；8/4 資金到位後再啟動台股補強
• 台股 8/3 開盤三情境：① 樂觀（費半續強→跳空高開，鐵律暫停當週買單）② 中性（開高走低→回檔承接視窗）③ 悲觀（AAPL 拖累蘋概＋油價續漲→觀望至 8/4 核貸後再動作）
• 總評：系統性風險未解除（長債 5.2%、油價 85+、關稅、Fed 鷹派分裂），短線動能偏多；紀律優先於預測 — 不追高、分批買、留子彈、等核貸"""

# 1) JSON
d = {
    "generated_at": "2026-07-31 21:35",
    "source": "美股緊急應變",
    "full_report": full_report,
}
(BASE / "data" / "emergency_llm_analysis.json").write_text(
    json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
n = len(full_report)
print(f"✅ JSON 寫入，full_report 長度 = {n} 字元（需 >1500）")

# 2) HTML 共用
market_rows = [
    ("S&P 500", "SPX", "7,483.41", "+45.78", "+0.62%", "up", "✅ 上漲"),
    ("道瓊工業", "DJI", "52,396.78", "+188.72", "+0.36%", "up", "✅ 上漲"),
    ("納斯達克", "IXIC", "25,408.17", "+285.99", "+1.14%", "up", "✅ 上漲"),
    ("費城半導體", "SOX", "11,858.19", "+555.20", "+4.91%", "up", "🚀 強漲"),
    ("TSMC ADR", "TSM", "417.50", "+14.23", "+3.53%", "up", "✅ 上漲"),
    ("NVIDIA", "NVDA", "198.70", "+3.66", "+1.88%", "up", "✅ 上漲"),
    ("Tesla", "TSLA", "313.93", "+5.08", "+1.64%", "up", "✅ 上漲"),
    ("Apple", "AAPL", "301.69", "-31.74", "-9.52%", "down", "⚠️ 財報賣壓"),
    ("Meta", "META", "554.83", "+15.80", "+2.93%", "up", "✅ 反彈"),
    ("Amazon", "AMZN", "267.32", "+31.82", "+13.51%", "up", "🚀 財報噴發"),
    ("S&P 期貨", "ES=F", "7,494.75", "+22.25", "+0.30%", "up", "➖ 平穩"),
    ("那斯達克期貨", "NQ=F", "28,546.5", "+308.75", "+1.09%", "up", "✅ 走強"),
    ("VIX 恐慌指數", "VIX", "17.06", "-0.03", "-0.18%", "down", "✅ 降溫"),
    ("10Y 美債殖利率", "TNX", "4.704%", "+0.041", "+0.88%", "down", "⚠️ 走升"),
    ("30Y 美債殖利率", "US30Y", "5.20%", "—", "防禦門檻", "down", "🚨 警戒"),
    ("黃金期貨", "GC=F", "4,101.0", "-59.6", "-1.43%", "down", "➖ 回落"),
    ("原油 WTI", "CL=F", "85.69", "+2.10", "+2.51%", "up", "⚠️ 中東溢價"),
]

def render_report(txt):
    out = []
    for line in txt.splitlines():
        if line.startswith("【"):
            out.append(f'<h3 class="sec-title">{line}</h3>')
        elif line.strip():
            out.append(f'<p class="rline">{line}</p>')
    return "\n".join(out)

css = """* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Segoe UI','PingFang TC','Microsoft JhengHei',sans-serif; background:#0a0e1a; color:#e0e0e0; padding:20px; }
.container { max-width:1200px; margin:0 auto; }
.header { background:linear-gradient(135deg,#1a1f3a,#0d1b2a); padding:25px; border-radius:12px; margin-bottom:20px; border:1px solid #2a3f5f; }
.header h1 { color:#ff4444; font-size:24px; margin-bottom:8px; }
.header h1::before { content:"🚨 "; }
.header .meta { color:#8899aa; font-size:13px; }
.alert-bar { background:#3a1a1a; border:1px solid #ff4444; padding:12px 20px; border-radius:8px; margin-bottom:20px; display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.alert-bar .level { background:#ff4444; color:#fff; padding:4px 12px; border-radius:4px; font-weight:bold; font-size:14px; }
.alert-bar .msg { color:#ff9999; font-size:14px; }
.section { background:#111827; border-radius:10px; padding:20px; margin-bottom:20px; border:1px solid #1e293b; }
.section h2 { color:#60a5fa; font-size:18px; margin-bottom:15px; padding-bottom:8px; border-bottom:1px solid #1e293b; }
.sec-title { color:#93c5fd; font-size:15px; margin:16px 0 8px; border-left:4px solid #60a5fa; padding-left:10px; }
.rline { color:#cbd5e1; font-size:13.5px; line-height:1.75; margin-bottom:6px; }
table { width:100%; border-collapse:collapse; margin-bottom:10px; font-size:13px; }
th { background:#1a2340; color:#93c5fd; padding:8px 12px; text-align:left; border:1px solid #2a3f5f; }
td { padding:8px 12px; border:1px solid #1e293b; }
tr:nth-child(even) { background:#0f172a; }
tr:nth-child(odd) { background:#111827; }
.up { color:#22c55e; font-weight:bold; }
.down { color:#ef4444; font-weight:bold; }
.risk-box { display:inline-block; padding:4px 10px; border-radius:4px; font-weight:bold; font-size:12px; }
.risk-high { background:#7f1d1d; color:#fca5a5; }
.risk-med { background:#713f12; color:#fde68a; }
.risk-low { background:#14532d; color:#86efac; }
.footer { text-align:center; color:#475569; font-size:12px; padding:20px; }
@media (max-width:768px){ body{ padding:10px; } }"""

def build_html(title, subtitle):
    rows = ""
    for name, code, price, chg, pct, cls, status in market_rows:
        rows += (f'<tr><td>{name}</td><td>{code}</td><td>{price}</td>'
                 f'<td class="{cls}">{chg}</td><td class="{cls}">{pct}</td>'
                 f'<td><span class="risk-box {"risk-high" if cls=="down" else "risk-low"}">{status}</span></td></tr>')
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>美股緊急應變分析報告</h1>
<div class="meta">{subtitle}</div>
</div>
<div class="alert-bar">
<span class="level">⚠️ 警戒</span>
<span class="msg">AI 財報行情續航、費半兩日 +13.6%；但 AAPL -9.52% 賣事實、US30Y 5.20% 恰觸防禦門檻、8/4 國泰核貸倒數 — 不追高、分批買、留子彈</span>
</div>
<div class="section">
<h2>📈 市場即時數據（2026-07-31 21:33 ET 開盤即時）</h2>
<table>
<tr><th>標的</th><th>代碼</th><th>現價</th><th>漲跌</th><th>漲跌幅</th><th>狀態</th></tr>
{rows}
</table>
</div>
<div class="section">
<h2>🧠 LLM 六大章節深度分析</h2>
{render_report(full_report)}
</div>
<div class="footer">龍九控股 Chief Reporter + 美股危機應變官 ｜ 自動化管線 2026-07-31 21:35 生成</div>
</div>
</body>
</html>"""

railway = build_html("美股緊急應變報告 2026-07-31", "生成時間：2026-07-31 21:35（台北）｜ 龍九控股 Chief Reporter + 美股危機應變官")
(BASE / f"emergency_report_{TODAY}.html").write_text(railway, encoding="utf-8")
(BASE / f"emergency_taiex_report_{TODAY}.html").write_text(railway, encoding="utf-8")
print(f"✅ emergency_report_{TODAY}.html ({len(railway):,} bytes)")
print(f"✅ emergency_taiex_report_{TODAY}.html ({len(railway):,} bytes)")
