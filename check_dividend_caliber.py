"""配息口徑守門（2026-09-23 起入庫）：保守底線＋當月實收成對顯示、三桶分類器、差異分析口徑。

只讀，不改任何檔案。PASS/FAIL 逐項列出，exit 0 = 全過。
用途：改動 build_dashboard / build_retirement_plan / asset_diff_monitor / build_investment_performance
或配息資料後，commit 前先跑：`python check_dividend_caliber.py`。
"""
import ast, json, re, subprocess, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent   # 需與 snapshot.json 同目錄執行
PY = BASE / "build_retirement_plan.py"
HTML = BASE / "retirement_plan_2026-09-23.html"
SNAP = BASE / "snapshot.json"
RULE = BASE / "DAILY_REPORT_PIPELINE_RULE.md"

checks = []
def ck(name, ok, detail=""):
    checks.append((name, bool(ok), detail))

# 1) 語法
src = PY.read_text(encoding="utf-8")
try:
    ast.parse(src); ck("build_retirement_plan.py AST", True)
except SyntaxError as e:
    ck("build_retirement_plan.py AST", False, str(e))

# 2) 禁止把「當期數字」寫死進模板
for lit in ["180,100", "228,075", "17,319", "65,294", "110.6", "140.1", "474%", "600%", "147,975"]:
    ck(f"模板無寫死 {lit}", lit not in src)

# 3) 快照真值 + 內容物
snap = json.loads(SNAP.read_text(encoding="utf-8"))
exp = snap["passive_income"]["fund_dividend_conservative"] + snap["passive_income"]["rent_monthly"]
ck("retirement_surplus == 被動 − 月支出",
   snap["retirement_surplus"] == exp - snap["monthly_expense"] == 17319,
   f"{snap['retirement_surplus']} vs {exp - snap['monthly_expense']}")
ck("RULE 檔已同步 +17,319", "退休後盈餘 **+17,319**" in RULE.read_text(encoding="utf-8"))
ck("RULE 檔無舊值 30,552", "30,552" not in RULE.read_text(encoding="utf-8"))

# 4) 頁面渲染
html = HTML.read_text(encoding="utf-8")
t = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.S)
t = re.sub(r"<[^>]+>", " ", t)
t = re.sub(r"\s+", " ", t)
ck("舊值 30,552 不出現", "30,552" not in t)
ck("浮點尾巴 147,975.0 不出現", "147,975.0" not in t)
for k, n in [("保守底線", 15), ("當月實收", 15)]:
    ck(f"標籤「{k}」≥{n} 處", t.count(k) >= n, str(t.count(k)))
for k in ["180,100", "228,075", "110.6%", "140.1%", "474%", "600%", "+17,319", "+65,294"]:
    ck(f"頁面含 {k}", k in t)

# 5) 每個「保守」覆蓋率都要有配對（同段 200 字內有 140.1% 或標籤「保守底線」）
lone = [t[max(0, m.start() - 200):m.end() + 200]
        for m in re.finditer(r"110\.6%", t)
        if "140.1%" not in t[max(0, m.start() - 200):m.end() + 200]
        and "保守底線" not in t[max(0, m.start() - 200):m.end() + 200]]
ck("110.6% 全部成對或標明保守底線", not lone, f"孤立 {len(lone)} 處: {[x[:60] for x in lone]}")

lone2 = [t[max(0, m.start() - 200):m.end() + 200]
         for m in re.finditer(r"140\.1%", t)
         if "110.6%" not in t[max(0, m.start() - 200):m.end() + 200]
         and "當月實收" not in t[max(0, m.start() - 200):m.end() + 200]]
ck("140.1% 全部成對或標明當月實收", not lone2, str(len(lone2)))

# 6) 三源校準（run_daily 真值閘門）
p = subprocess.run([sys.executable, "-c", "import run_daily; run_daily.calibrate_sources()"],
                   cwd=str(BASE), capture_output=True, text=True)
ck("run_daily.calibrate_sources 通過", p.returncode == 0, (p.stdout + p.stderr).strip()[-200:])

# 7) 變更範圍
raw = subprocess.run(["git", "status", "--porcelain"], cwd=str(BASE),
                     capture_output=True, text=True).stdout.splitlines()
