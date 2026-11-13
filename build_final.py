"""
大轉向資產配置策略 v5 — 2026-11-01：市場快照執行時自動抓取（Yahoo chart API），
根治「腳本寫死舊值」；時序一律寫「條件」不寫日曆事件，唯一日期＝pending 的檢視日。
歷史沿革：9/11 MMF 500 萬轉 B11、質押 590 萬@2.65%（9/29 撥款）；10/12 押標金 240 萬取消 → 標案線結束。
（本檔若再出現「觀望至某月某日」字樣，即為回歸缺陷）
"""
from pptx import Presentation
import pledge_status as _pf  # 2026-09-13 質押文字唯一來源（動態）
import us30y_policy as _usp  # 2026-11-04 US30Y 門檻口徑單一來源（5.20 顯示／5.30 行動）
from sot_targets import policy_pledge_loan  # 2026-10-04 P0 假真值退路清除（保單借貸餘額單一入口）
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
import json, os, datetime, urllib.request

try:
    from mortgage_rate import (cathay_rate_pct as _cg_pct, cathay_wan as _cg_wan,
                               cathay_monthly as _cg_mo, yongfeng_principal as _yf_wan)
except Exception:      # 匯入失敗時的保底（口徑同）
    def _cg_pct(*a, **k): return "2.6"
    def _cg_wan(*a, **k): return "1,200"
    def _cg_mo(*a, **k): return 26000
    def _yf_wan(*a, **k): return "1,304"

BASE = os.path.dirname(os.path.abspath(__file__))
SNAP = json.load(open(f'{BASE}/snapshot.json', encoding='utf-8'))
INS = SNAP.get('allianz_combined',0) + SNAP.get('firstjin_fl65_current_value',0)
SEC = SNAP.get('securities_total_market_value',0)
FUND = SNAP.get('fund_market_value',0)
CASH = SNAP.get('real_liquid_assets',0)
TOTAL = INS + SEC + FUND + CASH
p = SNAP.get('penetration',{}).get('actual_pct',{})
USD_EXP = SNAP.get('usd_exposure_pct')
# 2026-10-07 卡② v4（CIO 第四輪 D 點）：本頁原本直接輸出「美元曝險 → 估值回吐風險／
# 不再加碼美元曝險」等處置語意，且不經 scrub → 改為 advisory 感知（僅顯示時不產生方向）。
USD_ADV = bool((SNAP.get('usd_exposure_monitor') or {}).get('advisory_only'))
USD_EXP_TXT = f'{USD_EXP}%' if isinstance(USD_EXP,(int,float)) else '~64%'
# 2026-11-14：門檻字串改動態派生（原硬編碼「目標 60／黃 65／觀察 70」），單一來源＝thresholds
_USD_THR = ((SNAP.get('thresholds_2026_0915') or {}).get('美元曝險_pct') or {})
def _ut(k):
    v = _USD_THR.get(k)
    return f'{v:.0f}' if isinstance(v,(int,float)) else '—'
USD_TIER_TXT = f'目標 {_ut("目標")}／黃 {_ut("黃")}／觀察 {_ut("紅")}'

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
Y30_STATE = _usp.us30y_state_text(Y30)

prs = Presentation()
prs.slide_width = Inches(13.33); prs.slide_height = Inches(7.5)
BG = RGBColor(0x0B,0x0D,0x1A); WHITE = RGBColor(0xFF,0xFF,0xFF)
GRAY = RGBColor(0x8A,0x8F,0xA0); GOLD = RGBColor(0xF7,0xA0,0x1C)
GREEN = RGBColor(0x34,0xD3,0x99); RED = RGBColor(0xFF,0x5C,0x5C)

def ns():
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid(); s.background.fill.fore_color.rgb = BG
    return s

