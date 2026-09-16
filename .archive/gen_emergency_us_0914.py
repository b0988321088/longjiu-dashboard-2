# -*- coding: utf-8 -*-
"""2026-09-14 美股緊急應變（美股開盤 21:30 台北；gate 觸發 TRIGGER|SOX|-5.48%）

背景：9/14 美股開盤費半急殺 -5.51%（Yahoo ^SOX 11,172.72），21:30 monitor gate
（emergency_gate_us.py）偵測到 SOX 跌幅越過門檻 → TRIGGER，觸發本次 agent 產出。
市場數據：Yahoo chart API（^DJI/^GSPC/^IXIC/^SOX/^VIX/^TYX/^TNX/CL=F/GC=F/TWD=X/^TWII/^KS11，
2026-09-14 美股開盤盤中）；US30Y 交叉核對 us30y_state.json（5.354 為 9/11 值）。
新聞：鉅亨網 headline RSS（web_search 禁用 — Firecrawl 未訂閱）。
產出：data/emergency_llm_analysis.json（日報第八章注入源）+ 兩份 HTML（含 INC-134 穿透卡）。
"""
import json, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
NOW = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
DATE = "2026-09-14"

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
us_twd = pen_twd.get("美股市值型成長", 0)
us_tech = pen.get("美股市值型成長_科技", 0)
us_tech_twd = pen_twd.get("美股市值型成長_科技", 0)
us_nontech = pen.get("美股市值型成長_非科技", 0)
bond_pct = pen.get("債券", 0)
bond_twd = pen_twd.get("債券", 0)
def_pct = pen.get("防守型配息", 0)
def_twd = pen_twd.get("防守型配息", 0)
cash_pct = pen.get("現金/安全網", 0)

F = lambda v: f"{v:,.0f}"
P = lambda v: f"{v:.1f}"

# 帳面衝擊估算（明確標註為估算）
est_tech_half = us_tech_twd * -0.02
est_tech_full = us_tech_twd * -0.0551
est_tw_next = tw_twd * -0.02
est_total_pct = (est_tech_half + est_tw_next) / total_assets * 100

