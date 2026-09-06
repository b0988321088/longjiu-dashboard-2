#!/usr/bin/env python3
"""build_refinance_html.py — 從 大轉向資產配置策略_final.pptx 抽 11 頁內容 → 深色手機友善 HTML。
用法：python build_refinance_html.py（需先跑 build_final.py 產出 pptx）"""
import os
from pptx import Presentation
from pptx.util import Emu

BASE = os.path.dirname(os.path.abspath(__file__))
PPTX = os.path.join(BASE, '大轉向資產配置策略_final.pptx')
OUT = os.path.join(BASE, '大轉向資產配置策略.html')

prs = Presentation(PPTX)

def shape_top_in(sh):
    try:
        return Emu(sh.top).inches if sh.top is not None else 999
    except Exception:
        return 999

slides_html = []
for idx, slide in enumerate(prs.slides, 1):
    shapes = [sh for sh in slide.shapes if sh.has_text_frame and sh.text_frame.text.strip()]
    shapes.sort(key=shape_top_in)
    title, subtitle, body = '', '', []
    for sh in shapes:
        txt = sh.text_frame.text.strip()
        if not txt:
            continue
        top = shape_top_in(sh)
        if top < 1.0:          # 標題（top=0.3）
            title = txt
        elif top < 1.6:        # 副標（top=1.2）
            subtitle = txt
        else:                  # 內容（top=1.9+）
            body.append(txt)
    body_lines = []
    for b in body:
        for ln in b.split('\n'):
            s = ln.strip()
            body_lines.append(s)
    # 過濾純空行（保留單一空行作為段落間距）
    kept = []
    prev_blank = False
    for s in body_lines:
        blank = (s == '')
        if blank and prev_blank:
            continue
        kept.append(s)
        prev_blank = blank
    while kept and kept[-1] == '':
        kept.pop()

    paras = []
    for s in kept:
        if s == '':
            paras.append('<div class="gap"></div>')
        elif s.startswith(('1️⃣','2️⃣','3️⃣','4️⃣','5️⃣')):
            paras.append(f'<p class="act"><span class="act-num">{s[:2]}</span><span>{s[2:].strip()}</span></p>')
        elif s.startswith('🚫'):
            paras.append(f'<p class="no">{s}</p>')
        elif s.startswith(('📉','📈','📊','💵','📡','🔵','💡','⚠️','📋','🔴','🟡','🟢','🏠','💰','🎯','🔥','📅','✅')):
            paras.append(f'<p class="item">{s}</p>')
        else:
            paras.append(f'<p class="sub-item">{s}</p>')

    slides_html.append(f'''
    <section class="slide" id="s{idx}">
        <div class="slide-head">
            <span class="page-num">{idx:02d} / 11</span>
            <h2>{title}</h2>
            {f'<p class="subtitle">{subtitle}</p>' if subtitle else ''}
        </div>
        <div class="slide-body">{''.join(paras)}</div>
    </section>''')

html = f'''<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>大轉向資產配置策略（2026-09-06）</title>
<script src="assets/tailwind.min.js"></script>
<style>
    body {{ background:#0B0D1A; color:#E2E8F0; font-family:system-ui,-apple-system,"Segoe UI","Microsoft JhengHei",sans-serif; }}
    .wrap {{ max-width:880px; margin:0 auto; padding:16px; }}
    header {{ position:sticky; top:0; z-index:10; background:rgba(11,13,26,.92); backdrop-filter:blur(6px);
             border-bottom:1px solid #1E293B; padding:10px 0; }}
    h1 {{ font-size:20px; font-weight:800; color:#fff; margin:0; }}
    .meta {{ font-size:12px; color:#8A8FA0; }}
    .slide {{ background:#111527; border:1px solid #1E293B; border-radius:14px; margin:14px 0; padding:18px; }}
    .slide-head {{ border-bottom:1px solid #232B40; padding-bottom:10px; margin-bottom:12px; }}
    .page-num {{ font-size:11px; color:#F7A01C; font-weight:700; letter-spacing:.08em; }}
    h2 {{ font-size:22px; font-weight:800; color:#fff; margin:4px 0 0; }}
    .subtitle {{ font-size:13px; color:#8A8FA0; margin:6px 0 0; }}
    .item {{ margin:0 0 4px; font-size:15px; line-height:1.65; }}
    .sub-item {{ margin:0 0 4px 22px; font-size:14px; color:#C6CCDA; line-height:1.6; }}
    .gap {{ height:6px; }}
    .act {{ display:flex; gap:10px; margin:0 0 6px; font-size:15px; line-height:1.6; }}
    .act-num {{ color:#F7A01C; font-weight:800; }}
    .no {{ margin:10px 0 0; padding:8px 10px; background:#2A1418; border:1px solid #7F2A32; border-radius:8px;
           color:#FFB4B4; font-size:14px; }}
    nav.toc {{ position:fixed; right:12px; bottom:12px; z-index:20; }}
    nav.toc a {{ display:block; width:34px; height:34px; line-height:34px; text-align:center;
                 background:#1E293B; color:#F7A01C; border-radius:8px; font-size:13px; font-weight:700;
                 margin-top:6px; text-decoration:none; }}
    .dl {{ text-align:center; margin:20px 0; }}
    .dl a {{ display:inline-block; background:#F7A01C; color:#111; font-weight:700; font-size:13px;
             padding:8px 16px; border-radius:8px; text-decoration:none; }}
    footer {{ text-align:center; font-size:11px; color:#5A6072; padding:16px 0 60px; }}
</style>
</head>
<body>
<div class="wrap">
    <header>
        <h1>大轉向資產配置策略</h1>
        <div class="meta">數據基準 2026-09-06 ｜ 台股 9/4 收盤 ｜ 匯率/殖利率 9/5-9/6 ｜ 龍九控股</div>
    </header>

    <div class="dl">
        <a href="大轉向資產配置策略_final.pptx">⬇ 下載簡報檔（pptx，可編輯）</a>
    </div>
{''.join(slides_html)}
    <footer>龍九控股 ｜ 大轉向資產配置策略 v4.1 ｜ 2026-09-06</footer>
</div>
<nav class="toc">
    <a href="#s1">1</a><a href="#s2">2</a><a href="#s3">3</a><a href="#s4">4</a>
    <a href="#s5">5</a><a href="#s6">6</a><a href="#s7">7</a><a href="#s8">8</a>
    <a href="#s9">9</a><a href="#s10">10</a><a href="#s11">11</a>
</nav>
</body>
</html>'''

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'✅ 已產出 {OUT}（{len(slides_html)} 頁）')
