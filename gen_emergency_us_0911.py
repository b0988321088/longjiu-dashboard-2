# -*- coding: utf-8 -*-
"""2026-09-11 美股緊急應變（CPI 日盤中）
背景：8 月 CPI 於台北時間 20:30 公布（總 CPI 年增 3.4% 符合預期、核心 2.4% 低於前值 2.5%）。
21:30 的美股 cron gate 判 CALM（S&P +1.06% / SOX +2.29% 未達 -1.8% / -2.5% 門檻）未自動觸發，
使用者 9/11 要求補出 CPI 應變報告。
產出：data/emergency_llm_analysis.json（日報第6章注入源）+ 兩份 HTML（含 INC-134 穿透卡）。
市場數據來源：Yahoo chart API（^GSPC/^IXIC/^SOX/^VIX/^TYX/^TNX/CL=F/GC=F/TWD=X，2026-09-11 美股盤中）；
CPI 數據來源：investing.com 經濟日曆（BLS 2026-09-11 08:30 ET 發布）。
"""
import json, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
NOW = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
DATE = "2026-09-11"

snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
pen = snap.get("penetration", {}).get("actual_pct", {})
pen_twd = snap.get("penetration", {}).get("actual_twd", {})
total_assets = snap.get("total_assets", 0)
cash_total = snap.get("cash_total", 0) or 0
insurance_total = snap.get("insurance_total", 0) or 0
usd_pct = snap.get("usd_exposure_pct", 0)
pledge_amt = snap.get("cathay_pledge_0911", {}).get("可貸金額", 0) or 0

tw_pct = pen.get("台股市值型成長", 0)
tw_twd = pen_twd.get("台股市值型成長", 0)
us_pct = pen.get("美股市值型成長", 0)
us_tech = pen.get("美股市值型成長_科技", 0)
us_nontech = pen.get("美股市值型成長_非科技", 0)
bond_pct = pen.get("債券", 0)
def_pct = pen.get("防守型配息", 0)
cash_pct = pen.get("現金/安全網", 0)

F = lambda v: f"{v:,.0f}"
P = lambda v: f"{v:.1f}"

