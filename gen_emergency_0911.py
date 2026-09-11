# -*- coding: utf-8 -*-
"""2026-09-11 緊急應變：台股盤中 -2.21% + 美股連四黑（費半 -2.66%）+ 油價破百 + US30Y 5.36%
使用者 9/11 核准手動補跑（cron monitor 於 9/10 判 no_change 漏掉美股收盤那根）。
產出：data/emergency_llm_analysis.json（日報第6章注入源）+ 兩份 HTML。
"""
import json, datetime, re
from pathlib import Path

BASE = Path(__file__).resolve().parent
NOW = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
DATE = datetime.date.today().isoformat()

FULL = """🚨 緊急應變報告（2026-09-11 盤中｜手動補跑）
產出時間：__NOW__ ｜ 觸發：台股盤中 -2.21% + 美股連四黑（費半 -2.66%）+ 油價破百 + US30Y 突破 5.30%

【一、市場概況】
・台股：加權 46,142.16（-2.21%），開盤 46,651.21 後一路走弱；台積電 2,425 元（-1.02%），盤中一度下殺 35 元逼近月線。8 月營收首度突破 5,000 億創歷史新高，股價卻不漲反跌 → 典型「基本面利多、外部風險主導」。
・美股（9/10 收）：道瓊 52,064.10；S&P 7,591.70（-0.58%）；納指 26,081.72（-0.65%）；費半 11,614.17（-2.66%）→ 連四日收黑，半導體為重災區。
・波動與商品：VIX 17.84（+8.38%，單日跳升）；WTI 102.38（+6.59%）、Brent 107.45（+6.17%）→ 油價正式破 100 美元。
・利率：US30Y 5.36%（單日 +1.42%）、US10Y 4.94%（+2.21%）→ 30 年期突破 5.30% 債券凍結紅線。
・匯率：USD/TWD 31.64（台幣貶 0.57%）。

【二、重大事件分析】
1. 中東地緣 × 荷莫茲海峽管制威脅 → 原油供給疑慮，油價單日 +6%，是這輪「通膨預期回燃 → 殖利率上衝 → 股市承壓」的傳導起點。
2. 升息預期回燃：油價破百 + 今晚（美東 9/11）8 月 CPI 公布，市場提前定價緊縮風險，30Y 一舉跳上 5.36%。
3. 美股連四黑、費半 -2.66%：AI／半導體在高估值下遇到利率上行，性質是「估值修正」，不是企業獲利崩壞。
4. 台股結構差異：台積電基本面續強、卻是外資與國際風險主導短線，權值股拖累指數。
5. 判讀：這是「事件驅動的風險重定價」，不是景氣轉折。真正要盯的是今晚 CPI 與 9/16 FOMC，而非今天的指數點位。

【三、持倉關聯分析】（真值：snapshot 2026-09-11，總資產 26,161,227）
・台股部位 7.6%（1,980,680 元）→ 大盤 -2.2% 粗估 -4.4 萬（未實現，占總資產 -0.17%），傷害有限。
・美股部位 44.9%（科技 12.4% / 非科技 32.5%）→ 費半 -2.66%、納指 -0.65%，已反映在昨收；今日台股時段美股休市。
・債券 17.3%：30Y 5.36% 續壓價格，中短天期較抗；不因單日跳升加碼或砍倉。
・現金／安全網 22.4%：含國泰貨幣市場基金 5,003,846（贖回在途，9/16 入帳）＋銀行現金 857,298 → 底線 70 萬 ✅。
・保單 9,661,253（安聯 A+B 7,664,202 + 第一金 1,902,345）：淨值型受波動影響，但持有目的是配息現金流，不動。
・黃金 CFTC 淨多單 228,124（週減 -6.3%）；石油淨多單 -24,651（週減 -62.8%，聰明錢撤離）→ 油價漲勢由地緣風險溢價驅動，不是趨勢性做多。

【四、資產配置透視】
・實際 vs 目標：台股 7.6%（目標 10%，-2.4pp）｜美股 44.9%（目標 40%，+4.9pp）｜防守 4.4%（目標 20%）｜債券 17.3%（目標 25%）｜現金 22.4%（目標 5%，階段性停泊）。
・美股超標與現金超額是一體兩面：贖回資金停泊未部署、台股部位偏低的鏡像。
・目前不具備「逢跌加碼」的紀律條件：① 質押撥款未到位（今天才簽約、撥款 2-4 週）② Fed 新資料未落地（今晚 CPI、9/16 FOMC）③ US30Y 已破 5.30 凍結線，債券不進場。

【五、巴菲特視角建議】
・價格與價值分離：台積電營收創高、股價下跌，跌的原因是利率與油價，不是獲利轉弱 → 這種下跌不構成賣出理由，也不構成急著買進的理由。
・不追高、不殺低：部位是零槓桿現貨、無追繳風險，現金 22.4% 就是最大緩衝，不需要為單日行情調整。
・唯一被授權的動作仍是「台股慢慢買（0050／006208）」，但前提是質押撥款到位＋Fed 資料落地 → 今天不做。
・安全邊際來自「等」：油價破百若持續 → 通膨路徑惡化 → 升息 → 估值再壓；反之 CPI 溫和、殖利率回落才是進場訊號。

【六、風控檢查】
・🔴 US30Y 5.36% 突破 5.30% 凍結紅線（Yahoo ^TYX 9/10 收盤；FRED 官方值待公布）→ 債券 ladder 凍結、不加碼不贖回；若連 3 日站上 5.30，需重新檢視質押買債套利前提（CPI 低於 3% 未成立）。
・🔴 油價 102-107（破百）：通膨傳導是今晚 CPI 之外的最大變數。
・🟡 美元曝險 64.1%（超 50% 紅線 14pp）：台幣本日走貶，續觀察、不急調整。
・🟡 地緣風險 43.6（荷莫茲海峽）：緊急防範雷達監控中，石油部位 Locked 不參與。
・✅ 現金底線 857,298 元 ≥ 700,000 元；零槓桿、無追繳。
・✅ 保單：淨值 60% 為主風險，還債＝修保單路徑執行中；今天 13:00 板橋國泰質押簽約 350 萬 @2.8% 固定（撥款 2-4 週，屬銀行作業、不受市場 gate 影響）。
・⛔ 今日禁令：質押／轉貸資金禁止生活消費擴張；未達 gate 前不新增美元、不建債梯、不追台股。

【行動摘要】
1. 今天 13:00 質押簽約照常（銀行作業）；撥款到位後，部署仍等 US30Y 回落 5.30 以下或 9/16 FOMC 定調。
2. 今晚 CPI 是第一個開關：高於預期 → 維持全面觀望；低於預期 → 殖利率回落才考慮台股第一批（0050／006208）。
3. 9/16：FOMC + 國泰 MMF 贖回款 5,003,846 入帳（入帳後才 基金→現金 轉列）。
4. 系統缺口（待修）：美股應變只在 21:30 開盤時點檢查，昨晚收盤那根沒有第二輪檢核 → 建議新增「美股收盤檢核」。""".replace("__NOW__", NOW)

