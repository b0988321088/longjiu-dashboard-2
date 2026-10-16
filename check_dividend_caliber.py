"""配息口徑守門（2026-09-28 翻新為「全相對式 ＋ 指當日產物」）

只讀，不改任何檔案。PASS/FAIL 逐項列出，exit 0 = 全過。
用途：改動 build_retirement_plan / build_dashboard / asset_diff_monitor / build_investment_performance
或配息資料後，commit 前先跑：`python check_dividend_caliber.py`。

翻新原則（2026-09-28）——本檔不得再出現任何「當期」真值字面值：
  ① 期望值一律由 snapshot ＋ passive_caliber ＋ dividend_caliber 現算；檔名不寫死日期。
     舊版釘死「某一天的凍結稽核產物」與那一期的數字 → 該檔一封存、或真值一動就整檔爆紅。
  ② 逐日產物一律取「最新一份」＋新鮮度守門：產物比 snapshot.json 舊 → 記 SKIP 警語，不記 FAIL
     （避免產生與程式改動無關的假紅燈）。
  ③ 只有兩類可以寫死：已結算月份（歷史不再變動）、「已修掉的錯誤值」封鎖清單（不得回歸）。
  ④ 寫死掃描以 AST 常數為準（字串＋數值），不掃註解：註解不會讓頁面說錯話，
     用純文字比對掃註解只會製造假紅燈（舊版 4 個既有 FAIL 之一就是這樣來的）。
  ⑤ 已知界線：同一數字在同一頁重複多次時，只驗「存在 ＋ 成對」，不驗每處出現次數
     （單處被手改成別的數字不會被本檔抓到；跨頁一致性另由 tools/verify_ficriteria.py 守）。
"""
import ast
import glob
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent   # 需與 snapshot.json 同目錄執行
PY = BASE / "build_retirement_plan.py"
SNAP = BASE / "snapshot.json"
RULE = BASE / "DAILY_REPORT_PIPELINE_RULE.md"
CTX = BASE / "notion_shared_context.md"
IDX = BASE / "index.html"

sys.path.insert(0, str(BASE))
import passive_caliber as PC          # noqa: E402  情境口徑單一來源
import dividend_caliber as DC         # noqa: E402  分桶口徑正典
import build_dashboard as BD          # noqa: E402  儀表板分桶器（實跑驗證）
import build_investment_performance as BIP   # noqa: E402  投資績效分桶器（實跑驗證）

checks = []
def ck(name, ok, detail=""):
    checks.append((name, bool(ok), detail))

_SKIPS = 0

def skip(msg):
    """SKIP 一律顯性化：逐日產物未按當期真值重產時，該族斷言不計入分母（但必須看得見）。"""
    global _SKIPS
    _SKIPS += 1
    print("⏭️  SKIP " + msg)

def text_of(html):
    """去標籤／去 script／壓縮空白，供文字層斷言"""
    t = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t)

def has(hay, needle):
    """帶邊界比對：避免 '92.2' 命中 '192.2'（CIO 2026-09-28 建議）"""
    return re.search(rf"(?<![\d.]){re.escape(needle)}(?![\d])", hay) is not None

def latest(pattern):
    """取最新一份逐日產物（不寫死日期）"""
    hits = sorted(glob.glob(str(BASE / pattern)))
    return Path(hits[-1]) if hits else None

def fresh(p, ref=None):
    """新鮮度守門：檔名日期＝資料日（逐日產物命名慣例）或 mtime 不早於參考檔，即視為新鮮；
    兩者皆不成立 → 未按當期真值重產（同一跑批中 snapshot 常最後寫，純比 mtime 會永遠誤判）"""
    ref = ref or SNAP
    if SNAP_DATE and SNAP_DATE in p.name:
        return True
    return p.stat().st_mtime + 60 >= ref.stat().st_mtime

def daily_page(pattern, label, mtime_ref=None):
    """回傳 (最新逐日產物文字, 是否新鮮)；找不到／不新鮮時印 SKIP 警語"""
    p = latest(pattern)
    if not p:
        ck(f"{label}存在", False, f"無 {pattern}")
        return None, False
    if not fresh(p, mtime_ref):
        ref = (mtime_ref or SNAP).name
        skip(f"{label}斷言（{p.name} 比 {ref} 舊 → 待重產後再驗）")
        return None, False
    return text_of(p.read_text(encoding="utf-8")), True

snap = json.loads(SNAP.read_text(encoding="utf-8"))
SNAP_DATE = str(snap.get("date", ""))
SC = PC.scenarios(snap)
src = PY.read_text(encoding="utf-8")

# 已修掉的錯誤值／退役口徑：不得回歸（第一類可寫死）
RETIRED = ("正常 ≥150%", "距 A 級缺口", "30,552", "131,439", "244,172", "保守配息：")
# 舊重複計數（7 月配息把 ETF 11,719 併入基金又另列 ETF）；已結算月歷史值，不得回歸
RETIRED_DUP = 22459

# ── 當期真值 token（由 snapshot ＋ passive_caliber 現算，不寫死）──────────────
_thr = (snap.get("thresholds_2026_0915") or {}).get("現金_twd") or {}
_tok = {f"{float(_thr.get('合計底線') or 0):,.0f}"}                     # 政策值也算當期真值
for _k in ("con", "act", "stress", "extreme"):
    _tok.add(f"{SC[_k]['coverage']:.1f}")
    _tok.add(f"{SC[_k]['income']:,.0f}")
    _tok.add(f"{abs(SC[_k]['surplus']):,.0f}")
for _k in ("div_con", "div_norm", "div_act", "rent_norm", "rent_act", "expense", "cash", "vacancy"):
    _tok.add(f"{SC[_k]:,.0f}")
# 只留「格式化後不會誤撞」的 token：含千分位，或小數點且長度 ≥5（避開 100／540 這類純整數常數）
_tok = {t for t in _tok if ("," in t) or ("." in t and len(t) >= 5)}
# 房貸月付合計（現算自 snapshot.mortgage_monthly_total）亦屬當期真值 → 不得寫死
_MORTM = float(snap.get("mortgage_monthly_total") or 0)
if _MORTM:
    _tok.add(f"{_MORTM:,.0f}")

# ── 1) 語法閘門 ────────────────────────────────────────────────────────────
_tree = None
try:
    _tree = ast.parse(src)
    ck("build_retirement_plan.py AST", True)
except SyntaxError as e:
    ck("build_retirement_plan.py AST", False, str(e))

# ── 2) 當期真值不得以字面值寫死進模板（AST 常數掃描；不看註解）──────────────
if _tree is not None:
    def _fold(n):
        """常數摺疊：字串相加與 f-string 的常數段還原成一個字串，
        防 `"100" + ",000"`／`f"110{'.6'}"` 這類拼接繞過（CIO 2026-09-28 指出的盲區）。
        FormattedValue 一律插 '{}' 佔位，避免跨插值誤拼成真值。"""
        if isinstance(n, ast.Constant):
            if isinstance(n.value, bool):
                return ""
            if isinstance(n.value, str):
                return n.value
            if isinstance(n.value, (int, float)):
                return f"{n.value:,.0f}"
            return ""
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            return _fold(n.left) + _fold(n.right)
        if isinstance(n, ast.JoinedStr):
            return "".join("{}" if isinstance(v, ast.FormattedValue) else _fold(v) for v in n.values)
        return ""

    _hits = []
    for _n in ast.walk(_tree):
        _txt = _fold(_n)
        if not _txt:
            continue
        _hits += [f"L{getattr(_n, 'lineno', '?')}:{t}" for t in _tok if t in _txt]
    ck("模板無寫死當期真值（AST：字串＋數值＋常數摺疊）", not _hits, str(sorted(set(_hits))))

# 自查：本檔自身不得出現凍結產物檔名或當期真值字面值（CIO 2026-09-28 建議硬性化）
_self = Path(__file__).read_text(encoding="utf-8")
_self_frozen = sorted(set(re.findall(r"(?:retirement_plan|asset_diff|daily_report_v2|"
                                     r"dynamic_weekly_review)_\d{4}-\d{2}-\d{2}", _self)))
_self_tok = sorted({t for t in _tok if t in _self})
ck("本檔自身無凍結產物檔名與當期真值字面值", not _self_frozen and not _self_tok,
   f"檔名 {_self_frozen}／字面值 {_self_tok}")

# ── 3) snapshot 自洽 ＋ RULE 檔同步（regex 抽值比對，不寫死金額）─────────────
ck("retirement_surplus == 保守被動 − 月支出",
   abs(float(snap["retirement_surplus"]) - (SC["con"]["income"] - SC["expense"])) < 0.01,
   f"{snap['retirement_surplus']} vs {SC['con']['income'] - SC['expense']:,.0f}")
_rule = RULE.read_text(encoding="utf-8")
import run_daily as _rd   # noqa: E402  （唯讀：抽值工具 ＋ 三源校準）
_got = _rd.extract_markdown_value(_rule, r"退休後盈餘 \*\*([+-]?[0-9,]+)\*\*")
ck("RULE 檔退休後盈餘 == snapshot 現算（抽值比對，非寫死）",
   _got is not None and int(_got.replace(",", "").lstrip("+")) == int(round(SC["con"]["surplus"])),
   f"RULE={_got} 現算={SC['con']['surplus']:,.0f}")
