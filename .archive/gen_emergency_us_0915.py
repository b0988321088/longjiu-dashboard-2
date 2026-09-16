# -*- coding: utf-8 -*-
"""2026-09-15 美股緊急應變（美股開盤 21:30 台北；gate TRIGGER → CALM）

背景：9/14 21:30 gate 判 TRIGGER（費半 -5.51%），9/14 收 -5.86%；9/15 21:30 monitor
（emergency_gate_us.py）輸出由 TRIGGER 轉 CALM → 費半反彈未再越過門檻，本次為常態排程產出。
市場數據：Yahoo chart API（^DJI/^GSPC/^IXIC/^SOX/^VIX/^TYX/^TNX/CL=F/GC=F/TWD=X/^TWII/^KS11/
TLT/BIL/TSM/NVDA/AAPL/MSFT/AMD/QCOM/AVGO/TSLA/006208/009816/0050/00878，
2026-09-15 美股開盤盤中）；US30Y 交叉核對 us30y_state.json（last_rate 5.329 @9/14）＋ FRED DGS30。
新聞：daily_analysis.json briefing【最新市場消息】＋ tw.stock.yahoo.com RSS（web_search 禁用 — Firecrawl 未訂閱）。
產出：data/emergency_llm_analysis.json（日報第八章注入源）+ 兩份 HTML（含 INC-134 穿透卡）。
"""
import json, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
NOW = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
DATE = "2026-09-15"

snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
pen = snap.get("penetration", {}).get("actual_pct", {})
pen_twd = snap.get("penetration", {}).get("actual_twd", {})
total_assets = snap.get("total_assets", 0)
cash_total = snap.get("cash_total", 0) or 0
usd_pct = snap.get("usd_exposure_pct", 0)
pledge_amt = snap.get("cathay_pledge_0911", {}).get("可貸金額", 0) or 0
pool = snap.get("cathay_pledge_0911", {}).get("擔保池", {}).get("合計", 0) or 0
snap_at = str(snap.get("generated_at", ""))[:16].replace("T", " ")

tw_pct = pen.get("台股市值型成長", 0)
tw_twd = pen_twd.get("台股市值型成長", 0)
us_pct = pen.get("美股市值型成長", 0)
us_twd = pen_twd.get("美股市值型成長", 0)
us_tech = pen.get("美股市值型成長_科技", 0)
us_tech_twd = pen_twd.get("美股市值型成長_科技", 0)
us_nontech = pen.get("美股市值型成長_非科技", 0)
us_nontech_twd = pen_twd.get("美股市值型成長_非科技", 0)
bond_pct = pen.get("債券", 0)
bond_twd = pen_twd.get("債券", 0)
def_pct = pen.get("防守型配息", 0)
def_twd = pen_twd.get("防守型配息", 0)
cash_pct = pen.get("現金/安全網", 0)
cash_bucket_twd = pen_twd.get("現金/安全網", 0)

F = lambda v: f"{v:,.0f}"
P = lambda v: f"{v:.1f}"

# ── 帳面衝擊估算（明確標註為估算） ──
sox_prev_pct = -5.86   # 9/14 收盤
sox_now_pct = 1.45     # 9/15 開盤盤中
sox_2d_pct = (11292.77 / 11824.00 - 1) * 100          # 9/11 → 9/15 累計
est_tech_down = us_tech_twd * sox_prev_pct / 100      # 昨日衝擊
est_tech_up = us_tech_twd * sox_now_pct / 100         # 今日回補
est_tech_net = est_tech_down + est_tech_up
est_tw = tw_twd * -1.06 / 100                          # 006208 -1.06% 對映
est_total_net_pct = (est_tech_net + est_tw) / total_assets * 100
cash_excess = cash_total - 700000

