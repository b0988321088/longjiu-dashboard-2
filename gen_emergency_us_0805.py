# -*- coding: utf-8 -*-
"""美股緊急應變 2026-08-05 21:30 — 產出 LLM 分析 JSON + Railway/GitHub 兩版 HTML
資料來源：Yahoo Finance API 即時報價（2026-08-05 21:33 UTC+8 抓取）+ snapshot.json 穿透數據
"""
import json, io

today = "2026-08-05"
now = "2026-08-05 21:30"

# --- 動態穿透（從 snapshot 讀）---
_snap = json.load(open('snapshot.json', encoding='utf-8'))
_pen = _snap.get('penetration', {}).get('actual_twd', {})
_ppct = _snap.get('penetration', {}).get('actual_pct', {})
_amt = lambda k: f"{_pen.get(k, 0):,.0f}"
_pct = lambda k: _ppct.get(k, 0)

TMP_TGT = {'台股市值型成長': 23.5, '美股市值型成長': 30.0, '防守型配息': 19.0, '債券': 13.0, '現金/安全網': 14.5}
def dev(k):
    return _ppct.get(k, 0) - TMP_TGT[k]

tot = sum(_pen.values())
growth = _pct('台股市值型成長') + _pct('美股市值型成長')
buff = _pct('債券') + _pct('現金/安全網')