ck("RULE 檔無退役字樣（舊值不得殘留）", not [s for s in RETIRED if s in _rule],
   str([s for s in RETIRED if s in _rule]))

# ── 4) 當日退休規劃頁（最新一份，不釘死檔名）────────────────────────────────
_con_pct = f"{SC['con']['coverage']:.1f}"
_act_pct = f"{SC['act']['coverage']:.1f}"
_pg, _ = daily_page("retirement_plan_*.html", "退休規劃頁")
if _pg:
    ck("頁面『保守底線』與『當月實收』標籤成對（數量相等且 >0）",
       _pg.count("保守底線") == _pg.count("當月實收") > 0,
       f"{_pg.count('保守底線')}/{_pg.count('當月實收')}")
    ck("頁面含保守／實收覆蓋率現算值",
       has(_pg, _con_pct) and has(_pg, _act_pct), f"{_con_pct}/{_act_pct}")

    def _lone(needle, partners):
        out = []
        for m in re.finditer(re.escape(needle), _pg):
            win = _pg[max(0, m.start() - 200):m.end() + 200]
            if not any(pt in win for pt in partners):
                out.append(win[:60])
        return out

    _l1 = _lone(_con_pct, (_act_pct, "保守"))   # 標籤＝「保守」（含門檻句「保守 X% ≥100%」）
    ck(f"保守覆蓋率 {_con_pct}% 全部成對或標明保守底線", not _l1, f"孤立 {len(_l1)} 處: {_l1[:2]}")
    _l2 = _lone(_act_pct, (_con_pct, "當月實收"))
    ck(f"實收覆蓋率 {_act_pct}% 全部成對或標明當月實收", not _l2, f"孤立 {len(_l2)} 處: {_l2[:2]}")
    ck("頁面無浮點尾巴（x,xxx.0）", not re.search(r"\d[\d,]*\.0(?![\d%])", _pg),
       str(re.findall(r"\d[\d,]*\.0(?![\d%])", _pg)[:3]))
    ck("頁面無退役字樣（舊值不得殘留）", not [s for s in RETIRED if s in _pg],
       str([s for s in RETIRED if s in _pg]))

    # 門檻改版（2026-09-28）口徑：覆蓋率一律與被動收入口徑單一來源現算值相同
    ck("當日產物壓力情境覆蓋＝snapshot 口徑",
       has(_pg, f"{SC['stress']['coverage']:.1f}"), f"期望 {SC['stress']['coverage']:.1f}")
    ck("當日產物極端情境覆蓋＝snapshot 口徑（原壓力口徑降級後數值保留）",
       has(_pg, f"{SC['extreme']['coverage']:.1f}"), f"期望 {SC['extreme']['coverage']:.1f}")
    ck("當日產物含加碼級 A+ 標記（150% 為理想值，非門檻）", "A+級" in _pg)

    # 2026-09-28：當月實收語境的房租必須是實收真值（passive_income.rent_monthly_actual）；
    # 不得沿用常態 rent_monthly（實踩：實收卡片下方仍寫常態房租 → 明細加總與卡片值自相矛盾）。
    # 判準：配息用「實收值」時，房租亦必須是實收值；保守語境的配息非實收值 → 不受檢（零誤判）。
    if SC["div_act"] != SC["div_con"]:
        _d_act = f"{SC['div_act']:,.0f}"
        _r_act = f"{SC['rent_act']:,.0f}"
        _bad_rent = [m.group(0) for m in re.finditer(
            r"配息(?:實收)?\s*" + re.escape(_d_act) + r"\s*[＋+]\s*(?:房租|租金)(?:實收)?\s*([\d,]+)", _pg)
            if m.group(1) != _r_act]
        ck("退休規劃頁：配息用實收值時，房租亦為實收真值（不得混常態）",
           not _bad_rent, str(_bad_rent[:2]))

# ── 5) 儀表板：被動收入基準觀察小卡（自洽 ＋ 現算）────────────────────────────
if IDX.exists():
    _idx = IDX.read_text(encoding="utf-8")
else:
    ck("儀表板產物 index.html 存在（缺檔時不留 traceback，改以具名 FAIL 記）", False, str(IDX))
    _idx = ""
ck("儀表板無殘留 __DIVBASE_ 佔位符", "__DIVBASE_" not in _idx)
# 儀表板顯示的當期真值：標籤＋值成對（無 data-k 注入、也不在 rep 對映的純模板值＝會靜默說舊話）
_itxt = text_of(_idx)
ck("儀表板被動月固定收入（常態）＝現算保守底線",
   f"被動月固定收入（常態） {SC['con']['income']:,.0f} TWD" in _itxt,
   f"期望 被動月固定收入（常態） {SC['con']['income']:,.0f} TWD")
# 2026-09-28：該值已改 data-k 注入（+ 與數字被 span 分開）→ 用正則容忍標籤間空白；
# 瀏覽器渲染仍是「＋號緊貼數字」（相鄰行內元素不加空白），故不寫成固定字串。
_sur_txt = f"{SC['con']['surplus']:,.0f}"
ck("儀表板安全退休盈餘＝現算（標籤＋值成對）",
   re.search(r"安全退休盈餘\s*\+\s*" + re.escape(_sur_txt) + r"\s*TWD", _itxt) is not None,
   f"期望 安全退休盈餘 +{_sur_txt} TWD")
ck("儀表板月支出（月經常性總支出／退休維持月支出）＝現算",
   f"月經常性總支出 {SC['expense']:,.0f}" in _itxt and f"退休維持月支出 {SC['expense']:,.0f}" in _itxt,
   f"期望 {SC['expense']:,.0f}")
_i0 = _idx.find("被動收入基準觀察")
_card = text_of(_idx[_i0:_i0 + 4000]) if _i0 >= 0 else ""
ck("儀表板含基準觀察卡", bool(_card) and "基準月" in _card)
_m = re.search(r"基準月 (\d{4}-\d{2}) · 觀察 (\d+) 個月", _card)
if not _m:
    ck("基準觀察卡宣告可解析（基準月／觀察月數）", False, _card[:80])
else:
    _bm, _n = _m.group(1), int(_m.group(2))
    _by, _bmo = int(_bm[:4]), int(_bm[5:7])
    _ei = (_bmo - 1 + _n) % 12 + 1
    _ey = _by + (_bmo - 1 + _n) // 12
    _end = f"{_ey}-{_ei:02d}"                       # 檢視點 = 基準月 + N 個月
    _today_m = date.today().strftime("%Y-%m")
    _mi = (int(_today_m[:4]) - _by) * 12 + (int(_today_m[5:7]) - _bmo) + 1
    _ci = min(max(_mi, 1), _n)
    ck("基準觀察卡狀態計數與宣告基準月自洽", f"第 {_ci}/{_n} 個月" in _card, f"期望 第 {_ci}/{_n} 個月")
    ck("基準觀察卡觀察期／檢視點與宣告基準月自洽",
       f"觀察期 {_bm}～{_end}" in _card and f"檢視點 {_end}-01" in _card, f"期望 {_bm}～{_end}／{_end}-01")
    ck("基準觀察卡現行保守底線＝snapshot 配息保守基本值（標籤＋值成對）",
       f"現行保守底線 {SC['div_con']:,.0f}" in _card, f"期望 現行保守底線 {SC['div_con']:,.0f}")
    _ev = json.loads((BASE / "schedule_events.json").read_text(encoding="utf-8"))
    ck("未來清單已排檢視日事件（＝基準月＋觀察月數的 01 日）",
       any(str(e.get("date")) == f"{_end}-01" and "被動收入結構檢視" in str(e.get("item", "")) for e in _ev),
       f"期望 {_end}-01")
    # 基準列：該月三桶合計＝dividend_records 現算（不寫死金額）
    _brec = (snap.get("dividend_records", {}) or {}).get(_bm) or {}
    _btot = sum(v for k, v in _brec.items()
                if isinstance(v, (int, float)) and DC.bucket_of(k) in ("ins", "etf", "fund"))
    ck("基準列有標記『（基準）』且三桶合計＝現算",
       f"{_bm}（基準）" in _card and f"{_btot:,.0f}" in _card, f"現算 {_btot:,.0f}")
    ck("其他項（不計入三桶）動態列出、不寫死名稱",
       "註：不計入三桶之其他項＝" in _card,
       "應為 build_dashboard 依 dividend_bucket==other 動態產生")

# 當月正典 breakdown：分桶器實跑 == 正典（含三桶顯示於儀表板）
_rec = snap["dividend_records"]
_mdb = snap.get("monthly_dividend_breakdown", {}) or {}
_cur_m = str(snap.get("date", ""))[:7]
_rerun = {}
for _nm, _vv in (_rec.get(_cur_m) or {}).items():
    if isinstance(_vv, (int, float)):
        _rerun[BD.dividend_bucket(_nm)] = _rerun.get(BD.dividend_bucket(_nm), 0) + _vv