SUMMARY = "台股 -2.21%（46,142）＋美股連四黑（費半 -2.66%）＋油價破百（WTI 102.38）＋US30Y 5.36% 突破 5.30 凍結紅線。台股部位 7.6% 粗估 -4.4 萬，影響有限；現金底線 ✅。結論：事件驅動的風險重定價，非景氣轉折 — 全面觀望，等今晚 CPI 與 9/16 FOMC。"

chapters = {
    "一、市場概況": "台股 46,142.16（-2.21%）盤中走弱，台積電 2,425（-1.02%）；美股連四日收黑，S&P -0.58%、納指 -0.65%、費半 -2.66%；VIX 17.84（+8.38%）；WTI 102.38（+6.59%）、Brent 107.45 破百；US30Y 5.36%（+1.42%）；USD/TWD 31.64。",
    "二、重大事件分析": "中東地緣與荷莫茲海峽管制威脅推升油價，通膨預期回燃帶動殖利率跳升，AI／半導體高估值估值修正；今晚美東 8 月 CPI 公布為升息警戒開關。性質為事件驅動的風險重定價，非景氣轉折。",
    "三、持倉關聯分析": "台股 7.6%（1,980,680）粗估 -4.4 萬；美股 44.9%（科技 12.4%／非科技 32.5%）昨收已反映；債券 17.3% 價格承壓；現金／安全網 22.4%（含在途 MMF 5,003,846）；保單 9,661,253 配息目的不動；黃金淨多單週減 6.3%、石油淨多單週減 62.8%。",
    "四、資產配置透視": "台股 7.6%（目標 10%）｜美股 44.9%（目標 40%，+4.9pp）｜防守 4.4%（目標 20%）｜債券 17.3%（目標 25%）｜現金 22.4%（目標 5%）。美股超標＋現金停泊未部署；逢跌加碼的三個前提（撥款／Fed 資料／US30Y 回落）皆未成立。",
    "五、巴菲特視角建議": "台積電營收創高而股價下跌＝價格與價值分離，跌因利率與油價而非獲利；不追高不殺低，現金 22.4% 為最大緩衝；唯一授權動作台股慢慢買仍需等撥款與 Fed 資料；安全邊際來自等待。",
    "六、風控檢查": "US30Y 5.36% 破 5.30 凍結紅線（債券凍結）；油價破百為通膨傳導變數；美元曝險 64.1% 超線續觀察；地緣 43.6 監控中；現金底線 857,298 ≥ 70 萬 ✅；今日 13:00 質押簽約照常（銀行作業）。",
}

