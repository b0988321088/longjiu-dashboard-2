# -*- coding: utf-8 -*-
"""gen_emergency_us_0807.py — 美股緊急應變 8/7 21:30 六章節報告產生器
產出：data/emergency_llm_analysis.json + emergency_report_2026-08-07.html(Railway) + emergency_taiex_report_2026-08-07.html(GitHub)
資料：Yahoo Finance 即時 (21:35-21:40 台北 = 美東 09:35-09:40) / Google News RSS / snapshot.json penetration
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
TODAY = "2026-08-07"
NOW = "2026-08-07 21:40"

FULL_REPORT = """【一、市場概況】（8/7 21:36 台北 = 美東 09:36 開盤 6 分鐘，Yahoo Finance 即時）
美股四大指數：道瓊 53,849.76（-0.07%，-35.34）、S&P 500 7,735.31（+0.33%，+25.35）、納斯達克 26,605.43（+0.98%，+257.08）、費城半導體 12,361.17（+2.59%，+312.47）— 科技與半導體領漲、道瓊獨弱，成長股強力反彈。盤前期貨：ES 7,758.75（+0.31%）、NQ 29,728.50（+0.81%）、YM 54,071.00（+0.11%）。重要個股：台積電 ADR 421.65（+0.86%）、NVDA 222.13（+1.43%）、AVGO 428.01（+1.77%）、AMD 485.53（-0.77%）、AAPL 313.18（+0.25%）、TSLA 322.72（+1.00%）、META 592.49（+0.44%）、AMZN 276.08（+1.40%）、MSFT 503.44（+0.72%）、GOOGL 358.12（+0.10%）。債市：10 年 4.62%（-4bp）、30 年 5.19%（-2bp）— 長債殖利率回落至 5.20% 防禦線下方，為近 3 週最關鍵的緩解訊號。商品：黃金 4,410.3（+2.57% 暴漲創新高）、WTI 77.08（-0.27% 平盤）。VIX 15.29（+0.92%）低波動。台股 8/7 收盤：加權指數 44,225.91（-0.38%，-170.79）週漲 1,106 點、台積電 2,370.00；美元兌台幣 32.204。

【二、重大事件分析】
1) 7 月非農意外負成長 -23,000（預期 +80K，FactSet 預測 +97.5K），失業率降至 4.1%（Reuters/The Star）→ 市場大幅下修 9 月升息機率（Barron's：Odds of a Fed Rate Hike Drop；Bloomberg：Treasuries Rally as Soft Jobs Data Trims Rate-Hike Bets）→ 股債齊漲、金價暴衝。此為今晚最大驅動因子，直接逆轉過去兩週「Fed 鷹派重定價」壓力，也是 30Y 從 5.21% 回落至 5.19% 的主因。
2) 荷莫茲海峽重開談判進入最後階段：伊朗-阿曼協議接近（CBS 8/7），惟伊朗稱不會完全重開（WaPo）；油價橫盤 -0.27%，但黃金因「避險＋降息預期」雙重驅動暴漲 +2.57% 至 4,410 美元（本週金價自 4,300 下方急拉逾 6.6%，CoinGape），避險需求仍在。
3) AI/半導體強力反彈、賣壓正式收斂：費半 +2.59% 領漲，NVDA +1.43%、AVGO +1.77%、TSM ADR +0.86%、META +0.44%；昨日 SK海力士/三星重挫餘波明顯收斂，韓股散戶轉向回流美股（KOSPI 大跌後）。台灣方面：國安基金 8/7 淨買超 77 億元護盤（Focus Taiwan）、台股週漲 1,106 點收 44,225；TSMC 2nm 年底月產 10 萬片里程碑與 Druckenmiller 續持 TSM（Q2 財報後）為正向結構訊號。
4) Fed 官員路線仍分歧：Kashkari「現在是時候開始緩慢升息」（CNBC 8/5）、Cook「準備行動」（CNBC 8/5）、Warsh 鷹派溝通令債市不買單（30Y 曾衝 5.28% 19 年高）；但 Reuters VIEW 指弱 NFP 使升息必要性遭質疑 — 政策路徑高度不確定，9 月會議前波動放大，任何強勁數據都可能讓殖利率再度挑戰 5.20/5.30 紅線。

