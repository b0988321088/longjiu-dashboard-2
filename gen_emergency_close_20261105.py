# -*- coding: utf-8 -*-
"""2026-11-05 台股收盤版緊急應變重產（真重跑：收盤行情＋校正後真值）

13:00 版為盤中（41,862.47 −2.53%），收盤 41,574.72 −3.20%，尾盤再殺 288 點 → 舊敘述失效。
本檔以 11/05 台股收盤 + 11/04 美股收盤 + snapshot 真值（總資產 26,613,591）重寫六章。
"""
import json
from pathlib import Path
from datetime import datetime

LJ = Path(__file__).resolve().parent
today = "2026-11-05"

REPORT = """【一、市場概況】
11/05 台股收盤 41,574.72（-3.20%，單日 -1,374 點），昨收 42,948.91。盤中 13:00 時為 41,862.47（-2.53%），尾盤再殺約 288 點，收在當日相對低檔——這代表賣壓不是開盤恐慌一次性宣洩，而是愈接近收盤愈重。台積電 2,240.00（-0.88%），權值仍相對抗跌。
昨夜美股是相反世界：道瓊 53,356.12（+3.03%）、S&P 500 7,688.62（+1.58%）、納指 25,736.51（+1.44%），費半 10,268.65（-3.13%）是唯一重災。匯率是今天最關鍵的線索：美元兌台幣 32.94（+0.64%），台幣明顯走貶。US30Y 5.28%、10Y 4.89%，長天期殖利率小幅回落，沒有系統性風險惡化的跡象。

【二、重大事件分析】
1. 今天是「台股自己的評價修正＋外資匯出」的組合，不是全球風險事件。證據：美股四大指數昨夜三紅，台幣單日貶 0.64%，而台股杀 3.20%——若為全球性避險，美債殖利率應該同步跳升、黃金應該成為唯一避風港；實際上 30Y 反跌 4bp、黃金 4,127.5（+1.34%）只是溫和避險，符合「資金從台股評價高的地方搬走、不離開風險資產」的型態。
2. ETF 分化極為劇烈，直接標出資金去向：主動式與半導體最慘——00981A -7.43%、00927 -5.69%、0056 -3.73%、0050 -3.43%、006208 -3.47%；高息低波抗跌——00713 -0.93%、00919 -1.67%、00878 -2.48%。同一時間 00646（S&P500）逆勢 +2.51%、00983D +1.72%。這是「確定收益＋海外」對「高本益比台股」的相對強弱，不是全面崩跌。
3. 全球背景沒有轉壞：道瓊 +3.03% 創近期單日最大漲幅之一，市場對美國政策與利率路徑的定價在改善；費半 -3.13% 是 AI 硬體族群的獨立修正，與 8-10 月的節奏一致（硬體殺、軟體與大盤撐）。
4. 引擎情境：確定收益輪動仍為最高分情境、科技重新定價居次、美元信用壓力分數低；燈號維持黃燈。今天的盤面再次驗證這個排序——高息低波守住、科技主題被修理。
5. 風險煞車已觸發：單日 -3.20% ＞ 3% 門檻。依 8/24 授權規則，急跌超過 3% 一律「暫緩並回報」，今天不執行任何加碼或減碼動作。

【三、持倉關聯分析】
台股桶 2,731,350（10.3%），今日依逐檔昨收→收盤計算，組合實際損失 -70,310（-2.74%），略優於大盤 -3.20%，原因是高息低波與 00646/00983D 的逆勢部位提供緩衝。
① 跌最重＝主動式與半導體：00981A -14,800、00927 -3,600、0056 -2,000。00981A 單日 -7.43%，是全部持股中跌幅最深，這正是「主動式高本益比成分在評價收縮時沒有分散保護」的實證。
② 抗跌與逆勢：00646 +1,950（跟著昨夜 S&P +1.58%）、00983D +3,400（複合收益，利率回落受益）、00713 僅 -1,200。這三檔合計貢獻 +3,750，是今天沒有更慘的唯一原因。
③ 權值股 2330 -0.88% 明顯強於大盤 -3.20%，說明殺盤集中在中小型與高評價題材，不是對台灣 AI 供應鏈基本面的否定。
美股桶 10,043,301（37.7%），其中科技 3,841,800（14.4%）。科技 14.4% 距 15% 紅線僅 -0.6pp，是全部桶位裡最貼線的一項——但部位多數在保單與後收基金內（CDSC 未到期），可減性極低，減碼不是選項。

【四、資產配置透視】
總資產 26,613,591（校正後真值；淨值 -4,338,171）。台股 10.3%（目標 10，+0.3pp）｜美股 37.7%（目標 30，+7.7pp；單桶硬上限 40 未破）｜防守型配息 18.0%（目標 30，-12.0pp）｜債券 25.8%（目標 25，+0.8pp）｜現金 4.2%（目標 5，-0.8pp）｜科技 14.4%（目標 15，-0.6pp）、非科技 23.3%。
三個判讀：
① 台股 +0.3pp 是「微超標」不是「便宜該接」。跌 3.20% 之後仍在目標上方，凍結期內沒有任何理由動用押標金 700,000。
② 美股 +7.7pp 是最大的結構性超配，但可減性極低（保單／後收），減碼不是選項，導流才是。
③ 防守 -12.0pp 是最大缺口，且保單內部位不可即時調節 → 只能靠配息導流與保單內轉換慢慢補。雙維度防禦 49.5%（12,724,636／25,713,591），仍在 50% 下方一格。

【五、巴菲特建議】
不抄底，今天零交易。三個理由：
① 今天 -3.20% 已觸發單日急跌 3% 的風險煞車線。煞車線的設計不是「跌了就買」，而是「跌太快要先停手看清楚」——尾盤比盤中更弱，代表明天還有下探的可能。
② 2026-11-02～11-30 投資凍結令仍在：台股分批、0051 承接、美債 ladder、避險衛星加碼、再平衡加碼全部暫停。超標減碼與風控賣出不在凍結範圍，但今天沒有觸發（美股 37.7% 未破 40%）。
③ 子彈不夠：可動用現金 1,128,856，扣掉 11/11 押標金 700,000 待命後剩 428,856，恰等於距現金底線 700,000 的餘裕——沒有第二發。台幣同時在貶（32.94），此時加碼台股等於在匯率逆風時追高成本。
具體動作：台股不補（10.3% 仍在目標上）；美股不減（37.7% 未破 40%，且後收不可減）；本月配息 17,577 不投入成長桶，維持現金與防守導流。若 11/11 決定不投標，押標金 700,000 回歸後才有新的部署空間。

【六、風控檢查】
US30Y 5.28%（11/04），模式 A 防禦區 5.20–5.30 已連續 48 日，紅線 5.30 未破（紅線連續 0 日）→ 長天期債券新增買單維持凍結，科技部位上限不鬆綁。
質押：借款 5,900,000、池市值 11,909,979、維持率 201.9%、LTV 49.5%，未達內部停止線（LTV 53%）；距內部停止線池需再跌 6.53%，距銀行通知 160% 需跌 20.7%、距追繳 140% 需跌 30.6%。池子每跌 1% ＝ 119,100 元 ≈ 維持率 -2.0pp。今天殺台股，質押池是國泰三檔基金（富達／B11／聯博），直接衝擊有限——但 6.53% 的緩衝不算厚，若費半這種單日 -3% 的跌勢連續兩天出現，緩衝會被吃掉約一半，這是本週唯一需要盯的數字。銀行維持率公式與補繳期限仍待書面（E1），在此之前以內部線為準。
現金：可動用 1,128,856、指定款 900,000 不列可動用、底線 700,000（單一口徑），餘裕 428,856。
配息與租金：本月已收配息 17,577（保單 9,817＋基金 7,760，含聯博 7,027、路博邁 733），房租 24,000（店面；其餘 56,100 待收），被動月收 41,577。
美元曝險 69.9%（目標 60／黃 65／紅 70）→ advisory 只回報不觸發，但已貼紅線前一格；今天台幣貶 0.64%，方向對我們有利（美元資產折算台幣變多），但這不是可以依賴的報酬來源。
觸發狀態：單日急跌煞車已觸發（-3.20% > 3%）；依授權規則本班屬「暫緩並回報」，不做任何交易。台股 gate 門檻 -1.5% 早已達，屬門檻內正常產出，不是升級事故。
新聞來源：Yahoo 台股 RSS（tw.stock.yahoo.com）＋ Yahoo chart API 收盤行情＋ daily_analysis briefing。
"""

