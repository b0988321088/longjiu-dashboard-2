"""轉貸投資簡報產生器"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.enum.chart import XL_CHART_TYPE
from pptx.dml.color import RGBColor
from pptx.chart.data import CategoryChartData

prs = Presentation()
prs.slide_width = Inches(13.33)
prs.slide_height = Inches(7.5)

BG_DARK = RGBColor(0x1A, 0x1A, 0x2E)
BG_CARD = RGBColor(0x16, 0x21, 0x3E)
ACCENT = RGBColor(0xF5, 0x9E, 0x0B)
GREEN = RGBColor(0x10, 0xB9, 0x81)
RED = RGBColor(0xEF, 0x44, 0x44)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GRAY = RGBColor(0x71, 0x80, 0x96)

def bg(slide):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = BG_DARK

def txt(slide, text, left, top, width, height, size=14, bold=False, color=WHITE):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tb.text_frame.word_wrap = True
    p = tb.text_frame.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.color.rgb = color

def card(slide, left, top, width, height):
    s = slide.shapes.add_shape(1, Inches(left), Inches(top), Inches(width), Inches(height))
    s.fill.solid(); s.fill.fore_color.rgb = BG_CARD
    s.line.fill.background()

# === 封面 ===
sl = prs.slides.add_slide(prs.slide_layouts[6]); bg(sl)
txt(sl, '龍九控股', 1, 1.5, 5, 1, 20, False, GRAY)
txt(sl, '轉貸投資可行性評估計劃', 1, 2.2, 10, 1.5, 40, True)
txt(sl, '以低利資金 2.185% 優化負債結構・提升被動現金流', 1, 3.8, 10, 0.8, 18, False, GRAY)
txt(sl, '2026-07-26 ｜ 評估期間：2026 Q3~Q4', 1, 5, 8, 0.5, 14, False, GRAY)

# === 資產負債結構 ===
sl = prs.slides.add_slide(prs.slide_layouts[6]); bg(sl)
txt(sl, '現有資產負債結構 ｜ 負債率 41.8%', 0.5, 0.3, 8, 0.8, 28, True)
cd = CategoryChartData()
cd.categories = ['不動產 33.3M','保單 9.8M','證券 2.5M','現金 3.3M','基金 0.8M']
cd.add_series('資產', (33.3, 9.8, 2.5, 3.3, 0.8))
sl.shapes.add_chart(XL_CHART_TYPE.PIE, Inches(0.5), Inches(1.5), Inches(5.5), Inches(4.5), cd)
cd2 = CategoryChartData()
cd2.categories = ['房貸 13.2M','理財型 3.0M','保單借貸 4.0M','質押 1.0M']
cd2.add_series('負債', (13.2, 3.0, 4.0, 1.0))
sl.shapes.add_chart(XL_CHART_TYPE.PIE, Inches(6.5), Inches(1.5), Inches(5.5), Inches(4.5), cd2)
txt(sl, '總資產：50,689,930 TWD', 0.5, 6.3, 5, 0.4, 14, False, GREEN)
txt(sl, '總負債：21,165,869 TWD', 6.5, 6.3, 5, 0.4, 14, False, RED)

# === 每月收支 ===
sl = prs.slides.add_slide(prs.slide_layouts[6]); bg(sl)
txt(sl, '每月收支分析 ｜ 月缺口 -4,099 ⚠️', 0.5, 0.3, 8, 0.8, 28, True)
cd3 = CategoryChartData()
cd3.categories = ['薪資','房租','保單配息','股息','基金']
cd3.add_series('收入(K)', (43.1, 80.1, 73.0, 10.0, 0.6))
sl.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.5), Inches(1.5), Inches(5.5), Inches(4.5), cd3)
cd4 = CategoryChartData()
cd4.categories = ['房貸','理財利息','保單利息','信用卡','生活','質押']
cd4.add_series('支出(K)', (99.5, 10.0, 16.0, 38.0, 45.0, 2.5))
sl.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(6.5), Inches(1.5), Inches(5.5), Inches(4.5), cd4)

# === 轉貸方案 ===
sl = prs.slides.add_slide(prs.slide_layouts[6]); bg(sl)
txt(sl, '轉貸方案比較 ｜ 推薦：築巢優利貸 2.185%', 0.5, 0.3, 10, 0.8, 28, True)
cd5 = CategoryChartData()
cd5.categories = ['現狀 2.5%','國泰 2.6%','築巢 2.185%']
cd5.add_series('月付(K)', (99.5, 52.5, 49.8))
sl.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.5), Inches(1.5), Inches(5.5), Inches(4.5), cd5)
card(sl, 7, 1.5, 5.5, 5)
txt(sl, '推薦原因', 7.3, 1.7, 4, 0.5, 20, True, ACCENT)
txt(sl, '✅ 公務員專案，資格符合', 7.3, 2.5, 5, 0.4, 14, False, GREEN)
txt(sl, '✅ 月省房貸 49,658（vs 現狀）', 7.3, 3.1, 5, 0.4, 14, False, GREEN)
txt(sl, '✅ 資金可清償 4M 保單借貸', 7.3, 3.7, 5, 0.4, 14, False, GREEN)
txt(sl, '✅ 清償後月省利息 16,000', 7.3, 4.3, 5, 0.4, 14, False, GREEN)
txt(sl, '⚠️ 9/25 前須完成', 7.3, 5.1, 5, 0.4, 14, False, ACCENT)

# === 三階段 ===
sl = prs.slides.add_slide(prs.slide_layouts[6]); bg(sl)
txt(sl, '三階段資金部署計劃', 0.5, 0.3, 8, 0.8, 28, True)
phases = [
    ('第一階段：清償高利負債', '安聯A 2M + 安聯B 1M + 第一金 1M = 4,000,000\n月省利息 16,000 ｜ 配息實收 73K→89K', GREEN),
    ('第二階段：建立安全網', '保留理財型額度 3M（備而不用）\n補足星展備用金至 100K（6個月生活費）', ACCENT),
    ('第三階段：低利擴張投資', '00983D 每月10張→100張\n00919/00878 補張數\n保單第三站 PIMCO+AI+A10 400萬', ACCENT),
]
for i, (title, desc, color) in enumerate(phases):
    y = 1.5 + i * 1.8
    card(sl, 0.5, y, 12, 1.5)
    txt(sl, title, 1, y + 0.1, 10, 0.5, 20, True, color)
    for j, line in enumerate(desc.split('\n')):
        txt(sl, line, 1, y + 0.7 + j * 0.4, 11, 0.4, 14)

# === 時間表 ===
sl = prs.slides.add_slide(prs.slide_layouts[6]); bg(sl)
txt(sl, '執行時間表', 0.5, 0.3, 6, 0.8, 28, True)
timeline = [
    ('7/17 ✅', '國泰轉貸面簽/對保', GREEN),
    ('8~9月', '逐月買入 ETF + 補張數', GRAY),
    ('9/25 🔴', '永豐房貸到期', RED),
    ('9月底', '國泰轉貸撥款', ACCENT),
    ('10/1', '辦理築巢優利貸 2.185%', ACCENT),
    ('10~12月', 'ETF/保單第三站佈局', GRAY),
    ('12月底', '全年檢視', GRAY),
]
for i, (date, event, color) in enumerate(timeline):
    y = 1.5 + i * 0.75
    card(sl, 0.5, y, 12, 0.6)
    txt(sl, date, 0.8, y + 0.1, 2.5, 0.4, 14, True, ACCENT)
    txt(sl, event, 3.5, y + 0.1, 7, 0.4, 14, False, color)

# === 成效 ===
sl = prs.slides.add_slide(prs.slide_layouts[6]); bg(sl)
txt(sl, '預期成效對照', 0.5, 0.3, 6, 0.8, 28, True)
cd6 = CategoryChartData()
cd6.categories = ['轉貸前','轉貸後']
cd6.add_series('月收入(K)', (206.9, 247.6))
cd6.add_series('月支出(K)', (211.0, 145.3))
sl.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.5), Inches(1.5), Inches(6), Inches(4.5), cd6)
card(sl, 7, 1.5, 5.5, 5)
txt(sl, '改善摘要', 7.3, 1.7, 4, 0.5, 18, True, ACCENT)
items = [
    '負債率：41.8% → ~35%',
    '房貸月付：99,458 → 49,800',
    '保單利息：16,000 → 0',
    '月配息實收：73,000 → 106,500',
]
for i, item in enumerate(items):
    txt(sl, '📈 ' + item, 7.3, 2.5 + i * 0.5, 5, 0.4, 14, False, GREEN)
txt(sl, '月淨現金流', 7.3, 4.8, 5, 0.4, 16, True)
txt(sl, '-4,099 → +102,259', 7.3, 5.3, 5, 0.6, 28, True, GREEN)

prs.save('C:/Users/bot/Desktop/longjiu_system/轉貸投資簡報.pptx')
print('✅ 轉貸投資簡報.pptx')