_BMAP = {"ins": "insurance", "etf": "etf", "fund": "fund"}
if _mdb.get("total"):
    ck(f"分桶器實跑＝正典 breakdown（{_cur_m}）",
       all(abs(_rerun.get(b, 0) - float(_mdb.get(_BMAP[b]) or 0)) < 0.5 for b in ("ins", "etf", "fund"))
       and abs(sum(_rerun.get(b, 0) for b in ("ins", "etf", "fund")) - float(_mdb["total"])) < 0.5,
       f"實跑 {({k: round(v) for k, v in _rerun.items()})} vs 正典 {_mdb['total']}")
    ck("正典三桶分項顯示於儀表板",
       all(f"{float(_mdb[k] or 0):,.0f}" in _idx for k in ("insurance", "etf", "fund")),
       f"{_mdb.get('insurance')}/{_mdb.get('etf')}/{_mdb.get('fund')}")
    ck("正典三桶合計顯示於儀表板", f"{float(_mdb['total']):,.0f}" in _idx, f"{_mdb['total']:,.0f}")

# ── 6) 差異分析（最新一份）──────────────────────────────────────────────────
_ad, _ = daily_page("asset_diff_*.html", "差異分析頁")
if _ad:
    ck("差異分析：配息成對＝現算（保守基本值／當月實收）",
       f"配息 保守基本值 {SC['div_con']:,.0f}" in _ad and f"當月實收 {SC['div_act']:,.0f}" in _ad,
       f"期望 {SC['div_con']:,.0f}／{SC['div_act']:,.0f}")
    ck("差異分析：被動收入成對＝現算（覆蓋率亦現算）",
       f"被動收入 保守底線 {SC['con']['income']:,.0f}（覆蓋 {SC['con']['coverage']:.1f}%）" in _ad
       and f"當月實收 {SC['act']['income']:,.0f}（覆蓋 {SC['act']['coverage']:.1f}%）" in _ad,
       f"期望 {SC['con']['income']:,.0f}／{SC['act']['income']:,.0f}")
    ck("差異分析：退役字樣已清", not [s for s in RETIRED if s in _ad],
       str([s for s in RETIRED if s in _ad]))

# ── 7) 原始碼結構（相對式：看有沒有「派生」而不是看有沒有某個數字）────────────
_p2 = subprocess.run([sys.executable, "-c", "import run_daily; run_daily.calibrate_sources()"],
                     cwd=str(BASE), capture_output=True, text=True)
_out = _p2.stdout + _p2.stderr
ck("run_daily.calibrate_sources 通過", _p2.returncode == 0, _out.strip()[-200:])
ck("校準點位全數可比（allianz/firstjin 不再空轉）",
   _p2.returncode == 0 and "校準空轉" not in _out,
   _out.strip()[-160:])
# 2026-10-01：安聯A+B／第一金現值 regex 已改活（RULE 檔現值同步為真值），
# 本檢查由「WARN 必須可見（已知缺口揭露）」升級為「不得有空轉點」——
# 任一 regex 再失配即 FAIL，避免校準靜默空轉（原註記見 error_register 待對帳項）。
ck("壓力列改單一派生（f-string 無重複算式）",
   "div_c*0.8 + rent - 33000:,.0f" not in src and "{_stress_income:,.0f}" in src)
ck("極端列無缺口文案分支存在", "_ext_txt" in src and "無缺口（水庫不受壓）" in src)
ck("極端情境分母已保護（無裸除法）",
   "_ext_months = round(cash / _ext_gap, 1) if _ext_gap > 0 else 0" in src
   and "/(expense-(div_c*0.7+rent-33000))" not in src)
ck("已移除未使用變數 surplus/working_surplus",
   "surplus = snap.get" not in src and "working_surplus = snap.get" not in src)

# 2026-10-01 INC-270：月支出／月收入禁自帶寫死 fallback（一律走 sot_targets 單一入口）。
# 為什麼：162,781（8 月口徑）散在 15 個生產檔當 snap.get(..., 162781) 的退路 → snapshot 缺值時
# 靜默印出舊值。改為 accessor（缺值即 raise）後，這條守門防止下一個人再寫回退路。
_bad_fb = []
for _p in sorted(BASE.glob("*.py")):
    if _p.name == Path(__file__).name or _p.name.startswith("_"):
        continue
    _t = _p.read_text(encoding="utf-8", errors="replace")
    # 去註解再掃：註解（例如「原常數已移除」的說明）不會造成靜默舊值，不應誤判
    _code = "\n".join(_ln.split("#", 1)[0] for _ln in _t.splitlines())
    if (re.search(r'monthly_expense["\']?\s*,\s*162781', _code)
            or re.search(r"or\s+162781(?:\.0)?", _code)
            or re.search(r"MONTHLY_EXPENSE\s*=\s*162781", _code)):
        _bad_fb.append(_p.name)
ck("月支出無寫死 fallback（一律 sot_monthly_expense）", not _bad_fb, str(_bad_fb))

# 2026-10-02 裁示（第 1 批）：決策核心單一入口 —— 可動用現金／留停 Gate／觸發器
try:
    import sot_targets as _st_dc
    import json as _json_dc
    _s_dc = _json_dc.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    _ac = _st_dc.allowable_cash(_s_dc)
    # 2026-10-13 TD-20261011-16 口徑對齊：可動用真值鍵＝unrestricted_cash（available 為舊鍵）；
    # 穿透桶『現金/安全網』自 2026-10-12 起已改讀可動用真值（不含在途），在途改顯式揭露。
    _cl_uc = float(((_s_dc.get("cash_layers") or {}).get("unrestricted_cash")) or 0)
    _pen_dc = _s_dc.get("penetration") or {}
    _cl_pen = float(((_pen_dc.get("actual_twd") or {}).get("現金/安全網")) or 0)
    _in_transit = _pen_dc.get("cash_in_transit")
    ck("可動用現金＝cash_layers.unrestricted_cash（唯一真值）", abs(_ac - _cl_uc) < 0.5, f"{_ac} vs {_cl_uc}")
    ck("穿透桶『現金/安全網』＝可動用真值（不含在途／未對帳）",
       _cl_pen > 0 and abs(_cl_pen - _ac) < 0.5,
       f"穿透桶 {_cl_pen} vs 可動用 {_ac}（差 {_cl_pen - _ac}，須為 0）")
    ck("在途／未對帳顯式揭露且不併入桶位（penetration.cash_in_transit）",
       ("cash_in_transit" in _pen_dc) and isinstance(_in_transit, (int, float))
       and not isinstance(_in_transit, bool) and abs(_cl_pen - _ac) < 0.5,
       f"cash_in_transit={'缺鍵' if 'cash_in_transit' not in _pen_dc else _in_transit}"
       f"｜穿透桶 {_cl_pen} − 可動用 {_ac} = {_cl_pen - _ac}（桶位不得併入在途）")
    _g_dc = _st_dc.sabbatical_gate(_s_dc)
    ck("留停 Gate 三條派生（GO/WAIT）", _g_dc.get("判定") in ("GO", "WAIT") and len(_g_dc.get("gate") or []) == 3,
       str(_g_dc.get("判定")))
    _cm_dc = _st_dc.cash_mode(_s_dc)
    ck("現金模式派生（正常／防守／現金保全）",
       _cm_dc.get("模式") in ("正常", "防守模式", "現金保全模式"),
       f"{_cm_dc.get('模式')}｜可動用 {_cm_dc.get('可動用')}")
    _tr_dc = _st_dc.triggers(_s_dc)
    ck("觸發器單一入口可用（今日結論＋列表）",
       bool(_tr_dc.get("今日結論")) and isinstance(_tr_dc.get("列表"), list) and len(_tr_dc["列表"]) >= 5,
       f"{_tr_dc.get('今日結論')}｜{len(_tr_dc.get('列表') or [])} 條")
    _html_dc = (BASE / "index.html").read_text(encoding="utf-8", errors="replace") if (BASE / "index.html").exists() else ""
    ck("首頁含 CEO 決定卡（Gate＋今日動作）",
       "CEO 決定卡" in _html_dc and "留停 Gate" in _html_dc and "今日動作" in _html_dc, "index.html")
    # 第 2 批（裁示② 2026-10-02）：可接受範圍內＝完全靜默
    try:
        import sot_targets as _st_b
        import re as _re_b
        _sn_b = _json_dc.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        _bands_b = _st_b.acceptable_band(_sn_b)
        _alias_b = {"台股市值型成長": ("台股市值型", "台股"), "美股市值型成長": ("美股市值型", "美股"),
                    "防守型配息": ("防守型配息", "防守", "防禦"), "債券": ("債券",), "科技": ("科技", "高科技")}
        _BAD_b = ("缺口", "還差", "不足", "低於目標", "建議增加", "需再平衡", "距離目標")
        _noise = []
        for _f_b in ("index.html", "rebalance_dashboard_%s.html" % __import__("datetime").date.today().isoformat(),
                     "daily_report_v2_%s.html" % __import__("datetime").date.today().isoformat()):
            _fp_b = BASE / _f_b
            if not _fp_b.exists():
                continue
            _h_b = _fp_b.read_text(encoding="utf-8", errors="replace")
            for _n_b, _b_b in _bands_b.items():
                if _b_b.get("顯示行動") or not isinstance(_b_b.get("現值"), (int, float)):
                    continue                      # 範圍外 → 允許出現
                _tgt_b = _b_b.get("目標")
                if not isinstance(_tgt_b, (int, float)):
                    continue
                _pp_b = abs(_b_b["現值"] - _tgt_b)
                for _w_b in _alias_b.get(_n_b, (_n_b,)):
                    for _m_b in _re_b.finditer(_re_b.escape(_w_b), _h_b):
                        _win_b = _h_b[max(0, _m_b.start() - 110):_m_b.end() + 110]
                        for _a_b in _BAD_b:
                            if _re_b.search(_re_b.escape(_a_b) + r"\s*[+-]?{:.1f}\s*pp".format(_pp_b), _win_b):
                                _noise.append((_f_b, _n_b, _a_b, _pp_b))
        ck("可接受範圍內桶不得殘留缺口／行動字樣（範圍內＝完全靜默）", not _noise, str(_noise[:3]))
        ck("可接受範圍已建真值（5 桶、現金排除）",
           len(_bands_b) == 5 and all("現金" not in k for k in _bands_b), str(list(_bands_b)))
    except Exception as _e_b2:
        ck("可接受範圍守門可執行", False, str(_e_b2))

    ck("首頁無健康度分數敘事（93 分退場）",
       "龍九健康度" not in _html_dc and "健康度：" not in _html_dc,
       "健康度卡標題 x" + str(_html_dc.count("龍九健康度")))
