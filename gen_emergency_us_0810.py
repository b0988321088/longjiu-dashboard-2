# -*- coding: utf-8 -*-
"""gen_emergency_us_0810.py — 美股緊急應變 8/10 21:30 六章節報告產生器
產出：data/emergency_llm_analysis.json + emergency_report_2026-08-10.html(Railway) + emergency_taiex_report_2026-08-10.html(GitHub)
資料：Yahoo Finance 即時 (21:36 台北 = 美東 09:36 開盤約 6 分鐘) / Google News RSS / snapshot.json penetration / schedule_events.json 8/15 新計畫
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
TODAY = "2026-08-10"
NOW = "2026-08-10 21:36"

FULL_REPORT = """【一、市場概況】（8/10 21:36 台北 = 美東 09:36 開盤約 6 分鐘，Yahoo Finance 即時）
美股三大指數小幅低開：道瓊 53,949.80（-0.16%，-87.13）、S&P 500 7,751.69（-0.08%，-5.95）、納斯達克 26,646.24（-0.17%，-44.38）、費城半導體 12,322.48（-0.28%，-34.31）— 地緣風險壓抑風險偏好，惟跌幅溫和未見恐慌。盤前期貨：ES 7,771.50（-0.11%）、NQ 29,808.25（-0.09%）、YM 53,988.00（-0.30%）。重要個股：台積電 ADR 418.32（-0.38% 抗跌）、NVDA 223.66（-0.13% 平穩）、AAPL 305.60（-2.38% 領跌，Jefferies 降評）、AMD 473.97（-1.94%）、TSLA 328.45（-0.04%）、META 596.78（+0.79%）、AMZN 274.17（-0.11%）、MSFT 504.19（+0.84%）、GOOGL 355.69（+0.39%）、AVGO 430.51（+0.64%）。債市：10 年 4.68%（+2bp）、30 年 5.222%（+1.1bp）— 盤中再度站上 5.20% 防禦線，長債壓力未解。商品：黃金 4,392.70（-0.16% 高檔整理）、WTI 79.57（+1.78% 荷姆茲危機驅動）。VIX 15.42（+3.49%）仍處低波動。台股 8/10 收盤：加權指數 44,894.06（+1.51%，+668.15）強漲、6 千金齊亮燈、台積電 2,385（+0.63%）；美元兌台幣約 32.2。

【二、重大事件分析】
1) 荷姆茲海峽危機升溫（今日最大地緣風險）：Trump 稱美國「只是半協商中」並轉向經濟壓力（Benzinga 8/10），伊朗稱海峽在美國「修正行為」前不會重開（CBS/Al Jazeera 8/10），Bloomberg 指 Hormuz 石油運輸懸而未決 → WTI +1.78% 至 79.57，美股開盤承壓。惟幅度溫和，未見避險失控。
2) TSMC 7 月營收創歷史新高 NT$467.58B、年增 44.7%（Focus Taiwan/CNBC/Yahoo 8/10）— AI 需求強勁、Q3 展望加速；TSM ADR -0.38% 相對抗跌，為台股明日開盤最強支撐。
3) NVDA 焦點轉向 8/26 財報指引：上月市值激增 562B 美元（TechStock²），Musk 傳 xAI 獨家採用 Nvidia 晶片（tikr 8/9），分析師目標價上看 238 美元（Finbold）；NVDA -0.13% 等待財報。
4) AAPL 遭 Jefferies 降評至 Underperform、目標價砍至 263.66 美元（AppleInsider 8/10）→ -2.38% 領跌；Intel 啟動 150 億美元股票發行（S-3 shelf）→ -5%（Reuters/24-7 Wall St）— 半導體個股分化加劇。
5) Fed：主席 Kevin Warsh 重組聯準會（Axios 8/10）、7 月按兵不動、利率「higher for longer」（CNBC）；8 月通膨預測恐令 FOMC 陷入兩難（Yahoo）→ 30Y 盤中 5.222% 再越 5.20% 防禦線，長債殖利率壓力持續。