【三、持倉關聯分析】
台股市值型（0050 約 20.6 萬、006208 約 46.9 萬、009816 約 30.8 萬，穿透合計 155.7 萬）：TSM ADR +0.86%、費半 +2.59% → 下週一台股開盤偏多，台積電 2,370 站穩；長線分批策略不變。高股息防守（00878 51.9 萬續建 4 週、00919 17.8 萬、00713 12.3 萬、0056 4.9 萬、00918 3.3 萬、00981A 15.7 萬、00984A 14.1 萬、00888 15.7 萬，穿透合計 305.7 萬）：殖利率回落 + 弱數據環境下相對抗跌，防禦定位穩健。美股寬基（00646 7.6 萬、009823 10.3 萬、00924 9.9 萬）：S&P +0.33%、納指 +0.98%，00924 直接受惠科技巨頭拉抬，正面。00983D（10.1 萬）：核貸審查期暫緩加碼（8/4 已建首批 1 萬單位）。保單基金（安聯 A/B 796 萬＋第一金 193 萬，合計 989 萬、質借 400 萬）：貝萊德世界科技 A10（203 萬）直接受惠半導體反彈、NVDA/AAPL 撐盤；PIMCO 收益增長（271 萬）＋M&G 入息（108 萬）＋安聯收益成長（125 萬）等債券/平衡部位，30Y 回落至 5.19% 緩解壓價壓力；質借利率 4% 待 8/15 國泰 2.6% 撥款後清償。台新美日台半導體基金（12.9 萬，日圓計價）：韓股回穩＋費半反彈，壓力明顯緩解。整體持倉與市場連動正常，今晚科技反彈全面正面，無特殊風險事件。

【四、資產配置透視】（snapshot penetration.actual_twd，2026-08-07；總投資 16,842,905；臨時階段目標：美股30/台股23.5/防守19/債券13/現金14.5）
台股市值型成長 1,556,969（9.2%）vs 23.5% → -14.3pp（約 -241 萬，唯一大額缺口）；美股市值型成長 5,959,727（35.4%）vs 30% → +5.4pp（約 +91 萬，超配且已觸上限，嚴禁超配）；防守型配息 3,056,792（18.1%）vs 19% → -0.9pp 合規；債券 2,980,036（17.7%）vs 13% → +4.7pp（約 +79 萬，超標）；現金/安全網 3,289,381（19.5%）vs 14.5% → +5.0pp（約 +84 萬，超標）。警語：美股 35.4% 嚴重超配，今晚科技反彈行情中嚴禁追高；台股 -14.3pp 為最大再平衡缺口，靠國泰 8/15 撥款後 400 萬市值型計畫分批補足。

【五、巴菲特/蒙格式建議】（臨時階段規則：00878續建4週、00983D暫緩、單筆≥5萬暫停、現金底線6個月）
增持：00878 續建 4 週（小額、每筆<5萬）；0050/006208/009816 — 僅限國泰 8/15 撥款後 400 萬計畫（每週≤50萬、單筆<5萬、分批），台股 -14.3pp 為最大缺口，回檔即分批良機，惟不急於今晚追價。持有：00646、009823、00924、00713、00919、0056、00918、00981A、00984A、00888、貝萊德科技、安聯AI、保單基金 — 核心長持，不砍倉。減碼：美股 35.4% 超配 → 不新增；費半 +2.59% 反彈正是分批調降超配部位回 30% 上限內的好時機（僅小幅、不砍核心）。暫緩：00983D 暫緩加碼；單筆≥5萬申購一律暫停；債券/平衡基金 — 債券 17.7% 超標＋30Y 警戒維持零加碼。巴菲特視角：市場因單一數據（弱 NFP）劇烈擺動，正是「別人恐懼我貪婪」的紀律測試 — 不追逐短期催化劑，專注 8/15 撥款後的台股再平衡主軸。