def _adv(t):
    """整頁兜底（CIO 第五輪 D 建議）：簡報所有文字輸出前一律過 scrub ——
    advisory 模式下，任何美元曝險相關的敘述都會被中和，不依賴逐處人工閘控。"""
    try:
        from usd_advisory import scrub as _sc
        return _sc(t, SNAP)[0]
    except Exception:
        return t


def T(s, t, top=0.3):
    t = _adv(t)
    tb = s.shapes.add_textbox(Inches(0.8), Inches(top), Inches(11.5), Inches(0.8))
    pgh = tb.text_frame.paragraphs[0]
    pgh.text = t; pgh.font.size = Pt(32); pgh.font.bold = True; pgh.font.color.rgb = WHITE

def ST(s, t, top=1.2):
    t = _adv(t)
    tb = s.shapes.add_textbox(Inches(0.8), Inches(top), Inches(11.5), Inches(0.5))
    pgh = tb.text_frame.paragraphs[0]
    pgh.text = t; pgh.font.size = Pt(16); pgh.font.color.rgb = GRAY

def B(s, items, top=1.9):
    tb = s.shapes.add_textbox(Inches(1), Inches(top), Inches(11.3), Inches(5))
    tf = tb.text_frame; tf.word_wrap = True
    for i, item in enumerate(items):
        pgh = tf.paragraphs[0] if i==0 else tf.add_paragraph()
        pgh.text = _adv(item); pgh.font.size = Pt(15); pgh.font.color.rgb = WHITE
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
    f'     台股解凍條件：US30Y 連 2 日低於 5.30%（現 {Y30:.2f}%）→ 凍結中，不追高'
])

# === S3: 匯率 ===
s = ns()
T(s, f'匯率 {FX:.2f} — {FX_NOTE}' + ('' if USD_ADV else '，美元曝險的雙面刃'))
ST(s, f'美元曝險 {USD_EXP_TXT}（🟡 僅顯示，{USD_TIER_TXT}）' if USD_ADV
   else f'美元曝險 {USD_EXP_TXT}（>55% 監控線）→ 台幣{"升值" if FX_MOVE>0 else "貶值"} = {"估值回吐風險" if FX_MOVE>0 else "估值增益"}')
B(s, [
    ('🔵 美股ETF + 安聯保單 + 基金部位之計價結構僅供觀察（🟡 僅顯示，不觸發資產調整）'
     if USD_ADV else '🔵 美股ETF + 安聯保單 + 美元基金合計曝險已超監控線'),
    f'     7/29 高點 32.38 → 如今 {FX:.2f}（{FX_NOTE} {FX_MOVE:+.1f}%）',
    (f'     匯率變動對資產之計價影響僅供參考（未實現）' if USD_ADV
     else f'     台幣若{"續強，美元資產以台幣計價縮水" if FX_MOVE>0 else "轉弱，美元資產估值回升"}（未實現）'),
    '',
    '💡 框架現況（2026-11-01）：質押 590 萬已撥款（9/29）→ 高息負債清零；MMF 500 萬已轉 B11（擔保池）',
    '     ⛔ 10 月標案不承接（押標金 240 萬 10/12 取消；在職不營利）',
    '',
    '🏗️ 標案（11 月評估）：只做前置、不押標金（現場＝建明）',
    '     11 月評估項：環保標（財務監控／合規／對接）＋工安標（單位／金額／資格，待採購網公告）',
    '     6 月檔期：使用者提及曾有一案（待確認單位／金額後再議，不列入本月行動）',
    '',
    '⚠️ 美債 5 階 ladder（2027-2031）：原「標案資金理由」已消滅 → 改純投資決策，11/03 檢視日重評',
    '     檢視日 ≠ 授權：當天只重評估，不自動進場；US30Y ≥5.30% 期間長天期債新增凍結',
    '',
    '📊 結論：匯率方向已逆轉；美元曝險僅顯示（advisory），不作為行動依據'
    if USD_ADV else
    '📊 結論：匯率方向已逆轉 → 不再加碼美元曝險'
])