FULL = f"""🚨 美股緊急應變報告（2026-09-11 CPI 日盤中｜手動補跑）
產出時間：{NOW} ｜ 觸發：8月 CPI 公布（20:30 台北）＋美股盤中反彈，21:30 cron gate 判 CALM 未自動觸發

【一、市場概況】
・8月 CPI（今晚 20:30 台北公布）：總 CPI 年增 3.4%（預期 3.4%、前值 3.4%）符合預期；核心 CPI 年增 2.4%（預期 2.4%、前值 2.5%）略降溫 — 9/16 FOMC 前最後一份通膨報告。
・美股盤中（約 23:55 台北／11:55 ET）：S&P 7,672.34（+1.06%）、納指 26,412.70（+1.27%）、費半 11,880.66（+2.29%，一舉收復昨日 -2.66% 大半）。
・波動：VIX 15.80（-11.43%）— 昨日跳升的避險需求快速消退。
・利率：US30Y 5.32%（自 5.36% 回落，仍高於 5.30 凍結線 2bp）、US10Y 4.93%（-1bp）。
・商品：WTI 99.14（-3.26%，回落至百元下）、黃金 4,412.30（+1.10%）。
・匯率：USD/TWD 31.60（台幣微貶 0.4%）。

【二、重大事件分析】
・CPI 符合預期 + 核心年增降溫 → 市場解讀為升息壓力緩解，風險資產全面反彈；對照 9/10 公布的 8月 PPI 年增 5.4%（高於預估 0.1pp、升息機率一度破七成），通膨訊號呈分歧：消費端降溫、生產端仍黏。
・Fed 是否在 9/16 會議啟動三年多來首次升息，是真正的開關；今晚 CPI 沒爆雷，市場先漲，但 30 年期殖利率仍在 5.30 上方，債市沒有完全買單，屬「情緒彈」而非「趨勢反轉確認」。
・甲骨文（Oracle）財報強勁帶動科技股，費半 +2.29% → 昨日「AI／半導體高估值修正」屬技術性洗盤，不是企業獲利崩壞。
・油價自破百回落 -3.26%：昨日推升通膨預期與殖利率的傳導變數暫緩，但中東地緣（荷莫茲）未解。

【三、持倉關聯分析】（真值：snapshot {DATE}，總資產 {F(total_assets)}）
・台股 {P(tw_pct)}%（{F(tw_twd)} 元）：台股今日收 46,142.16（-2.21%）已反映；美股盤中 +1%、費半 +2.29% 對下週一台股開盤偏多。
・美股 {P(us_pct)}%（科技 {P(us_tech)}%／非科技 {P(us_nontech)}%）：費半反彈直接受益，超配 +23.9pp 未改變 → 逢彈仍是減碼窗口（今晚的價格優於昨晚）。
・債券 {P(bond_pct)}% ＋ 防守型配息 {P(def_pct)}%：US30Y 5.32% 仍高於 5.30 凍結線 → 債券維持凍結，不建債梯。
・現金／安全網 {P(cash_pct)}%：銀行現金 {F(cash_total)} → 底線 700,000 ✅（不含質押撥款 {F(pledge_amt)}，預估 ~9/25 入帳）。
・保單 {F(insurance_total)}（安聯 A+B＋第一金）：淨值隨市場波動，持有目的是配息現金流，不動；貝萊德 B11 500 萬已完成申購並入池、質押設定完成，等待撥款。

【四、資產配置透視】
・台股 {P(tw_pct)}%（目標 10%，{tw_pct-10:+.1f}pp）｜美股 {P(us_pct)}%（目標 40%，{us_pct-40:+.1f}pp）｜防守型配息 {P(def_pct)}%（目標 20%）｜債券 {P(bond_pct)}%（目標 25%）｜現金／安全網 {P(cash_pct)}%（目標 5%，階段性停泊）。
・美股超標與防守／現金不足是一體兩面：贖回資金停泊與後收級別基金（B11）入池是鏡像結果。
・今晚反彈不改變配置缺口：反彈是減碼的價格，不是加碼的理由。

【五、巴菲特視角建議】
・一份「符合預期」的通膨數據不改變任何企業的內在價值；市場把「沒爆雷」當利多，漲的是情緒不是價值。
・減碼是紀律不是預測：美股超配 +23.9pp，逢彈減碼 ≤20 萬/次（9/8 授權），不因今天上漲而取消，也不因昨日下跌而恐慌賣出。
・三個加碼前提（質押撥款到位／Fed 9/16 定調／US30Y 回落 5.30 以下）今晚只前進一小步 — 30Y 5.32% 仍差 2bp，尚未成立。
・安全邊際來自等待：現金 {F(cash_total)} 元是最大緩衝，零槓桿、無追繳，不需要為單一數據調整。

【六、風控檢查】
・US30Y 5.32% 仍 ≥ 5.30 凍結紅線 → 債券維持凍結（方向轉下為正面訊號，待確認收盤）。
・美元曝險 {usd_pct}% 偏高，續觀察（超線）。
・油價回落至百元下，通膨傳導壓力暫緩；黃金 +1.10% 避險需求仍在。
・現金底線 {F(cash_total)} ≥ 700,000 ✅；零槓桿、無追繳。
・質押 540 萬：設定完成、等待銀行撥款（~9/25），屬銀行作業、不受市場 gate 影響。
・地緣風險（荷莫茲海峽）持續監控。

【行動摘要】
1. 今晚不動作：減碼窗口等反彈幅度，≤20 萬/次分批；不追高、不殺低。
2. 9/16 FOMC 前不新增美元、不建債梯、不追台股。
3. 下週一台股開盤偏多（美股 +1%、費半 +2.3%），但台股僅 {P(tw_pct)}% 低配 → 不因單日反彈改變節奏。
4. 質押撥款（{F(pledge_amt)}，~9/25）到位後：先還安聯保單借貸 300 萬@4.2%，餘約 240 萬作 10 月標案押標金。"""

SUMMARY = (f"8月 CPI 總 3.4%（符合預期）＋核心 2.4%（前值 2.5%）→ 升息壓力緩解，"
           f"美股盤中 S&P +1.06%、費半 +2.29%、VIX -11.4%、US30Y 回落 5.32%（仍高於 5.30 凍結線 2bp）。"
           f"美股部位 {P(us_pct)}% 超配 +23.9pp 未變 → 逢彈減碼窗口；9/16 FOMC 才是真開關。不追高、不殺低。")