【三、持倉關聯分析】
台股市值型（0050 2,000 股／006208 2,000 股／009816 21,000 股，穿透 157.9 萬）：TSM ADR -0.38% 但 7 月營收創紀錄 +44.7%、台股今日 +1.51% → 明日台股開盤偏多，惟留意費半 -0.28% 小幅拖累；長線分批策略不變。美股部位（00646 1,000 股／009823 10,000 股／009824 美國科技巨頭 10,000 股，穿透 593.3 萬）：納指 -0.17%，MSFT/META/AVGO 逆勢上漲、AAPL -2.38% 拖累，009824 受惠微軟/ Meta 走強，整體影響中性偏正。高股息防守（00878 16,000 股續建 4 週／00919／00713／0056／00918／00981A／00984A／00888，穿透 313.4 萬）：低開環境相對抗跌，防禦定位穩健。00983D（2 萬股，約 20 萬）：核貸審查期暫緩加碼維持（8/4 首批、8/10 已加碼至 2 萬股）。保單基金（安聯 A/B 約 796 萬＋第一金 199 萬＝約 995 萬、質借 400 萬）：貝萊德世界科技 A10 受 NVDA 平穩支撐、AAPL -2.38% 小幅拖累；PIMCO 收益增長／M&G／安聯收益成長等債券平衡部位，受 30Y 再越 5.20% 壓價壓力。台新美日台半導體（12.9 萬）：費半 -0.28% 小幅壓力。整體持倉與市場連動正常，無個別暴險事件。

【四、資產配置透視】（snapshot penetration.actual_twd，2026-08-10；總投資 15,921,797；臨時階段目標：美股30/台股23.5/防守19/債券13/現金14.5）
台股市值型成長 1,578,518（9.9%）vs 23.5% → -13.6pp（缺口約 216 萬，最大結構缺口）；美股市值型成長 5,932,893（37.3%）vs 30% → +7.3pp（超配約 116 萬，且較 8/7 的 35.4% 續升，嚴禁追高）；防守型配息 3,133,579（19.7%）vs 19% → +0.7pp 合規；債券 2,984,711（18.7%）vs 13% → +5.7pp（超標約 91 萬）；現金/安全網 2,292,096（14.4%）vs 14.5% → -0.1pp 合規（8/10 已償還星展 100 萬）。警語：美股 37.3% 超配擴大，今晚任何反彈都是分批調降機會、嚴禁追高；台股 -13.6pp 為最大缺口，惟 8/15 新計畫 1,200 萬額度全數配置於還款與債券（無直接買股額度），台股補缺將延後至後續再平衡；債券超標 + 30Y 越線 → 現階段維持零加碼，8/15 短中期投資級債（1-3yr）買入依定案計畫執行並於撥款後校準目標。

【五、巴菲特/蒙格式建議】（臨時階段規則：00878續建4週、00983D暫緩、單筆≥5萬暫停、現金底線6個月）
增持：00878 續建 4 週（小額、每筆<5萬）；台股市值型（0050/006208/009816）— 8/15 新計畫無直接額度，若撥款後現金流改善（質押 500 萬清償高息後月現金流釋放）可小額分批回補 -13.6pp 缺口，不急於今晚追價。持有：00646／009823／009824／00713／00919／0056／00918／00981A／00984A／00888／貝萊德科技／安聯AI／保單基金 — 核心長持，不砍倉；AAPL/AMD 單日個股利空不構成砍倉理由。減碼：美股 37.3% 超配 → 不新增；科技股分化（MSFT/META 強、AAPL/AMD 弱）勿追強砍弱。暫緩：00983D 暫緩加碼；單筆≥5萬申購一律暫停；債券/平衡基金 — 債券 18.7% 超標＋30Y 越線維持零加碼（8/15 依定案計畫執行）。巴菲特視角：荷姆茲地緣緊張＋個股降評造成的開盤小跌，屬噪音非系統性風險；不追逐短期催化劑，專注 8/15 撥款後的部署主軸。

