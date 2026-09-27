"""配息口徑守門（2026-09-23 入庫；2026-09-28 翻新為「全相對式 ＋ 指當日產物」）

只讀，不改任何檔案。PASS/FAIL 逐項列出，exit 0 = 全過。
用途：改動 build_retirement_plan / build_dashboard / asset_diff_monitor / build_investment_performance
或配息資料後，commit 前先跑：`python check_dividend_caliber.py`。

翻新原則（2026-09-28）——本檔不得再出現任何「當期」真值字面值：
  ① 期望值一律由 snapshot ＋ passive_caliber ＋ dividend_caliber 現算；檔名不寫死日期。
     舊版釘死 retirement_plan_2026-09-23.html 與 9/23 期數字 → 該檔一封存、或真值一動就整檔爆紅。
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

def skip(msg):
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

# ── 1) 語法閘門 ────────────────────────────────────────────────────────────
_tree = None
try:
    _tree = ast.parse(src)
    ck("build_retirement_plan.py AST", True)
except SyntaxError as e:
    ck("build_retirement_plan.py AST", False, str(e))

# ── 2) 當期真值不得以字面值寫死進模板（AST 常數掃描；不看註解）──────────────
if _tree is not None:
    _hits = []
    for _n in ast.walk(_tree):
        if not isinstance(_n, ast.Constant) or isinstance(_n.value, bool):
            continue
        if isinstance(_n.value, str):
            _hit = [t for t in _tok if t in _n.value]
        elif isinstance(_n.value, (int, float)):
            _f = f"{_n.value:,.0f}"
            _hit = [_f] if _f in _tok else []
        else:
            _hit = []
        # 模板是單一長字串 → 報「字面值起點行」，再指出命中值供人工定位
        _hits += [f"L{_n.lineno}:{t}" for t in _hit]
    ck("模板無寫死當期真值（AST 常數掃描：字串＋數值）", not _hits, str(sorted(set(_hits))))

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

# ── 5) 儀表板：被動收入基準觀察小卡（自洽 ＋ 現算）────────────────────────────
_idx = IDX.read_text(encoding="utf-8")
ck("儀表板無殘留 __DIVBASE_ 佔位符", "__DIVBASE_" not in _idx)
# 儀表板顯示的當期真值：標籤＋值成對（無 data-k 注入、也不在 rep 對映的純模板值＝會靜默說舊話）
_itxt = text_of(_idx)
ck("儀表板被動月固定收入（常態）＝現算保守底線",
   f"被動月固定收入（常態） {SC['con']['income']:,.0f} TWD" in _itxt,
   f"期望 被動月固定收入（常態） {SC['con']['income']:,.0f} TWD")
ck("儀表板安全退休盈餘＝現算",
   f"安全退休盈餘 +{SC['con']['surplus']:,.0f} TWD" in _itxt,
   f"期望 安全退休盈餘 +{SC['con']['surplus']:,.0f} TWD")
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
ck("校準空轉 WARN 已可見（allianz/firstjin）",
   "校準空轉" in _out and "allianz_value" in _out and "firstjin_value" in _out, _out.strip()[-160:])
ck("壓力列改單一派生（f-string 無重複算式）",
   "div_c*0.8 + rent - 33000:,.0f" not in src and "{_stress_income:,.0f}" in src)
ck("極端列無缺口文案分支存在", "_ext_txt" in src and "無缺口（水庫不受壓）" in src)
ck("極端情境分母已保護（無裸除法）",
   "_ext_months = round(cash / _ext_gap, 1) if _ext_gap > 0 else 0" in src
   and "/(expense-(div_c*0.7+rent-33000))" not in src)
ck("已移除未使用變數 surplus/working_surplus",
   "surplus = snap.get" not in src and "working_surplus = snap.get" not in src)
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

# ── 12) 變更範圍（限自身檔案集；外部排程寫入另列，不計入）────────────────────
_raw = subprocess.run(["git", "status", "--porcelain"], cwd=str(BASE),
                      capture_output=True, text=True).stdout.splitlines()
_dirty = [ln[3:].strip().strip('"') for ln in _raw if ln.strip()]
_dirty = [d for d in _dirty if not d.endswith("_preview.png")]
# 外部排程（cron）寫入：非本班變更，只提示不阻擋
_EXT = re.compile(r"^(cost\.html|cost_data\.json|data/|logs/|dragon_assets\.db)")
_ext = [d for d in _dirty if _EXT.match(d)]
_dirty = [d for d in _dirty if d not in _ext]
allowed = {"build_retirement_plan.py", "snapshot.json", "snapshot.json.bak",
           "DAILY_REPORT_PIPELINE_RULE.md", "run_daily.py",
           "notion_shared_context.md", "index_template.html", "build_dashboard.py", "index.html",
           "schedule_events.json", "error_register.md",
           "dashboard_decisions.json",   # 決策登記（decision-governance 主檔，逐筆新增屬預期）
           "asset_diff_monitor.py",
           "build_investment_performance.py", "check_dividend_caliber.py",
           "dividend_caliber.py", "dividend_tracker.py", "asset_moat_monitor.py",
           "investment_performance_adjust.json", "investment_performance.html",
           "mtd_data.json", "mtd_performance.html", "passive_caliber.py",
           "sabbatical_checklist_update.py", "work_log.json", "radar_state.json"}
# 逐日產物：命名比對，跨月不失效（舊版 allowed_prefixes 釘死 2026-09）
_DAILY = re.compile(r"^(asset_diff|retirement_plan|daily_report_v2|rebalance_dashboard|"
                    r"dynamic_weekly_review)_\d{4}-\d{2}-\d{2}\.html$")
_extra = [d for d in _dirty if Path(d).name not in allowed and not _DAILY.match(Path(d).name)]
ck("變更範圍僅預期檔案", not _extra, str(_extra))
if _ext:
    print("ℹ️  外部排程寫入（非本班變更，不計入範圍檢查）：" + "、".join(_ext))

fail = [c for c in checks if not c[1]]
for name, ok, detail in checks:
    print(("✅" if ok else "❌"), name, ("｜" + detail if detail and not ok else ""))
print(f"\n{len(checks) - len(fail)}/{len(checks)} PASS"
      + ("" if not fail else f" — FAIL: {[c[0] for c in fail]}"))
sys.exit(1 if fail else 0)
