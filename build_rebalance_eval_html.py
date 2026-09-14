# -*- coding: utf-8 -*-
"""build_rebalance_eval_html.py — 再平衡評估（全源整合）md → 手機可讀 HTML（2026-09-14）

背景：`rebalance_summary_{date}.md` 由 build_rebalance_dashboard.py 每日產出，但主儀表板
「📌 再平衡評估」按鈕是 glob `rebalance_eval_*.html` — 而這支 HTML **沒有任何產生器**
（最後一份停在 2026-09-05，靠人工/舊流程產出）→ 按鈕永遠指向舊檔。
本腳本補上產生器：md 是唯一真值來源（single source），HTML 每次重生成。

用法：
  python build_rebalance_eval_html.py            # 用今日 rebalance_summary_{today}.md
  python build_rebalance_eval_html.py 2026-09-14 # 指定日期
輸出：rebalance_eval_{date}.html（深色、手機優先、表格可橫向捲動）
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).parent.resolve()

CSS = """
:root{--bg:#0b1220;--card:#111c33;--line:#1e293b;--txt:#e2e8f0;--sub:#94a3b8;--acc:#38bdf8}
*{box-sizing:border-box}
body{font-family:-apple-system,'Segoe UI','Noto Sans TC','Microsoft JhengHei',sans-serif;
     background:var(--bg);color:var(--txt);margin:0;padding:18px;line-height:1.75;font-size:15px}
.wrap{max-width:940px;margin:0 auto}
h1{font-size:20px;margin:0 0 6px;color:#f1f5f9}
h2{font-size:17px;margin:22px 0 8px;padding-left:10px;border-left:3px solid var(--acc);color:#e2e8f0}
h3{font-size:15px;margin:16px 0 6px;color:#cbd5e1}
p{margin:8px 0}
blockquote{margin:10px 0;padding:10px 12px;background:var(--card);border-left:3px solid var(--acc);
           border-radius:8px;color:var(--sub);font-size:13px}
ul{margin:8px 0;padding-left:20px}
li{margin:5px 0}
hr{border:none;border-top:1px solid var(--line);margin:18px 0}
strong{color:#f8fafc}
code{background:#1e293b;padding:1px 5px;border-radius:4px;font-size:13px}
.tw{overflow-x:auto;margin:10px 0;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;min-width:520px;font-size:13.5px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:#152player;color:#94a3b8;font-weight:700;white-space:nowrap}
tbody tr:nth-child(even){background:rgba(255,255,255,.02)}
a{color:var(--acc)}
.foot{margin-top:26px;color:#475569;font-size:11.5px;line-height:1.7}
""".replace("#152player", "#152238")

try:
    import markdown  # noqa
    _HAS_MD = True
except Exception:
    _HAS_MD = False


def md_to_html(md_text: str) -> str:
    if _HAS_MD:
        return markdown.markdown(md_text, extensions=["tables", "sane_lists", "nl2br"])
    # fallback：極簡轉換（無套件時仍可交付）
    out, in_tbl = [], False
    for raw in md_text.splitlines():
        line = raw.rstrip()
        if re.match(r"^\|", line):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            tag = "th" if not in_tbl else "td"
            in_tbl = True
            out.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_tbl:
            out.append("</table></div>")
            in_tbl = False
        if line.startswith("### "):
            out.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("> "):
            out.append(f"<blockquote>{line[2:]}</blockquote>")
        elif line.startswith("- "):
            out.append(f"<li>{line[2:]}</li>")
        elif not line:
            out.append("")
        else:
            out.append(f"<p>{line}</p>")
    if in_tbl:
        out.append("</table></div>")
    html = "\n".join(out)
    html = re.sub(r"</li>\s*<li>", "</li><li>", html)
    html = html.replace("<li>", '<ul><li>', 1)
    return html


def build(day: str | None = None) -> Path | None:
    day = day or date.today().isoformat()
    src = BASE / f"rebalance_summary_{day}.md"
    if not src.exists():
        print(f"⚠️ 找不到 {src.name} → 不產出（按鈕 fallback 由 build_dashboard 處理）")
        return None
    md_text = src.read_text(encoding="utf-8")
    body = md_to_html(md_text)
    body = re.sub(r"<table>", '<div class="tw"><table>', body)
    body = re.sub(r"</table>", "</table></div>", body)
    title = f"龍九再平衡評估（全源整合版）{day}"
    html = f"""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title><style>{CSS}</style></head><body><div class="wrap">
{body}
<div class="foot">資料源：{src.name}（唯一真值）｜由 build_rebalance_eval_html.py 於 {datetime.now():%Y-%m-%d %H:%M} 產生
｜規則權威：rebalance-monitoring-sop 技能｜本頁為評估建議，不自動下單。</div>
</div></body></html>"""
    out = BASE / f"rebalance_eval_{day}.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ 已輸出 {out.name}（{len(html):,} bytes｜來源 {src.name}｜markdown={'yes' if _HAS_MD else 'fallback'}）")
    return out


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