dirty = [ln[3:].strip().strip('"') for ln in raw if ln.strip()]
dirty = [d for d in dirty if not d.endswith("_preview.png")]
_external = [d for d in dirty if Path(d).name == "dragon_assets.db"]   # 外部 cron 寫入，非本班變更
dirty = [d for d in dirty if Path(d).name != "dragon_assets.db"]
allowed = {"build_retirement_plan.py", "retirement_plan_2026-09-23.html", "snapshot.json",
           "DAILY_REPORT_PIPELINE_RULE.md", "snapshot.json.bak", "run_daily.py",
           "notion_shared_context.md", "index_template.html", "build_dashboard.py", "index.html",
           "schedule_events.json", "error_register.md",
           "asset_diff_monitor.py", "asset_diff_2026-09-23.html",
           "build_investment_performance.py", "check_dividend_caliber.py", "error_register.md"}
extra = [d for d in dirty if Path(d).name not in allowed]
ck("變更範圍僅預期檔案", not extra, str(extra))

# 8) 二階段修正（CIO findings）
ck("極端情境分母已保護（無裸除法）",
   "_ext_months = max(1, round((cash - 300000) / _ext_gap)) if _ext_gap > 0 else 0" in src
   and "/(expense-(div_c*0.7+rent-33000))" not in src)
ck("已移除未使用變數 surplus/working_surplus",
   "surplus = snap.get" not in src and "working_surplus = snap.get" not in src)

# 9) retirement_surplus 三源校準必須是「活的」（regex 曾用簡體導致空轉）
sys.path.insert(0, str(BASE))
import run_daily as _rd
_got = _rd.extract_markdown_value(RULE.read_text(encoding="utf-8"), r"退休後盈餘 \*\*([+-]?[0-9,]+)\*\*")
ck("RULE regex 抓得到退休後盈餘（校準非空轉）", _got is not None and int(_got.replace(",", "").lstrip("+")) == 17319, str(_got))

# 10) 共享上下文與被動收入鍵同步
ctx = (BASE / "notion_shared_context.md").read_text(encoding="utf-8")
ck("notion_shared_context 欄位已是 17,319",
   "- **Retirement Surplus**: 17319" in ctx and "- **Retirement Surplus**: 30552" not in ctx)
pi = snap["passive_income"]
ck("passive_income 實收鍵同步 147,975",
   pi["fund_dividend_monthly"] == pi["dividend_actual_sum"] == snap["dividend_month_actual"] == 147975,
   f'{pi["fund_dividend_monthly"]}/{pi["dividend_actual_sum"]}/{snap["dividend_month_actual"]}')
ck("passive_income note 已更新（無 9/18 舊值）", "131,439" not in pi["note"])

# 11) 條圖寬度 == 標籤數字
w = re.findall(r"width:min\(([\d.]+)%,100%\)", html)
ck("進度條寬度等於標籤值", w[:2] == ["110.6", "140.1"], str(w[:2]))

# 12) 三階段修正：校準空轉可見化 + 重複算式收斂 + 共享上下文重生
p2 = subprocess.run([sys.executable, "-c", "import run_daily; run_daily.calibrate_sources()"],
                    cwd=str(BASE), capture_output=True, text=True)
_out = p2.stdout + p2.stderr
ck("校準空轉 WARN 已可見（allianz/firstjin）",
   "校準空轉" in _out and "allianz_value" in _out and "firstjin_value" in _out, _out.strip()[-160:])
ck("壓力列改單一派生（f-string 無重複算式）",
   "div_c*0.8 + rent - 33000:,.0f" not in src and "{_stress_income:,.0f}" in src)
ck("極端列無缺口文案分支存在", "_ext_txt" in src and "無缺口（水庫不受壓）" in src)
ctx2 = (BASE / "notion_shared_context.md").read_text(encoding="utf-8")
ck("共享上下文已重生（實收鍵 147,975／現金 861818／盈餘 17319）",
   "'fund_dividend_monthly': 147975" in ctx2 and "'dividend_actual_sum': 147975" in ctx2
   and "- **Real Liquid Assets**: 861818" in ctx2 and "- **Retirement Surplus**: 17319" in ctx2
   and "'fund_dividend_monthly': 131439" not in ctx2
   and "'dividend_actual_sum': 131439" not in ctx2
   and "- **Retirement Surplus**: 30552" not in ctx2)
ck("頁面壓力/極端情境值不變", "127,100" in t and "71.9%" in t and "12 個月" in t)

