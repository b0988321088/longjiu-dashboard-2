"""
龍九控股 — Sell Put / ELN 策略評估簡報
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from presentation_engine import SlideDeck, GREEN, RED, GOLD, BLUE, PURPLE, GRAY, WHITE, TEXT

d = SlideDeck()

# S1: 封面
d.slide_cover(
    title="Sell Put / ELN 策略評估報告",
    subtitle="以輝達（NVDA）為標的之結構型商品風險分析",
    date="2026 年 7 月 26 日 ｜ 證券推薦產品評估",
)

# S2: 目錄
d.slide_toc("CONTENTS", [
    "產品結構說明：什麼是 Sell Put / ELN？",
    "吸引力分析：為什麼聽起來很好？",
    "風險一：現金流不穩定，無法取代配息",
    "風險二：資金鎖定與尾端風險",
    "風險三：高維護成本，背離被動投資",
    "情境模擬：三種走勢結果",
    "結論：不建議，提供替代方案",
])

# S3: 產品說明
sl = d._new()
d.page_title(sl, "Sell Put / ELN 策略：賣出賣權賺權利金，跌到價外接股", "以輝達（NVDA）為標的，履約價設在現價 50% off")
d.card(sl, 0.5, 1.8, 5.5, 4.5)
d.txt(sl, "策略運作機制", 0.8, 2, 5, 0.4, 20, True, GOLD)
d.multi(sl, [
    "1️⃣ 選定標的：輝達 NVDA",
    "2️⃣ 設定履約價：現價 × 50%（深度價外）",
    "3️⃣ 賣出賣權（Sell Put），收取權利金",
    "4️⃣ 四種結果：",
    "    📌 股價沒跌 → 賺權利金（像利息）",
    "    📌 股價跌 50% → 強制接股（半價買入）",
    "    📌 股價跌 >50% → 深度套牢",
    "    📌 股價大漲 → 只賺微薄權利金",
], 0.8, 2.6, 4.5, 3.5, 13)

d.card(sl, 6.5, 1.8, 5.5, 4.5)
d.txt(sl, "關鍵參數", 6.8, 2, 5, 0.4, 20, True, RED)
d.multi(sl, [
    "⚠️ 需預留 100% 現金保證金",
    "⚠️ 合約期間：3 個月一期",
    "⚠️ 需持續 Roll Over（展期）",
    "⚠️ 權利金收入 = 固定，無上漲空間",
    "⚠️ 接股後 = 持有個股，無分散風險",
    "",
    "🔄 每次到期需重新評估：",
    "  波動率 → 履約價 → 接盤意願",
], 6.8, 2.6, 4.8, 3.5, 13)

# S4: 為什麼聽起來好
sl = d._new()
d.page_title(sl, "吸引力分析：高利息 + 半價接股的雙贏幻覺", "證券話術 vs 實際風險")
items = [
    ("話術：沒跌就領高利息", "事實：權利金本質是承擔風險的補償，非長期穩定配息", RED),
    ("話術：跌了半價接股賺到", "事實：跌 50% 後還有可能再跌 70%+，深度套牢", RED),
    ("話術：適合穩健投資人", "事實：需盯盤 + 滾動調整，非被動投資", RED),
    ("話術：科技巨頭不會倒", "事實：個股風險永遠存在（Nokia/Intel 案例）", RED),
]
for i, (hook, truth, color) in enumerate(items):
    y = 1.8 + i * 1.3
    d.card(sl, 0.5, y, 12, 1)
    d.txt(sl, hook, 0.8, y + 0.1, 5.5, 0.4, 16, True)
    d.txt(sl, truth, 6.5, y + 0.15, 5.5, 0.4, 14, False, color)

# S5: 風險一
sl = d._new()
d.page_title(sl, "現金流不穩定，無法取代固定的月配息", "權利金收入 ≠ 配息收入，本質完全不同")
d.card(sl, 0.5, 1.8, 5.5, 4.5)
d.txt(sl, "Sell Put 權利金收入", 0.8, 2, 5, 0.4, 18, True, RED)
d.multi(sl, [
    "❌ 收入非長期持續",
    "   每次合約到期後需重新尋找機會",
    "   條件可能大不相同",
    "",
    "❌ 市場大漲時錯失主升段",
    "   輝達漲 30% → 只拿固定權利金",
    "   完全吃不到資本利得",
    "",
    "❌ 無法預測的現金流",
    "   無法納入被動收入規劃",
], 0.8, 2.6, 4.5, 3.5, 12)

d.card(sl, 6.5, 1.8, 5.5, 4.5)
d.txt(sl, "現有月配息系統", 6.8, 2, 5, 0.4, 18, True, GREEN)
d.multi(sl, [
    "✅ 保單配息：73,000/月（穩定）",
    "    清償後變 89,000/月",
    "",
    "✅ ETF 股息：10,000/月（穩定）",
    "    00919/00878/00983D 長期配息",
    "",
    "✅ 保單第三站：17,500/月（預計）",
    "    PIMCO+AI+A10 月配型",
    "",
    "✅ 全部可預測、低維護",
], 6.8, 2.6, 4.5, 3.5, 12)

# S6: 風險二
sl = d._new()
d.page_title(sl, "資金鎖定與尾端風險：100% 保證金 + 無底跌幅", "個股（即便是 NVDA）跌幅沒有底限")
d.metric_card(sl, 0.5, 1.8, 3.5, 1.8, "保證金要求", "100% 現金", RED, "資金效率極低")
d.metric_card(sl, 4.3, 1.8, 3.5, 1.8, "個股最大跌幅", "無底限", RED, "NVDA 曾跌 80%+")
d.metric_card(sl, 8.1, 1.8, 3.5, 1.8, "對比 VT/ETF", "分散風險", GREEN, "全球指數")

d.card(sl, 0.5, 4, 11.5, 2.5)
d.txt(sl, "情境模擬：假設投入 1,000 萬做 Sell Put", 0.8, 4.2, 8, 0.4, 18, True, GOLD)
d.multi(sl, [
    "NVDA 跌 50% → 強制接股 500 萬 NVDA + 500 萬現金退款",
    "NVDA 再跌 20%（總跌 60%）→ NVDA 持股市值=400 萬，虧損 100 萬",
    "NVDA 跌 80%（半導體景氣循環）→ 市值=200 萬，虧損 300 萬",
    "",
    "💡 相比之下：買 VT 或 006208，分散風險+長期複利，無需盯盤",
], 0.8, 4.7, 10, 1.5, 13)

# S7: 風險三
sl = d._new()
d.page_title(sl, "高維護成本，背離被動投資初衷", "期權合約每 3 個月需重新評估，無法自動化")
comps = [
    ("Sell Put / ELN", "每 3 個月", "需盯盤 + Roll Over", "高", "N/A", RED),
    ("保單配息", "每月自動入帳", "零維護", "零", "2.185%", GREEN),
    ("ETF（00919/00878）", "每季自動入帳", "零維護", "零", "6-8%", GREEN),
    ("VT / 006208", "長期持有", "零維護", "零", "市場報酬", GREEN),
]
for i, (product, freq, maintenance, effort, cost, color) in enumerate(comps):
    y = 1.8 + i * 1.1
    d.card(sl, 0.5, y, 12, 0.9)
    d.txt(sl, product, 0.8, y + 0.15, 3, 0.4, 16, True, color)
    d.txt(sl, freq, 4, y + 0.15, 2.5, 0.4, 13, False)
    d.txt(sl, maintenance, 6.5, y + 0.15, 3, 0.4, 13, False)
    d.txt(sl, f'維護成本：{effort}', 9.5, y + 0.15, 1.5, 0.4, 13, False, color)

# S8: 情境模擬
sl = d._new()
d.page_title(sl, "三種走勢結果模擬：只有一種情境有利", "Sell Put 本質是賣出保險，賺小錢賠大錢")
scenarios = [
    ("NVDA 小跌或持平", "賺權利金 ~5%", "✅ 有限獲利", "最佳情境，但不可持續", GOLD),
    ("NVDA 跌 50% 接股", "接股後回漲", "✅ 半價買到", "接股後變個股集中持股", BLUE),
    ("NVDA 跌 70%+", "深度套牢", "❌ 重大虧損", "需數年解套，資金凍結", RED),
]
for i, (scenario, profit, result, risk, color) in enumerate(scenarios):
    y = 2 + i * 1.5
    d.card(sl, 0.5, y, 12, 1.2)
    d.card(sl, 0.5, y, 0.06, 1.2)
    d.txt(sl, scenario, 0.8, y + 0.1, 4, 0.4, 18, True, color)
    d.txt(sl, profit, 5, y + 0.1, 2, 0.4, 16, True)
    d.txt(sl, result, 7.5, y + 0.1, 2, 0.4, 16, True, color)
    d.txt(sl, risk, 0.8, y + 0.6, 10, 0.4, 12, False, GRAY)

# S9: 結論
d.slide_summary("結論：不建議採用，維持 ETF + 保單的被動系統", [
    ("❌", "現金流不穩", "權利金無法取代月配息，長期不可預測", RED),
    ("❌", "資金效率低", "100% 保證金鎖死，拖累複利成長", RED),
    ("❌", "尾端風險高", "個股跌幅無底，半導體景氣循環可跌 80%+", RED),
    ("✅", "替代方案", "VT / 006208 分散配置，或小額定期定額 NVDA 現股", GREEN),
    ("✅", "保持簡單", "轉貸→清償→ETF→保單第三站，已經足夠", GREEN),
])

d.save(str(Path(__file__).resolve().parent / "Sell_Put_ELN_評估報告.pptx"))
print("✅ Sell_Put_ELN_評估報告.pptx")