FULL = f"""🚨 美股緊急應變報告（2026-09-14 美股開盤｜gate TRIGGER：SOX -5.51%）
產出時間：{NOW} ｜ 觸發：21:30 monitor gate 判 TRIGGER（費半急殺 -5.51%，越過 -2.5% 門檻）

【一、市場概況】
・美股開盤（21:30 台北／09:30 ET）：道瓊 52,423.96（-0.28%）、S&P 7,600.28（-0.74%）、納指 26,019.78（-1.19%）、費半 11,172.72（-5.51%）← 今日觸發源。
・個股分歧：台積電 ADR 418.98（-3.29%）、NVDA 209.67（-3.95%）、博通 347.67（-3.96%）、高通 174.23（-4.25%）；但蘋果 332.42（+0.05%）、微軟 496.75（+0.23%）— 資金是「離開半導體」，不是「離開股市」。
・波動：VIX 17.65（+11.43%），避險需求單日跳升。
・利率：US30Y 5.36%（^TYX，+0.6bp）、US10Y 4.985%（+1bp）；TLT 80.86（-0.02%）。
・商品匯率：WTI 103.78（+3.73%，中東供給風險）、黃金 4,314.6（-1.18%）、USD/TWD 31.806（台幣貶 0.54%）。
・亞洲今日收盤：台股加權 45,862.52（-0.70%，外資賣超 369 億、自台積電提款 266 億）、KOSPI 6,684.37（-3.26%）、日經 63,493（-0.81%）。

【二、重大事件分析】
1) 半導體全球性撤資（本次核心）：外資上周拋售約 4 兆韓元三星與 SK 海力士持股，今日韓股 -3.26%、台股外資賣超 369 億集中撤出半導體 → 費半 -5.51% 不是單一市場事件，而是 AI／記憶體循環的全球部位同步調整。
2) 評級與集中度警示：花旗將美股評級調降至「中立」（AI 疑慮引發市場冷卻）；高盛指出 AI 資本支出貢獻標普 500 半數獲利成長、集中度風險加劇，並列舉美股漲勢的三重阻力。市場賣的是「集中度與估值」，不是 AI 的現金流。
3) 折現率風險（真正壓力源）：30Y 5.36% 距 5.30% 凍結紅線上方 6bp、連 12 次站上；10Y 4.985% 逼近 5%。國泰金徐之強示警「最擔憂倒掛重創股市」。油價 +3.73% 破 103 美元 → 通膨預期再起，9/16 FOMC 前的鷹派風險升溫（市場已消化 3 次升息預期）。
4) 匯率：台幣貶至 31.806 → 對美元資產帳面是順風（外幣換算回台幣變多），但同一現象也是外資撤出的鏡像，兩者不可混為一談。

【三、持倉關聯分析】（真值：snapshot {DATE} 20:25，總資產 {F(total_assets)}）
・台股 {P(tw_pct)}%（{F(tw_twd)}）：今日 -0.70% 已反映；台積電 ADR -3.29% → 週二開盤 0050／006208／009816／00888（合計 1,127,810）有補跌壓力。
・美股 {P(us_pct)}%（{F(us_twd)}；科技 {P(us_tech)}%／{F(us_tech_twd)}、非科技 {P(us_nontech)}%）：科技部位貼近 15% 上限（9/13 裁示 科≤15%）→ 今日是本部位的主要受衝擊面。
・直接半導體／AI 主題部位：台新美日台半導體 123,721、009824 群益美國科技巨頭 99,700、路博邁台灣5G（累積＋月配）331,526、安聯AI收益成長 6,423、貝萊德世界科技A10 4,168、安聯台灣科技 3,108 = 568,646（純主題，佔總資產 2.2%）。
・大型美股基金：富達全球動能 5,853,439、貝萊德 B11 4,981,060、聯博全球多元收益 971,483 — 淨值 T+1 揭露，今晚盤後才見實際影響（非即時報價）。
・帳面衝擊試算（⚠️ 估算值、非真值）：科技部位 3,902,642 若單日 -2.0% → 約 -78,053（總資產 0.30%）；若全額對映 SOX -5.51% → 約 -215,036（0.83%）；台股部位若明日 -2% → 約 -46,513。中性情境合計帳面波動約 -124,566 ≈ 總資產 -0.48%，遠低於任何追繳門檻（零槓桿、無融資）。
・防守型配息 {P(def_pct)}%（{F(def_twd)}）＋債券 {P(bond_pct)}%（{F(bond_twd)}）：高股息與投資級債非本次殺盤核心；30Y 5.36% 高檔下債券價格承壓但 TLT 僅 -0.02%，殖利率尚未失控。

【四、資產配置透視】（9/13 裁示目標：台10／美30／科≤15／防30／債25／現金5）
・實際：台股 {P(tw_pct)}%（{tw_pct-10:+.1f}pp）｜美股 {P(us_pct)}%（{us_pct-30:+.1f}pp，其中科技 {P(us_tech)}% 貼頂 {us_tech-15:+.1f}pp）｜防守型配息 {P(def_pct)}%（{def_pct-30:+.1f}pp）｜債券 {P(bond_pct)}%（{bond_pct-25:+.1f}pp）｜現金／安全網 {P(cash_pct)}%（{cash_pct-5:+.1f}pp）。
・缺口方向解讀：美股整體低配 {abs(us_pct-30):.1f}pp，但「低配」的成因是科技已貼頂而提不出加碼額度 → 未來補的部位必須落在非科技（{P(us_nontech)}%）與防守型配息，不可再往科技加。
・超標處置：債券 {P(bond_pct)}%＋現金 {P(cash_pct)}% 合計超標 4.7pp（對齊 snapshot 缺口表），但今日屬「急跌 >3%」情境 → 依 9/8 再平衡授權：自動減碼暫緩、先回報（即本報告），不在殺盤日賣券賣債。
・配置結論：殺盤不改變缺口方向，只改變「用什麼價格補」。今日的價格不構成行動理由。

【五、巴菲特視角建議】
・一天 -5.51% 的費半不改變台積電、博通的現金流，改變的是「別人今天願意付的價格」。市場在賣集中度與估值風險，不是在賣企業獲利。
・真正的風險不是今天的跌幅，而是 30Y 5.36% ＋ 油價 103 美元 ＋ 9/16 FOMC 鷹派風險的組合 — 折現率上升才是估值的敵人，而這件事本檔無法對沖，只能靠不加碼與現金緩衝應對。
・今晚不做的事：①不在第一天接刀（科技貼 15% 上限，沒有加碼額度）②不在殖利率高檔賣債（等於鎖定損失）③不因恐懼停掉配息現金流（防守型配息 {P(def_pct)}% 是現金流的根）。
・今晚要做的事：把今天的收盤價當「價格清單」更新。若後續續跌使美股非科技部位與防守型配息出現折價，且 US30Y 回落 5.30% 下方、9/16 FOMC 定調明朗，才啟動分批（≤20 萬／次，9/8 授權）。
・安全邊際：銀行現金 {F(cash_total)}（底線 700,000 ✅）＋零槓桿、無追繳 = 不必在錯誤的價格被迫做正確的事。這就是等待的價值。

【六、風控檢查】
・US30Y 5.36% ≥ 5.30% 凍結紅線（自 9/10 起連 12 次站上，今日 +0.6bp 方向不利）→ 債券新增永久凍結，不建債梯。
・急跌閘門：費半 -5.51% > 3% → 依 9/8 授權，桶權重自動減碼「暫緩、先回報」；本日不執行任何再平衡交易。
・美元曝險 {usd_pct}%（超線）＋台幣貶 0.54% → 匯率順風正在掩蓋部位風險，須分開評估，不可因帳面數字穩定而忽略曝險集中度。
・質押 540 萬（LTV 45.9%，利率 2.77%）：尚未對保、未撥款（估 ~9/25）→ 今日殺盤不影響銀行作業；擔保池 1,177 萬無追繳風險，但擔保品約 92% 為後收級別（CDSC 3 年）→ 一旦追繳不可賣出，緩衝只能靠現金，故現金底線不可動用。
・現金底線 {F(cash_total)} ≥ 700,000 ✅；零槓桿、無追繳；信用卡待扣 60,810 無虞。
・地緣：中東緊張推升 WTI 破 103 美元 → 通膨傳導 → 殖利率上行壓力，續盯。

【行動摘要】
1. 今晚不動作：急跌日暫緩再平衡（先回報）；科技貼 15% 上限，無加碼額度。
2. 明日台股開盤盯 0050／006208／009816 補跌幅度，不主動殺低、不攤平科技。
3. 9/16 FOMC 前：不新增美元、不建債梯、不加科技。
4. 質押 540 萬對保後（估 ~9/25 撥款）→ 優先清償 500 萬高息負債（保單 400 萬@4.0%＋券商 100 萬@3.92%）。
5. 升級條件：SOX 連續兩日累計 < -8% 或 US30Y ≥ 5.5% → 轉紅燈，重評後收基金部位與美元曝險。"""

