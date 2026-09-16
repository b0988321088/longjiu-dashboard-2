#!/usr/bin/env python3
"""儀表板同步檢查（2026-09-01 建立）：產出 index.html 後驗證無舊值/佔位符/月份寫死。
整合進 regenerate_report.py（產出後自動跑）；也可獨立執行：python check_dashboard_sync.py
失敗 exit 1（regenerate 會印警告），全過 exit 0。"""
import datetime
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
html = (BASE / "index.html").read_text(encoding="utf-8")
fails = []

# 1. 佔位符殘留（build_dashboard 未注入）
# 2026-09-16 INC-166 補修：純子字串比對會把「檢討紀錄散文裡提到的佔位符」當成殘留
# （例：工作日誌寫「四個段落全改動態注入（__RISK_FUNDS__/__RISK_RULES__/…）」）→ 每天假警報。
# 只擋「真的留在語法位置」的：①佔位符清單 run（A__/__B__/__C__）②前後緊鄰中日韓字元＝散文。
_PH = r"__[A-Z_]+__"
_CJK = re.compile(r"[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]")


def _is_prose_list(m):
    """佔位符被 / 、 , 串成一串（多半是散文列舉）"""
    return bool(re.match(rf"(?:{_PH}\s*[/、,]\s*)+{_PH}", m.group(0))) and "/" in m.group(0)


def _adjacent_cjk(s, i, j):
    return bool((i > 0 and _CJK.match(s[i - 1])) or (j < len(s) and _CJK.match(s[j])))


_prose_spans = [m.span() for m in re.finditer(rf"(?:{_PH}\s*[/、,]\s*){{2,}}{_PH}", html)]
_bad = []
for m in re.finditer(_PH, html):
    if any(a <= m.start() and m.end() <= b for a, b in _prose_spans):
        continue
    if _adjacent_cjk(html, m.start(), m.end()):
        continue
    _bad.append(m.group(0))
phs = sorted(set(_bad))
if phs:
    fails.append(f"佔位符殘留: {phs}")

# 2. JS 月份寫死（讀 dividend_records/rent_received 的 key 寫死某月）
if re.search(r"\['2026-0\d'\]", html):
    fails.append("JS 月份寫死 (['2026-0X'] 殘留)")

# 3. 已知舊值殘留（非 data-k fallback 的裸舊值 = build 沒跑或 rep 漏）
#    2026-09-16（INC-208）：排除**審查者原文引用**，避免固定誤報（例：審查者「現況錨點」寫
#    「可動用 772,607」命中此清單 → 每次重產都 ❌，誤報會蓋掉真問題）。
#    精準切法（INC-208b，取代第一版「切到檔尾」）：只排除
#      (a) panel-6 區段（CIO 戰略審查頁，78908..</main>）
#      (b) <script> 區塊（JS 內嵌同一份引用文字）
#    → footer／再平衡備忘等 build 產出的區塊仍照掃，不犧牲覆蓋率。
_p6 = html.find('id="panel-6"')
_m2 = html.find("</main>")
_scan = html if (_p6 < 0 or _m2 <= _p6) else (html[:_p6] + html[_m2:])
_scan = re.sub(r"<script\b.*?</script>", "", _scan, flags=re.S | re.I)
OLD = [
    "753,388", "138,627", "102,469", "123,607", "243,434",
    "225,918", "799,612", "20260829", "20260821_1", "772,607",
    "08月現金流入", "系統時間：2026-08",
]
for v in OLD:
    for m in re.finditer(re.escape(v), _scan):
        ctx = _scan[max(0, m.start() - 80):m.start() + 80]
        if "data-k=" in ctx or "/*" in ctx or "--" in ctx:
            continue  # data-k fallback / 註解可接受
        fails.append(f"舊值殘留: {v} @ {m.start()}")
        break

# 4. 月度流入標題 = 當月
_ym = datetime.date.today().strftime("%Y-%m")
if f"{int(_ym[5:])}月現金流入檢對核實" not in html:
    fails.append("月度流入標題非當月")

# 5. 戰略區塊已注入（健康度/雷達/交易計畫/P0）
for kw in ["龍九健康度", "雷達更新", "本週交易計畫（動態）", "P0 戰略任務"]:
    if kw not in html:
        fails.append(f"戰略區塊缺失: {kw}")

# 6. 系統時間 JS 動態（非寫死日期）
if "sys-date" not in html:
    fails.append("系統時間非 JS 動態")

# 7. 分頁結構（2026-09-01 血淚：改 template 少閉合 → 全分頁失效 → 必驗）
for i in range(1, 7):
    if f'id="tab-r{i}"' not in html:
        fails.append(f"radio tab-r{i} 缺失")
    if f'id="panel-{i}"' not in html:
        fails.append(f"panel-{i} 缺失")
    if f"#tab-r{i}:checked ~ main #panel-{i}" not in html:
        fails.append(f"CSS 切換規則 tab-r{i} 缺失")
if not (0 < html.find('id="tab-r1"') < html.find("<main")):
    fails.append("radio 不在 main 前（CSS ~ 選擇器失效）")
_p4, _p5, _p6, _m2 = html.find('id="panel-4"'), html.find('id="panel-5"'), html.find('id="panel-6"'), html.find("</main>")
if not (0 < _m2 and _p4 > 0 and _p5 > 0 and _p6 > 0 and _p4 < _m2 and _p5 < _m2 and _p6 < _m2):
    fails.append("panel-4/5/6 不在 main 內（分頁打不開）")

# 8. 收入核對清單兩段制（2026-09-01：✅已收 + ⏳待收 + 各自合計）
if "✅ 已收（" not in html:
    fails.append("收入清單缺「✅ 已收（合計）」段")
if "⏳ 待收（" not in html:
    fails.append("收入清單缺「⏳ 待收（合計）」段")

# 9. 穿透卡非載入中（2026-09-01：build 靜態渲染，不依賴 JS）
_i_pen = html.find('id="pen-card"')
if _i_pen < 0 or "資產穿透" not in html[_i_pen:_i_pen + 300]:
    fails.append("穿透卡未靜態渲染（資產穿透缺失）")

# 10. 債物流出含沙鹿（2026-09-01：snapshot debt_schedule）
try:
    _snap_now = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    if not any("沙鹿" in str(d.get("項目", "")) for d in _snap_now.get("debt_schedule", [])):
        fails.append("debt_schedule 缺沙鹿租屋")
except Exception:
    pass

if fails:
    print("❌ 儀表板同步檢查失敗:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("✅ 儀表板同步檢查全過（無佔位符 / 月份寫死 / 舊值，戰略區塊已注入）")
