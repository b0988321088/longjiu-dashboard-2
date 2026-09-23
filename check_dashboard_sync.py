#!/usr/bin/env python3
"""儀表板同步檢查（2026-09-01 建立）：產出 index.html 後驗證無舊值/佔位符/月份寫死。
整合進 regenerate_report.py（產出後自動跑）；也可獨立執行：
  python check_dashboard_sync.py              # 預設：靜態檢查（含連結『本機存在＋已版控』）
  python check_dashboard_sync.py --post-push  # 推送後：index.html 全部本機連結驗線上 Pages 200
失敗 exit 1（regenerate 會印警告），全過 exit 0。

2026-09-23（INC-240）兩段制：第 12 條「未進版控」在 commit 前必然成立（今天的檔還沒 commit）
→ 晨間班會自我誤報。故 commit 前用環境變數 LJ_PREPUSH=1（regenerate 的 9c2/9c3 呼叫）只驗
本機存在、未版控者列 ℹ️；真正的「連結指向沒上線的檔 → Pages 404」改由推送後 --post-push 驗。"""
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
POST_PUSH = "--post-push" in sys.argv
PREPUSH = os.environ.get("LJ_PREPUSH") == "1"
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

# 11. 「重要連結」區的每個佔位符都必須存在於 links_config.py（單一來源）
#     2026-09-22 改版：原本是「兩份清單跨檔一致性」檢查（update_dashboard_links._LINK_PATTERNS
#     ↔ build_dashboard._link_map）。現在兩者都從 links_config 生成 → 不變式簡化為
#     「模板用到的佔位符，設定表裡一定要有」，否則 build_dashboard 注入不到 → 按鈕壞掉／佔位符殘留。
_PREFIX_EXEMPT = set()
try:
    import sys as _sys2
    _sys2.path.insert(0, str(BASE))
    import links_config as _links_cfg
    _tpl = (BASE / "index_template.html").read_text(encoding="utf-8")
    _s = _tpl.find("<!-- 🔗 重要連結")
    _e = _tpl.find("<!-- 🚨", _s) if _s != -1 else -1
    if _s == -1 or _e == -1:
        fails.append("找不到 index_template.html 的「重要連結」區塊（區塊註解被改動？）")
    else:
        _phs = set(re.findall(r"__[A-Z_]+__", _tpl[_s:_e]))
        _known = _links_cfg.all_placeholder_keys()
        _miss = sorted(_phs - _known)
        if _miss:
            fails.append("重要連結區有佔位符未納入 links_config（不會被注入／會殘留，按鈕會壞）: "
                         + ", ".join(_miss))
        _orphan = sorted(_known - _phs)
        if _orphan:
            print(f"  ℹ️ links_config 有 {len(_orphan)} 個佔位符模板未使用（非故障）: " + ", ".join(_orphan))
        # 2026-09-22 審查補強：佔位符的前綴必須都能在 PREFIX_RULES 查到副檔名，
        # 否則 build_link_map 會 raise（或舊版會靜默回退成 .html → .md/.png 連結靜默壞掉）
        _p_missing = sorted({p for p in _links_cfg.PLACEHOLDER_PREFIX.values()
                             if p not in _links_cfg.PREFIX_RULES})
        if _p_missing:
            fails.append("links_config: PLACEHOLDER_PREFIX 的前綴未定義於 PREFIX_RULES"
                         "（glob 會錯、連結會壞）: " + ", ".join(_p_missing))
except Exception as _e:
    fails.append(f"連結設定一致性檢查無法執行: {_e}")