SUMMARY = (f"費半 -5.51%（gate TRIGGER）、納指 -1.19%、道瓊僅 -0.28%、VIX +11.4% — 半導體全球性撤資"
           f"（外資拋 4 兆韓元三星/SK、台股賣超 369 億）；AAPL/MSFT 逆勢小漲 = 賣集中度非賣股市。"
           f"US30Y 5.36% 仍在 5.30 凍結紅線上方、WTI 破 103 美元、9/16 FOMC 前鷹派風險。"
           f"科技部位 {P(us_tech)}% 貼 15% 上限無加碼額度 → 急跌日暫緩再平衡、先回報；現金 {F(cash_total)} 為緩衝。")

chapters = {
    "一、市場概況": ("美股開盤：道瓊 52,423.96（-0.28%）、S&P 7,600.28（-0.74%）、納指 26,019.78（-1.19%）、"
                "費半 11,172.72（-5.51%，觸發源）；TSM ADR 418.98（-3.29%）、NVDA 209.67（-3.95%）、"
                "AVGO 347.67（-3.96%）、QCOM 174.23（-4.25%），但 AAPL（+0.05%）、MSFT（+0.23%）逆勢；"
                "VIX 17.65（+11.43%）；US30Y 5.36%、US10Y 4.985%；WTI 103.78（+3.73%）、黃金 4,314.6（-1.18%）、"
                "USD/TWD 31.806（台幣貶 0.54%）；亞洲：台股 45,862.52（-0.70%）、KOSPI -3.26%、日經 -0.81%。"),
    "二、重大事件分析": ("①半導體全球撤資：外資上周拋售約 4 兆韓元三星/SK 海力士、台股外資賣超 369 億集中撤出半導體 "
                 "→ 費半 -5.51% 為全球部位同步調整 ②花旗降美股評級至「中立」＋高盛示警 AI 資本支出集中度風險 "
                 "→ 賣的是集中度與估值，不是 AI 現金流 ③折現率壓力：30Y 5.36%（距凍結線 6bp）、油價破 103 美元 "
                 "→ 通膨預期再起，9/16 FOMC 鷹派風險（市場已消化 3 次升息）④台幣貶 0.54% 是美元資產順風、也是外資撤出鏡像。"),
    "三、持倉關聯分析": (f"台股 {P(tw_pct)}%（{F(tw_twd)}）今日 -0.70% 已反映，ADR -3.29% → 週二 0050/006208/009816/00888"
                  f"（1,127,810）補跌壓力；美股 {P(us_pct)}%（科技 {P(us_tech)}%／非科技 {P(us_nontech)}%）為主要受衝擊面；"
                  f"純主題半導體/AI 部位合計 568,646（佔總資產 2.2%）；富達 5,853,439＋B11 4,981,060 淨值 T+1 揭露；"
                  f"帳面衝擊估算 -12.5 萬（≈ -0.48% 總資產）遠低於追繳門檻；防守 {P(def_pct)}%＋債券 {P(bond_pct)}% 非殺盤核心。"),
    "四、資產配置透視": (f"實際 vs 9/13 目標：台股 {P(tw_pct)}%（{tw_pct-10:+.1f}pp）｜美股 {P(us_pct)}%（{us_pct-30:+.1f}pp，"
                  f"科技 {P(us_tech)}% 貼頂 {us_tech-15:+.1f}pp）｜防守 {P(def_pct)}%（{def_pct-30:+.1f}pp）｜"
                  f"債券 {P(bond_pct)}%（{bond_pct-25:+.1f}pp）｜現金 {P(cash_pct)}%（{cash_pct-5:+.1f}pp）。"
                  f"美股低配但科技無額度 → 補倉須落非科技與防守型；債＋現金合計超標 4.7pp，急跌日依 9/8 授權暫緩減碼、先回報。"),
    "五、巴菲特視角建議": ("一天的費半急殺不改變台積電與博通的現金流，只改變市場今天願付的價格。真正風險是 30Y 5.36%＋油價 103 "
                  "＋FOMC 鷹派的折現率組合。不做：不接第一天刀、不在殖利率高檔賣債、不停配息現金流。"
                  "要做：更新價格清單，待 US30Y 回落 5.30 下方＋FOMC 定調後才分批（≤20 萬/次）。"
                  f"安全邊際＝現金 {F(cash_total)}＋零槓桿無追繳。"),
    "六、風控檢查": (f"US30Y 5.36% ≥ 5.30 凍結紅線（連 12 次站上）→ 債券永久凍結；費半 -5.51% > 3% 急跌閘門 → "
                f"再平衡自動減碼暫緩先回報；美元曝險 {usd_pct}% 超線且台幣貶值掩蓋部位風險；質押 540 萬未對保未撥款（~9/25），"
                f"擔保池 92% 後收級別 → 追繳不可賣，緩衝僅靠現金；現金底線 {F(cash_total)} ≥ 70 萬 ✅；地緣（WTI 破 103）續盯。"),
    "行動摘要": ("①今晚不動作（急跌日暫緩再平衡、先回報）②明日盯 0050/006208/009816 補跌，不攤平科技 "
             "③FOMC 前不新增美元、不建債梯、不加科技 ④質押 540 萬（~9/25 撥款）優先清償 500 萬高息 "
             "⑤SOX 兩日累計 < -8% 或 US30Y ≥ 5.5% → 轉紅燈重評後收部位與美元曝險。"),
}