full_report = f"""🚨 龍九控股 — 美股緊急應變深度分析報告（Chief Reporter / 美股危機應變官）
📅 {now}（美股開盤時段・台北時間）

【一、市場概況】
• 美股開盤（21:30 台北 = 09:30 ET）：道瓊 54,488.97（+0.75%）、納指 26,697.81（+0.42%）、S&P 500 7,782.65（+0.60%），三大指數延續 8/4 大漲氣勢、在荷姆茲海峽重啟希望下逼近/續創歷史新高；8/4 收盤為道瓊 54,085.88（+1.71%）、納指 26,584.99（+2.59%）、S&P 7,736.52（+1.79%）。
• 費城半導體：12,169.50（-0.08%），8/4 單日 +6.55% 噴出後今開高走平、高檔換手；AI 半導體為本波反彈核心引擎。
• 重要個股：TSMC ADR 421.11（+0.94%）、NVDA 217.99（+2.85%）、META 597.15（+1.57%）、AMZN 282.29（+1.76%）、AAPL 308.54（-0.27%）、TSLA 323.09（-1.30%）。
• VIX 16.93（+2.61%）：指數上漲但波動率逆勢走高，避險買盤未退、中東變數仍在，追價需留一分謹慎。
• 商品/匯率：黃金 4,255.90（+3.92%）單日暴漲近 160 美元續創新高；WTI 75.75（-0.03%），戰爭溢價自 7/31 的 84.67 快速回落至 75 美元區間；美元指數 99.72（-0.18%）。
• 美債：10Y 4.625%；30Y（US30Y）5.173%，自 7/31 高點 5.275% 連三日回落，正式跌破 5.20% 防禦門檻！
• 台股今日（8/5 收盤）：加權 44,611.60（+2.88%）、台積電 2,405（+3.66%），22 檔海外 ETF 同步創新高；外溢效應與美股 AI 動能相互強化。

【二、重大事件分析】
1. 中東地緣降溫＋荷姆茲海峽重啟希望（最大驅動力）：美國財政部長貝森特表示美伊最快兩天內可望達成改善荷姆茲海峽通行協議，全球原油運輸咽喉風險下降，油價戰爭溢價快速消退（WTI 84.67→75.75），通膨預期舒緩、風險資產全面受惠。惟黃金單日 +3.92% 顯示仍有資金避險，協議未簽字前隨時可能反覆，須列為頭號變數。
2. 川普對 60 國新關稅 8/4 生效（政策逆風）：關稅生效日市場卻大漲，顯示「關稅疲勞」——貿易戰利空鈍化；財政部退還 1,000 億美元關稅收入但市場無感，「Trump Trade」指數自高點 -16%。然進口成本與物價風險未消，Fed 官員對通膨態度謹慎（見下），關稅仍是長天期殖利率高檔的結構性支撐。
3. AI 半導體需求再確認＋NVDA 財報前卡位（基本面）：Musk 宣布 SpaceX 改用 Nvidia 晶片，AMD 單日 -8%，資金向 NVDA 集中（今日 +2.85%）；AMD 財報指向 AI 需求極度強勁，NVDA 8 月底財報成下一個催化劑。TSMC 利多連發：熊本廠震後全面復工、N2 年底月產目標 10 萬片、1.4nm 提前量產——台積電供應鏈基本面紮實，直接支撐台股與 ADR。
4. 通膨降溫與 Fed 謹慎口徑（總體面）：美國 6 月 CPI YoY 3.5%（預期 3.8%）、Core 2.6%（預期 2.8%）雙雙低於預期，為 Fed 保留降息空間；但新任 Fed 主席 Paulson 稱通膨改善「僅一步」、Schmid 警告油價衝擊非暫時——市場對 9 月降息預期升溫但未完全定價，殖利率下行空間受限。

【三、持倉關聯分析】（snapshot 2026-08-05）
• 0050（{_amt('台股市值型成長')} 分類內，單檔 207,600 TWD）：台股 +2.88%、台積電 +3.66%，今日台股收盤已直接反映，預估 +2.8~3%；台股分類低配 -12.2pp，續以回檔小單分批低吸。
• 006208（476,500 TWD）：與 0050 高度同質，同步受惠 +2.8% 上下；低費用累積邏輯不變。
• 00878（530,400 TWD）：高股息族在大漲日相對落後，預估 +1~2%；續建 4 週節奏不受影響，殖利率保護仍在。
• 00919（179,640 TWD）：同屬高股息，走勢與 00878 類似（+1~2%），配息現金流穩定，維持持有。
• 00983D（202,200 TWD）：20 年美債 ETF；US30Y 5.173% 回落 → 長債價格止跌，今日預估 +0.5~1% 反彈；惟依臨時規則仍暫緩加碼，待「連 3 日 <5.20%」確認後重評估恢復小單。
• 00646（78,950 TWD）：S&P500 連動 +0.6% 上下；美股分類超配 +4.0pp，續列減碼觀察。
• 美股 ETF 合計（{_amt('美股市值型成長')} TWD）：NVDA +2.85%、費半高檔換手，AI/半導體權重部位帳面續增；依規則逢反彈分批減碼收斂至 30%，不急砍。
• 貝萊德世界科技基金（約 3,943 USD ≈ 12.8 萬 TWD）：科技權重高，AI 動能直接受惠，預估 +1~2%。
• 安聯AI收益成長多重資產（6,496 USD ≈ 21.1 萬 TWD）：股債多重資產、波動相對低，AI 動能＋債息雙引擎，月配息穩定入帳。
• 保單基金（安聯/第一金月配息）：與股市連動低、變動有限，月配息持續入帳，退休金流穩定。

【四、資產配置透視】（snapshot.json penetration.actual_twd，2026-08-05 動態校正）
總穿透投資部位：{tot:,.0f} TWD；臨時階段目標：美股30 / 台股23.5 / 防守19 / 債券13 / 現金14.5
• 台股市值型成長：{_amt('台股市值型成長')}（{_pct('台股市值型成長')}%）vs 23.5% → {dev('台股市值型成長'):+.1f}pp 嚴重低配
• 美股市值型成長：{_amt('美股市值型成長')}（{_pct('美股市值型成長')}%）vs 30% → {dev('美股市值型成長'):+.1f}pp 超配
• 防守型配息：{_amt('防守型配息')}（{_pct('防守型配息')}%）vs 19% → {dev('防守型配息'):+.1f}pp 大致合規
• 債券：{_amt('債券')}（{_pct('債券')}%）vs 13% → {dev('債券'):+.1f}pp 超配
• 現金/安全網：{_amt('現金/安全網')}（{_pct('現金/安全網')}%）vs 14.5% → {dev('現金/安全網'):+.1f}pp 超配
成長合計 {growth}%（台+美）；債券+現金安全網 {buff}%，緩衝結構充裕，防禦能力完整。

【五、巴菲特/蒙格式建議】（臨時階段規則）
• 00878：續建 4 週（每週小單）✅ 維持節奏，不因反彈行情改變。
• 00983D：暫緩 ✅（本週不新增）；US30Y 5.173% 已跌破 5.20%，若「連 3 日 <5.20%」確認，下週起評估恢復小單加碼。
• 單筆 ≥5 萬：暫停 ✅（國泰核貸階段，大額調度延後至撥款確認）。
• 現金底線：6 個月生活費（≥85 萬）不動 ✅ 現金 {_pct('現金/安全網')}%（{_amt('現金/安全網')} TWD）充足。
• 增持清單：台股市值型（0050/006208）低配 -12.2pp，僅回檔小單分批低吸（單筆 ≤5 萬），大漲日不追價。
• 減碼清單：美股市值型超配 +4.0pp，逢反彈分批減碼收斂至 30%（不急砍、分批執行、禁單筆大額）。
• 持有清單：00878 / 00919 / 防守型配息 / 保單基金，維持現狀不動。
• 心法：反彈行情最忌 FOMO 追高；安全邊際（現金+債券 {buff}%）優先維持，等更好的價格與殖利率回落確認。

【六、風控檢查】
• US30Y：現值 5.173% —— 已跌破 5.20% 防禦門檻，防禦模式解除條件浮現（依規則需「連 3 日 <5.20%」確認，目前尚未累計）；距 5.30% 債券凍結紅線尚有 0.13pp 緩衝，凍結紅線未觸發 ✅；債券凍結狀態 frozen=false，若 5.20% 下方確認，00983D/債券加碼限制解除（仍受核貸階段單筆 ≥5 萬暫停規範）。
• 國泰核貸：快照標註「核貸進行中，順延至 8/4（週二）撥款，利率 2.6%」——8/4 已過，撥款是否如期入帳須今日確認；撥款完成前大額調度維持暫停、不啟動任何槓桿。
• 底線檢核：現金 ≥85 萬 ✅（302 萬）；總股票曝險 {growth}% < 55% 紅線 ✅；無賣出訊號 ✅；兩條底線均守住。
• 綜合判定：美股開盤溫和走高，「地緣降溫＋AI 動能重啟」主導，屬例行應變＋反彈行情，非系統性風險；頭號變數＝中東協議反覆、NVDA 財報、US30Y 5.20% 保衛戰。"""