except Exception as _e_dc:
    ck("決策核心（可動用／Gate／觸發器）可派生", False, str(_e_dc))

# 第 4 批（裁示④ 2026-10-02）：90 天資金需求 A/B 分區
try:
    import sot_targets as _st_n
    _sn_n = _json_dc.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    _nd_n = _st_n.cash_need_90d(_sn_n)
    _a_n = float(_nd_n["A_已確認"]["合計"])
    _cfg_n = _sn_n.get("cash_need_90d") or {}
    ck("90 天需求不建立 B 區（未得標款項不得進模型）",
       "B_條件式" not in _cfg_n and "B_條件式" not in _nd_n,
       str([k for k in _cfg_n if "B" in str(k)]))
    ck("A 區＝固定月支出 × 3（無其他未確認項）",
       abs(_a_n - float(_nd_n["A_已確認"]["固定月支出_合計"])) < 1.0,
       "A=" + format(_a_n, ",.0f"))
    ck("90 天覆蓋率＝可動用 ÷ A 區（毛需求）",
       abs(float(_nd_n["覆蓋率_pct"]) - (_nd_n["可動用"] / _a_n * 100.0)) < 0.05,
       str(_nd_n["覆蓋率_pct"]) + "%")
    # 2026-10-09（使用者裁決：押標金未得標→不列入 90 天已確認需求、不預先辦理保證函）：
    #   原散文正則「否定句附近出現 2,400,000」無法辨識否定語意，會把**明示排除**的句子
    #   誤判為違規（實測：當日日報 ⑥ 條件式事件一句）。
    #   改為數值判定：產物渲染的 90 天需求分母必須＝A 區計算值。
    #   比原式強：原式僅「碰巧鄰近」才觸發且無法區分否定；本式直接比對計算結果。
    #   實作見 tools/cash_need_90d_guard.py（附正反向測試）。
    #   註：第一版曾加「語境」檢查（押標金附近需有排除詞），實測同樣脆弱——
    #       產物在多處合法語境提及押標金（決策卡清單／本週計劃／條件式事件），
    #       固定字元窗無法區分「提及」與「列為需求」→ 又製造假紅燈，故**不採用散文式判定**。
    import sys as _sys_n
    _sys_n.path.insert(0, str(BASE / "tools"))
    import cash_need_90d_guard as _cg_n
    _pg_n = ""
    for _f_n in ("index.html", "daily_report_v2_%s.html" % __import__("datetime").date.today().isoformat()):
        _fp_n = BASE / _f_n
        if _fp_n.exists():
            _pg_n += _fp_n.read_text(encoding="utf-8", errors="replace")
    _ok_den_n, _d_den_n = _cg_n.check_rendered_denominator(_pg_n, _a_n)
    ck("產物 90 天需求分母＝A 區計算值（押標金未併入）", _ok_den_n, _d_den_n)
    ck("產物含 90 天覆蓋率（毛需求口徑）",
       "未來 90 天現金需求覆蓋率" in _pg_n or "未來 90 天現金需求" in _pg_n, "index/daily")
except Exception as _e_n:
    ck("90 天資金需求守門可執行", False, str(_e_n))

# 第 3 批（裁示③ 2026-10-02）：Pending 期限管理 schema 與狀態機
try:
    import datetime as _dt_p
    import pending_engine as _pe_p
    _items_p = _pe_p.load_items()
    _need_fields = ("due_date", "last_confirmed", "owner", "external_owner", "status")
    _missing_p = [(x.get("title"), k) for x in _items_p for k in _need_fields if k not in x]
    # 2026-10-05（使用者核准 PEND-20261005-04）：原 `len(_items_p) == 26` 是一次性遷移留下的硬編碼，
    # 卡片長到 34 張後即使資料完全合規也永遠 FAIL（假紅燈）。改動態口徑：只驗「每一張都有五欄」。
    ck("Pending schema 五欄齊備（全卡動態）",
       not _missing_p and len(_items_p) > 0, str(_missing_p[:3]) + "｜n=" + str(len(_items_p)))
    _bad_src = [x.get("title") for x in _items_p
                if x.get("due_date") and not str(x.get("due_date_source") or "").startswith("既有文字")]
    ck("due_date 一律來自既有文字（不猜、不推算）", not _bad_src, str(_bad_src[:3]))
    # 2026-10-12：期限管理只對「進行中」（待處理／已確認）生效。結案態（已完成／關案）
    # 不該再被要求帶期限或補 needs_due_date——否則第一張結案卡即假紅燈（紅燈必須陳述真問題）。
    # 狀態判定一律委派 pending_engine（單一來源），此處不自帶副本。
    _active_p = [x for x in _items_p if _pe_p.is_active(x)]
    _null_no_flag = [x.get("title") for x in _active_p if not x.get("due_date") and not x.get("needs_due_date")]
    ck("無 due_date 者標記 needs_due_date（僅進行中卡；結案態不受期限管理）",
       not _null_no_flag, str(_null_no_flag[:3]))
    _enum_bad = [x.get("title") for x in _items_p if x.get("status") not in _pe_p.STATUS_ENUM]
    ck("status 正規化為四態（原字串保留 status_raw）",
       not _enum_bad and all("status_raw" in x for x in _items_p), str(_enum_bad[:3]))
    _t_p = _dt_p.date(2026, 10, 2)
    _st_p = {d: _pe_p.escalation_stage(d, _t_p)["stage"] for d in
             ("2026-10-03", "2026-10-02", "2026-10-01", "2026-09-29", "2026-09-25")}
    ck("升級門檻＝0／今日／+1／+3／+7",
       _st_p["2026-10-03"] == 0 and _st_p["2026-10-02"] == 1 and _st_p["2026-10-01"] == 2
       and _st_p["2026-09-29"] == 3 and _st_p["2026-09-25"] == 4, str(_st_p))
    _pg_p = ""
    for _f_p in ("index.html", "daily_report_v2_%s.html" % _dt_p.date.today().isoformat()):
        _fp_p = BASE / _f_p
        if _fp_p.exists():
            _pg_p += _fp_p.read_text(encoding="utf-8", errors="replace")
    _seg_p = [m.group(0) for m in re.finditer(r"📌 Pending：[^<]{0,200}", _pg_p)]
    _cmd_p = [s for s in _seg_p if re.search(r"建議(買|賣)|加碼|減碼|質押|借款|賣股|應買|應賣", s)]
    _line_p = _seg_p
    ck("Pending 行只提醒、不含交易指令", bool(_line_p) and not _cmd_p, str(_cmd_p[:2]))
    ck("Pending 行只突出今日到期（其餘為升級／不提醒）",
       all(("今日到期" in l or "今日無到期" in l) for l in _line_p) if _line_p else False,
       str(_line_p[:1]))
except Exception as _e_p:
    ck("Pending 期限守門可執行", False, str(_e_p))

ck("壓力/極端判定與顏色已派生（無寫死 red 判定）",
   'class="red">&lt;100%' not in src and "{_stress_cls}" in src and "{_ext_cls}" in src
   and "{_stress_note}" in src)
for _f in ("run_daily.py", "dividend_tracker.py", "build_dashboard.py", "build_investment_performance.py"):
    _s = (BASE / _f).read_text(encoding="utf-8")
    ck(_f + " 已委派正典分類器（無自帶抄本規則）",
       "dividend_caliber" in _s and 'or ("安聯" in' not in _s and 'if "ETF" in name:' not in _s)

# ── 8) 分類器口徑（實跑，非文字斷言）────────────────────────────────────────
ck("保單子帳含『基金』仍歸保單（不誤分基金）", BD.dividend_bucket("第一金FA81聯博多元AD基金配息") == "ins")
ck("基金名含『安聯』歸基金（58 元誤分案）", BD.dividend_bucket("基金配息 安聯收益AMg7") == "fund")
ck("投資績效頁分類器已同口徑",
   BIP.classify_dividend("基金配息 安聯收益AMg7") == "基金"
   and BIP.classify_dividend("安聯保單撥回") == "保單"
   and BIP.classify_dividend("ETF配息 00878") == "股票")