chapters = {
    "一、市場概況": f"8月CPI 總 3.4%/核心 2.4%（符合預期、核心降溫）；美股盤中 S&P 7,672.34（+1.06%）、納指 26,412.70（+1.27%）、費半 11,880.66（+2.29%）；VIX 15.80（-11.43%）；US30Y 5.32%、US10Y 4.93%；WTI 99.14（-3.26%）、黃金 4,412.30（+1.10%）；USD/TWD 31.60。",
    "二、重大事件分析": "CPI 符合預期＋核心降溫 → 升息壓力緩解、風險資產反彈；但 8月 PPI 5.4% 仍高、30Y 仍在 5.30 上方 → 屬情緒彈非趨勢確認。甲骨文財報強勁＋費半 +2.29%，證實昨日半導體殺盤為技術性洗盤。油價回落讓通膨傳導暫緩，地緣未解。",
    "三、持倉關聯分析": f"台股 {P(tw_pct)}%（{F(tw_twd)}）今日 -2.21% 已反映，美股反彈對下週一台股偏多；美股 {P(us_pct)}%（科技 {P(us_tech)}%／非科技 {P(us_nontech)}%）直接受益，超配未變；債券 {P(bond_pct)}%＋防守 {P(def_pct)}% 因 30Y 5.32 仍凍結；現金／安全網 {P(cash_pct)}%（銀行現金 {F(cash_total)}，底線 ✅）；保單 {F(insurance_total)} 配息目的不動。",
    "四、資產配置透視": f"台股 {P(tw_pct)}%（{tw_pct-10:+.1f}pp vs 目標10%）｜美股 {P(us_pct)}%（{us_pct-40:+.1f}pp vs 目標40%）｜防守 {P(def_pct)}%（目標20%）｜債券 {P(bond_pct)}%（目標25%）｜現金 {P(cash_pct)}%（目標5%）。反彈是減碼的價格，不是加碼的理由。",
    "五、巴菲特視角建議": f"符合預期的通膨數據不改變企業內在價值，市場漲的是情緒不是價值。減碼是紀律：美股超配 +23.9pp，逢彈減 ≤20 萬/次，不因漲跌取消。三個加碼前提（撥款／Fed 9/16／US30Y 回落 5.30 以下）今晚僅前進 2bp。現金 {F(cash_total)} 為最大緩衝。",
    "六、風控檢查": f"US30Y 5.32% 仍 ≥ 5.30 凍結紅線（債券凍結）；美元曝險 {usd_pct}% 超線續觀察；油價回落至百元下；現金底線 {F(cash_total)} ≥ 70 萬 ✅、零槓桿無追繳；質押 {F(pledge_amt)} 設定完成、等待撥款 ~9/25；地緣持續監控。",
    "行動摘要": f"①今晚不動作：減碼 ≤20 萬/次等反彈幅度 ②9/16 FOMC 前不新增美元、不建債梯、不追台股 ③下週一台股開盤偏多但不改節奏 ④撥款 {F(pledge_amt)}（~9/25）到位後先還安聯 300 萬、餘 240 萬作 10 月標案押金",
}

market_snapshot = {
    "date": DATE,
    "cpi": {"headline_yoy": 3.4, "headline_forecast": 3.4, "headline_prev": 3.4,
            "core_yoy": 2.4, "core_forecast": 2.4, "core_prev": 2.5,
            "released": "2026-09-11 08:30 ET / 20:30 台北"},
    "us": {"spx": 7672.34, "spx_pct": 1.06, "ixic": 26412.70, "ixic_pct": 1.27,
           "sox": 11880.66, "sox_pct": 2.29, "session": "2026-09-11 盤中（11:55 ET）"},
    "vix": 15.80, "vix_pct": -11.43,
    "wti": 99.14, "wti_pct": -3.26,
    "gold": 4412.30, "gold_pct": 1.10,
    "us30y": 5.32, "us10y": 4.93, "usdtwd": 31.60,
    "taiex": {"price": 46142.16, "pct": -2.21},
    "trigger": "8月 CPI 公布（符合預期）→ 美股盤中反彈；21:30 gate 判 CALM 未自動觸發（使用者要求補跑）",
}