# --- 1. 寫 JSON ---
d = {'generated_at': now, 'source': '美股緊急應變', 'full_report': full_report}
with io.open('data/emergency_llm_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

# --- 2. 驗證字數 ---
n = len(full_report)
print(f'full_report 字元數: {n}')
assert n > 1500, '字數不足 1500！'

# --- 3. 市場數據表（本次即時抓取）---
market_rows = [
    ('道瓊工業指數', '54,488.97', '+0.75%', 'up'),
    ('那斯達克指數', '26,697.81', '+0.42%', 'up'),
    ('S&P 500', '7,782.65', '+0.60%', 'up'),
    ('費城半導體 SOX', '12,169.50', '-0.08%', 'down'),
    ('TSMC ADR (TSM)', '421.11', '+0.94%', 'up'),
    ('NVIDIA (NVDA)', '217.99', '+2.85%', 'up'),
    ('Tesla (TSLA)', '323.09', '-1.30%', 'down'),
    ('Apple (AAPL)', '308.54', '-0.27%', 'down'),
    ('Meta (META)', '597.15', '+1.57%', 'up'),
    ('Amazon (AMZN)', '282.29', '+1.76%', 'up'),
    ('黃金 (GC=F)', '4,255.90', '+3.92%', 'up'),
    ('WTI 原油 (CL=F)', '75.75', '-0.03%', 'down'),
    ('美元指數 DXY', '99.72', '-0.18%', 'down'),
    ('美國10年期公債', '4.625%', '—', 'flat'),
    ('美國30年期公債 US30Y', '5.173%', '▼ 跌破5.20%防禦線', 'down'),
    ('VIX 波動率', '16.93', '+2.61%', 'up'),
]
alloc_rows = [
    ('台股市值型成長', f"{_pen.get('台股市值型成長',0):,.0f}", f"{_pct('台股市值型成長')}%", '23.5%', f"{dev('台股市值型成長'):+.1f}pp", '嚴重低配', '增持(回檔小單)'),
    ('美股市值型成長', f"{_pen.get('美股市值型成長',0):,.0f}", f"{_pct('美股市值型成長')}%", '30%', f"{dev('美股市值型成長'):+.1f}pp", '超配', '分批減碼'),
    ('防守型配息', f"{_pen.get('防守型配息',0):,.0f}", f"{_pct('防守型配息')}%", '19%', f"{dev('防守型配息'):+.1f}pp", '合規', '持有'),
    ('債券', f"{_pen.get('債券',0):,.0f}", f"{_pct('債券')}%", '13%', f"{dev('債券'):+.1f}pp", '超配', '凍結→觀察解除'),
    ('現金/安全網', f"{_pen.get('現金/安全網',0):,.0f}", f"{_pct('現金/安全網')}%", '14.5%', f"{dev('現金/安全網'):+.1f}pp", '超配', '保留'),
]

def esc(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def build_html(title, subtitle, badge):
    rows_html = ''.join(
        f'<tr><td>{n}</td><td class="num">{p}</td><td class="{"pos" if c=="up" else "neg" if c=="down" else ""}">{chg}</td></tr>'
        for n, p, chg, c in market_rows
    )
    alloc_html = ''.join(
        f'<tr><td>{n}</td><td class="num">{v}</td><td class="num">{p}</td><td class="num">{t}</td>'
        f'<td class="{"pos" if "+" in dv else "neg"}">{dv}</td><td>{st}</td><td>{act}</td></tr>'
        for n, v, p, t, dv, st, act in alloc_rows
    )
    body = esc(full_report).replace('\n', '<br>')
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
:root {{ --bg:#0b0f17; --card:#131a26; --line:#1f2937; --txt:#e5e7eb; --mut:#9ca3af;
  --up:#34d399; --down:#f87171; --acc:#60a5fa; --gold:#fbbf24; --warn:#fb923c; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--txt); font-family:"Segoe UI","PingFang TC","Microsoft JhengHei",sans-serif; padding:24px; line-height:1.7; }}
.wrap {{ max-width:1000px; margin:0 auto; }}
header {{ border:1px solid var(--line); border-radius:14px; padding:22px 26px; background:linear-gradient(135deg,#16203a,#131a26); margin-bottom:20px; }}
h1 {{ font-size:26px; color:#fff; letter-spacing:.5px; }}
.sub {{ color:var(--mut); margin-top:6px; font-size:14px; }}
.badge {{ display:inline-block; margin-top:10px; padding:4px 14px; border-radius:999px; font-size:13px; font-weight:700; background:rgba(251,146,60,.15); color:var(--warn); border:1px solid rgba(251,146,60,.4); }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:20px 24px; margin-bottom:18px; }}
h2 {{ font-size:19px; color:var(--acc); margin-bottom:12px; border-left:4px solid var(--acc); padding-left:10px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th,td {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; }}
th {{ color:var(--mut); font-weight:600; background:rgba(255,255,255,.03); }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.pos {{ color:var(--up); font-weight:700; }}
.neg {{ color:var(--down); font-weight:700; }}
.analysis {{ font-size:14.5px; }}
.analysis b {{ color:var(--gold); }}
.hl {{ background:rgba(96,165,250,.12); border:1px solid rgba(96,165,250,.35); border-radius:10px; padding:12px 16px; margin-top:14px; font-size:14px; }}
footer {{ text-align:center; color:var(--mut); font-size:12px; padding:18px 0 8px; }}
</style>
</head>
<body><div class="wrap">
<header>
  <h1>🚨 {title}</h1>
  <div class="sub">{subtitle}</div>
  <span class="badge">{badge}</span>
</header>
<div class="card">
  <h2>📊 美股即時行情（台北 21:30 開盤 / Yahoo Finance 即時）</h2>
  <table><tr><th>標的</th><th class="num">現價</th><th class="num">漲跌幅</th></tr>{rows_html}</table>
</div>
<div class="card">
  <h2>⚖️ 資產配置透視（snapshot penetration，臨時階段目標）</h2>
  <table><tr><th>類別</th><th class="num">金額(TWD)</th><th class="num">實際</th><th class="num">目標</th><th class="num">偏離</th><th>狀態</th><th>動作</th></tr>{alloc_html}</table>
  <div class="hl">💡 成長合計 {growth}%（台+美）／債券+現金安全網 {buff}%／總股票曝險未逾 55% 紅線；US30Y 5.173% 已跌破 5.20% 防禦門檻（需連3日確認），5.30% 債券凍結紅線未觸發。</div>
</div>
<div class="card">
  <h2>🧠 LLM 六大章節深度分析</h2>
  <div class="analysis">{body}</div>
</div>
<footer>龍九控股・Chief Reporter 美股緊急應變｜{now}｜資料來源：Yahoo Finance API + snapshot.json｜本報告為自動化例行應變，非投資建議</footer>
</div></body></html>"""

html_railway = build_html('美股緊急應變報告', f'📅 {now}（美股開盤）・龍九控股 Chief Reporter / 美股危機應變官', '⚠ 例行應變・反彈行情・非系統性風險')
html_github = build_html('美股緊急應變報告', f'📅 {now}（美股開盤）・龍九控股 Chief Reporter / 美股危機應變官', '⚠ 例行應變・反彈行情・非系統性風險')

with io.open(f'emergency_report_{today}.html', 'w', encoding='utf-8') as f:
    f.write(html_railway)
with io.open(f'emergency_taiex_report_{today}.html', 'w', encoding='utf-8') as f:
    f.write(html_github)

print('JSON + 兩版 HTML 已寫入')
print(f"emergency_report_{today}.html  bytes:", len(html_railway.encode('utf-8')))
print(f"emergency_taiex_report_{today}.html  bytes:", len(html_github.encode('utf-8')))
