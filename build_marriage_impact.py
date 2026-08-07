"""
龍九控股 — 結婚生子財務衝擊評估簡報
使用 SlideDeck 引擎
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from presentation_engine import SlideDeck, GREEN, RED, GOLD, BLUE, PURPLE, GRAY, WHITE, TEXT

d = SlideDeck()

# 載入資料
BASE = Path(__file__).resolve().parent
snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
ins = snap.get("insurance_current_value", 9802872)
sec = snap.get("securities", {}).get("total_market_value", 2479320)
cash = snap.get("cash", 3614169)
fund = snap.get("fund_market_value", 793434)
real_estate = snap.get("real_estate", 33316467)
total_assets = ins + sec + cash + fund + real_estate
mortgage = 13159422
fin_mortgage = 3006447
salary = 39727
rent = 80100
dividend = 118296
passive = rent + dividend  # 198,396
monthly_income = salary + passive
mortgage_pmt = 99458

# === S1: 封面 ===
d.slide_cover(
    title="結婚生子財務衝擊評估",
    subtitle="家庭擴張對龍九控股資產負債與現金流的影響分析",
    date="2026 年 7 月 26 日 ｜ 三種情境：基本／適度／全面",
)

# === S2: 目錄 ===
d.slide_toc("CONTENTS", [
    "現狀回顧：當前財務基本面",
    "情境設定：結婚＋生子的三種劇本",
    "一次性支出分析",
    "每月經常性支出變化",
    "轉貸計劃對沖效果",
    "三情境結果對照",
    "總結與建議",
])

# S3: 現狀
sl = d._new()
d.page_title(sl, "當前財務基本面：月淨現金流 -4,099，轉貸後將翻正", "總資產 50.7M｜負債率 41.8%｜被動月收 198K")
d.metric_card(sl, 0.5, 1.8, 3.5, 1.5, "總資產", f"{total_assets:,.0f}", GOLD, "含不動產 33.3M")
d.metric_card(sl, 4.3, 1.8, 3.5, 1.5, "總負債", "16,218,870", RED, f"房貸 {mortgage:,}")
d.metric_card(sl, 8.1, 1.8, 3.5, 1.5, "月被動收入", f"{passive:,}", GREEN, "房租 80K + 配息 118K")
d.metric_card(sl, 0.5, 3.6, 3.5, 1.5, "月薪資", f"{salary:,}", GOLD, "台電")
d.metric_card(sl, 4.3, 3.6, 3.5, 1.5, "月支出", "~210,958", RED, "轉貸後 ~145K")
d.metric_card(sl, 8.1, 3.6, 3.5, 1.5, "關鍵變數", "轉貸 +102K/月", GREEN, "轉貸後現金流充沛")
d.card(sl, 0.5, 5.5, 11.5, 1)
d.multi(sl, [
    "💡 轉貸計劃若順利執行（築巢優利貸 2.185%＋清償保單借貸），月淨現金流可達 +102,259",
    "   這筆盈餘將是未來結婚生子的主要財源緩衝",
], 0.8, 5.65, 10, 0.7, 14, GOLD)

# S4: 三種劇本
sl = d._new()
d.page_title(sl, "三種情境假設：婚禮規模與子女人數為核心變數", "依台灣中位數婚禮/育兒成本設定")
scenarios = [
    ("基本方案", "登記＋小宴", "1 子", "約 30 萬", "月增 2 萬", GREEN),
    ("適度方案", "中型婚宴 20 桌", "1-2 子", "約 80 萬", "月增 4 萬", GOLD),
    ("全面方案", "傳統婚禮 30 桌", "2 子", "約 150 萬", "月增 6 萬", RED),
]
for i, (name, wedding, child, once, monthly, color) in enumerate(scenarios):
    x = 0.5 + i * 4.2
    d.card(sl, x, 1.8, 3.8, 4.5)
    d.card(sl, x, 1.8, 3.8, 0.06)
    d.txt(sl, name, x + 0.3, 2, 3, 0.4, 20, True, color)
    d.txt(sl, f"💒 {wedding}", x + 0.3, 2.6, 3, 0.3, 14, False)
    d.txt(sl, f"👶 {child}", x + 0.3, 3.1, 3, 0.3, 14, False)
    d.metric_card(sl, x + 0.2, 3.5, 3.4, 1.2, "一次性支出", once, color)
    d.txt(sl, f"📊 每月經常性增支 {monthly}", x + 0.3, 5, 3, 0.3, 12, False, GRAY)
d.card(sl, 0.5, 6.7, 11.5, 0.5)
d.txt(sl, "數據來源：行政院主計總處婚禮/育兒費用統計 + 台北市保母/幼稚園均價", 0.8, 6.8, 10, 0.3, 11, False, GRAY)

# S5: 一次性支出
sl = d._new()
d.page_title(sl, "一次性支出 30~150 萬，可從轉貸資金支應", "不影響日常現金流，屬可控制一次性支出")
items = [
    ("婚宴場地 + 酒席", "15~60 萬", "20~30 桌"),
    ("婚紗攝影 + 新秘", "5~15 萬", "含婚紗/新秘/攝錄影"),
    ("戒指 + 金飾", "3~10 萬", "對戒＋龍鳳掛"),
    ("蜜月旅行", "5~15 萬", "日本/歐洲 7-10 天"),
    ("月子中心", "10~20 萬", "30 天，台北市均價"),
    ("新生兒用品 + 醫療", "2~5 萬", "嬰兒車/床/安全座椅"),
]
for i, (item, cost, note) in enumerate(items):
    y = 1.8 + i * 0.8
    d.card(sl, 0.5, y, 12, 0.65)
    d.txt(sl, item, 0.8, y + 0.1, 4, 0.4, 15, True)
    d.txt(sl, cost, 5.5, y + 0.1, 2, 0.4, 18, True, GOLD)
    d.txt(sl, note, 8, y + 0.1, 4, 0.4, 13, False, GRAY)
d.card(sl, 0.5, 6.7, 11.5, 0.5)
d.txt(sl, "💡 轉貸後保留的理財型額度 3M，足以支應任何情境的一次性支出", 0.8, 6.8, 10, 0.3, 13, False, GOLD)

# S6: 經常性支出
sl = d._new()
d.page_title(sl, "每月經常性支出增 2~6 萬，轉貸後現金流仍充裕", "轉貸後月盈餘 +102K，足以覆蓋育兒支出")
categories = [
    ("保母費", "15,000~22,000", "全日托，台北市均價"),
    ("奶粉 + 尿布", "4,000~6,000", "新生兒基本開銷"),
    ("幼稚園學費", "12,000~18,000", "私立幼稚園月均"),
    ("醫療 + 保險", "2,000~5,000", "自費疫苗/健檢/兒醫"),
    ("教育基金", "5,000~10,000", "每月儲蓄/006208定投"),
]
for i, (item, cost, note) in enumerate(categories):
    y = 1.8 + i * 0.85
    d.card(sl, 0.5, y, 12, 0.7)
    d.txt(sl, item, 0.8, y + 0.1, 4, 0.4, 15, True)
    d.txt(sl, cost, 5.5, y + 0.1, 2.5, 0.4, 18, True, GOLD)
    d.txt(sl, note, 8.5, y + 0.1, 4, 0.4, 13, False, GRAY)
d.card(sl, 0.5, 6.2, 11.5, 0.8)
d.multi(sl, [
    "💡 每月新增支出頂標約 6 萬，轉貸後月盈餘 +102K，覆蓋率 170%",
    "   若採用適度方案（月增 4 萬），盈餘仍剩 62K，安全邊際充足",
], 0.8, 6.35, 10, 0.7, 13, GOLD)

# S7: 轉貸對沖
sl = d._new()
d.page_title(sl, "轉貸計劃是關鍵對沖工具：月釋放 106K 現金流", "築巢優利貸 2.185%＋清償保單借貸為核心")
d.card(sl, 0.5, 1.8, 5.5, 4.5)
d.txt(sl, "轉貸前（現狀）", 0.8, 2, 5, 0.4, 20, True, RED)
items_before = [
    ("月收入", "206,859"),
    ("月支出", "210,958"),
    ("月淨現金流", "-4,099 ⚠️"),
]
for i, (label, value) in enumerate(items_before):
    y = 2.6 + i * 0.8
    d.txt(sl, label, 0.8, y, 2, 0.3, 14, False, GRAY)
    d.txt(sl, value, 3, y, 2.5, 0.4, 22, True, RED if '-' in value else WHITE)

d.card(sl, 6.5, 1.8, 5.5, 4.5)
d.txt(sl, "轉貸後（10月起）", 6.8, 2, 5, 0.4, 20, True, GREEN)
items_after = [
    ("月收入", "247,559"),
    ("月支出", "145,300"),
    ("月淨現金流", "+102,259 ✅"),
]
for i, (label, value) in enumerate(items_after):
    y = 2.6 + i * 0.8
    d.txt(sl, label, 6.8, y, 2, 0.3, 14, False, GRAY)
    d.txt(sl, value, 9, y, 2.5, 0.4, 22, True, GREEN if '+' in value else WHITE)

d.card(sl, 0.5, 6.7, 11.5, 0.5)
d.txt(sl, "結論：轉貸後每月盈餘 +102K，即使頂標育兒支出 60K，仍剩 42K 緩衝", 0.8, 6.8, 11, 0.3, 14, False, GOLD)

# S8: 寬限期分析
sl = d._new()
d.page_title(sl, "寬限期過後月付 53,803，比現狀仍省 45,655", "築巢優利貸寬限期 3 年（利息月付 23,961），每省下的錢可用於育兒")
d.metric_card(sl, 0.5, 1.8, 3.5, 1.8, "現狀月付", "99,458", RED, "永豐三筆房貸")
d.metric_card(sl, 4.3, 1.8, 3.5, 1.8, "寬限期月付 1-3年", "23,961 ✅", GREEN, "僅利息，省 75,497/月")
d.metric_card(sl, 8.1, 1.8, 3.5, 1.8, "寬限期後月付 4-30年", "53,803 ✅", GOLD, "比現狀省 45,655/月")

d.card(sl, 0.5, 4, 11.5, 3)
d.txt(sl, "三種情境 vs 寬限期前後對照", 0.8, 4.2, 8, 0.4, 20, True, GOLD)
d.multi(sl, [
    "情境／月現金流          寬限期（1-3年）    寬限期後（4年起）",
    "─────────────────────────────────────────",
    "基本方案：月增 2 萬      +82K → +140K ✅   +82K → +85K ✅",
    "適度方案：月增 4 萬      +62K → +120K ✅   +62K → +63K ✅",
    "全面方案：月增 6 萬      +42K → +100K ✅   +42K → +43K ✅",
    "",
    "💡 結論：寬限期內現金流極度充裕，寬限期後即使月付回升至 53,803",
    "   仍低於現狀 99,458，全情境安全無虞。",
], 0.8, 4.8, 10, 2, 12, TEXT)

# S9: 三情境結果
sl = d._new()
d.page_title(sl, "三情境結果對照：即使全面方案仍在安全範圍內", "轉貸後月盈餘 +102K vs 最低育兒增支 20K vs 最高 60K")
results = [
    ("基本方案", "30 萬", "20K/月", "+82K/月 ✅", "極安全", GREEN),
    ("適度方案", "80 萬", "40K/月", "+62K/月 ✅", "安全", GOLD),
    ("全面方案", "150 萬", "60K/月", "+42K/月 ✅", "可控", BLUE),
]
for i, (name, once, monthly, remaining, level, color) in enumerate(results):
    x = 0.5 + i * 4.2
    d.card(sl, x, 1.8, 3.8, 4.5)
    d.card(sl, x, 1.8, 3.8, 0.06)
    d.txt(sl, name, x + 0.3, 2, 3, 0.4, 20, True, color)
    d.metric_card(sl, x + 0.2, 2.6, 3.4, 1, "一次性支出", once, color)
    d.metric_card(sl, x + 0.2, 3.8, 3.4, 1, "月經常性增支", monthly, color)
    d.txt(sl, f"剩餘現金流 {remaining}", x + 0.3, 5.2, 3, 0.4, 14, False, color)
    d.txt(sl, f"風險級別：{level}", x + 0.3, 5.7, 3, 0.3, 13, False, color)
d.card(sl, 0.5, 6.7, 11.5, 0.5)
d.txt(sl, "💡 最壞情境（全面方案）每月仍剩 42K 緩衝，相當於 3 個月基本生活費的安全邊際", 0.8, 6.8, 11, 0.3, 14, False, GOLD)

# S9: 總結
d.slide_summary("結論：結婚生子財務可行，關鍵在轉貸計劃順利執行", [
    ("💰", "現金流充足", "轉貸後月盈餘 +102K，即使頂標支出仍剩 42K", GREEN),
    ("🛡️", "一次性支出有解", "理財型額度 3M 備援，不影響現金流", BLUE),
    ("📈", "育兒有充裕緩衝", "保母/幼稚園月均 3-4 萬，只佔盈餘 30-40%", GOLD),
    ("⚠️", "風險因子", "轉貸若延遲將壓縮緩衝空間，需確保 9/25 前完成", RED),
])
d.save(str(BASE / "結婚生子財務衝擊評估.pptx"))
print("✅ 結婚生子財務衝擊評估.pptx")