# 13) 被動收入基準觀察小卡（儀表板）＋ 情境判定派生（2026-09-23 使用者指示）
_idx = (BASE / "index.html").read_text(encoding="utf-8")
ck("儀表板無殘留 __DIVBASE_ 佔位符", "__DIVBASE_" not in _idx)
ck("儀表板含基準觀察卡", "被動收入基準觀察" in _idx and "⏳ 第 1/3 個月" in _idx and 'class="overflow-x-auto"' in _idx)
_rec = snap["dividend_records"]
_mdb = snap.get("monthly_dividend_breakdown", {}) or {}
exp09 = _mdb.get("total") or sum(v for v in _rec["2026-09"].values() if isinstance(v, (int, float)))
ck("基準月三桶合計＝正典 breakdown.total（147,975）", exp09 == 147975 and f"{exp09:,.0f}" in _idx, f"{exp09}")
ck("基準月三桶分項＝正典 breakdown（保險/ETF/基金）",
   all(f"{_mdb[k]:,.0f}" in _idx for k in ("insurance", "etf", "fund")),
   f"{_mdb.get('insurance')}/{_mdb.get('etf')}/{_mdb.get('fund')}")
ck("一次性『台灣特品現金股息』不計入三桶（8 月三桶合計 123,637）",
   "123,637" in _idx, "8月三桶合計應為 123,637（14,990 計入 other 不列桶）")
_ev = json.loads((BASE / "schedule_events.json").read_text(encoding="utf-8"))
ck("未來清單已排 12/01 被動收入結構檢視",
   any(e.get("date") == "2026-12-01" and "被動收入結構檢視" in str(e.get("item", "")) for e in _ev))
ck("snapshot 已記基準月定案", "基準月" in snap["passive_income"]["note"])
ck("壓力/極端判定與顏色已派生（無寫死 red 判定）",
   'class="red">&lt;100%' not in src and "{_stress_cls}" in src and "{_ext_cls}" in src
   and "{_stress_note}" in src)

# 14) 差異分析（asset_diff）覆蓋率也要成對顯示（2026-09-23 使用者指向「差異分析裡面的資料」）
_ad = (BASE / f"asset_diff_{__import__('datetime').date.today().isoformat()}.html")
if _ad.exists():
    _at = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _ad.read_text(encoding="utf-8")))
    ck("差異分析：配息為成對顯示（保守基本值 100,000／當月實收 147,975）",
       "配息 保守基本值 100,000" in _at and "當月實收 147,975" in _at)
    ck("差異分析：被動收入成對（110.6%／124.1%）且舊字串已清",
       "被動收入 保守底線 180,100（覆蓋 110.6%）" in _at and "當月實收 201,975（覆蓋 124.1%）" in _at
       and "保守配息：" not in _at)
else:
    ck("差異分析檔案存在", False, str(_ad))

# 15) 分類器實跑驗證（CIO finding：只斷言字串不足以證明分類器正確）
sys.path.insert(0, str(BASE))
import build_dashboard as _bd
import build_investment_performance as _bip
_bkt = {"ins": 0.0, "etf": 0.0, "fund": 0.0, "other": 0.0}
for _n, _v in _rec["2026-09"].items():
    if isinstance(_v, (int, float)):
        _bkt[_bd.dividend_bucket(_n)] += _v
ck("實跑 dividend_bucket 對 9 月分桶＝正典 breakdown",
   (_bkt["ins"], _bkt["etf"], _bkt["fund"]) == (74461, 16340, 57174)
   and _bkt["ins"] + _bkt["etf"] + _bkt["fund"] == 147975,
   str({k: round(v) for k, v in _bkt.items()}))
ck("保單子帳含『基金』仍歸保單（不誤分基金）", _bd.dividend_bucket("第一金FA81聯博多元AD基金配息") == "ins")
ck("基金名含『安聯』歸基金（58 元誤分案）", _bd.dividend_bucket("基金配息 安聯收益AMg7") == "fund")
ck("投資績效頁分類器已同口徑",
   _bip.classify_dividend("基金配息 安聯收益AMg7") == "基金"
   and _bip.classify_dividend("安聯保單撥回") == "保單"
   and _bip.classify_dividend("ETF配息 00878") == "股票")
ck("小卡其他項動態列出（2026-08 台灣特品現金股息 14,990）",
   "2026-08 台灣特品現金股息 14,990" in _idx)

fail = [c for c in checks if not c[1]]
for name, ok, detail in checks:
    print(("✅" if ok else "❌"), name, ("｜" + detail if detail and not ok else ""))
print(f"\n{len(checks) - len(fail)}/{len(checks)} PASS" + ("" if not fail else f" — FAIL: {[c[0] for c in fail]}"))
sys.exit(1 if fail else 0)