FULL = f"""🚨 美股緊急應變報告（2026-09-15 美股開盤｜gate CALM：費半 +1.45% 反彈，未越門檻）
產出時間：{NOW} ｜ 觸發：21:30 monitor gate 由 TRIGGER（9/14 SOX -5.48%）轉 CALM → 常態排程產出

【一、市場概況】
・美股開盤（21:30 台北／09:30 ET）：道瓊 52,181.36（-0.46%）、S&P 7,606.84（-0.17%）、納指 26,122.17（-0.25%）、費半 11,292.77（+1.45%）← 昨日重挫後首日反彈。
・個股分歧（反彈集中在超跌半導體）：AMD 506.52（+2.66%）、高通 187.05（+3.83%）、NVDA 213.74（+1.32%）、台積電 ADR 419.34（+0.32%）、博通 345.74（+0.30%）；但蘋果 330.44（-0.79%）、微軟 500.43（-0.99%）、特斯拉 356.03（-0.82%）→ 大型權值反而走弱，指數因此不漲反跌。
・波動：VIX 16.86（-1.40%）→ 恐慌情緒降溫，昨日跳升的避險需求部分消退。
・利率（今日真正的主線）：US10Y 5.00%（+3.5bp，正式攻入 5% 關卡）、US30Y 5.37%（+4bp）；TLT 80.64（-0.35%）。30Y 自 9/10 起連續站上 5.30% 凍結紅線。
・商品匯率：WTI 102.19（+0.79%，中東供給風險未解）、黃金 4,328.00（-0.55%）、USD/TWD 31.83（台幣貶 0.48%）。
・亞洲今日收盤：台股加權 45,511.49（-0.77%、跌 351 點、量縮至 6,034 億為今年次低）、KOSPI 6,627.26（-0.85%）、台積電 2,385.00（+0.21%）→ 台股是「量縮下跌＋權值持平」，非恐慌賣壓。

【二、重大事件分析】
1) 反彈品質不高：費半 +1.45%，但領漲是 AMD／高通這類超跌股，NVDA／TSM 僅小漲、AAPL／MSFT 走弱 → 昨日的「資金離開半導體」今天沒有變成「資金回到權值」，而是科技內部的重新分配。反彈首日不構成趨勢翻轉的證據。
2) 10Y 攻入 5.00%「危險區」（華爾街劃出的生死線）：市場頭條聚焦 10 年期美債殖利率觸及 5%，30Y 同步 5.37%。這是估值分母端的壓力，也是今天指數不漲、只有超跌股彈的真正原因 — 折現率上升對「久期長的成長股」傷害最大。
3) 9/16 FOMC 前夜：升息預期已部分消化，但油價 102 美元撐住通膨端（中東供給風險）→ 鷹派尾端風險未消除。決策公布前不新增風險資產是本文最重要的行動結論。
4) 台股量能警訊：成交 6,034 億為今年次低，投顧點名資金被新股抽走（漢測）＋國際油價與美股收黑 → 跌 351 點但無恐慌特徵，屬「量縮整理」。
5) gate 狀態轉折：昨日 TRIGGER（SOX -5.48% 偵測值／實測 -5.51%，收 -5.86%）→ 今日 CALM。費半自 9/11 的 11,824.00 至今日 11,292.77，累計 {sox_2d_pct:.2f}%，未達「兩日累計 < -8%」的紅燈門檻。

【三、持倉關聯分析】（真值：snapshot {snap_at}，總資產 {F(total_assets)}）
・台股 {P(tw_pct)}%（{F(tw_twd)}）：今日 006208 243.50（-1.06%）、009816 15.75（-0.82%）、0050 106.25（-0.61%）、00878 34.20（-0.09%）→ 帳面估算約 {F(est_tw)}（佔總資產 {abs(est_tw)/total_assets*100:.2f}%），高股息幾乎持平，緩衝有效。
・美股 {P(us_pct)}%（{F(us_twd)}；科技 {P(us_tech)}%／{F(us_tech_twd)}、非科技 {P(us_nontech)}%／{F(us_nontech_twd)}）：本部位是昨日費半 -5.86% 的主要受衝擊面。科技部位帳面估算昨日 {F(est_tech_down)}、今日回補 {F(est_tech_up)}，兩日淨 {F(est_tech_net)}（總資產 {est_total_net_pct:+.2f}%）← ⚠️ 估算值、非真值（實際以基金淨值 T+1 揭露為準）。
・純主題半導體／AI 部位（台新美日台半導體、009824 群益美國科技巨頭、路博邁台灣5G、安聯AI收益成長、貝萊德世界科技A10、安聯台灣科技）約 56.9 萬，佔總資產 2.2% → 主題集中度可控。
・後收級別：富達全球動能 585.3 萬＋貝萊德 B11 498.1 萬（合計約 {F(0.4015*total_assets)}，約總資產 40.2%）：淨值 T+1 揭露，今晚盤後才見實際影響，非即時報價。
・防守型配息 {P(def_pct)}%（{F(def_twd)}）＋債券 {P(bond_pct)}%（{F(bond_twd)}）：高股息今日幾乎未跌；債券桶受 30Y 上行壓制（TLT -0.35%）但無追繳、無融資維持率壓力。
・零槓桿、無追繳 → 這一輪波動是帳面數字事件，不是現金流事件。

【四、資產配置透視】（9/13 裁示目標：台 10／美 30／科 ≤15／防 30／債 25／現金 5）
・實際：台股 {P(tw_pct)}%（{tw_pct-10:+.1f}pp）｜美股 {P(us_pct)}%（{us_pct-30:+.1f}pp，其中科技 {P(us_tech)}% 貼頂 {us_tech-15:+.1f}pp）｜防守型配息 {P(def_pct)}%（{def_pct-30:+.1f}pp）｜債券 {P(bond_pct)}%（{bond_pct-25:+.1f}pp）｜現金／安全網 {P(cash_pct)}%（{cash_pct-5:+.1f}pp）。
・美股 {P(us_pct)}% 已破 40% 單桶硬上線 → 停新增、配息導流（既有裁示），且科技 {P(us_tech)}% 貼 15% 天花板 → 即使看多也無加碼額度。這是「想加而不能加」的紀律，不是看空。
・最大缺口在防守型配息 {def_pct-30:+.1f}pp：補缺口要靠配息再投入與質押撥款後的現金流（而非賣科技換手），因此優先序仍鎖在 9/25 撥款後的負債清償，而非資產換手。
・現金 {P(cash_pct)}%（{F(cash_total)}）以底線制（70 萬）衡量 ✅ 超額 {F(cash_excess)} → 依 8/19 裁示超額部署收益資產；但今晚為 FOMC 前夜，不新增、不動用。
・再平衡授權（9/8）：桶權重超標自動減碼的觸發條件為「急跌 >3%」；今日費半 +1.45% 反向，減碼閘門未觸發，無需暫緩回報。

【五、巴菲特視角建議】
・今天市場賣的是折現率，不是企業。10Y 站上 5% 的意義是「所有未來的錢都變便宜了」— 這件事比任何單日跌幅重要，而且無法靠換股解決。
・昨日殺半導體、今日只彈超跌股：這種反彈的品質不高，不需要為它做事，也不需要為昨天的下跌做補償交易。不因反彈追高、不因昨日下跌賣低，是同一件事的兩面。
・FOMC 前夜最好的部位調整是「不調整」。決策未定前進場，等於用猜測交換手續費與錯價風險。
・正面訊號要記下來：VIX 16.86 回落、費半止穩、台股量縮下跌而非崩跌 → 系統性風險沒有升溫；這正是防守型配息 {P(def_pct)}%＋債券 {P(bond_pct)}% 這個結構要處理的盤。
・要做的是更新價格清單：等 US30Y 回落 5.30 下方、且 FOMC 定調明朗後，才出現分批補「非科技與防守型」的第一個理由（≤20 萬／次，9/8 授權）。
・安全邊際：銀行現金 {F(cash_total)} ≥ 70 萬 ✅ ＋零槓桿、無追繳 → 不必在錯誤的價格被迫做任何事。

【六、風控檢查】
・US30Y 5.37% ≥ 5.30% 凍結紅線（自 9/10 起連續站上，今日再 +4bp 方向不利）→ 債券新增永久凍結，不建債梯、不加長債。
・新增觀察點 US10Y 5.00%：若站穩 5% 以上，估值壓力將由長端擴散至整體風險資產 → 列入升級條件。
・急跌閘門：費半今日 +1.45% 未觸發；9/11→9/15 兩日累計 {sox_2d_pct:.2f}%，未達 -8% 紅燈。
・美元曝險 {usd_pct}%（超線）＋台幣貶 0.48% → 匯率順風正在掩蓋部位集中度風險，兩者必須分開評估。
・質押 {F(pledge_amt)}（擔保池 {F(pool)} × 45%、利率 2.77%）：尚未對保、未撥款（估 ~9/25）→ 銀行作業不受殺盤影響；撥款後優先清償 500 萬高息負債（保單質押 400 萬@4.0%＋券商 100 萬），月省息約 1.66 萬。擔保品約 92% 為後收級別（CDSC 3 年）→ 追繳時不可賣出，緩衝只能靠現金，故 70 萬底線不可動用。
・現金底線 {F(cash_total)} ≥ 700,000 ✅；零槓桿、無融資維持率、無追繳。
・地緣：WTI 102.19 美元高位 → 通膨傳導至長端殖利率，續盯。
・（真值修正）本日 13:00 台股版報告引用加權 45,693.02（-0.37%），與收盤真值 45,511.49（-0.77%、-351 點）不符 → 以本次 Yahoo 收盤真值為準。

【行動摘要】
1. 今晚不動作：FOMC 前夜不新增美元、不建債梯、不加科技（科技已貼 15% 上限）。
2. 明日台股開盤盯半導體型 ETF（0050／006208／009816）是否跟隨費半反彈，不主動加減碼。
3. 9/16 FOMC 後重評兩件事：US30Y 是否回落 5.30 下方（債券解凍前提）、US10Y 是否站穩 5%。
4. 質押 540 萬對保（估 ~9/25 撥款）→ 清償 500 萬高息負債，月省息約 1.66 萬。
5. 升級條件：US30Y ≥ 5.5% 或 費半兩日累計 < -8% 或 US10Y 站穩 5.10% 以上 → 轉紅燈，重評後收基金部位與美元曝險。"""