_PROBE = ["ETF配息 00878", "安聯保單撥回", "基金配息 安聯收益AMg7",
          "第一金FL65安聯收益成長配息", "台灣特品現金股息", "基金息pi收益 - 存入"]
_IPMAP = {"etf": "股票", "oneoff": "股票", "ins": "保單", "fund": "基金"}
_DBMAP = {"etf": "etf", "oneoff": "other", "ins": "ins", "fund": "fund"}
ck("分類器單一口徑（正典 ↔ 儀表板 ↔ 投資績效）",
   all(BD.dividend_bucket(_n) == _DBMAP[DC.bucket_of(_n)] for _n in _PROBE)
   and all(BIP.classify_dividend(_n) == _IPMAP[DC.bucket_of(_n)] for _n in _PROBE))
ck("Moneybook 原始明細：ETF 連結基金不得誤判 ETF（元大0050連結A→基金）",
   DC.classify_mb_memo("基金配息 元大0050連結A") == "fund"
   and DC.classify_mb_memo("媒體轉入 - 基金配息00981afund") == "etf")

# ── 9) 保守口徑鍵禁止靜默退路（缺值不得沿用「當月實收／total」冒充保守基本值）──
_flagged = []
for _p in sorted(BASE.glob("*.py")):
    _t = open(_p, encoding="utf-8", newline="").read()
    for _i, _line in enumerate(_t.splitlines(), 1):
        if "fund_dividend_conservative" not in _line:
            continue
        _tail = _line.split("fund_dividend_conservative", 1)[1]
        if "div_total" in _tail or "_div_sum_current_month" in _tail:
            _flagged.append(_p.name + ":" + str(_i) + " 實收冒充")
        elif " or " in _tail and not _tail.split(" or ", 1)[1].strip().startswith("0"):
            _flagged.append(_p.name + ":" + str(_i) + " or 退路")
ck("保守口徑鍵無『or 實收／or total』退路", not _flagged, str(_flagged[:6]))

# ── 10) 校正檔：每月機械重算比對（已結算月可寫死的只有歷史事實本身）──────────
_adj = json.loads((BASE / "investment_performance_adjust.json").read_text(encoding="utf-8"))
for _mm in sorted(k for k in _adj if re.match(r"^\d{4}-\d{2}$", str(k))):
    _a = _adj[_mm].get("配息") or {}
    if not _a:
        continue                      # 當月尚未結算（配息為空 dict）
    _r = {}
    for _nm, _vv in (_rec.get(_mm) or {}).items():
        if isinstance(_vv, (int, float)):
            _c = BIP.classify_dividend(_nm)
            _r[_c] = _r.get(_c, 0) + _vv
    ck(f"校正檔 {_mm} 保單桶＝分類器重算", abs(float(_a.get("保單", 0)) - _r.get("保單", 0)) < 0.5,
       f"校正 {_a.get('保單')} vs 重算 {_r.get('保單')}")
    if set(_a) <= set(_r):
        ck(f"校正檔 {_mm} 三桶全等重算（dividend_records 完整覆蓋）",
           all(abs(float(_a[k]) - _r.get(k, 0)) < 0.5 for k in _a), f"校正 {_a} vs 重算 {_r}")
    else:
        ck(f"校正檔 {_mm} 為 MB 補充月：無舊重複計數回歸",
           RETIRED_DUP not in [float(v) for v in _a.values()], str(_a))

# ── 11) 共享上下文（自動生成檔）：日期相符才驗，否則 SKIP ─────────────────────
_ctx = CTX.read_text(encoding="utf-8")
_cd = re.search(r"^- \*\*Date\*\*: (\d{4}-\d{2}-\d{2})", _ctx, re.M)
if not _cd:
    ck("共享上下文有 Date 欄（自動生成檔）", False, "找不到 Date 欄")
elif _cd.group(1) != str(snap.get("date")):
    skip(f"共享上下文斷言（由 {_cd.group(1)} 的 snapshot 產生，現為 {snap.get('date')} → 待重生後再驗）")
else:
    _pi = snap["passive_income"]
    ck("共享上下文實收鍵＝snapshot 現值",
       f"'fund_dividend_monthly': {int(_pi['fund_dividend_monthly'])}" in _ctx
       and f"'dividend_actual_sum': {int(_pi['dividend_actual_sum'])}" in _ctx,
       f'{_pi["fund_dividend_monthly"]}')
    ck("共享上下文 Retirement Surplus＝snapshot 現值",
       f"- **Retirement Surplus**: {int(snap['retirement_surplus'])}" in _ctx,
       str(snap["retirement_surplus"]))
    ck("共享上下文 Real Liquid Assets＝snapshot 現值",
       f"- **Real Liquid Assets**: {int(snap['real_liquid_assets'])}" in _ctx,
       str(snap["real_liquid_assets"]))

# ── 11b) 儀表板模板的當期真值必須走 data-k 注入（2026-09-28 補）────────────────
# 這兩處原本是純文字寫死、既無 data-k 也不在 rep 對映內 → 真值一動就靜默說舊話。
_tpl = (BASE / "index_template.html").read_text(encoding="utf-8")
ck("儀表板模板：常態被動／退休盈餘已改 data-k 注入（非純文字）",
   'data-k="passive_norm"' in _tpl and 'data-k="retire_surplus"' in _tpl)
# 四審 N1：只驗「存在」不夠（把 fmt(真值) 改成 fmt(0) 照樣過）→ 釘住來源式
# 五審 N6：整檔 re.search 會被「V 物件外的誘餌註解」騙過 → 改結構式：抽出的 V 區塊內逐鍵取值再驗運算式
_V_EXPECT = {
    "passive_norm": r"^fmt\(\(\(s\.passive_income\|\|\{\}\)\.total_conservative\)\|\|0\)$",
    "retire_surplus": r"^fmt\(s\.retirement_surplus\|\|0\)$",
}


def _vblock(_t):
    """V 區塊（含結尾大括號）：切片必須含 \"      };\"，否則 rindex(\"}\") 會抓到值裡的
    `(s.passive_income||{})` 那個右大括號、把後半段切掉（2026-09-28 實踩）。"""
    _i = _t.index("var V = {")
    return _t[_i:_t.index("      };", _i) + len("      };")]


def _vpairs(_block):
    """V 區塊 → {鍵: 值運算式}；逗號只在括號深度 0 才算分隔（值本身含 fmt(...)）。"""
    # 先去 JS 行註解：註解裡的「：」會被當成鍵值分隔（2026-09-28 實踩：V 物件內的沿革註解）
    _body = re.sub(r"//[^\n]*", "", _block[_block.index("{") + 1:_block.rindex("}")])
    _out, _depth, _cur = {}, 0, ""
    for _ch in _body:
        if _ch == "(":
            _depth += 1
        elif _ch == ")":
            _depth -= 1
        if _ch == "," and _depth == 0:
            _kv = _cur.split(":", 1)
            if len(_kv) == 2:
                _out[_kv[0].strip()] = _kv[1].strip()
            _cur = ""
        else:
            _cur += _ch
    _kv = _cur.split(":", 1)
    if len(_kv) == 2:
        _out[_kv[0].strip()] = _kv[1].strip()
    return _out


_V_PAIRS = _vpairs(_vblock(_tpl))
_V_BAD = sorted(k for k, _pat in _V_EXPECT.items() if re.match(_pat, _V_PAIRS.get(k, "")) is None)
ck("儀表板模板：V 區塊內兩鍵來源式正確（結構式；V 物件外的誘餌不算）", not _V_BAD, str(_V_BAD))

# produced index.html 的 V 區塊必須與模板逐字相同（注入只改資料、不得偷改 JS）
_idx_p = BASE / "index.html"
if _idx_p.exists():
    ck("儀表板 JS 值對照表：built index.html 與 index_template.html 逐字相同",
       _vblock(_idx_p.read_text(encoding="utf-8")) == _vblock(_tpl))
else:
    ck("儀表板 JS 值對照表：built index.html 與 index_template.html 逐字相同", False,
       f"缺 {_idx_p.name} → 無法比對")
# 2026-09-28：留停表 snapshot 記錄的「房租淨現金流」也必須同源（防只改頁面、記錄留舊值）
_sab_rec = ((snap.get("sabbatical_checklist") or {}).get("記錄") or {})
if _sab_rec:
    _rk = sorted(_sab_rec.keys())[-1]
    _rv = _sab_rec[_rk].get("房租淨現金流")
    ck(f"留停表記錄（{_rk}）房租淨現金流 == 常態房租收入（口徑與頁面一致）",
       _rv is not None and abs(float(_rv) - SC['rent_norm']) < 0.5,
       f"記錄 {_rv} vs 現算 {SC['rent_norm']:,.0f}")

ck("房貸月付合計真值可得（缺值時不得靜默放行）", _MORTM > 0,
   f"snapshot.mortgage_monthly_total = {_MORTM:,.0f}；為 0 表示查詢失敗、房租淨現金流保護已失效")
if _pg:
    # 2026-09-28 使用者裁示：房貸月付已計入月支出（週報同口徑）→ 房租端不再重複扣，
    # 本列＝常態房租收入本身。
    ck("頁面房租淨現金流 == 常態房租收入（房貸不重複扣；現算）",
       f"房租淨現金流（常態房租收入 {SC['rent_norm']:,.0f}" in _pg
       and has(_pg, f"{SC['rent_norm']:,.0f}"),
       f"期望 房租淨現金流…（常態房租收入 {SC['rent_norm']:,.0f}），值 {SC['rent_norm']:,.0f}")

