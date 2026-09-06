"""
大轉向資產配置策略 v5 — 2026-09-06：市場快照改執行時自動抓取（Yahoo chart API），
根治「腳本寫死舊值」；策略框架對齊 9/6 核准（500萬MMF、質押350萬@2.77%、ladder延10月）
"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
import json, os, datetime, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
SNAP = json.load(open(f'{BASE}/snapshot.json', encoding='utf-8'))
INS = SNAP.get('allianz_combined',0) + SNAP.get('firstjin_fl65_current_value',0)
SEC = SNAP.get('securities_total_market_value',0)
FUND = SNAP.get('fund_market_value',0)
CASH = SNAP.get('real_liquid_assets',0)
TOTAL = INS + SEC + FUND + CASH
p = SNAP.get('penetration',{}).get('actual_pct',{})
USD_EXP = SNAP.get('usd_exposure_pct')
USD_EXP_TXT = f'{USD_EXP}%' if isinstance(USD_EXP,(int,float)) else '~64%'

# ── 市場快照執行時抓取（v5：取代寫死 as-of 值；失敗 fallback + 印警告）──
def _fetch_chart(sym, host="query1"):
    u = f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1mo"
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=12).read())
    r = d["chart"]["result"][0]
    ts = r.get("timestamp", [])
    q = r["indicators"]["quote"][0]
    closes = [x for x in q.get("close", []) if x is not None]
    return ts, closes

def _asof(ts):
    return datetime.datetime.utcfromtimestamp(ts[-1]).strftime("%m/%d") if ts else "?"

def fetch_market():
    fb = {"taiex": 46551.13, "fx": 31.62, "y10": 4.78, "y30": 5.25,
          "asof": "09/04", "w_low": 45857.66, "prev_w": 46128.47, "chg1d_pct": 1.51}
    try:
        out = {}
        for key, sym in [("taiex", "%5ETWII"), ("fx", "USDTWD%3DX"), ("y10", "%5ETNX"), ("y30", "%5ETYX")]:
            try:
                ts, c = _fetch_chart(sym)
            except Exception:
                ts, c = _fetch_chart(sym, host="query2")  # 備援主機
            if not c or len(c) < 2:
                raise RuntimeError(f"{sym} 資料不足")
            out[key] = c[-1]
            if key == "taiex":
                out["asof"] = _asof(ts)
                out["chg1d_pct"] = (c[-1] - c[-2]) / c[-2] * 100
                out["prev_w"] = c[0]          # 一個月前首日
                out["w_low"] = min(c)          # 近一月低點
        return out
    except Exception as e:
        print(f"⚠️ 市場抓取失敗，fallback 9/6 寫死值：{e}")
        return dict(fb)

M = fetch_market()
TAIEX = M["taiex"]; FX = M["fx"]; Y10 = M["y10"]; Y30 = M["y30"]
ASOF = M["asof"]; W_LOW = M["w_low"]; PREV_W = M["prev_w"]; CHG1D = M["chg1d_pct"]
# 台幣方向：32.38 為 7/29 波段高點基準
FX_BASE = 32.38
FX_MOVE = (FX_BASE - FX) / FX_BASE * 100
FX_NOTE = "台幣偏強" if FX_MOVE > 0 else "台幣偏弱"
Y30_STATE = "已達 5.30 凍結線，新增質押全域凍結" if Y30 >= 5.30 else (f"{Y30:.2f}% 警戒區（5.20-5.30），未觸發凍結" if Y30 >= 5.20 else "警戒線下，質押空間開放")

prs = Presentation()
prs.slide_width = Inches(13.33); prs.slide_height = Inches(7.5)
BG = RGBColor(0x0B,0x0D,0x1A); WHITE = RGBColor(0xFF,0xFF,0xFF)
GRAY = RGBColor(0x8A,0x8F,0xA0); GOLD = RGBColor(0xF7,0xA0,0x1C)
GREEN = RGBColor(0x34,0xD3,0x99); RED = RGBColor(0xFF,0x5C,0x5C)

def ns():
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid(); s.background.fill.fore_color.rgb = BG
    return s

def T(s, t, top=0.3):
    tb = s.shapes.add_textbox(Inches(0.8), Inches(top), Inches(11.5), Inches(0.8))
    pgh = tb.text_frame.paragraphs[0]
    pgh.text = t; pgh.font.size = Pt(32); pgh.font.bold = True; pgh.font.color.rgb = WHITE

def ST(s, t, top=1.2):
    tb = s.shapes.add_textbox(Inches(0.8), Inches(top), Inches(11.5), Inches(0.5))
    pgh = tb.text_frame.paragraphs[0]
    pgh.text = t; pgh.font.size = Pt(16); pgh.font.color.rgb = GRAY

def B(s, items, top=1.9):
    tb = s.shapes.add_textbox(Inches(1), Inches(top), Inches(11.3), Inches(5))
    tf = tb.text_frame; tf.word_wrap = True
    for i, item in enumerate(items):
        pgh = tf.paragraphs[0] if i==0 else tf.add_paragraph()
        pgh.text = item; pgh.font.size = Pt(15); pgh.font.color.rgb = WHITE
        pgh.space_after = Pt(5)

# === S1: 封面 ===
s = ns()
T(s, '大轉向資產配置策略', 1.5)
ST(s, f'USD/TWD {FX:.2f}  ×  台股 {TAIEX:,.0f}（{ASOF} 收盤）  ×  10yr {Y10:.2f}%', 2.5)
B(s, [
    f'數據基準：{ASOF} 最新收盤（執行時自動抓取）｜ 龍九控股策略框架 9/6 核准',
    '',
    '龍九控股 ｜ Chief Secretary + CIO 聯合分析'
], 3.5)

# === S2: 市場現況（資料驅動）===
s = ns()
T(s, f'即時市場：台股 {TAIEX:,.0f}（{CHG1D:+.2f}%）')
recover = (TAIEX / W_LOW - 1) * 100 if W_LOW else 0
if TAIEX >= PREV_W * 0.98:
    trend_line = '台股位處近一月高檔區 — 無系統性風險'
elif recover > 3:
    trend_line = f'自低點已回升 {recover:.1f}% — 跌勢收復中'
else:
    trend_line = '近一月仍在低檔整理 — 維持觀望'
ST(s, f'{trend_line} ｜ 近一月低點 {W_LOW:,.0f}')
B(s, [
    f'📈 台股最新收盤 {TAIEX:,.0f}（單日 {CHG1D:+.2f}%），asof {ASOF}',
    '     證交所維持率健康，無大規模斷頭風險',
    '',
    f'💵 USD/TWD {FX:.2f} — {FX_NOTE}（較 7/29 高點 32.38 {FX_MOVE:+.1f}%）',
    '     美元資產以台幣計價估值波動 — 長期配置不因短期匯率調整',
    '',
    f'📡 10yr {Y10:.2f}% / 30yr {Y30:.2f}% — {Y30_STATE}',
    '     觀望至 9/11 CPI + 9/16 FOMC，方向明朗前不加碼不恐慌'
])

# === S3: 匯率 ===
s = ns()
T(s, f'匯率 {FX:.2f} — {FX_NOTE}，美元曝險的雙面刃')
ST(s, f'美元曝險 {USD_EXP_TXT}（>55% 監控線）→ 台幣{"升值" if FX_MOVE>0 else "貶值"} = {"估值回吐風險" if FX_MOVE>0 else "估值增益"}')
B(s, [
    '🔵 美股ETF + 安聯保單 + 美元基金合計曝險已超監控線',
    f'     7/29 高點 32.38 → 如今 {FX:.2f}（{FX_NOTE} {FX_MOVE:+.1f}%）',
    f'     台幣若{"續強，美元資產以台幣計價縮水" if FX_MOVE>0 else "轉弱，美元資產估值回升"}（未實現）',
    '',
    '💡 9/6 核准：500 萬 MMF（國泰貨基）= 10 月標案預備金',
    '     不換匯、不買債 → 保留台幣流動性，當標案+升息雙重緩衝',
    '',
    '⚠️ 美債 5 階 ladder（2027-2031）延至 10 月標案結果',
    '     沒標到 → 重評估匯率/美元曝險/利率是否見頂，再換匯建 ladder 或還債',
    '     標到 → 履約保證函優先（年費 0.5-1.5%），不新增保單借貸',
    '',
    '📊 結論：匯率方向已逆轉 → 不再加碼美元曝險，等 10 月重評估'
])

# === S4: 證券持股對策 ===
s = ns()
T(s, '證券持股對策：核心續抱，觀望期凍結新增')
ST(s, f'證券總市值 {SEC:,.0f} 元（snapshot 9/4）— 台股 8/24 裁示暫緩、9/6 全面觀望')
sec_hold = SNAP.get('securities',{}).get('holdings',[])
rows = []
for h in sec_hold[:8]:
    v = h.get('pnl_pct') or 0
    rows.append(f'   {h["ticker"]:<8} {h["value"]:>10,.0f}  ({v:+.1f}%)  {h["name"]}')
B(s, [
    '✅ 核心續抱（市值型+高息+低波）：',
    '',
    *rows,
    '',
    '🔴 台股新增凍結：8/24 裁示全暫緩 → 9/6 觀望至 9/11 CPI / 9/16 FOMC',
    '     0050/006208 慢慢買計畫暫停；既有部位續抱不賣',
    '     美股科技 15.4% 已達標 → 不再建議降科技',
    '',
    '💡 00983D 債券梯照收息（月配），其餘不動作',
    '     觀望期結束（9/16 後）依 CPI/FOMC 結果再評估'
])

# === S5: 基金對策 ===
s = ns()
T(s, '基金持股對策（國泰直購 + 鉅亨）')
ST(s, f'基金總市值 {FUND:,.0f} 元（snapshot 9/4 報價日 9/3）')
fb = SNAP.get('funds_breakdown',{})
gk = fb.get('國泰直購',{})
jy = fb.get('自由Pay',{})
gy = fb.get('一般申購',{})
B(s, [
    '✅ 國泰直購（配息主力 + 標案預備金）：',
    '     富達全球動能B月配美元 ' + f"{gk.get('富達全球動能多元B股C月配息美元',0):,.0f}".replace(',',',') + ' 元 — 月配息主力',
    '     國泰貨幣市場基金 ' + f"{gk.get('國泰台灣貨幣市場基金',0):,.0f}".replace(',',',') + ' 元 = 500萬標案預備金（9/6 核准，不換匯不買債）',
    '     聯博全球多元收益AD美元月配 ' + f"{gk.get('聯博全球多元收益AD美元月配',0):,.0f}".replace(',',',') + ' 元',
    '',
    '✅ 鉅亨：自由Pay（路博邁5G累積/統一奔騰/0050連結A）+ 一般申購 19 檔',
    '     ⚠️ 美元/日圓計價部位多 → 計入外幣曝險，續抱不加碼',
    '',
    '💡 基金結構不改：月配息覆蓋生活費，其餘交市場',
    '     任何基金轉換（如接力排程）→ 同步更新三下游報表'
])

# === S6: 債務分析 ===
s = ns()
T(s, '債務結構：低利優勢不變，質押降息進行中')
ST(s, '市場利率 6-7% vs 您的加權 ~2.6% — 結構性優勢')
pl = SNAP.get('policy_pledge_loan',4000000)
B(s, [
    f'🔴 保單借貸 {pl/10000:,.0f} 萬 @4%+ → 9/10 PI 認列後質押 350 萬@2.77% 償還',
    '     （還安聯 300 萬 + 元大 50 萬），利息成本 4%+ → 2.77%',
    '',
    '🟡 洲際W 1,312 萬（600+700）@2.5% 9/25 到期 → 不急，最差續約 2.5%',
    '     國泰備案主軸 ≤2.5%+3 年寬限+全額代償；築巢 2.185%（台電專屬）優先洽詢',
    '',
    f'🟡 大義街 1,200 萬 @2.6%（國泰 8/20 已撥款）→ 3 年寬限期，月付 26,000',
    '',
    '🟢 理財型房貸已全數清償（8/11）✅ ｜ 證券質押 100 萬凍結中',
    '',
    '🏠 優勢：別人貸款 6-7%，您 2.5-2.6% → 升息環境反而擴大利差優勢',
    '     質押上限紀律：US30Y ≥ 5.30 全域凍結新增質押（目前 5.25 未觸發）'
])

# === S7: 配置診斷 ===
s = ns()
T(s, '配置診斷：觀望期不動，等 CPI/FOMC + 10 月標案')
ST(s, f'穿透：台股 {p.get("台股市值型成長",0):.1f}%｜美股 {p.get("美股市值型成長",0):.1f}%（科技{p.get("美股市值型成長_科技",0):.1f}）｜防守配息 {p.get("防守型配息",0):.1f}%｜債券 {p.get("債券",0):.1f}%｜現金 {p.get("現金/安全網",0):.1f}%')
B(s, [
    '🔴 現況（9/6 核准框架）：',
    '     500 萬 MMF（國泰貨基）= 10 月標案預備金，不動',
    f'     台股穿透 {p.get("台股市值型成長",0):.1f}% → 偏低，但觀望期凍結新增',
    '',
    '✅ 不動：美股（匯率回吐風險但長線持有）、安聯、FL65、債券梯',
    '',
    '💡 觀望至 9/11 CPI / 9/16 FOMC：',
    '     升息確定 → 500 萬 MMF 轉還債安全墊（不換匯）',
    '     降息/持平 → 10 月標案結果後再評估 ladder 進場',
    '',
    f'📊 現金/安全網穿透 {p.get("現金/安全網",0):.1f}%：底線 70 萬已守住',
    '     口徑 = 台幣帳戶（不含外幣），月支出 ×3 安全水位達標'
])

# === S8: 三情境 ===
s = ns()
T(s, '三種情境 × 觀望期的準備')
ST(s, 'A:升息 ｜ B:高原 ｜ C:降息 — 9/11 CPI 與 9/16 FOMC 決定方向')
B(s, [
    f'🔴 情境A：升息（30yr {Y30:.2f}% 警戒區，CPI 9/11 關鍵）',
    '     500 萬 MMF 緩衝 ✅ 00983D 短債抗跌 ✅ 質押新增凍結（≥5.30 線）✅',
    '',
    '🟡 情境B：高原（利率不動，最可能）',
    '     月配息覆蓋生活費 ✅ 債券梯照收息 ✅ 美元曝險不再加碼 ✅',
    '',
    '🟢 情境C：降息（若 CPI 走軟 + FOMC 轉鴿）',
    '     10 月標案結果後重評估 ladder ✅ 台股解凍分批買 ✅',
    '',
    '🏠 三情境都安全：房貸 ~2.6% 固定低利，升息環境利差反而擴大',
    '     債務清洗監測啟動（DXY 月跌>3% / 10Y breakeven>3% 等觸發才動作）'
])

# === S9: 時間表 ===
s = ns()
T(s, '執行時間表：9-10 月關鍵節點')
ST(s, '核准框架一次到位，等待 CPI / FOMC / 標案三訊號')
B(s, [
    '📅 9/10：PI 認列 → 質押 350 萬 @2.77% 還安聯 300 + 元大 50',
    '',
    '📅 9/11：CPI 公布 → 9/16 FOMC → 決定觀望期結束後方向',
    '     升息確定 → 500 萬 MMF 轉還債安全墊（不換匯不買債）',
    '',
    '📅 9/25：洲際W 1,312 萬到期 → 轉貸定案（築巢 2.185% 優先 / 國泰備案 ≤2.5%）',
    '',
    '📅 10 月：環保標案結果 →',
    '     沒標到 → 重評估匯率/曝險/ladder 時機（或直接還債）',
    '     標到 → 履約保證函優先，500 萬 MMF 作為營運預備金',
    '',
    '📅 常態：月配息覆蓋生活費，盈餘依序償債（4%+ 優先）'
])

# === S10: 明確行動指示 ===
s = ns()
T(s, '✅ 明確行動指示：接下來做這 5 件事')
ST(s, '核准框架 → 到期前完成 ｜ 您本人 2 件｜龍九自動盯 2 件｜建明 1 件')
B(s, [
    '1️⃣ 【您】9/10 PI 認列後 → 質押 350 萬 @2.77%（國泰）',
    '      還安聯 300 萬 + 元大 50 萬 → 保單借貸成本 4%+ 降至 2.77%',
    '',
    '2️⃣ 【您】9/25 前 → 洲際W 1,312 萬轉貸定案（9/25 到期）',
    '      築巢 2.185% 優先洽詢（台電專屬）｜國泰備案 ≤2.5%+3年寬限',
    '      最差續約 2.5% — 到期前不用急，但不放著不管',
    '',
    '3️⃣ 【龍九盯】9/11 CPI + 9/16 FOMC → 觀望結束判定',
    '      升息確定 → 500 萬 MMF 轉還債安全墊（不換匯不買債）',
    '      降息/持平 → 10 月標案結果後再評估 ladder',
    '',
    '4️⃣ 【龍九盯】持續 → 雷達 pending：凍結台股/輪動至 9/11 前不加碼',
    '      月配息覆蓋生活費自動入帳，盈餘依序償債（4%+ 優先）',
    '',
    '5️⃣ 【建明】10 月 → 標案結果出爐（500 萬 MMF 預備金已就位）',
    '      沒標到 → 重評估 ladder 或直接還債｜標到 → 履約保證函優先',
    '',
    '🚫 明確不做：不換匯買債｜台股不加碼｜不新增質押（US30Y ≥5.30 凍結線）'
])

# === S11: 結論 ===
s = ns()
T(s, '結論：觀望不是靜止 — 三個訊號前都已就位')
ST(s, '低利債務 + 現金緩衝 + 配息覆蓋 → 等訊號再出手')
B(s, [
    f'💰 匯率 {FX:.2f}：{FX_NOTE} → 不再加碼美元曝險，等 10 月重評估',
    '',
    '🏠 債務 ~2.6%：比市場低 4pp+，9/10 質押 350 萬@2.77% 再降成本',
    '',
    f'📈 台股 {TAIEX:,.0f}（{ASOF} 收盤，單日 {CHG1D:+.2f}%）→ 無系統風險，不恐慌不追高',
    '',
    '🎯 9/6 核准框架：500 萬 MMF 標案預備金（不換匯不買債）→',
    '     9/11 CPI → 9/16 FOMC → 9/25 轉貸 → 10 月標案 → ladder 重評估',
    '',
    '🔥 大轉向：不是市場轉向，是您已把資金結構轉向防禦+緩衝',
    '     訊號明朗前不動，訊號一來子彈已就位'
])

prs.save(f'{BASE}/大轉向資產配置策略_final.pptx')
print('✅ 完成！11 頁（v5：市場快照執行時自動抓取，asof ' + ASOF + '）')