SUMMARY = (f"gate 由 TRIGGER 轉 CALM：費半 +1.45%（11,292.77）反彈，但道瓊 -0.46%、S&P -0.17%、納指 -0.25% — "
           f"反彈集中 AMD +2.66%／高通 +3.83%，AAPL -0.79%、MSFT -0.99% 走弱，屬科技內部輪動非趨勢翻轉。"
           f"主線是利率：US10Y 5.00% 攻入危險區、US30Y 5.37% 仍在 5.30 凍結紅線上方（連 13 次），TLT -0.35%。"
           f"台股 45,511.49（-0.77%／跌 351 點、量縮 6,034 億今年次低）。"
           f"科技部位 {P(us_tech)}% 貼 15% 上限無加碼額度 → FOMC 前夜不新增、不建債梯；現金 {F(cash_total)} 為緩衝。")

chapters = {
    "一、市場概況": ("美股開盤：道瓊 52,181.36（-0.46%）、S&P 7,606.84（-0.17%）、納指 26,122.17（-0.25%）、"
                "費半 11,292.77（+1.45%）；AMD 506.52（+2.66%）、高通 187.05（+3.83%）、NVDA 213.74（+1.32%）、"
                "台積電 ADR 419.34（+0.32%），但 AAPL 330.44（-0.79%）、MSFT 500.43（-0.99%）走弱；"
                "VIX 16.86（-1.40%）；US10Y 5.00%（+3.5bp）、US30Y 5.37%（+4bp）、TLT 80.64（-0.35%）；"
                "WTI 102.19（+0.79%）、黃金 4,328.00（-0.55%）、USD/TWD 31.83（台幣貶 0.48%）；"
                "亞洲：台股 45,511.49（-0.77%、-351 點、量縮 6,034 億今年次低）、KOSPI 6,627.26（-0.85%）。"),
    "二、重大事件分析": ("①反彈品質不高：領漲為超跌股（AMD／高通），NVDA／TSM 僅小漲、AAPL／MSFT 走弱 → "
                 "科技內部輪動而非資金回歸權值 ②10Y 攻入 5.00%「危險區」＋30Y 5.37% → 折現率壓力是今日指數不漲的主因 "
                 "③9/16 FOMC 前夜＋油價 102 美元撐住通膨端 → 鷹派尾端風險未除 ④台股量縮 6,034 億（今年次低）"
                 "為量縮整理非恐慌賣壓 ⑤gate 由 TRIGGER 轉 CALM；費半 9/11→9/15 累計 -4.49%，未達 -8% 紅燈。"),
    "三、持倉關聯分析": (f"台股 {P(tw_pct)}%（{F(tw_twd)}）：006208 -1.06%／009816 -0.82%／0050 -0.61%／00878 -0.09%，"
                  f"帳面估算 {F(est_tw)}；美股 {P(us_pct)}%（科技 {P(us_tech)}%／{F(us_tech_twd)}、非科技 {P(us_nontech)}%）"
                  f"為主要受衝擊面，科技部位昨日估算 {F(est_tech_down)}、今日回補 {F(est_tech_up)}，兩日淨 {F(est_tech_net)}"
                  f"（{est_total_net_pct:+.2f}% 總資產，估算值）；純主題半導體/AI 部位約 56.9 萬（2.2%）；"
                  f"後收級別富達 585.3 萬＋B11 498.1 萬（約 40.2% 總資產）淨值 T+1 揭露；"
                  f"防守 {P(def_pct)}% 幾乎未跌、債券 {P(bond_pct)}% 受 30Y 壓制但無追繳；零槓桿。"),
    "四、資產配置透視": (f"實際 vs 9/13 目標：台 {P(tw_pct)}%（{tw_pct-10:+.1f}pp）｜美 {P(us_pct)}%（{us_pct-30:+.1f}pp，"
                  f"科技 {P(us_tech)}% 貼頂 {us_tech-15:+.1f}pp）｜防 {P(def_pct)}%（{def_pct-30:+.1f}pp）｜"
                  f"債 {P(bond_pct)}%（{bond_pct-25:+.1f}pp）｜現 {P(cash_pct)}%（{cash_pct-5:+.1f}pp）。"
                  f"美股破 40% 硬上線＋科技貼頂 → 想加也不能加；最大缺口在防守型（{def_pct-30:+.1f}pp），"
                  f"靠配息再投入與撥款後現金流補，不賣科技換手；現金 {F(cash_total)} 超額 {F(cash_excess)} 依裁示部署收益資產，"
                  f"今晚 FOMC 前夜不動；急跌減碼閘門今日未觸發（費半 +1.45%）。"),
    "五、巴菲特視角建議": ("市場今天賣的是折現率不是企業；10Y 破 5% 無法靠換股解決。昨日殺半導體、今日只彈超跌股 → "
                  "反彈品質不高，不因反彈追高、不因昨日下跌賣低。FOMC 前夜最好的調整是不調整。"
                  "正面訊號：VIX 回落、費半止穩、台股量縮下跌 → 系統性風險未升溫。"
                  f"待 US30Y 回落 5.30 下方且 FOMC 定調後，才啟動分批補非科技與防守（≤20 萬/次）。"
                  f"安全邊際＝現金 {F(cash_total)}＋零槓桿無追繳。"),
    "六、風控檢查": (f"US30Y 5.37% ≥ 5.30 凍結紅線（連 13 次）→ 債券永久凍結、不建債梯；新增觀察點 US10Y 5.00%，"
                f"站穩則列入升級條件；急跌閘門未觸發（費半 +1.45%、兩日累計 {sox_2d_pct:.2f}%）；"
                f"美元曝險 {usd_pct}% 超線且台幣貶值掩蓋集中度風險；質押 {F(pledge_amt)} 未對保未撥款（~9/25），"
                f"撥款後清償 500 萬高息（月省息約 1.66 萬），擔保池 92% 後收級別 → 追繳不可賣、緩衝僅靠現金；"
                f"現金底線 {F(cash_total)} ≥ 70 萬 ✅；WTI 102 美元續盯。另修正 13:00 版台股收盤真值（45,511.49／-0.77%）。"),
    "行動摘要": ("①今晚不動作（FOMC 前夜不新增美元/不建債梯/不加科技）②明日盯 0050/006208/009816 是否跟隨費半反彈，"
             "不主動加減碼 ③FOMC 後重評 US30Y 是否回落 5.30 下方、US10Y 是否站穩 5% ④質押 540 萬（~9/25 撥款）"
             "清償 500 萬高息負債 ⑤US30Y ≥5.5% 或 費半兩日累計 <-8% 或 US10Y 站穩 5.10% → 轉紅燈重評。"),
}