# ── 12) 變更範圍（限自身檔案集；外部排程寫入另列，不計入）────────────────────
_raw = subprocess.run(["git", "status", "--porcelain"], cwd=str(BASE),
                      capture_output=True, text=True).stdout.splitlines()
_dirty = [ln[3:].strip().strip('"') for ln in _raw if ln.strip()]
_dirty = [d for d in _dirty if not d.endswith("_preview.png")]
# 他班／未追蹤檔（非本班 scope）：只提示不阻擋（2026-10-02 使用者裁示：不納入本班 commit）
_OTHER_AGENT = re.compile(r"^gen_emergency_us_\d{8}\.py$")
_other_agent = [_d for _d in _dirty if _OTHER_AGENT.match(_d)]
_dirty = [d for d in _dirty if d not in _other_agent]
# 他班／前批未追蹤檔（明確歸屬、非本班 scope）：只提示不阻擋，且**不得混入本班 commit**。
#   2026-10-09 使用者裁決：「未提交的其他檔案必須維持原有歸屬，不可混入本次提交；由工程端隔離」。
#   隔離＝明列歸屬並排除於本班範圍；不是當成本班變更（吸收），也不是靜默忽略（消失）。
_OTHER_OWNER = {
    "apply_truth_20261008.py": "2026-10-08 真值套用腳本（前批產物，非本班）",
    # 2026-10-13 TD-20261011-16：以下 5 檔為既存「非本班」檔，維持原歸屬、排除於本班 commit。
    #   未明列時，本守門每晚以「未宣告的程式檔異動」把本班驗收一起誤擋（假紅燈）。
    "apply_truth_20261012.py": "2026-10-12 真值套用腳本（前批產物，非本班）",
    "_archive_closed_card_20261010.py": "2026-10-10 一次性歸檔腳本（已執行完成，置於 .archive/deprecated_scripts/）",
    "health_alert_check.py": "2026-10-10 健康度 A 案修改版（裁決：限施工與驗收，不含提交／推送／發布；待另行發布）",
    "it_health_alert_check.py": "2026-10-10 健康度 A 案整合測試（同上裁決，待另行發布）",
    "test_health_alert_check.py": "2026-10-10 健康度 A 案單元測試（同上裁決，待另行發布）",
}
_other_owner = [_d for _d in _dirty if Path(_d.strip()).name in _OTHER_OWNER]
_dirty = [d for d in _dirty if d not in _other_owner]
# 外部排程（cron）寫入：非本班變更，只提示不阻擋
_EXT = re.compile(r"^(cost\.html|cost_data\.json|data/|logs/|dragon_assets\.db)")
_ext = [d for d in _dirty if _EXT.match(d)]
_dirty = [d for d in _dirty if d not in _ext]
allowed = {"build_retirement_plan.py", "snapshot.json", "snapshot.json.bak",
           "sot_targets.py",   # 決策核心單一入口（Gate／現金模式／觸發器；2026-10-02 第 1 批）
           "report_components.py",   # 首頁 CEO 決定卡（健康度分數退場；2026-10-02 第 1 批）
           "check_dashboard_sync.py",   # 首頁必備關鍵字改「CEO 決定卡」（2026-10-02 第 1 批）
           "check_dashboard_stale.py", "check_narrative_numbers.py",
           "check_narrative_numbers_selftest.py",   # 可動用現金口徑改讀 cash_layers.available
           "build_rebalance_dashboard.py",   # 第 2 批：本週投資計劃文案過 band_filter（裁示②靜默）
           "pending_engine.py", "pending_decisions.json",   # 第 3 批：Pending 期限管理（裁示③）
           "DAILY_REPORT_PIPELINE_RULE.md", "run_daily.py",
           "notion_shared_context.md", "index_template.html", "build_dashboard.py", "index.html",
           "check_caliber_mutation.py",   # 本守門的變異測試（2026-09-28 從 %TEMP% 搬進版控，置於 tools/）
           "test_daily_report_penetration_live.py",   # 日報「五桶佔比」段落＝當日真值之回歸（2026-10-15 本班）
           "test_retirement_rebalance_live.py",   # 退休規劃／再平衡評估 live 欄位回歸（2026-10-15 本班）
           "build_rebalance_eval_html.py",   # 再平衡評估頁渲染：snapshot 真值欄位即時覆蓋（本班）
           "build_retirement_plan.py",   # 留停缺口表「現金水位」改讀 live 可動用（本班）
           "verify_ciostatus_pushbase.py",   # cio_approve --status 基準修正的唯讀驗證器（tools/）
           "schedule_events.json", "error_register.md",
           "dashboard_decisions.json",   # 決策登記（decision-governance 主檔，逐筆新增屬預期）
           "asset_diff_monitor.py",
           "build_investment_performance.py", "check_dividend_caliber.py",
           "dividend_caliber.py", "dividend_tracker.py", "asset_moat_monitor.py",
           "investment_performance_adjust.json", "investment_performance.html",
           "mtd_data.json", "mtd_performance.html", "passive_caliber.py",
           "sabbatical_checklist_update.py", "work_log.json", "radar_state.json",
           "cio_approve.py",   # 治理工具（--status 比較基準修正，2026-09-28）
           "buffett_cto_analyzer.py",   # 2026-10-02：現金底線字面改 cash_floor_label() 現讀（口徑殘留清理）
           "debt_restructure_tracker.py",   # 2026-10-02：移除已作廢的 1,200,000 合計底線退路
           # 2026-10-07 政策一致性修正 ①②③（使用者核准：健康度中性／門檻單一來源／觀測線命名）
           "usd_advisory.py", "usd_exposure_sync.py",   # 政策門檻唯一入口（policy/cap/tier）＋監控區塊只留真值
           "market_indicator_panel.py", "risk_factor_penetration.py",
           "build_audit_dashboard.py", "institutional_flow.py",
           # 2026-10-07 INC-289 P0（日報雙 producer 產出一致性）：抽出唯一實作＋守門
           "daily_report_assembly.py", "regenerate_report.py",
           "verify_daily_report_single_producer.py",   # 守門置於 tools/
           # 2026-10-09 使用者核准：週報同口徑事件鏈判定修正（唯讀稽核後）
           "notion_weekly_trend_wrapper.py", "test_weekly_trend_event_chain.py",
           "audit_weekly_trend_event_chain_20261009.md",
           # 2026-10-09 本班（Phase 03 績效閘門解耦 ＋ 90 天需求守門改數值判定）
           #   授權：PEND-20261009-13／-14／-15 ＋ 使用者 2026-10-09「一次完成所有必要修復」裁決
           "build_weekly_report.py", "lj.py", "weekly_report.py",
           "verify_performance_monthly.py", "verify_performance_core_task12.py",
           "perf_gate_contract.py", "verify_perf_gate_tests.py",
           # 2026-10-11 本班：pending 治理修復（1/3 只增不減根治）
           #   授權：使用者 2026-10-11 Telegram 核准「A+B+D 一次做完（修引擎＋修前端計數＋清理）」
           "decision_auto_close.py",   # 逾時歸檔改四態判定＋閉環改歸檔（不再直接覆寫正本）
           "tech_debt.py",   # 技術債登錄工具（工程/治理類分流去處；新增）
           "tech_debt.json",   # 技術債資料檔（新增；非程式檔但一併宣告）
           # 2026-10-14 本班（v1.2 US30Y 閘門；TD-20261015-02）：
           #   授權＝使用者 2026-10-14 Telegram 裁決「核准開工施工 v1.2，限程式修訂、測試、
           #   獨立驗收及真 CIO 審查」；範圍＝sot_targets.py（已宣告）／us30y_monitor.py／
           #   action_loop.py／pending_reconcile.py／check_thresholds.py／index_template.html
           #   （已宣告）＋ build_dashboard.py（已宣告；P3 紅線連續日數標示）＋測試。
           "us30y_monitor.py",   # US30Y 監控：紅線連續天數真值＋警示語意（原「永久凍結」）
           "action_loop.py",     # 建議快照帶出 gate_mode／risk_warning／unfreeze_conditions
           "pending_reconcile.py",   # 解凍卡敘述改列實體未達條件（不再以 US30Y 為單一理由）
           "check_thresholds.py",   # 閘門斷言：hard_veto 沿用 v1.1／advisory 重算複合條件
           "test_us30y_hardening.py",   # 測試：M1–M8 v1.2 正向／負向／回復案例
           # 2026-10-15 本班（⑨ Pages 部署稽核；使用者同日 Telegram 核准）：
           #   授權＝使用者 2026-10-15 「✅ 核准」將 Pages 部署結論納入收工檢查；
           #   觸發：10/14 23:59 本機＝遠端＝HEAD、收工全綠，但 Pages deploy 逾時失敗，
           #   費用頁落後一版卻只能靠人工看到 GitHub 失敗通知（④ 的 Pages 檢查只看檔案存在）。
           "closeout_check.py",   # 新增 ⑨ 步驟：讀 Pages workflow 最新一版結論（公開 API，無 token）
           "test_pages_deploy_check.py",   # 上項之單元測試（4 狀態＋真實整合，11 條）
           # 2026-10-15 本班（常態配息層；同批核准）：
           #   授權＝使用者 2026-10-15 Telegram「✅ 核准」常態層最小變更集（基金常態＋保單常態＝配息常態；
           #   保單值標示為「暫定規劃值」；保守配息不動；三層實收／保守／常態並列且互不覆寫）。
           "passive_caliber.py",   # div_norm 改讀 monthly_dividend_normal＋新增 norm 情境
           "test_normal_dividend_layer.py",   # 上項之單元測試（正向／負向回退／回歸隔離，11 條）
           # 2026-10-15 本班（真 CIO 工作區審查 3 blocking 修復 ＋ 緊急應變分離；TD-20261015-05）：
           #   授權＝使用者同日 Telegram 裁決「授權修復 3 個 blocking、授權補記第③筆決策；
           #   緊急應變採 B 方案從 sync_all 主流程分離；三項均不含 commit／push／發布」。
           #   ① asset_diff 同頁矛盾：新增「指定用途款³」欄使 分項＋指定款＝總資產 逐列自洽。
           #   ② index 美股口徑：顯示層以 snapshot.penetration 即時值改寫雷達週計畫數字。
           #   ③ apply_truth 未定義變數：覆核為誤判（P／_FUNDS 皆有定義、可編譯）→ 補靜態守門測試。
           "sync_all.py",   # 緊急應變步驟移出主流程（B 方案）＋根因註解；不調整任何 timeout
           "test_page_truth_consistency.py",   # asset_diff 逐列加總＋index 桶位/live 一致性（含負向自測）
           "test_apply_truth_scoping.py",   # apply_truth_*.py 名稱解析靜態守門（含負向案例）
           # 2026-10-15 本班 B1（單一施工批次；R1 審查鏈／R2 bonds／R3 CTO 報告／緊急應變只產出／HTML 方案 A）：
           #   授權＝使用者 2026-10-15 13:29 Telegram 裁決「授權執行 B1 單一施工批次，HTML 採 A
           #   （納入版控＋白名單）」；同批邊界＝只授權修改、測試與留存證據，不含 commit／push／發布。
           #   （regenerate_report.py／asset_diff_monitor.py／buffett_cto_analyzer.py 已於前批宣告）
           "review_chain.py",   # R1：契約驗證＋分段完整涵蓋＋一致性（temperature 不再當確定性保證）
           "test_review_chain_20261013.py",   # R1：契約／涵蓋率純函式測試（T10–T14）
           "test_review_chain_stability.py",   # R1：離線穩定性整合測試（打樁 _layers，25 條）
           "test_history_schema_completeness.py",   # R2：bonds fallback／缺值拒絕／鍵集完整性（11 條）
           "test_cto_report_rules.py",   # R3：凍結禁令／紅線數字／ETF 標籤守門（16 條）
           "emergency_1330.py",   # §4：_commit_own() 預設不提交（LJ_EMERGENCY_COMMIT 閘門）
           "test_emergency_no_commit.py",   # §4：預設零 git 寫入＋產出/告警不受影響（35 條；含 E11/E12 真 git 沙盒）
           "test_html_publish_consistency.py",   # §5：producer ↔ 白名單 ↔ 輸出路徑一致性（19 條）
           # 2026-10-15 21:5x 本輪（使用者裁決「緊急應變產線採 B 修正版：產出與驗收可以完成，
           #   發布權限仍受獨立閘門控制；不得 commit／push／發布，也不得間接繞過」）：
           #   ① gen_emergency_taiex_auto.py（本次宣告）：標題／副標改依 JSON `source` 判「分析標的」
           #      （INC-214b）—— 21:30 美股班不再被渲染成「台股緊急應變報告」；兩報告家族同批重產。
           #   ② regenerate_report.py（已宣告）：新增 LJ_EMERGENCY_LANE「只收緊」車道
           #      （13:00／21:30 班即使 prompt 漂移也不會 commit/push）＋ emergency_taiex_report_*
           #      納入 stage 候選；發布閘門（publish_gate／publish_plan／LJ_EMERGENCY_COMMIT）不動。
           #   ③ run_daily.py（已宣告）：檔頭標明四階段口徑（本檔天然只產出＋驗收）。
           #   ④ publish_allowlist.json（已宣告）：白名單條目追加 emergency_taiex_report_*.html。
           #   ⑤ tools/test_html_publish_consistency.py（已宣告）：覆蓋擴及兩家族＋修正 P5b 過期斷言。
           "gen_emergency_taiex_auto.py",
           # 2026-10-15 21:5x 本輪續（同裁決，一次收尾）：③ check_dashboard_sync.py 第 1 條
           #   排除 `window.` 之後的樣式（build_dashboard 合法注入的 JS 變數
           #   `window.__LJ_LIVE_ROWS__` 被誤判為殘留 → 本檔恆紅）；④ tools/
           #   test_dashboard_sync_placeholder.py（新增，鑑別力：位置型佔位符仍必須被抓到）。
           #   註：同批未宣告的 site_sync.py／tools/test_site_isolation.py 非本輪產物
           #   （10/15 16:24 公開面隔離工作班殘留，另列管 TD-20261015-09），本輪不納入、不代宣告。
           "test_dashboard_sync_placeholder.py",
           # 2026-10-15 22:2x 本輪續（使用者裁決「路線 A：先處理 13bd9b28 真缺陷，再與 A＋B
           #   合併成單一可完整審查的 commit」）：① pending_reconcile.py（已宣告）修時間戳同步
           #   （狀態重算時維護 updated_at ＋ 既有落後項自我修復）與紅線／模式A streak 語意標示；
           #   ② tools/test_pending_reconcile_stamp.py（新增；T0–T5 共 8 條，含負向與守恆）。
           "test_pending_reconcile_stamp.py",
           # 2026-10-15 22:3x 本輪續（使用者裁決「路線 1：修復審查基建，不採例外放行」）：
           #   ① cio_lane.py（本次宣告）：送審改走 review_chain 單一真值（build_review_prompts／
           #      review_segmented），消除「脈絡串進 patch → 二次截斷 → 涵蓋率 99.6% → 必然
           #      REJECT」的假截斷；並補車道自檢（涵蓋率 <100% 不得送審）與跨段 REJECT 無 blocking
           #      的無效審查判定。審查判準不放寬。
           #   ② tools/test_cio_lane_coverage.py（新）：U0–U6 共 14 條（分段覆蓋、無二次截斷、
           #      負向截斷警告、涵蓋率守門、真實 0da98b37 覆蓋 100%、單段邊界）。
           #   ③ tools/test_cio_lane_fullpatch.py（本次宣告）：W1 套件對齊新介面（stub 改
           #      review_segmented 底層 review），原保證不變，新增 02b（不得二次截斷、涵蓋率 100%）、
           #      09（涵蓋率不足不得送審）、10（REJECT 無 blocking＝無效審查不得核准）。
           #   ④ tools/review_commit_and_record.py（新）：對「範圍內舊 commit」跑真審查＋落 RECORD 的
           #      腳本化實作（auto_push 官方指示的人工路徑，2026-10-15 因 22:30 lane 疊 commit 而需要）。
           "cio_lane.py",
           "test_cio_lane_coverage.py",
           "test_cio_lane_fullpatch.py",
           "review_commit_and_record.py",
           # 2026-10-16（使用者裁決「修掉切片造成的假拒絕」）：本輪範圍＝送審包裝層
           #   ① review_chain.py（已宣告）：分段改以**檔案邊界**優先（split_patch）、單段上限
           #      12,000 → 32,000、僅技術性失敗每段最多重試 2 次、段級無效結果列入 blocking。
           #   ② cio_lane.py／regenerate_report.py（已宣告）：改走 split_patch 單一真值；
           #      上限常數同步 32,000。審查對象、異質審查者、判準與 100% 覆蓋率均不變。
           #   ③ tools/test_review_chain_packaging_20261016.py（新增）：P1–P6 共 33 條
           #      （跨檔案不切穿／大型單檔／JSON 完整性／覆蓋率守門／重試行為／真實 d28b889d 回歸）。
           "test_review_chain_packaging_20261016.py",
           "test_stale_source_guard_20261016.py",   # 2026-10-16（本輪②）：舊快照混入防線（weekly_plan 資料日閘門／科技口徑／真實產物一致）
           # 2026-10-15 同批延伸（使用者裁決「修 calc_penetration 的餘數法」）：
           #   update_all.py 桶位先取整、餘數與在途差額改整數相減 → 不變量整數層精確成立
           "update_all.py",
           # 2026-10-15 本輪（P1-1／P0-3／P1-2 三項 blocking 之修復收攏；使用者同日裁決
           #   「繼續施工、維持 HOLD」——範圍＝補完測試／登錄宣告／全套回歸／第二輪複審／
           #   發布前核對，不含 commit／push／發布）：
           #   ① P1-1 Dashboard 比例口徑：build_dashboard.py 已於本輪改讀
           #      sot_targets.defensive_caliber()（配息資產合計真值）單一來源＋即時卡資料注入
           #      （build_dashboard.py 第 307–312 行；index.html／index_template.html 已宣告）。
           #   ② P0-3 緊急流程禁止未授權發布：emergency_1330.py（已宣告）計畫層 publish_plan()
           #      ／_plan_violations()；測試併入 test_emergency_no_commit.py E8–E12（已宣告）。
           #   ③ P1-2 提交責任鏈：新增 artifact_commit.py 並接入 evening_sync.py。
           "artifact_commit.py",   # P1-2＋裁決 b：受控資料產物提交（宣告清單＋顯式 pathspec；commit 前驗證 staged ⊆ 宣告清單）；**不推送**
           "evening_sync.py",   # P1-2：晚報步 5 收尾提交（唯一責任邊界；失敗在晚報逐字揭露）
           "test_artifact_commit_responsibility.py",   # P1-2：責任鏈真 git 沙盒驗收 R1–R13（42 條）
           "publish_allowlist.json",   # B1｜HTML 方案 A：首頁重要連結報告頁白名單（非程式檔但一併宣告）
           # 2026-10-15 第二輪（使用者裁決「三項逐一修到根因、完整複審一次，再決定發布」：
           #   ① 基金口徑 12,503 差額 → 追查真值來源並補可追溯說明（不放寬檢查器）
           #   ② Dashboard stale token → 逐項證明後退休＋改用更精確比對條件
           #   ③ auto_push --dry-run 誤判純資料 commit → 修正分類依據（不繞過發布閘門）
           #   範圍＝修正、測試、證據留存；不含 commit／push／發布）
           "publish_gate.py",   # 新增 force_cio_reasons()／force_cio_summary()：按真實類別揭露拒因
           "auto_push.py",      # 拒推訊息改按類別揭露（rc／攔截能力不變）；退出碼語意補述
           "check_dashboard_stale.py",   # 衍生差值（穿透卡 ±Zpp）視為活顯示值 → 列「清單過時」不誤判
           "test_dashboard_stale_tokens.py",   # 上項正／負向驗收（12 條：真舊句仍抓、活值不誤紅）
           "test_push_commit_classification.py",   # 上項正／負向驗收（16 條：純資料辨識、程式／混合仍攔）
           "dashboard_stale_tokens.json",   # 資料檔：四個過寬 token 逐項退休＋新增完整舊句條件
           }
