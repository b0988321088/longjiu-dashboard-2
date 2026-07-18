#!/usr/bin/env python3
"""Generate personal loan contract DOCX — Plan B, 300K, 5%, 8/1-12/31."""
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

doc = Document()

for section in doc.sections:
    section.page_height = Inches(11.69)
    section.page_width = Inches(8.27)
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)
    section.left_margin = Inches(0.9)
    section.right_margin = Inches(0.9)


def fmt(run, font_name='標楷體', size=12, bold=False, color=None):
    run.font.name = font_name
    run._element.rPr.rFonts.set(qn('w:eastAsia'), font_name)
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)


def add_article_header(doc, title):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run('■ ' + title)
    fmt(run, size=12, bold=True)
    run.font.color.rgb = RGBColor(0x1A, 0x47, 0x8A)


def add_item(doc, text, style='List Number'):
    p = doc.add_paragraph(text, style=style)
    for run in p.runs:
        fmt(run, size=12)


def add_indent(doc, text):
    p = doc.add_paragraph(text)
    p.paragraph_format.left_indent = Inches(0.5)
    for run in p.runs:
        fmt(run, size=12)


# ===== PAGE 1 =====
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('金錢借貸契約書')
fmt(run, size=22, bold=True)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('（方案B：按月還款、到期一筆清償暨本票擔保版）')
fmt(run, size=11)

doc.add_paragraph()

for party in [
    '貸與人（以下簡稱甲方）：梁世賓',
    '借款人（以下簡稱乙方）：陳宛琳',
]:
    p = doc.add_paragraph()
    run = p.add_run(party)
    fmt(run, size=12)

doc.add_paragraph()

p = doc.add_paragraph()
run = p.add_run('茲因乙方因個人資金週轉需要，向甲方借款，經雙方充分協議，同意條款如下，以資共同遵守：')
fmt(run, size=12)

doc.add_paragraph()
add_article_header(doc, '第一條：借貸明細與交付方式')

for item in [
    '一、借貸總金額：新台幣參拾萬元整（NT$ 300,000）。',
    '二、借貸期限：自民國 115 年 8 月 1 日起，至民國 115 年 12 月 31 日止。',
    '三、交付方式：甲方於契約簽署完成後，將借款匯入乙方指定帳戶。匯款完成即視為交付完畢。',
]:
    add_item(doc, item)

doc.add_paragraph()
add_article_header(doc, '第二條：還款方式與利息計算')

for item in [
    '一、利息計算：雙方約定本借款之年利率為 5%，月利率為 5% ÷ 12，約 0.4167%。',
    '二、按月還款：借款期間內，乙方承諾自民國 115 年 8 月起，於每月 5 日前固定償還新台幣 陸仟元整（NT$ 6,000）予甲方（即 8/5、9/5、10/5、11/5、12/5 共五期）。前開款項應優先沖抵利息，剩餘部分沖抵借款本金。',
    '三、到期清償（年底尾款）：本契約於民國 115 年 12 月 31 日到期，乙方承諾應於當日將未償還之賸餘全額本金新台幣 276,050 元整及最後一期應付利息，共計匯付新台幣 277,032 元整予甲方，一次全額清償結清。',
    '四、甲方指定收款帳戶：',
]:
    add_item(doc, item)

for item in [
    '銀行：________　　分行：________',
    '戶名：________',
    '帳號：________',
]:
    add_indent(doc, item)

doc.add_paragraph()

# 還款明細表
p = doc.add_paragraph()
run = p.add_run('五、還款明細表（基準：8月5日開扣）')
fmt(run, size=12, bold=True)

table = doc.add_table(rows=1, cols=6)
table.style = 'Table Grid'

headers = ['期數', '還款日期', '應付總額 (元)', '當期利息 (5%÷12)', '沖抵本金 (元)', '償還後剩餘本金 (元)']
for i, text in enumerate(headers):
    cell = table.rows[0].cells[i]
    cell.text = text
    for run in cell.paragraphs[0].runs:
        fmt(run, size=11, bold=True)
    cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

rows = [
    ('第 1 期', '115 年 8 月 5 日', 6000, 1250, 4750, 295250),
    ('第 2 期', '115 年 9 月 5 日', 6000, 1230, 4770, 290480),
    ('第 3 期', '115 年 10 月 5 日', 6000, 1210, 4790, 285690),
    ('第 4 期', '115 年 11 月 5 日', 6000, 1190, 4810, 280880),
    ('第 5 期', '115 年 12 月 5 日', 6000, 1170, 4830, 276050),
]