market_snapshot = {
    "date": DATE,
    # 扁平鍵（相容 gen_emergency_taiex_auto.py 的 KPI 卡渲染）
    "TWII": 45862.52, "TWII_chg_pct": -0.70,
    "TSMC_2330": 2380.00, "TSMC_2330_chg_pct": -1.24,
    "SOX": 11172.72, "SOX_chg_pct": -5.51,
    "DJI": 52423.96, "DJI_chg_pct": -0.28,
    "SPX": 7600.28, "SPX_chg_pct": -0.74,
    "IXIC": 26019.78, "IXIC_chg_pct": -1.19,
    "US30Y": 5.36, "US30Y_chg_pct": 0.06,
    "us": {"dji": 52423.96, "dji_pct": -0.28, "spx": 7600.28, "spx_pct": -0.74,
           "ixic": 26019.78, "ixic_pct": -1.19, "sox": 11172.72, "sox_pct": -5.51,
           "session": "2026-09-14 美股開盤（09:30 ET / 21:30 台北）"},
    "us_equities": {"TSM": {"px": 418.98, "pct": -3.29}, "NVDA": {"px": 209.67, "pct": -3.95},
                    "AVGO": {"px": 347.67, "pct": -3.96}, "QCOM": {"px": 174.23, "pct": -4.25},
                    "AAPL": {"px": 332.42, "pct": 0.05}, "MSFT": {"px": 496.75, "pct": 0.23},
                    "TLT": {"px": 80.86, "pct": -0.02}, "BIL": {"px": 91.50, "pct": 0.01}},
    "vix": 17.65, "vix_pct": 11.43,
    "wti": 103.78, "wti_pct": 3.73,
    "gold": 4314.60, "gold_pct": -1.18,
    "us30y": 5.36, "us10y": 4.985, "usdtwd": 31.806,
    "taiex": {"price": 45862.52, "pct": -0.70, "note": "9/14 收盤；外資賣超 369 億、台積電提款 266 億"},
    "kospi": {"price": 6684.37, "pct": -3.26},
    "nikkei": {"price": 63492.99, "pct": -0.81},
    "trigger": "21:30 monitor gate TRIGGER（SOX -5.48% 偵測值 / 實測 -5.51%，越過 -2.5% 門檻）",
}