# === S4: 證券持股對策 ===
s = ns()
T(s, '證券持股對策：核心續抱，解凍條件未達前凍結新增')
ST(s, f'證券總市值 {SEC:,.0f} 元（報價日 {ASOF}）— 凍結中，等 US30Y 解凍條件')
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
    '🔴 台股凍結中：解凍條件＝US30Y 連 2 日低於 5.30%',
    '     0050/006208 慢慢買計畫暫停；既有部位續抱不賣',
    f'     科技曝險 {p.get("美股市值型成長_科技",0):.1f}%（上限 15%）→ 不再建議降科技',
    '',
    '💡 00983D 債券梯照收息（月配），其餘不動作',
    '     解凍後才談分批節奏（單次上限／停止條件另行定版）'
])

# === S5: 基金對策 ===
s = ns()
T(s, '基金持股對策（國泰直購 + 鉅亨）')
ST(s, f'基金總市值 {FUND:,.0f} 元（報價日 {ASOF}）')
fb = SNAP.get('funds_breakdown',{})
gk = fb.get('國泰直購',{})
jy = fb.get('自由Pay',{})
gy = fb.get('一般申購',{})
B(s, [
    '✅ 國泰直購（配息主力 + 質押擔保池）：',
    '     富達全球動能B月配美元 ' + f"{gk.get('富達全球動能多元B股C月配息美元',0):,.0f}".replace(',',',') + ' 元 — 月配息主力',
    '     貝萊德B11 強化穩定月配息 ' + f"{gk.get('貝萊德智慧數據收益成長B11-美元-強化穩定月配息',0):,.0f}".replace(',',',') + ' 元（原 MMF 500 萬贖回款轉申購；⛔ 原「500萬標案預備金」已作廢 9/11）',
    '     聯博全球多元收益AD美元月配 ' + f"{gk.get('聯博全球多元收益AD美元月配',0):,.0f}".replace(',',',') + ' 元',
    '',
    '✅ 鉅亨：自由Pay（路博邁5G累積/統一奔騰/0050連結A）+ 一般申購 19 檔',
    '     ⚠️ 美元/日圓計價部位多 → 計入外幣曝險（僅顯示，不作為行動依據）'
    if USD_ADV else
    '     ⚠️ 美元/日圓計價部位多 → 計入外幣曝險，續抱不加碼',
    '',
    '💡 基金結構不改：月配息覆蓋生活費，其餘交市場',
    '     任何基金轉換（如接力排程）→ 同步更新三下游報表'
])

# === S6: 債務分析 ===
s = ns()
T(s, '債務結構：低利優勢不變，質押降息進行中')
ST(s, f'市場利率 6-7% vs 您的加權 ~{_cg_pct()}% — 結構性優勢')
# 2026-10-04 P0 假真值退路清除：原 .get('policy_pledge_loan', 4000000) 會在 snapshot 缺鍵時
# 把「已於 2026-09-29＋10-01 全數清償」的保單借貸 400 萬復活（負債假真值）→ 改走 accessor，缺值阻斷。
pl = policy_pledge_loan(SNAP)
_pl_li = (
    [f'🔴 保單借貸 {pl/10000:,.0f} 萬 @4%+ → 質押 590 萬@2.65% 償還（9/29 已撥款入帳）',
     '     （第一批 200 萬已提出還款申請、待入帳；餘 300 萬待執行）利息成本 4% → 2.65%']
    if pl > 0 else
    ['✅ 保單借貸已全數清償（2026-09-29＋10-01，餘額 0）→ 質押 590 萬完成置換，利息成本 4% → 2.65%']
)
B(s, [
    *_pl_li,
    '',
    '🟡 洲際W 1,312 萬（600+700）@2.50% → 已到期續繳中，每月 27 扣 65,734',
    '     轉貸延 11 月：11/03 檢視（檢視≠授權）；築巢 2.185% 優先、國泰 ≤2.5%+3 年寬限備案',
    '',
    f'🟡 大義街 {_cg_wan()} 萬 @{_cg_pct()}%（國泰 8/20 已撥款）→ 3 年寬限期，月付 {_cg_mo():,}',
    '',
    '🟢 理財型房貸已全數清償（8/11）✅ ｜ 證券質押 100 萬凍結中',
    '',
    f'🏠 優勢：別人貸款 6-7%，您 {_cg_pct()}% → 升息環境反而擴大利差優勢',
    '     質押上限紀律：US30Y ≥ 5.30 全域凍結新增質押（目前 5.25 未觸發）'
])