def main():
    snap = json.loads((LJ / "snapshot.json").read_text(encoding="utf-8"))
    p = snap["penetration"]; t = p["actual_twd"]; pc = p["actual_pct"]
    mkt = json.loads((LJ / "_mkt.json").read_text(encoding="utf-8"))
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "date": today,
        "source": "台股緊急應變（11/05 收盤重產｜真值校正後）",
        "analysis_target": "台股收盤",
        "market_snapshot": {
            "TWII": mkt["加權"]["last"], "TWII_chg_pct": mkt["加權"]["pct"],
            "TSMC_2330": mkt["台積電"]["last"], "TSMC_2330_chg_pct": mkt["台積電"]["pct"],
            "SOX": mkt["費半"]["last"], "SOX_chg_pct": mkt["費半"]["pct"],
            "DJI": mkt["道瓊"]["last"], "DJI_chg_pct": mkt["道瓊"]["pct"],
            "SPX": mkt["S&P500"]["last"], "SPX_chg_pct": mkt["S&P500"]["pct"],
            "IXIC": mkt["納指"]["last"], "IXIC_chg_pct": mkt["納指"]["pct"],
            "US30Y": snap.get("us30y_yield") or 5.282,
            "US10Y": mkt["10Y"]["last"], "USDTWD": mkt["美元台幣"]["last"],
            "GOLD": mkt["黃金"]["last"], "OIL": mkt["原油"]["last"],
        },
        "portfolio_intraday": {
            "台股桶_twd": t["台股市值型成長"], "台股桶_pct": pc["台股市值型成長"],
            "美股桶_twd": t["美股市值型成長"], "美股桶_pct": pc["美股市值型成長"],
            "科技穿透_twd": t["美股市值型成長_科技"], "科技穿透_pct": pc["美股市值型成長_科技"],
            "台股組合今日損益": -70310,
            "0050_pct": mkt["0050"]["pct"], "006208_pct": mkt["006208"]["pct"],
            "0056_pct": mkt["0056"]["pct"], "00878_pct": mkt["00878"]["pct"],
            "00919_pct": mkt["00919"]["pct"], "00713_pct": mkt["00713"]["pct"],
            "00981A_pct": mkt["00981A"]["pct"], "00927_pct": mkt["00927"]["pct"],
            "00646_pct": mkt["00646"]["pct"], "00983D_pct": mkt["00983D"]["pct"],
        },
        "total_assets": snap["total_assets"],
        "full_report": REPORT.strip(),
    }
    out = LJ / "data" / "emergency_llm_analysis.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 已寫入 {out}（full_report {len(REPORT)} 字）")

    # ── HTML（沿用 13:03 版的版面語言：卡片式、淺底、表格）──
    def kpi(label, val, sub=""):
        return (f'<div class="kpi"><div class="l">{label}</div><div class="v">{val}</div>'
                f'<div class="s">{sub}</div></div>')
    cards = [
        ("📉", "台股收盤", f'{mkt["加權"]["last"]:,.2f}', f'{mkt["加權"]["pct"]:+.2f}%｜尾盤再殺 288 點', "neg"),
        ("🇺🇸", "美股昨收 S&P", f'{mkt["S&P500"]["last"]:,.2f}', f'{mkt["S&P500"]["pct"]:+.2f}%｜道瓊 {mkt["道瓊"]["pct"]:+.2f}%', "pos"),
        ("💵", "美元兌台幣", f'{mkt["美元台幣"]["last"]:.2f}', f'{mkt["美元台幣"]["pct"]:+.2f}%｜台幣走貶', "neg"),
        ("📊", "總資產", f'{snap["total_assets"]:,}', f'淨值 {snap["net_worth"]:,}', ""),
        ("🛡️", "雙維度防禦", f'{snap["dual_dimension_metric"]["防禦維度"]["佔比"]}%', "門檻 50%（未達）", "warn"),
        ("💧", "可動用現金", f'{snap["cash_layers"]["unrestricted_cash"]:,}', f'乾粉 {snap["cash_layers"]["dry_powder"]:,}', ""),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="l">{i} {l}</div><div class="v {c}">{v}</div><div class="s">{s}</div></div>'
        for i, l, v, s, c in cards)

    def para(block):
        lines = [x for x in block.split("\n") if x.strip()]
        html = []
        for ln in lines:
            if ln.startswith("【"):
                html.append(f'<h2>{ln.strip("【】")}</h2>')
            else:
                html.append(f"<p>{ln}</p>")
        return "\n".join(html)

    body = "\n".join(para(b) for b in REPORT.strip().split("【"))

    tbl_rows = "".join(
        f"<tr><td>{k}</td><td class='num'>{t[k]:,}</td><td class='num'>{pc[k]}%</td></tr>"
        for k in ["台股市值型成長", "美股市值型成長", "防守型配息", "債券", "現金/安全網"])

    html = f"""<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🚨 台股緊急應變（收盤版）{today}</title>
<style>
:root{{--bg:#f5f5f7;--card:#fff;--line:#e3e3e8;--tx:#1d1d1f;--mut:#6e6e73;--red:#d32f2f;--grn:#0f9d58;--yel:#b26a00;--blu:#0b63c5}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--tx);font-family:-apple-system,'Noto Sans TC','Microsoft JhengHei',sans-serif;line-height:1.75;padding:20px}}
.wrap{{max-width:920px;margin:0 auto}}
header{{background:linear-gradient(135deg,#1c1c1e,#3a3a3c);color:#fff;border-radius:14px;padding:24px 26px;margin-bottom:16px}}
header h1{{font-size:23px;font-weight:800;letter-spacing:.5px}}
header .sub{{color:#c7c7cc;font-size:13px;margin-top:6px}}
.alert{{background:#ffebee;border-left:5px solid var(--red);color:var(--red);font-weight:700;padding:14px 18px;border-radius:10px;margin-bottom:18px;font-size:16px}}
.kpis{{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:18px}}
.kpi{{flex:1;min-width:150px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}}
.kpi .l{{font-size:12px;color:var(--mut)}}
.kpi .v{{font-size:21px;font-weight:800;margin-top:4px}}
.kpi .s{{font-size:12px;color:var(--mut);margin-top:2px}}
.pos{{color:var(--grn)}} .neg{{color:var(--red)}} .warn{{color:var(--yel)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 22px;margin-bottom:16px}}
.card h2{{font-size:18px;font-weight:800;color:var(--blu);border-bottom:1px solid var(--line);padding-bottom:8px;margin:18px 0 10px}}
.card h2:first-child{{margin-top:0}}
.card p{{font-size:16px;margin:8px 0}}
table{{width:100%;border-collapse:collapse;font-size:15px;margin-top:10px}}
th,td{{border:1px solid var(--line);padding:9px 10px;text-align:left}}
th{{background:#fafafa;font-weight:700}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.meta{{text-align:center;color:var(--mut);font-size:12px;padding:16px 0}}
</style></head><body><div class="wrap">
<header>
  <h1>🚨 台股緊急應變｜收盤版</h1>
  <div class="sub">{today} 15:5x 重產（真值校正後）｜觸發：加權 -3.20%（>3% 急跌煞車）｜原 13:00 盤中版已作廢</div>
</header>
<div class="alert">⚠️ 單日急跌 -3.20% 已觸發風險煞車 → 依授權規則「暫緩並回報」，今日零交易。</div>
<div class="kpis">{kpi_html}</div>
<div class="card">
{body}
<h2>五桶穿透（真值）</h2>
<table><tr><th>桶位</th><th class="num">金額 TWD</th><th class="num">佔比</th></tr>{tbl_rows}</table>
</div>
<div class="meta">資料來源：Yahoo chart API（11/05 台股收盤／11/04 美股收盤）＋ snapshot.json 真值｜產生 {payload["generated_at"]}</div>
</div></body></html>"""
    (LJ / f"emergency_report_{today}.html").write_text(html, "utf-8")
    print(f"✅ 已寫出 emergency_report_{today}.html（{len(html):,} bytes）")

if __name__ == "__main__":
    main()