【六、風控檢查】
US30Y 現值 5.191%（CBOE ^TYX 盤中，-2.2bp）vs 5.20% 防禦門檻：未觸發（低 0.9bp）；惟 8/6 收盤 5.213% 一度再度站上防禦線（7/30 5.21/7/31 5.28/8/3 5.23 連續 3 日越線 → 8/4 5.19、8/5 5.17 回落 → 8/6 又 5.21%），若收盤 ≥5.20% 連續 2 交易日 → 模式A 防禦正式啟動（停止新增存續期>5年債券、平衡基金禁加碼）；實務上已視同警戒執行。vs 5.30% 債券凍結紅線：緩衝 10.9bp；弱 NFP 後短期壓力緩解，但 9 月會議前任何強勁數據都可能再測紅線。國泰核貸階段：8/3 對保完成 → 8/4 地政設定申請 → 8/7 地政完成寄回國泰（今日）→ 8/15 撥款 1,200萬 @2.6%（預計）→ 清償 800萬（理財300＋保單質借400＋質押100）→ 剩 400萬 依市值型計畫分批（每週≤50萬、單筆<5萬）。審查期規則全部維持：00983D 暫緩、單筆≥5萬暫停、00878 續建4週、現金底線 6 個月（約 85.2 萬）；現金 329 萬為底線 3.9 倍，安全無虞。"""


def write_json():
    d = {"generated_at": NOW, "source": "美股緊急應變 cron (deepseek-v4-flash)", "full_report": FULL_REPORT}
    p = BASE / "data" / "emergency_llm_analysis.json"
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(d["full_report"])
    print(f"[JSON] {p} written, full_report len = {n} chars")
    assert n > 1500, f"full_report too short: {n}"
    chk = json.loads(p.read_text(encoding="utf-8"))
    print(f"[VERIFY] reload len = {len(chk['full_report'])} -> {'OK' if len(chk['full_report'])>1500 else 'FAIL'}")

CSS = """
:root{--bg:#0b0f17;--card:#131a26;--line:#1f2937;--txt:#e5e7eb;--mut:#9ca3af;--up:#34d399;--down:#f87171;--acc:#60a5fa;--gold:#fbbf24;--warn:#fb923c;}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--txt);font-family:"Segoe UI","PingFang TC","Microsoft JhengHei",sans-serif;padding:24px;line-height:1.75;}
.wrap{max-width:1020px;margin:0 auto;}
.hd{border:1px solid var(--line);border-radius:14px;padding:22px 26px;background:linear-gradient(135deg,#101828,#0b0f17);margin-bottom:18px;}
.hd h1{font-size:24px;letter-spacing:1px;color:#fff;}
.hd .sub{color:var(--mut);font-size:13px;margin-top:6px;}
.badge{display:inline-block;background:#7c3aed33;border:1px solid #7c3aed;color:#c4b5fd;border-radius:20px;padding:2px 12px;font-size:12px;margin-left:8px;vertical-align:middle;}
.badge.red{background:#f8717133;border-color:#f87171;color:#fca5a5;}
.badge.gold{background:#fbbf2433;border-color:#fbbf24;color:#fcd34d;}
.badge.green{background:#34d39933;border-color:#34d399;color:#6ee7b7;}
.sec{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 24px;margin-bottom:16px;}
.sec h2{font-size:18px;color:var(--acc);border-left:4px solid var(--acc);padding-left:10px;margin-bottom:14px;}
.sec h3{font-size:15px;color:var(--gold);margin:12px 0 8px;}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin:8px 0;}
th,td{padding:8px 10px;border:1px solid var(--line);text-align:right;}
th{background:#1a2332;color:#cbd5e1;text-align:center;}
td:first-child,th:first-child{text-align:left;}
.up{color:var(--up);font-weight:600;}
.down{color:var(--down);font-weight:600;}
.flat{color:var(--mut);}
.card{background:#0f1626;border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0;}
.card b{color:#fff;}
.tag{display:inline-block;border-radius:6px;padding:1px 9px;font-size:12px;margin-right:6px;font-weight:600;}
.tag.buy{background:#34d39933;color:var(--up);border:1px solid var(--up);}
.tag.hold{background:#60a5fa33;color:var(--acc);border:1px solid var(--acc);}
.tag.trim{background:#fb923c33;color:var(--warn);border:1px solid var(--warn);}
.tag.stop{background:#f8717133;color:var(--down);border:1px solid var(--down);}
ul{padding-left:20px;}
li{margin:5px 0;}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin:10px 0;}
.kpi{flex:1;min-width:150px;background:#0f1626;border:1px solid var(--line);border-radius:10px;padding:12px 14px;text-align:center;}
.kpi .v{font-size:20px;font-weight:700;margin-top:4px;}
.kpi .l{color:var(--mut);font-size:12px;}
.foot{color:var(--mut);font-size:12px;text-align:center;margin:20px 0 8px;}
"""

HTML = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>美股緊急應變報告 2026-08-07 21:30｜龍九控股</title>
<style>__CSS__</style>
</head>
<body><div class="wrap">

<div class="hd">
<h1>龍九控股 LONGJIU｜美股緊急應變報告<span class="badge red">開盤即時</span><span class="badge green">費半反彈 +2.59%</span><span class="badge gold">30Y 回落 5.19%</span></h1>
<div class="sub">2026-08-07 21:36 台北（美東 09:36 開盤 6 分鐘）｜Chief Reporter + 美股危機應變官｜資料來源：Yahoo Finance 即時 / Google News RSS / snapshot.json 穿透數據</div>
</div>

<div class="sec">
<h2>一、市場概況｜三大指數 + 費半 + 期貨 + 商品 + 債市</h2>
<table>
<tr><th>標的</th><th>現價</th><th>前收</th><th>漲跌點</th><th>漲跌幅</th></tr>
<tr><td>道瓊指數 DJI</td><td>53,849.76</td><td>53,885.10</td><td>-35.34</td><td class="down">-0.07%</td></tr>
<tr><td>S&amp;P 500</td><td>7,735.31</td><td>7,709.96</td><td>+25.35</td><td class="up">+0.33%</td></tr>
<tr><td>納斯達克 IXIC</td><td>26,605.43</td><td>26,348.35</td><td>+257.08</td><td class="up">+0.98%</td></tr>
<tr><td>費城半導體 SOX</td><td>12,361.17</td><td>12,048.69</td><td>+312.47</td><td class="up">+2.59% 🔥</td></tr>
<tr><td>加權指數 TAIEX（台股收盤）</td><td>44,225.91</td><td>44,396.70</td><td>-170.79</td><td class="down">-0.38%（週漲 1,106 點）</td></tr>
</table>
<div class="kpis">
<div class="kpi"><div class="l">盤前期貨 ES</div><div class="v up">+0.31%</div></div>
<div class="kpi"><div class="l">那斯達克期貨 NQ</div><div class="v up">+0.81%</div></div>
<div class="kpi"><div class="l">道瓊期貨 YM</div><div class="v up">+0.11%</div></div>
<div class="kpi"><div class="l">黃金 GC</div><div class="v up">4,410.3 (+2.57%)</div></div>
<div class="kpi"><div class="l">WTI 原油</div><div class="v flat">77.08 (-0.27%)</div></div>
<div class="kpi"><div class="l">美債 10Y</div><div class="v up">4.62% (-4bp)</div></div>
<div class="kpi"><div class="l">美債 30Y</div><div class="v up">5.19% (-2bp) ⬇️</div></div>
<div class="kpi"><div class="l">VIX</div><div class="v flat">15.29 (+0.92%)</div></div>
</div>
<h3>重要個股</h3>
<table>
<tr><th>個股</th><th>現價</th><th>前收</th><th>漲跌幅</th><th>訊號</th></tr>
<tr><td>台積電 ADR (TSM)</td><td>421.65</td><td>418.06</td><td class="up">+0.86%</td><td>費半反彈領漲</td></tr>
<tr><td>NVIDIA (NVDA)</td><td>222.13</td><td>218.99</td><td class="up">+1.43%</td><td>強勢反彈</td></tr>
<tr><td>Broadcom (AVGO)</td><td>428.01</td><td>420.57</td><td class="up">+1.77%</td><td>AI 族群走強</td></tr>
<tr><td>AMD</td><td>485.53</td><td>489.28</td><td class="down">-0.77%</td><td>相對弱勢</td></tr>
<tr><td>Apple (AAPL)</td><td>313.18</td><td>312.41</td><td class="up">+0.25%</td><td>平穩</td></tr>
<tr><td>Tesla (TSLA)</td><td>322.72</td><td>319.53</td><td class="up">+1.00%</td><td>走強</td></tr>
<tr><td>Meta (META)</td><td>592.49</td><td>589.90</td><td class="up">+0.44%</td><td>微漲</td></tr>
<tr><td>Amazon (AMZN)</td><td>276.08</td><td>272.26</td><td class="up">+1.40%</td><td>走強</td></tr>
<tr><td>Microsoft (MSFT)</td><td>503.44</td><td>499.87</td><td class="up">+0.72%</td><td>穩健</td></tr>
</table>
</div>

<div class="sec">
<h2>二、重大事件分析｜四大驅動因子</h2>
<div class="card"><b>① 7 月非農意外負成長 -23,000（最大驅動因子）</b><br>
非農 -23,000（預期 +80K）、失業率降至 4.1% → 市場大幅下修 9 月升息機率（Barron's／Bloomberg：Treasuries Rally as Soft Jobs Data Trims Rate-Hike Bets）→ 股債齊漲、金價暴衝。直接逆轉過去兩週「Fed 鷹派重定價」壓力，也是 30Y 從 5.21% 回落至 5.19% 的主因。</div>
<div class="card"><b>② 荷莫茲海峽談判進入最後階段、金價暴漲</b><br>
伊朗-阿曼協議接近（CBS），惟伊朗稱不會完全重開（WaPo）；油價橫盤 -0.27%，黃金因「避險＋降息預期」雙重驅動暴漲 +2.57% 至 4,410 美元（本週自 4,300 下方急拉逾 6.6%），避險需求仍在。</div>
<div class="card"><b>③ AI/半導體強力反彈、賣壓正式收斂</b><br>
費半 +2.59% 領漲，NVDA +1.43%、AVGO +1.77%、TSM ADR +0.86%；昨日 SK海力士/三星重挫餘波收斂，韓股散戶回流美股。台灣：國安基金 8/7 淨買超 77 億護盤、台股週漲 1,106 點；TSMC 2nm 年底月產 10 萬片里程碑＋Druckenmiller 續持 TSM 為正向結構訊號。</div>
<div class="card"><b>④ Fed 官員路線分歧、政策高度不確定</b><br>
Kashkari「現在是時候開始緩慢升息」（8/5）、Cook「準備行動」（8/5）、Warsh 鷹派溝通（30Y 曾衝 5.28% 19 年高）；但 Reuters VIEW 指弱 NFP 使升息必要性遭質疑 — 9 月會議前任何強勁數據都可能讓殖利率再測 5.20/5.30 紅線。</div>
</div>

<div class="sec">
<h2>三、持倉關聯分析｜逐檔影響評估</h2>
<table>
<tr><th>標的</th><th>市值(台幣)</th><th>類別</th><th>今晚影響</th></tr>
<tr><td>0050 / 006208 / 009816</td><td>98.3萬（穿透155.7萬）</td><td>台股市值型</td><td>TSM ADR +0.86%、費半 +2.59% → 下週一台股開盤偏多</td></tr>
<tr><td>00878 國泰永續高股息</td><td>51.9萬</td><td>高股息防守</td><td>殖利率回落有利，續建 4 週</td></tr>
<tr><td>00919 / 00713 / 0056 / 00918 / 00981A / 00984A / 00888</td><td>約 253萬</td><td>高股息防守</td><td>防守 305.7萬，弱數據環境抗跌，持有</td></tr>
<tr><td>00646 / 009823</td><td>17.9萬</td><td>美股寬基</td><td>S&amp;P +0.33%，影響正面</td></tr>
<tr><td>00924 美國科技巨頭</td><td>9.9萬</td><td>美股科技</td><td>納指 +0.98%，直接受惠</td></tr>
<tr><td>00983D 富邦複合收益</td><td>10.1萬</td><td>主動複合</td><td>核貸審查期暫緩加碼（8/4 首批已建）</td></tr>
<tr><td>貝萊德世界科技A10（保單內）</td><td>203萬</td><td>保單基金</td><td>半導體反彈直接受惠，NVDA/AAPL 撐盤</td></tr>
<tr><td>安聯AI收益（保單內）</td><td>90萬</td><td>保單基金</td><td>AI 反彈受惠</td></tr>
<tr><td>PIMCO收益增長＋M&amp;G＋安聯收益成長</td><td>504萬</td><td>債券/平衡</td><td>30Y 回落至 5.19% 緩解壓價壓力</td></tr>
<tr><td>台新美日台半導體（日圓）</td><td>12.9萬</td><td>基金</td><td>韓股回穩＋費半反彈，壓力緩解</td></tr>
<tr><td>安聯保單A/B＋第一金保單</td><td>989萬</td><td>核心保單</td><td>質借 400萬@4%，待國泰 2.6% 撥款清償</td></tr>
</table>
</div>

<div class="sec">
<h2>四、資產配置透視｜穿透實際 vs 臨時階段目標</h2>
<table>
<tr><th>類別</th><th>實際(TWD)</th><th>實際%</th><th>目標%</th><th>偏離</th></tr>
<tr><td>台股市值型成長</td><td>1,556,969</td><td>9.2%</td><td>23.5%</td><td class="down">-14.3pp（缺口約241萬）</td></tr>
<tr><td>美股市值型成長</td><td>5,959,727</td><td>35.4%</td><td>30.0%</td><td class="down">+5.4pp（超配91萬，觸上限）</td></tr>
<tr><td>防守型配息</td><td>3,056,792</td><td>18.1%</td><td>19.0%</td><td class="flat">-0.9pp 合規</td></tr>
<tr><td>債券</td><td>2,980,036</td><td>17.7%</td><td>13.0%</td><td class="down">+4.7pp（超標79萬）</td></tr>
<tr><td>現金/安全網</td><td>3,289,381</td><td>19.5%</td><td>14.5%</td><td class="down">+5.0pp（超標84萬）</td></tr>
</table>
<div class="card"><b>結論：</b>美股 35.4% 嚴重超配（+5.4pp），今晚科技反彈行情中嚴禁追高；台股 -14.3pp 為唯一大額缺口，靠國泰 8/15 撥款後 400 萬市值型計畫分批補足（每週≤50萬、單筆&lt;5萬）。債券與現金超標，維持零加碼。</div>
</div>

<div class="sec">
<h2>五、巴菲特/蒙格式建議｜臨時階段紀律</h2>
<ul>
<li><span class="tag buy">增持</span><b>00878</b>：續建 4 週，小額分批、每筆&lt;5萬</li>
<li><span class="tag buy">增持</span><b>0050 / 006208 / 009816</b>：僅限國泰 8/15 撥款後 400 萬計畫（每週≤50萬、單筆&lt;5萬）；台股 -14.3pp 為最大缺口，回檔即分批良機，不急於今晚追價</li>
<li><span class="tag hold">持有</span><b>00646 / 009823 / 00924 / 00713 / 00919 / 0056 / 00918 / 00981A / 00984A / 00888 / 貝萊德科技 / 安聯AI / 保單基金</b>：核心長持，不砍倉</li>
<li><span class="tag trim">減碼</span><b>美股超配部分</b>：35.4% vs 30% → 不新增；費半 +2.59% 反彈正是分批調降超配部位回上限內的好時機（僅小幅、不砍核心）</li>
<li><span class="tag stop">暫緩</span><b>00983D</b>：核貸審查期暫緩加碼（8/4 首批已建）</li>
<li><span class="tag stop">暫緩</span><b>單筆≥5萬申購</b>：一律暫停，改小額分批</li>
<li><span class="tag stop">暫緩</span><b>債券/平衡基金</b>：債券 17.7% 超標 + 30Y 警戒 → 不新增長債；平衡基金禁止再加碼</li>
</ul>
<div class="card"><b>巴菲特視角：</b>市場因單一數據（弱 NFP）劇烈擺動，正是「別人恐懼我貪婪」的紀律測試 — 不追逐短期催化劑，專注 8/15 撥款後的台股再平衡主軸。</div>
</div>

<div class="sec">
<h2>六、風控檢查｜US30Y 門檻 + 國泰核貸階段</h2>
<div class="kpis">
<div class="kpi"><div class="l">US30Y 現值</div><div class="v up">5.191%</div></div>
<div class="kpi"><div class="l">5.20% 防禦門檻</div><div class="v up">未觸發（低 0.9bp）</div></div>
<div class="kpi"><div class="l">5.30% 凍結紅線</div><div class="v flat">緩衝 10.9bp</div></div>
<div class="kpi"><div class="l">現金 vs 6個月底線</div><div class="v up">329萬 = 底線 3.9 倍</div></div>
</div>
<div class="card"><b>US30Y 判定：</b>現值 5.191%（CBOE ^TYX 盤中，-2.2bp）低於 5.20% 防禦門檻，未正式觸發；惟 8/6 收盤 5.213% 一度再度站上防禦線（7/30 5.21／7/31 5.28／8/3 5.23 連續 3 日越線 → 8/4-8/5 回落 → 8/6 又 5.21%），若收盤 ≥5.20% 連續 2 交易日 → 模式A 防禦正式啟動（停止新增存續期&gt;5年債券、平衡基金禁加碼），實務上已視同警戒執行。弱 NFP 後短期壓力緩解，但 9 月會議前任何強勁數據都可能再測紅線。</div>
<div class="card"><b>國泰核貸階段：</b>8/3 對保完成 → 8/4 地政設定申請 → <b>8/7 地政完成寄回國泰（今日）</b> → <b>8/15 撥款 1,200萬 @2.6%</b> → 清償 800萬（理財300＋保單質借400＋質押100）→ 剩 400萬 依市值型計畫分批（每週≤50萬、單筆&lt;5萬）。審查期規則全數維持：00983D 暫緩、單筆≥5萬暫停、00878 續建 4 週、現金底線 6 個月（約 85.2 萬）；現金 329 萬為底線 3.9 倍，安全無虞。</div>
</div>

<div class="foot">龍九控股內部報告｜僅供決策參考，非投資建議｜資料時間 2026-08-07 21:36 台北（開盤 6 分鐘）｜Yahoo Finance 即時 + Google News RSS + snapshot.json 穿透數據</div>
</div></body></html>"""


def write_htmls():
    css_html = HTML.replace("__CSS__", CSS)
    rail = BASE / f"emergency_report_{TODAY}.html"
    gh = BASE / f"emergency_taiex_report_{TODAY}.html"
    rail.write_text(css_html, encoding="utf-8")
    gh.write_text(css_html.replace("美股緊急應變報告 2026-08-07 21:30｜龍九控股", "台股/美股緊急應變報告 2026-08-07 21:30｜龍九控股"), encoding="utf-8")
    print(f"[HTML] {rail} ({rail.stat().st_size} bytes)")
    print(f"[HTML] {gh} ({gh.stat().st_size} bytes)")


if __name__ == "__main__":
    write_json()
    write_htmls()
    print("[DONE]", NOW)