market_snapshot = {
    "date": DATE,
    # 扁平鍵（相容 gen_emergency_taiex_auto.py 的 KPI 卡渲染）
    "TWII": 45511.49, "TWII_chg_pct": -0.77,
    "TSMC_2330": 2385.00, "TSMC_2330_chg_pct": 0.21,
    "SOX": 11292.77, "SOX_chg_pct": 1.45,
    "DJI": 52181.36, "DJI_chg_pct": -0.46,
    "SPX": 7606.84, "SPX_chg_pct": -0.17,
    "IXIC": 26122.17, "IXIC_chg_pct": -0.25,
    "US30Y": 5.37, "US30Y_chg_pct": 0.04,
    "us": {"dji": 52181.36, "dji_pct": -0.46, "spx": 7606.84, "spx_pct": -0.17,
           "ixic": 26122.17, "ixic_pct": -0.25, "sox": 11292.77, "sox_pct": 1.45,
           "session": "2026-09-15 美股開盤（09:30 ET / 21:30 台北）"},
    "us_equities": {"TSM": {"px": 419.34, "pct": 0.32}, "NVDA": {"px": 213.74, "pct": 1.32},
                    "AMD": {"px": 506.52, "pct": 2.66}, "QCOM": {"px": 187.05, "pct": 3.83},
                    "AVGO": {"px": 345.74, "pct": 0.30}, "AAPL": {"px": 330.44, "pct": -0.79},
                    "MSFT": {"px": 500.43, "pct": -0.99}, "TSLA": {"px": 356.03, "pct": -0.82},
                    "TLT": {"px": 80.64, "pct": -0.35}, "BIL": {"px": 91.50, "pct": 0.01}},
    "vix": 16.86, "vix_pct": -1.40,
    "wti": 102.19, "wti_pct": 0.79,
    "gold": 4328.00, "gold_pct": -0.55,
    "us30y": 5.37, "us10y": 5.00, "usdtwd": 31.83,
    "taiex": {"price": 45511.49, "pct": -0.77, "note": "9/15 收盤；跌 351 點、量縮 6,034 億（今年次低）"},
    "kospi": {"price": 6627.26, "pct": -0.85},
    "trigger": "gate CALM（9/14 TRIGGER SOX -5.48% → 9/15 CALM；費半 +1.45% 未越門檻）",
}