# 12. 連結可達性（2026-09-22 實踩：連結刷新後指向今天的新檔，但該檔未進版控 → Pages 404）
#     條件：①本機存在 ②在 git HEAD 樹中（未追蹤＝push 不會帶上去＝線上 404）
#     2026-09-23（INC-240）：②只在「非 commit 前」成立 —— LJ_PREPUSH=1 時今天的檔必然還沒 commit，
#     拿它當失敗＝每天自我誤報；此時只驗①，未版控者改成 ℹ️ 待本次 commit（真 404 由 --post-push 驗）。
_pending_untracked = []
try:
    _tracked = set(subprocess.run(["git", "ls-files"], cwd=str(BASE), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace").stdout.split())
    _rel = {u for u in re.findall(r'href="([^"]+)"', html)
            if not u.startswith(("http", "#", "mailto")) and "/" not in u}
    for _u in sorted(_rel):
        if not (BASE / _u).exists():
            fails.append(f"連結目標本機不存在: {_u}")
        elif _u not in _tracked and not PREPUSH:
            fails.append(f"連結目標未進版控（Pages 會 404）: {_u}")
        elif _u not in _tracked:
            _pending_untracked.append(_u)
    if _pending_untracked:
        print(f"  ℹ️ 待本次 commit 進版控 {len(_pending_untracked)} 檔（commit 前必然狀態，非故障；"
              f"上線後由 --post-push 驗線上 200）")
except Exception as _e:
    fails.append(f"連結可達性檢查無法執行: {_e}")

# 14. 房租待收口徑（2026-09-23 INC-241）
#     實踩：逐項待收用「常態 rent_breakdown」比對實收 → 一次性折讓（2026-09 洲際W 維修費 3,000）
#     變成幽靈待收 26,100（真值 23,100），差異分析還宣告「全數實收」（當月只收到 54,000）。
#     閘門：儀表板 ⏳ 待收清單內「房租」類項目的合計必須 == snapshot.rent_monthly_gap；
#     且 gap>0 時不得出現「全數實收」字樣。
try:
    _snap14 = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    _gap14 = float(_snap14.get("rent_monthly_gap") or 0)
    _pend14 = 0.0
    for _m14 in re.finditer(
            r"⏳ 待收</span><span class=\"text-slate-300\">([^<]+)</span></div><span[^>]*>([\d,]+) TWD", html):
        if "房租" in _m14.group(1):
            _pend14 += float(_m14.group(2).replace(",", ""))
    if abs(_pend14 - _gap14) > 0.5:
        fails.append(f"房租待收合計 {_pend14:,.0f} ≠ snapshot.rent_monthly_gap {_gap14:,.0f}"
                     f"（逐項應收須用 rent_receivable_by_month 當月口徑，勿用常態 rent_breakdown）")
    if _gap14 > 0 and "全數實收" in html:
        fails.append("房租尚有未收（rent_monthly_gap>0）卻出現「全數實收」字樣")
except Exception as _e14:
    fails.append(f"房租待收口徑檢查無法執行: {_e14}")

# 15. 日報房租待收口徑（2026-09-23 INC-241b）
#     日報「房租金流」段落由 scripts/components/report_utils._fmt_rent_status 產生；
#     原本拿常態 80,100 相減 → 一次性折讓（2026-09 洲際W 3,000）變幽靈待收（26,100 vs 23,100）。
#     閘門：若有當日日報，「｜待收 N」必須等於 snapshot.rent_monthly_gap。
try:
    _dr15 = BASE / f"daily_report_v2_{datetime.date.today().isoformat()}.html"
    if _dr15.exists():
        _txt15 = _dr15.read_text(encoding="utf-8")
        _gap15 = float(json.loads((BASE / "snapshot.json").read_text(encoding="utf-8")).get("rent_monthly_gap") or 0)
        _ms15 = re.findall(r"｜待收 ([\d,]+)", _txt15)
        _bad15 = sorted({m for m in _ms15 if abs(float(m.replace(",", "")) - _gap15) > 0.5})
        if _bad15:
            fails.append(f"日報房租待收 {'/'.join(_bad15)} ≠ snapshot.rent_monthly_gap {_gap15:,.0f}")
        elif not _ms15:
            fails.append("日報找不到「｜待收 N」房租待收字樣（_fmt_rent_status 輸出格式變了？）")
except Exception as _e15:
    fails.append(f"日報房租待收口徑檢查無法執行: {_e15}")

# 13. --post-push：推送後對「線上 Pages」逐連結驗 200（2026-09-23 INC-240 新增）
#     為什麼要拆出來：第 12 條的「未進版控」只能判斷 commit 前的狀態，而 commit 前今天的檔必然
#     還沒進版控 → 晨間班每天自我誤報。真風險（連結指向沒上線／被 push 漏掉的檔 ＝ 線上 404）
#     只有推送後才驗得準。原本只驗 4 個檔（日報/差異/index/穿透），現在驗 index.html 全部連結。
#     ⚠️ 2026-09-23 CIO 審查 REJECT 後的修正（INC-240 補記）：
#       ①網路異常（ERR）原本只印警告、不進 fails → 22 條全 ERR 也會印「✅ 全過（22 條 200）」＋rc=0
#         ＝假成功（正是本顆要消滅的病徵）。現在：ERR 與「總預算用盡未驗」都算失敗 → rc≠0。
#       ②成功訊息原本用 len(_links)（連結數）冒充已驗證數 → 改印實得 200 的條數。
#       ③總預算由 420s 收到 240s 且**硬停**（逾時後剩下的連結不再嘗試，直接算未驗），
#         最壞 ≈240s＋最後一條的 10s，不再有 ~630s 的長尾打爆 emergency_1330.py 的 300s 呼叫端。
import time as _t13
import urllib.error as _ue13
import urllib.request as _ur13

_POSTPUSH_BUDGET = int(os.environ.get("LJ_POSTPUSH_BUDGET", "240"))  # 秒；測試可用環境變數縮短
if POST_PUSH:
    _t0 = _t13.time()
    _BASE_URL = "https://b0988321088.github.io/longjiu-dashboard-2"
    _links = sorted({u for u in re.findall(r'href="([^"]+)"', html)
                     if not u.startswith(("http", "#", "mailto")) and "/" not in u})
    _deadline = _t0 + _POSTPUSH_BUDGET
    _bad_codes, _unknown, _skipped = [], [], []
    _n200 = 0
    for _u in _links:
        if _t13.time() > _deadline:
            _skipped.append(_u)  # 硬停：逾時後不再嘗試（未驗證 ≠ 通過）
            continue
        _code = "ERR"
        for _try in range(4):
            try:
                _rq = _ur13.Request(f"{_BASE_URL}/{_u}", headers={"User-Agent": "longjiu-postpush"})
                with _ur13.urlopen(_rq, timeout=10) as _rs:
                    _code = str(_rs.status)
            except _ue13.HTTPError as _he:
                _code = str(_he.code)
            except Exception:
                _code = "ERR"
            if _code == "200" or _t13.time() > _deadline:
                break
            _t13.sleep(20)
        _mark = "✅" if _code == "200" else ("⚠️" if _code == "ERR" else "❌")
        print(f"  {_mark} 線上 {_u} → {_code}")
        if _code == "200":
            _n200 += 1
        elif _code == "ERR":
            _unknown.append(_u)
        else:
            _bad_codes.append(f"{_u} → {_code}")
    if _unknown:
        print(f"  ⚠️ 線上無法判定 {len(_unknown)} 條（網路異常，非 404）: " + ", ".join(_unknown[:8]))
        fails.append(f"線上連結無法判定（網路異常，非 404）{len(_unknown)} 條（未驗證不視為通過）: "
                     + ", ".join(_unknown[:8]))
    if _skipped:
        print(f"  ⚠️ 總預算 {_POSTPUSH_BUDGET}s 用盡，{len(_skipped)} 條未驗")
        fails.append(f"線上連結未驗（總預算 {_POSTPUSH_BUDGET}s 用盡）{len(_skipped)} 條: "
                     + ", ".join(_skipped[:8]))
    if _bad_codes:
        fails.append(f"線上連結非 200（Pages 404/未上線）{len(_bad_codes)} 個: " + ", ".join(_bad_codes[:8]))
    _elapsed = int(_t13.time() - _t0)

if fails:
    print("❌ 儀表板同步檢查失敗:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
if POST_PUSH:
    print(f"✅ 線上連結驗證全過（實得 {_n200}/{len(_links)} 條 200，耗時 {_elapsed}s）"
          f"＋ 靜態檢查全過（無佔位符 / 月份寫死 / 舊值）")
else:
    print("✅ 儀表板同步檢查全過（無佔位符 / 月份寫死 / 舊值，戰略區塊已注入）")