market_snapshot = {
    "date": DATE,
    "taiex": {"price": 46142.16, "pct": -2.21, "open": 46651.21},
    "tsmc": {"price": 2425.00, "pct": -1.02},
    "us": {"dji": 52064.10, "spx": 7591.70, "spx_pct": -0.58, "ixic": 26081.72, "ixic_pct": -0.65,
           "sox": 11614.17, "sox_pct": -2.66, "session": "2026-09-10 收"},
    "vix": 17.84, "vix_pct": 8.38,
    "wti": 102.38, "wti_pct": 6.59, "brent": 107.45, "brent_pct": 6.17,
    "us30y": 5.36, "us10y": 4.94, "usdtwd": 31.64,
    "trigger": "台股盤中 -2.21%（< -2% 門檻）＋美股連四黑＋油價破百＋US30Y 破 5.30",
}

payload = {
    "generated_at": NOW,
    "source": "台股盤中緊急應變 09:40 手動補跑（使用者核准；cron 9/10 21:30 monitor 判 no_change 漏掉美股收盤跌幅）",
    "full_report": FULL,
    "chapters": chapters,
    "market_snapshot": market_snapshot,
    "summary": SUMMARY,
}
jf = BASE / "data" / "emergency_llm_analysis.json"
old = json.loads(jf.read_text(encoding="utf-8")) if jf.exists() else {}
bak = BASE / "data" / f"emergency_llm_analysis.bak-{datetime.date.today().strftime('%Y%m%d')}.json"
if old:
    bak.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
jf.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"✅ JSON 已寫入（full_report {len(FULL)} 字）｜舊版備份 {bak.name}")

# ── HTML（兩版共用同一份內容） ──
def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

paras = "".join(
    f"<p style='margin:8px 0'>{_esc(ln)}</p>" if ln.strip() else ""
    for ln in FULL.split("\n")
)

CSS = """body{background:#0d1117;color:#e6edf3;font-family:'Segoe UI','Microsoft JhengHei',sans-serif;
line-height:1.75;padding:22px;max-width:900px;margin:0 auto}
h1{font-size:24px;margin:0 0 6px}
.sub{color:#8b949e;font-size:13px;margin-bottom:16px}
.bar{background:rgba(248,81,73,.12);border:1px solid rgba(248,81,73,.45);border-radius:8px;
padding:10px 14px;font-weight:700;margin:14px 0;color:#f85149}
.card{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:18px 22px;margin-bottom:16px}
.card h2{font-size:17px;color:#58a6ff;border-bottom:1px solid #30363d;padding-bottom:8px;margin:0 0 12px}
p{margin:7px 0}
.meta{color:#8b949e;font-size:12.5px;margin-top:18px;text-align:center}"""

def build(title, alert, note):
    return f"""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} {DATE}</title><style>{CSS}</style></head><body>
<h1>{title}</h1>
<div class="sub">報告日：{DATE} ｜ 產出：{NOW} ｜ {note}</div>
<div class="bar">{alert}</div>
<div class="card"><h2>完整分析（六章節）</h2>{paras}</div>
<div class="meta">⏰ 下一輪：今日 13:00 台股應變 ／ 今日 21:30 美股應變</div>
</body></html>"""

alert = "🔴 台股 -2.21% ｜ 費半 -2.66%（連四黑）｜ WTI 102.38 破百 ｜ US30Y 5.36% 破 5.30 凍結紅線"
p_taiex = BASE / f"emergency_taiex_report_{DATE}.html"
p_emerg = BASE / f"emergency_report_{DATE}.html"
p_taiex.write_text(build("🚨 台股緊急應變報告", alert, "觸發：台股盤中 -2.21% × 美股連四黑 × 油價破百"), "utf-8")
p_emerg.write_text(build("🚨 緊急應變報告（台股／美股綜合）", alert, "觸發：台股盤中 -2.21% × 美股連四黑 × 油價破百 × US30Y 破線"), "utf-8")
print(f"✅ HTML：{p_taiex.name} / {p_emerg.name}")