# 逐日產物：命名比對，跨月不失效（舊版 allowed_prefixes 釘死 2026-09）
_DAILY = re.compile(r"^(asset_diff|retirement_plan|daily_report_v2|rebalance_dashboard|"
                    r"dynamic_weekly_review)_\d{4}-\d{2}-\d{2}\.html$")
# 硬擋＝「未宣告的程式檔異動」，副檔名定義與推送閘門一致：
# 這才是「改了不該改的」；cron 產出（html／json／log／歸檔）隨時在變，
# 硬性要求逐一列舉只會製造假紅燈（2026-09-28 實踩：etf_report／hunter_cache／notion_bridge 為他支排程產物）。
_CODE = re.compile(r"\.(py|sh|bat|ps1|cmd|toml|yml|yaml|js|ts|sql)$|^\.githooks/"
                   r"|^\.gitattributes$|^\.gitignore$|^index_template\.html$", re.I)


def _declared(s):
    """單一路徑是否已宣告（改名條目會有兩側，逐側判定）"""
    n = Path(s.strip()).name
    return n in allowed or bool(_DAILY.match(n))


# 改名條目在 porcelain 是 "old -> new"：兩側都要宣告，且任一侧是程式檔就要硬擋
_undeclared = [d for d in _dirty if not all(_declared(s) for s in d.split("->"))]
_hard = [d for d in _undeclared if any(_CODE.search(s.strip()) for s in d.split("->"))]
ck("變更範圍：無未宣告的程式檔異動", not _hard, str(_hard))
if _other_agent:
    print(f"ℹ️  他班／未追蹤檔（非本班 scope，不納入本班 commit）：{_other_agent}")