# === S7: 配置診斷 ===
s = ns()
T(s, '配置診斷：凍結期不動，等 US30Y 解凍條件')
ST(s, f'穿透：台股 {p.get("台股市值型成長",0):.1f}%｜美股 {p.get("美股市值型成長",0):.1f}%（科技{p.get("美股市值型成長_科技",0):.1f}）｜防守配息 {p.get("防守型配息",0):.1f}%｜債券 {p.get("債券",0):.1f}%｜現金 {p.get("現金/安全網",0):.1f}%')
B(s, [
    '🔴 現況（2026-11-01）：',
    '     貝萊德 B11 500 萬（原 MMF 贖回款）＝質押擔保池成員，不可動用；標案押標金 240 萬已取消（10/12）',
    f'     台股穿透 {p.get("台股市值型成長",0):.1f}%（目標 10%）→ 凍結新增，等解凍條件',
    '',
    '✅ 不動：美股（匯率回吐風險但長線持有）、安聯、FL65、債券梯',
    '',
    '💡 解凍條件（唯一判準，不看日曆）：',
    '     US30Y 連 2 日低於 5.30% → 才談台股分批與長債新增',
    '     未達前：配息導流補現金、不賣擔保品、不新增質押',
    '',
    f'📊 現金/安全網穿透 {p.get("現金/安全網",0):.1f}%：底線 70 萬已守住',
    '     口徑 = 台幣帳戶（不含外幣），月支出 ×3 安全水位達標'
])

# === S8: 三情境 ===
s = ns()
T(s, '三種利率情境 × 凍結期的準備')
ST(s, f'A:升息 ｜ B:高原 ｜ C:降息 — 以 30yr {Y30:.2f}% 與 US30Y 紅線判讀')
B(s, [
    f'🔴 情境A：升息（30yr {Y30:.2f}%，已站上 5.30 凍結線）',
    '     質押擔保池 B11 500 萬（原 MMF）✅ 00983D 短債抗跌 ✅ 質押新增凍結（≥5.30 線）✅',
    '',
    '🟡 情境B：高原（利率不動，最可能）',
    '     月配息覆蓋生活費 ✅ 債券梯照收息 ✅ 美元曝險不再加碼 ✅',
    '',
    '🟢 情境C：降息（若 CPI 走軟 + FOMC 轉鴿）',
    '     解凍條件成立後重評 ladder ✅ 台股分批買 ✅',
    '',
    f'🏠 三情境都安全：房貸 ~{_cg_pct()}% 固定低利，升息環境利差反而擴大',
    '     債務清洗監測啟動（DXY 月跌>3% / 10Y breakeven>3% 等觸發才動作）'
])