payload = {
    "generated_at": NOW,
    "source": "美股開盤緊急應變（2026-09-14 21:30 cron；gate TRIGGER｜SOX -5.51% 半導體全球撤資）",
    "full_report": FULL,
    "chapters": chapters,
    "market_snapshot": market_snapshot,
    "summary": SUMMARY,
}

jf = BASE / "data" / "emergency_llm_analysis.json"
old = json.loads(jf.read_text(encoding="utf-8")) if jf.exists() else {}
old_len = len(str(old.get("full_report", "")))
# 寫入端單向保護（INC-169）：既有完整版 >1500 且新版更短 → 不覆寫
if old_len > 1500 and len(FULL) < old_len:
    print(f"⏭️ 既有完整分析 {old_len} 字 > 新版 {len(FULL)} 字，跳過覆寫")
else:
    if old:
        bak = BASE / "data" / f"emergency_llm_analysis.bak-{DATE.replace('-', '')}.json"
        bak.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
    jf.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ JSON 已寫入（full_report {len(FULL)} 字）｜generated_at {NOW}")

# ── 穿透卡（INC-134：任何產 emergency_report_{today}.html 的腳本都必須含） ──
pen_card = (f"<div class='pen'><h3>📊 資產穿透（{DATE}）</h3>"
            f"<p>總資產 {F(total_assets)}｜台股 {P(tw_pct)}%｜美股 {P(us_pct)}%（科技 {P(us_tech)}%）｜"
            f"防守型配息 {P(def_pct)}%｜債券 {P(bond_pct)}%｜現金／安全網 {P(cash_pct)}%</p></div>")


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


paras = "".join(f"<p style='margin:8px 0'>{_esc(ln)}</p>" if ln.strip() else ""
                for ln in FULL.split("\n"))

CSS = """body{background:#0d1117;color:#e6edf3;font-family:'Segoe UI','Microsoft JhengHei',sans-serif;
line-height:1.75;padding:22px;max-width:900px;margin:0 auto}
h1{font-size:24px;margin:0 0 6px}
.sub{color:#8b949e;font-size:13px;margin-bottom:16px}
.bar{background:rgba(248,81,73,.14);border:1px solid rgba(248,81,73,.5);border-radius:8px;
padding:10px 14px;font-weight:700;margin:14px 0;color:#ff7b72}
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
<div class="meta">⏰ 下一輪：9/15（二）13:00 台股應變 ／ 21:30 美股應變</div>
</body></html>"""


alert = ("🔴 gate TRIGGER：費半 -5.51%（11,172.72）｜ 納指 -1.19%、S&P -0.74%、道瓊 -0.28% ｜ VIX +11.43% ｜ "
         "US30Y 5.36%（凍結紅線上方 6bp）｜ WTI 103.78（+3.73%）｜ 半導體全球撤資")
note = "觸發：21:30 monitor gate 判 TRIGGER（SOX -5.48% / 實測 -5.51%，越過 -2.5% 門檻）"
p_taiex = BASE / f"emergency_taiex_report_{DATE}.html"
p_emerg = BASE / f"emergency_report_{DATE}.html"
p_taiex.write_text(build("🚨 美股緊急應變報告", alert, note), "utf-8")
p_emerg.write_text(build("🚨 緊急應變報告（美股開盤／SOX 急殺）", alert, note), "utf-8")
print(f"✅ HTML：{p_taiex.name} / {p_emerg.name}")