if _other_owner:
    for _d_o in _other_owner:
        print(f"ℹ️  非本班檔（維持原歸屬、排除於本班 commit）：{_d_o}"
              f"｜{_OTHER_OWNER[Path(_d_o.strip()).name]}")
# 本班變更範圍（CIO 紀錄用；8 條決策核心守門屬於本班 schema 變更）
print(f"ℹ️  本班異動（{len(_dirty)} 檔）：{_dirty}")
print("ℹ️  DECISION_CORE_CHECKS=8")
_other = [d for d in _undeclared if d not in _hard]
if _other:
    print(f"ℹ️  其他產出異動（排程／報表產物，非程式檔，另列不計入）：{len(_other)} 檔 ｜ "
          + "、".join(_other[:10]) + ("…" if len(_other) > 10 else ""))

# ── 10.5) 常態配息層（2026-10-15 使用者裁決新增）──────────────────────────────
#   三層口徑（實收／保守／常態）各自獨立、互不覆寫。常態層只改壓力情境的配息來源；
#   保守層與極端情境（含跑道）必須逐位元不變。保單常態＝最近完整月實收（暫定規劃值）。
#   本節刻意「零當期真值字面值」——一律以關係式比對（值改了就對不上，而不是靠改字面值）。
_pi = snap.get("passive_income") or {}
_nf = _pi.get("fund_dividend_normal_fund")
_np = _pi.get("fund_dividend_normal_policy")
_nd = _pi.get("fund_dividend_normal")
_rt_n = _pi.get("rent_monthly_normal")
ck("常態層拆解等式：基金常態 ＋ 保單常態 ＝ 配息常態（三鍵皆須存在且為正）",
   all(isinstance(x, (int, float)) and x > 0 for x in (_nf, _np, _nd, _rt_n))
   and _nd == (_nf or 0) + (_np or 0)
   and snap.get("monthly_dividend_normal") == _nd,
   f"基金 {_nf}／保單 {_np}／配息常態 {_nd}／monthly_dividend_normal={snap.get('monthly_dividend_normal')}")
ck("常態被動 ＝ 配息常態 ＋ 租金常態（且與租金常態口徑同源）",
   _pi.get("total_normal") == (_nd or 0) + (_rt_n or 0) and _rt_n == _pi.get("rent_monthly"),
   f"total_normal={_pi.get('total_normal')}／rent_monthly_normal={_rt_n}／rent_monthly={_pi.get('rent_monthly')}")
_scn = PC.scenarios(snap)
_exp_m = float(snap.get("monthly_expense") or 0) or 1.0
ck("常態層覆蓋率＝常態被動 ÷ 月支出（與宣告值及實算一致）",
   abs(_scn["norm"]["coverage"] - float(_pi.get("coverage_pct_normal") or 0)) < 0.05
   and abs(_scn["norm"]["coverage"] - float(_pi.get("total_normal") or 0) / _exp_m * 100) < 0.05,
   f"實算 {_scn['norm']['coverage']:.1f}% vs 宣告 {_pi.get('coverage_pct_normal')}%")
ck("常態層來源＝monthly_dividend_normal（不得退回最後一個完整月實收鍵）",
   _scn["div_norm"] == snap.get("monthly_dividend_normal")
   and _scn["div_norm"] != _pi.get("fund_dividend_monthly"),
   f"div_norm={_scn['div_norm']}／fund_dividend_monthly={_pi.get('fund_dividend_monthly')}")
ck("三層互不覆寫：保守配息＝宣告鍵且 ≠ 常態配息 ≠ 實收配息",
   _scn["div_con"] == _pi.get("fund_dividend_conservative")
   and _scn["div_con"] != _scn["div_norm"] and _scn["div_act"] != _scn["div_norm"]
   and _scn["act"]["coverage"] < _scn["norm"]["coverage"],
   f"保守 {_scn['div_con']}／常態 {_scn['div_norm']}／實收 {_scn['div_act']}")
ck("壓力情境＝常態配息×STRESS_DIV_RATIO ＋ 租金常態 − 洲際W 空置（實算一致）",
   abs(_scn["stress"]["income"]
       - (_scn["div_norm"] * PC.STRESS_DIV_RATIO + _scn["rent_norm"] - _scn["vacancy"])) < 0.5
   and abs(_scn["stress"]["coverage"]
           - _scn["stress"]["income"] / _exp_m * 100) < 0.05,
   f"stress income={_scn['stress']['income']:,.0f}／{_scn['stress']['coverage']:.1f}%")
ck("極端情境／跑道 仍讀保守配息（不受常態層影響）",
   abs(_scn["extreme"]["income"] - (_scn["div_con"] * PC.STRESS_DIV_RATIO
                                    + _scn["rent_norm"] - _scn["vacancy"])) < 0.5
   and _scn["extreme"]["coverage"] < _scn["con"]["coverage"]
   and _scn["stress"]["coverage"] > _scn["con"]["coverage"],
   f"extreme income={_scn['extreme']['income']:,.0f}／跑道 {_scn['extreme']['runway_days']}")

fail = [c for c in checks if not c[1]]
for name, ok, detail in checks:
    print(("✅" if ok else "❌"), name, ("｜" + detail if detail and not ok else ""))
print(f"\n{len(checks) - len(fail)}/{len(checks)} PASS"
      + (f"（另 {_SKIPS} 條 SKIP，未計入分母）" if _SKIPS else "")
      + ("" if not fail else f" — FAIL: {[c[0] for c in fail]}"))
sys.exit(1 if fail else 0)