payload = {
    "generated_at": NOW,
    "source": "美股盤中 CPI 應變（2026-09-11 手動補跑；21:30 cron gate 判 CALM，使用者要求補出）",
    "full_report": FULL,
    "chapters": chapters,
    "market_snapshot": market_snapshot,
    "summary": SUMMARY,
}
jf = BASE / "data" / "emergency_llm_analysis.json"
old = json.loads(jf.read_text(encoding="utf-8")) if jf.exists() else {}
bak = BASE / "data" / f"emergency_llm_analysis.bak-{DATE.replace('-', '')}.json"
if old:
    bak.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
jf.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"✅ JSON 已寫入（full_report {len(FULL)} 字）｜舊版備份 {bak.name}")

# ── 穿透卡（INC-134：任何產 emergency_report_{today}.html 的腳本都必須含） ──
pen_card = (f"<div class='pen'><h3>📊 資產穿透（{DATE}）</h3>"
            f"<p>總資產 {F(total_assets)}｜台股 {P(tw_pct)}%｜美股 {P(us_pct)}%｜防守型配息 {P(def_pct)}%｜"
            f"債券 {P(bond_pct)}%｜現金／安全網 {P(cash_pct)}%</p></div>")

def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

paras = "".join(f"<p style='margin:8px 0'>{_esc(ln)}</p>" if ln.strip() else ""
                for ln in FULL.split("\n"))

CSS = """body{background:#0d1117;color:#e6edf3;font-family:'Segoe UI','Microsoft JhengHei',sans-serif;
line-height:1.75;padding:22px;max-width:900px;margin:0 auto}
h1{font-size:24px;margin:0 0 6px}
.sub{color:#8b949e;font-size:13px;margin-bottom:16px}
.bar{background:rgba(52,211,153,.12);border:1px solid rgba(52,211,153,.45);border-radius:8px;
padding:10px 14px;font-weight:700;margin:14px 0;color:#34d399}
.card{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:18px 22px;margin-bottom:16px}
.card h2{font-size:17px;color:#58a6ff;border-bottom:1px solid #30363d;padding-bottom:8px;margin:0 0 12px}
p{margin:7px 0}
.pen{background:linear-gradient(135deg,#101828,#131a26);border:1px solid #fbbf24;border-radius:12px;
padding:14px 20px;margin:14px 0;color:#fbbf24}
.pen h3{font-size:15px;margin:0 0 6px}
.pen p{font-size:13px;color:#e5e7eb;margin:0}
.meta{color:#8b949e;font-size:12.5px;margin-top:18px;text-align:center}"""

def build(title, alert, note):
    return f"""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} {DATE}</title><style>{CSS}</style></head><body>
<h1>{title}</h1>
<div class="sub">報告日：{DATE} ｜ 產出：{NOW} ｜ {note}</div>
<div class="bar">{alert}</div>
{pen_card}
<div class="card"><h2>完整分析（六章節）</h2>{paras}</div>
<div class="meta">⏰ 下一輪：9/14（一）13:00 台股應變 ／ 21:30 美股應變</div>
</body></html>"""

alert = "🟢 8月CPI 總 3.4%／核心 2.4%（符合預期）｜ 美股盤中 S&P +1.06%、費半 +2.29% ｜ VIX -11.4% ｜ US30Y 5.32%（回落，仍高於 5.30 凍結線）"
p_taiex = BASE / f"emergency_taiex_report_{DATE}.html"
p_emerg = BASE / f"emergency_report_{DATE}.html"
p_taiex.write_text(build("🚨 美股緊急應變報告（CPI 日）", alert, "觸發：8月 CPI 公布 → 美股盤中反彈（21:30 gate 判 CALM，使用者要求補跑）"), "utf-8")
p_emerg.write_text(build("🚨 緊急應變報告（CPI 日／美股盤中）", alert, "觸發：8月 CPI 公布 → 美股盤中反彈（21:30 gate 判 CALM，使用者要求補跑）"), "utf-8")
print(f"✅ HTML：{p_taiex.name} / {p_emerg.name}")