【六、風控檢查】
US30Y 現值 5.222%（CBOE ^TYX 盤中，+1.1bp）vs 5.20% 防禦門檻：盤中已越線（8/6 收盤 5.213%、8/7 收盤 5.19% 回落 → 今日盤中 5.222% 再越）；若今日收盤 ≥5.20%，近 3 個交易日 2 度越線 → 模式A 防禦正式啟動（停止新增存續期>5年債券、平衡基金禁加碼），實務上已視同警戒執行。vs 5.30% 債券凍結紅線：緩衝 7.8bp；Warsh 鷹派溝通＋8 月通膨預測上修風險下，9 月會議前任何強勁數據都可能再測紅線。國泰核貸階段（8/10 19:14 新計畫定案，a8810cc/49b3497）：8/3 對保 → 8/4 地政設定 → 8/7 地政完成寄回國泰 → 8/12 板橋國泰及地政 → 8/15 撥款 1,200萬 @2.6% → ①償還星展理財型 200萬 @4% 全清（8/10 已先還 100萬）②剩 1,000萬買短中期投資級債券（1-3yr）③債券質押 5 成拉出 500萬（質押成數 4 成改 5 成、禁疊三層）④500萬清償高利貸：保單質押 400萬＋證券質押 100萬 ⑤盤點金融資產申請專業投資人（3,000萬門檻）。審查期規則全數維持：00983D 暫緩、單筆≥5萬暫停、00878 續建 4 週、現金底線 6 個月（約 85.2 萬）；現金 229.2 萬 = 底線 2.7 倍，安全無虞（較 8/7 329 萬下降係因 8/10 償還星展 100 萬）。"""


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
<title>美股緊急應變報告 2026-08-10 21:30｜龍九控股</title>
<style>__CSS__</style>
</head>
<body><div class="wrap">

<div class="hd">
<h1>龍九控股 LONGJIU｜美股緊急應變報告<span class="badge red">開盤即時</span><span class="badge gold">荷姆茲危機 油+1.78%</span><span class="badge red">30Y 越線 5.222%</span></h1>
<div class="sub">2026-08-10 21:36 台北（美東 09:36 開盤約 6 分鐘）｜Chief Reporter + 美股危機應變官｜資料來源：Yahoo Finance 即時 / Google News RSS / snapshot.json 穿透數據 / schedule_events.json 8/15 新計畫</div>
</div>

<div class="sec">
<h2>一、市場概況｜三大指數 + 費半 + 期貨 + 商品 + 債市</h2>
<table>
<tr><th>標的</th><th>現價</th><th>前收</th><th>漲跌點</th><th>漲跌幅</th></tr>
<tr><td>道瓊指數 DJI</td><td>53,949.80</td><td>54,036.93</td><td>-87.13</td><td class="down">-0.16%</td></tr>
<tr><td>S&amp;P 500</td><td>7,751.69</td><td>7,757.64</td><td>-5.95</td><td class="down">-0.08%</td></tr>
<tr><td>納斯達克 IXIC</td><td>26,646.24</td><td>26,690.62</td><td>-44.38</td><td class="down">-0.17%</td></tr>
<tr><td>費城半導體 SOX</td><td>12,322.48</td><td>12,356.79</td><td>-34.31</td><td class="down">-0.28%</td></tr>
<tr><td>加權指數 TAIEX（台股收盤）</td><td>44,894.06</td><td>44,225.91</td><td>+668.15</td><td class="up">+1.51%（6千金齊亮燈）</td></tr>
</table>
<div class="kpis">
<div class="kpi"><div class="l">盤前期貨 ES</div><div class="v down">-0.11%</div></div>
<div class="kpi"><div class="l">那斯達克期貨 NQ</div><div class="v down">-0.09%</div></div>
<div class="kpi"><div class="l">道瓊期貨 YM</div><div class="v down">-0.30%</div></div>
<div class="kpi"><div class="l">黃金 GC</div><div class="v down">4,392.7 (-0.16%)</div></div>
<div class="kpi"><div class="l">WTI 原油</div><div class="v up">79.57 (+1.78%) ⚠️</div></div>
<div class="kpi"><div class="l">美債 10Y</div><div class="v up">4.68% (+2bp)</div></div>
<div class="kpi"><div class="l">美債 30Y</div><div class="v up">5.222% (+1.1bp) 🚨</div></div>
<div class="kpi"><div class="l">VIX</div><div class="v up">15.42 (+3.49%)</div></div>
</div>
<h3>重要個股</h3>
<table>
<tr><th>個股</th><th>現價</th><th>前收</th><th>漲跌幅</th><th>訊號</th></tr>
<tr><td>台積電 ADR (TSM)</td><td>418.32</td><td>419.90</td><td class="down">-0.38%</td><td>7月營收創紀錄+44.7% 抗跌</td></tr>
<tr><td>NVIDIA (NVDA)</td><td>223.66</td><td>223.95</td><td class="down">-0.13%</td><td>等待 8/26 財報</td></tr>
<tr><td>Apple (AAPL)</td><td>305.60</td><td>313.05</td><td class="down">-2.38%</td><td>Jefferies 降評至 Underperform</td></tr>
<tr><td>AMD</td><td>473.97</td><td>483.33</td><td class="down">-1.94%</td><td>相對弱勢</td></tr>
<tr><td>Tesla (TSLA)</td><td>328.45</td><td>328.59</td><td class="down">-0.04%</td><td>平穩</td></tr>
<tr><td>Meta (META)</td><td>596.78</td><td>592.10</td><td class="up">+0.79%</td><td>逆勢走強</td></tr>
<tr><td>Microsoft (MSFT)</td><td>504.19</td><td>499.99</td><td class="up">+0.84%</td><td>逆勢走強</td></tr>
<tr><td>Amazon (AMZN)</td><td>274.17</td><td>274.47</td><td class="down">-0.11%</td><td>平穩</td></tr>
<tr><td>Broadcom (AVGO)</td><td>430.51</td><td>427.76</td><td class="up">+0.64%</td><td>AI 族群撐盤</td></tr>
</table>
</div>

<div class="sec">
<h2>二、重大事件分析｜五大驅動因子</h2>
<div class="card"><b>① 荷姆茲海峽危機升溫（今日最大地緣風險）</b><br>
Trump 稱美國「只是半協商中」並轉向經濟壓力（Benzinga）；伊朗稱海峽在美國「修正行為」前不會重開（CBS/Al Jazeera）；Bloomberg 指 Hormuz 石油運輸懸而未決 → WTI +1.78% 至 79.57，美股開盤承壓。惟跌幅溫和，未見避險失控。</div>
<div class="card"><b>② TSMC 7 月營收創歷史新高 NT$467.58B、年增 44.7%</b><br>
Focus Taiwan/CNBC/Yahoo 8/10：AI 需求強勁、Q3 展望加速；TSM ADR -0.38% 相對抗跌，為台股明日開盤最強支撐。</div>
<div class="card"><b>③ NVDA 焦點轉向 8/26 財報指引</b><br>
上月市值激增 562B 美元（TechStock²）；Musk 傳 xAI 獨家採用 Nvidia 晶片（tikr）；分析師目標價上看 238 美元（Finbold）。NVDA -0.13% 平穩等待財報。</div>
<div class="card"><b>④ 個股利空：AAPL 降評、Intel 增發</b><br>
Jefferies 降 AAPL 至 Underperform、目標價砍至 263.66（AppleInsider）→ -2.38% 領跌；Intel 啟動 150 億美元股票發行 → -5%（Reuters）。半導體個股分化加劇。</div>
<div class="card"><b>⑤ Fed：Warsh 重組聯準會、higher for longer</b><br>
Axios：主席 Kevin Warsh 重組 Fed；7 月按兵不動（Morningstar）；8 月通膨預測恐令 FOMC 兩難（Yahoo）→ 30Y 盤中 5.222% 再越 5.20% 防禦線。</div>
</div>

<div class="sec">
<h2>三、持倉關聯分析｜逐檔影響評估</h2>
<table>
<tr><th>標的</th><th>部位</th><th>類別</th><th>今晚影響</th></tr>
<tr><td>0050 / 006208 / 009816</td><td>穿透 157.9萬</td><td>台股市值型</td><td>TSM 營收創紀錄+44.7%、ADR -0.38% → 明日台股開盤偏多</td></tr>
<tr><td>00646 / 009823 / 009824</td><td>穿透 593.3萬</td><td>美股寬基/科技</td><td>納指 -0.17%；MSFT/META/AVGO 逆漲、AAPL 拖累，中性偏正</td></tr>
<tr><td>00878 國泰永續高股息</td><td>16,000股</td><td>高股息防守</td><td>低開環境抗跌，續建 4 週</td></tr>
<tr><td>00919/00713/0056/00918/00981A/00984A/00888</td><td>穿透 313.4萬</td><td>高股息防守</td><td>防禦定位穩健，持有</td></tr>
<tr><td>00983D 富邦複合收益</td><td>2萬股（約20萬）</td><td>主動複合</td><td>核貸審查期暫緩加碼（8/10 已加碼至 2 萬股）</td></tr>
<tr><td>貝萊德世界科技A10（保單內）</td><td>約203萬</td><td>保單基金</td><td>NVDA 平穩支撐、AAPL -2.38% 小幅拖累</td></tr>
<tr><td>PIMCO收益增長＋M&amp;G＋安聯收益成長</td><td>約504萬</td><td>債券/平衡</td><td>30Y 5.222% 再越防禦線 → 壓價壓力重現</td></tr>
<tr><td>台新美日台半導體（日圓）</td><td>12.9萬</td><td>基金</td><td>費半 -0.28%，小幅壓力</td></tr>
<tr><td>安聯保單A/B＋第一金保單</td><td>約995萬</td><td>核心保單</td><td>質借 400萬@4%，待國泰 8/15 撥款清償</td></tr>
</table>
</div>

<div class="sec">
<h2>四、資產配置透視｜穿透實際 vs 臨時階段目標</h2>
<table>
<tr><th>類別</th><th>實際(TWD)</th><th>實際%</th><th>目標%</th><th>偏離</th></tr>
<tr><td>台股市值型成長</td><td>1,578,518</td><td>9.9%</td><td>23.5%</td><td class="down">-13.6pp（缺口約216萬）</td></tr>
<tr><td>美股市值型成長</td><td>5,932,893</td><td>37.3%</td><td>30.0%</td><td class="down">+7.3pp（超配116萬，續升）</td></tr>
<tr><td>防守型配息</td><td>3,133,579</td><td>19.7%</td><td>19.0%</td><td class="flat">+0.7pp 合規</td></tr>
<tr><td>債券</td><td>2,984,711</td><td>18.7%</td><td>13.0%</td><td class="down">+5.7pp（超標91萬）</td></tr>
<tr><td>現金/安全網</td><td>2,292,096</td><td>14.4%</td><td>14.5%</td><td class="flat">-0.1pp 合規</td></tr>
</table>
<div class="card"><b>結論：</b>美股 37.3% 超配（較 8/7 的 35.4% 續升），今晚任何反彈都是分批調降機會、嚴禁追高；台股 -13.6pp 為最大缺口，惟 8/15 新計畫 1,200 萬額度全數配置於還款與債券（無直接買股額度），補缺延後至後續再平衡；債券超標 + 30Y 越線 → 現階段零加碼，8/15 短中期投資級債（1-3yr）依定案計畫執行。</div>
</div>

<div class="sec">
<h2>五、巴菲特/蒙格式建議｜臨時階段紀律</h2>
<ul>
<li><span class="tag buy">增持</span><b>00878</b>：續建 4 週，小額分批、每筆&lt;5萬</li>
<li><span class="tag buy">增持</span><b>0050 / 006208 / 009816</b>：8/15 新計畫無直接額度；撥款後現金流改善可小額分批回補 -13.6pp 缺口，不急於今晚追價</li>
<li><span class="tag hold">持有</span><b>00646 / 009823 / 009824 / 00713 / 00919 / 0056 / 00918 / 00981A / 00984A / 00888 / 貝萊德科技 / 安聯AI / 保單基金</b>：核心長持，不砍倉；AAPL/AMD 單日利空不構成砍倉理由</li>
<li><span class="tag trim">減碼</span><b>美股超配部分</b>：37.3% vs 30% → 不新增；科技股分化（MSFT/META 強、AAPL/AMD 弱）勿追強砍弱</li>
<li><span class="tag stop">暫緩</span><b>00983D</b>：核貸審查期暫緩加碼</li>
<li><span class="tag stop">暫緩</span><b>單筆≥5萬申購</b>：一律暫停，改小額分批</li>
<li><span class="tag stop">暫緩</span><b>債券/平衡基金</b>：債券 18.7% 超標 + 30Y 越線 → 零加碼（8/15 依定案計畫執行）</li>
</ul>
<div class="card"><b>巴菲特視角：</b>荷姆茲地緣緊張＋個股降評造成的開盤小跌，屬噪音而非系統性風險；「別人恐懼我貪婪」的紀律測試 — 不追逐短期催化劑，專注 8/15 撥款後的部署主軸。</div>
</div>

<div class="sec">
<h2>六、風控檢查｜US30Y 門檻 + 國泰核貸階段</h2>
<div class="kpis">
<div class="kpi"><div class="l">US30Y 現值</div><div class="v up">5.222% (+1.1bp)</div></div>
<div class="kpi"><div class="l">5.20% 防禦門檻</div><div class="v up">盤中越線 🚨</div></div>
<div class="kpi"><div class="l">5.30% 凍結紅線</div><div class="v flat">緩衝 7.8bp</div></div>
<div class="kpi"><div class="l">現金 vs 6個月底線</div><div class="v up">229.2萬 = 底線 2.7 倍</div></div>
</div>
<div class="card"><b>US30Y 判定：</b>現值 5.222%（CBOE ^TYX 盤中，+1.1bp）已越過 5.20% 防禦門檻；8/6 收盤 5.213%、8/7 收盤 5.19% 回落 → 今日盤中 5.222% 再越；若今日收盤 ≥5.20%，近 3 個交易日 2 度越線 → 模式A 防禦正式啟動（停止新增存續期&gt;5年債券、平衡基金禁加碼），實務上已視同警戒執行。距 5.30% 債券凍結紅線僅 7.8bp；Warsh 鷹派溝通＋8 月通膨預測上修風險下，9 月會議前任何強勁數據都可能再測紅線。</div>
<div class="card"><b>國泰核貸階段（8/10 19:14 新計畫定案）：</b>8/3 對保 → 8/4 地政設定 → 8/7 地政完成寄回國泰 → 8/12 板橋國泰及地政 → <b>8/15 撥款 1,200萬 @2.6%</b> → ①償還星展理財型 200萬 @4% 全清（8/10 已先還 100萬）②剩 1,000萬買短中期投資級債（1-3yr）③債券質押 5 成拉出 500萬（質押成數 4 成改 5 成、禁疊三層）④500萬清償高利貸：保單質押 400萬＋證券質押 100萬 ⑤盤點金融資產申請專業投資人（3,000萬門檻）。審查期規則全數維持：00983D 暫緩、單筆≥5萬暫停、00878 續建 4 週、現金底線 6 個月（約 85.2 萬）；現金 229.2 萬 = 底線 2.7 倍，安全無虞（較 8/7 329 萬下降係因 8/10 償還星展 100 萬）。</div>
</div>

<div class="foot">龍九控股內部報告｜僅供決策參考，非投資建議｜資料時間 2026-08-10 21:36 台北（開盤約 6 分鐘）｜Yahoo Finance 即時 + Google News RSS + snapshot.json 穿透數據</div>
</div></body></html>"""


def write_htmls():
    css_html = HTML.replace("__CSS__", CSS)
    rail = BASE / f"emergency_report_{TODAY}.html"
    gh = BASE / f"emergency_taiex_report_{TODAY}.html"
    rail.write_text(css_html, encoding="utf-8")
    gh.write_text(css_html.replace("美股緊急應變報告 2026-08-10 21:30｜龍九控股", "台股/美股緊急應變報告 2026-08-10 21:30｜龍九控股"), encoding="utf-8")
    print(f"[HTML] {rail} ({rail.stat().st_size} bytes)")
    print(f"[HTML] {gh} ({gh.stat().st_size} bytes)")


if __name__ == "__main__":
    write_json()
    write_htmls()
    print("[DONE]", NOW)