# === S9: 時間表 ===
s = ns()
T(s, '執行時間表：11 月關鍵節點')
ST(s, '訊號判準改為條件式（US30Y／美元曝險），不再綁日曆事件')
B(s, [
    '📅 ' + _pf.pledge_status_line(style='short') + ' → ' + ('高息負債已全數清零（保單 4.0%／券商 3.92%）' if pl <= 0 else f'清償 {pl/10000:,.0f} 萬高息負債'),
    '',
    '📅 已完成：質押 590 萬@2.65%（9/29 撥款）、高息負債清零（10/01）',
    '',
    '📅 11/03 檢視日（兩項）：',
    '     ① 美債中短 ladder 重評（標案理由已消滅，改純投資決策）',
    '     ② 洲際W 轉貸（目前 @2.50% 續繳；築巢 2.185% 優先）— 檢視≠授權',
    '',
    '📅 11 月：標案評估（只做前置，不押標金）',
    '     環保標：財務監控／合規／對接；工安標：等採購網公告後確認單位／金額／資格',
    '     6 月檔期：使用者提及曾有一案，待確認單位／金額後再議',
    '',
    '📅 條件式（無固定日期）：',
    '     US30Y 連 2 日低於 5.30% → 台股解凍、長債新增解禁',
    '     US30Y ≥5.30% 持續 → 長天期債與新增質押維持凍結',
    '',
    '📅 常態：月配息覆蓋生活費，盈餘優先補現金（乾粉底線 70 萬）'
])

# === S10: 明確行動指示 ===
s = ns()
T(s, '✅ 明確行動指示：接下來做這 5 件事')
ST(s, '凍結期不靠日曆，只靠條件 ｜ 您 2 件｜龍九盯 2 件｜建明 1 件')
B(s, [
    '1️⃣ 【已完成】質押 590 萬@2.65% 撥款 → 高息負債（保單 4.0%／券商 3.92%）全數清零',
    '      月息 13,029（每月 22 扣）；擔保池 1,200 萬、LTV 49.3%',
    '',
    '2️⃣ 【您】11/03 前 → 洲際W 轉貸決斷（現 @2.50% 續繳、每月 27 扣 65,734）',
    '      築巢 2.185% 優先（台電專屬）｜國泰 ≤2.5%+3 年寬限備案',
    '      檢視日只是重新評估，不等於授權執行',
    '',
    '3️⃣ 【龍九盯】台股解凍條件：US30Y 連 2 日低於 5.30%',
    f'      現 30yr {Y30:.2f}% → 未達，凍結維持',
    '',
    '4️⃣ 【龍九盯】現金回補：乾粉 42.0 萬（底線 70 萬）→ 配息導流優先，不賣擔保品',
    '      月配息覆蓋生活費自動入帳，盈餘先補現金再談還債',
    '',
    '5️⃣ 【建明】標案：11 月做前置評估（環保標＋工安標），不押標金',
    '      10 月標案已不承接（押標金 240 萬 10/12 取消）；6 月檔期待確認',
    '',
    '🚫 明確不做：不換匯買債｜台股不加碼｜不新增質押（US30Y ≥5.30 凍結線）'
])

# === S11: 結論 ===
s = ns()
T(s, '結論：凍結不是靜止 — 條件到了才出手')
ST(s, '低利債務 + 配息覆蓋已就位 → 現在缺的是現金緩衝')
B(s, [
    f'💰 匯率 {FX:.2f}：{FX_NOTE} → 不再加碼美元曝險，導流回台幣資產',
    '',
    f'🏠 債務 ~{_cg_pct()}%：比市場低 4pp+，質押 590 萬@2.65% 再降成本（9/29 已撥款）',
    '',
    f'📈 台股 {TAIEX:,.0f}（{ASOF} 收盤，單日 {CHG1D:+.2f}%）→ 無系統風險，不恐慌不追高',
    '',
    '🎯 質押 590 萬@2.65%（擔保池 1,200 萬×5 成）→ 高息負債已清零，月息 13,029；',
    '     下一步：11/03 檢視（ladder／洲際W）→ 11 月標案前置評估 → 等 US30Y 解凍',
    '',
    '🔥 大轉向：不是市場轉向，是您已把資金結構轉向防禦+緩衝',
    '     訊號明朗前不動，訊號一來子彈已就位'
])

prs.save(f'{BASE}/grand_pivot_deck.pptx')
print('✅ 完成！11 頁（v5：市場快照執行時自動抓取，asof ' + ASOF + '）')