payload = {
    "generated_at": NOW,
    "source": "美股開盤緊急應變（2026-09-15 21:30 cron；gate TRIGGER→CALM｜費半 +1.45% 反彈、US10Y 破 5.00%）",
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
            f"防守型配息 {P(def_pct)}%｜債券 {P(bond_pct)}%｜現金／安全網 {P(cash_pct)}%（{F(cash_total)}）</p></div>")


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


paras = "".join(f"<p style='margin:8px 0'>{_esc(ln)}</p>" if ln.strip() else ""
                for ln in FULL.split("\n"))

CSS = """body{background:#0d1117;color:#e6edf3;font-family:'Segoe UI','Microsoft JhengHei',sans-serif;
line-height:1.75;padding:22px;max-width:900px;margin:0 auto}
h1{font-size:24px;margin:0 0 6px}
.sub{color:#8b949e;font-size:13px;margin-bottom:16px}
.bar{background:rgba(210,153,34,.14);border:1px solid rgba(210,153,34,.55);border-radius:8px;
padding:10px 14px;font-weight:700;margin:14px 0;color:#e3b341}
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
<div class="meta">⏰ 下一輪：9/16（三）13:00 台股應變 ／ 21:30 美股應變 ｜ 9/16 FOMC</div>
</body></html>"""


alert = (f"🟡 gate CALM：費半 +1.45%（11,292.77）反彈 ｜ 道瓊 -0.46%、S&P -0.17%、納指 -0.25% ｜ "
         f"US10Y 5.00%（攻入危險區）、US30Y 5.37%（凍結紅線上方） ｜ 台股 -0.77%／量縮 6,034 億 ｜ 9/16 FOMC 前夜不動作")
note = "觸發：21:30 monitor gate 由 TRIGGER（9/14 SOX -5.48%）轉 CALM，本次為常態排程產出"
p_taiex = BASE / f"emergency_taiex_report_{DATE}.html"
p_emerg = BASE / f"emergency_report_{DATE}.html"
p_taiex.write_text(build("🚨 美股緊急應變報告", alert, note), "utf-8")
p_emerg.write_text(build("🚨 緊急應變報告（美股開盤／費半反彈、10Y 破 5%）", alert, note), "utf-8")
print(f"✅ HTML：{p_taiex.name} / {p_emerg.name}")