for vals in rows:
    row = table.add_row().cells
    for i, v in enumerate(vals):
        row[i].text = f'{v:,}' if isinstance(v, int) else str(v)
        for run in row[i].paragraphs[0].runs:
            fmt(run, size=11)
        row[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

# Final row
row = table.add_row().cells
final_vals = ['第 6 期', '115 年 12 月 31 日 (到期結清)', 277032, 982, 276050, '0 (結清)']
for i, v in enumerate(final_vals):
    row[i].text = f'{v:,}' if isinstance(v, int) else str(v)
    for run in row[i].paragraphs[0].runs:
        fmt(run, size=11, bold=(i == 0))
    row[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

doc.add_paragraph()

p = doc.add_paragraph()
run = p.add_run('★ 12 月 31 日到期需一筆清償尾款：277,032 元（本金 276,050 + 利息 982）')
fmt(run, size=12, bold=True)
run.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)

doc.add_paragraph()

add_article_header(doc, '第三條：擔保本票約定')

for item in [
    '一、為擔保本筆借款本息之按期清償，乙方同意於簽署本契約之同時，簽發本票乙紙，交付甲方收執。',
    '二、本票記載：面額新台幣 300,000 元整，到期日民國 115 年 12 月 31 日。',
    '三、乙方如依約按期並於到期日全額清償本息完畢，甲方應於清償當日無條件返還本票正本。',
]:
    add_item(doc, item)

doc.add_page_break()

# ===== PAGE 2 =====
add_article_header(doc, '第四條：違約責任與加速條款（保護甲方條款）')

for item in [
    '一、期限利益喪失（加速條款）：乙方如有一期未按時償還，或到期未一次清償剩餘本息，即視為全部到期。甲方得直接依法持本契約及上述擔保本票，向法院聲請本票裁定強制執行，扣押、拍賣乙方名下之財產。',
    '二、違約金：逾期未還期間，除原定利息外，乙方應自逾期之日起，按未償金額每日加計萬分之五之違約金直至完全清償日止。',
]:
    add_item(doc, item)

doc.add_paragraph()
add_article_header(doc, '第五條：管轄法院')

p = doc.add_paragraph('一、因本契約涉訟時，雙方同意以臺灣 ______ 地方法院為第一審管轄法院。')
for run in p.runs:
    fmt(run, size=12)

doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
run = p.add_run('第 2 頁，共 2 頁')
fmt(run, size=10, color=(0x99, 0x99, 0x99))

doc.add_page_break()

# ===== PAGE 3 =====
p = doc.add_paragraph()
run = p.add_run('甲方（貸與人）：梁世賓')
fmt(run, size=12, bold=True)

for f in ['身分證字號：B121674155', '地址：台中市北屯區四平路568巷5號18樓B6', '電話：____________']:
    p = doc.add_paragraph(f)
    for run in p.runs:
        fmt(run, size=12)

p = doc.add_paragraph('（簽名）')
for run in p.runs:
    fmt(run, size=11, color=(0x88, 0x88, 0x88))

p = doc.add_paragraph('────────────────────────────────────────────')
p.paragraph_format.space_before = Pt(12)
p.paragraph_format.space_after = Pt(12)
for run in p.runs:
    fmt(run, size=10, color=(0xCC, 0xCC, 0xCC))

p = doc.add_paragraph()
run = p.add_run('乙方（借款人）：___________________________')
fmt(run, size=12, bold=True)

for f in ['姓名：陳宛琳', '身分證字號：____________', '地址：____________', '電話：____________']:
    p = doc.add_paragraph(f)
    for run in p.runs:
        fmt(run, size=12)

p = doc.add_paragraph('（簽名）')
for run in p.runs:
    fmt(run, size=11, color=(0x88, 0x88, 0x88))

doc.add_paragraph()
doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('中華民國 115 年 7 月 ____ 日')
fmt(run, size=12, bold=True)

doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
run = p.add_run('第 3 頁，共 3 頁')
fmt(run, size=10, color=(0x99, 0x99, 0x99))

out = Path('C:/Users/bot/Desktop/龍九系統/loan_contract_300k_b.docx')
doc.save(str(out))
print(f'✅ saved: {out}')
