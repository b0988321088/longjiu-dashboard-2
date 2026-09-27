# -*- coding: utf-8 -*-
"""配息口徑守門（check_dividend_caliber.py）變異測試 — 版控內、可重跑。

用途：證明守門真的抓得到缺陷，而不是永遠綠燈。逐案植入單一缺陷 → 跑守門
→ 比對「相對基準的紅點數」與預期 → 還原 → 最後驗證工作樹與執行前相同。

執行：python tools/check_caliber_mutation.py      （任何工作目錄皆可）
副作用：會在 repo 內暫時改檔（全部 try/finally 還原）。請先確認工作樹乾淨。
        product 類案例指向「最新一份」當日產物；若該產物過期（守門記 SKIP），
        該案例會顯示 MISMATCH，屬預期 — 先讓產物新鮮再跑。

規則（CIO 2026-09-28 三輪審查要求）：
  1. 先跑基準；可歸因紅＝本次紅 − 基準紅（否則「抓到 N 項」會被基準噪音灌水）。
  2. 每案都印「錨點命中數」；命中 0 表示根本沒植入缺陷（前一輪 M2 就是這樣假通過）。
  3. 每案在 try/finally 內還原，最後比對 git status 確認還原乾淨。
kind: sub=字串取代 / create=新增檔案 / append=追加一行
已知界線：M6 預期 0 ＝ 守門的已知界線（同一頁重複值只驗存在與成對，見守門檔頭 ⑤）。
"""
import glob
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PY = sys.executable
CHECKER = "check_dividend_caliber.py"


def latest(pat):
    """指「最新一份」當日產物（不釘死日期，否則一過期整支就爆）。"""
    hits = sorted(glob.glob(str(BASE / pat)))
    return Path(hits[-1]).name if hits else None


RETIRE = latest("retirement_plan_*.html")
DIFF = latest("asset_diff_*.html")


def run():
    r = subprocess.run([PY, CHECKER], cwd=str(BASE), capture_output=True,
                       text=True, encoding="utf-8")
    out = r.stdout or ""
    fails = [ln.strip() for ln in out.splitlines() if ln.startswith("❌")]
    skips = [ln.strip() for ln in out.splitlines() if ln.startswith("⏭")]
    return r.returncode, sorted({f.split("｜")[0].replace("❌", "").strip() for f in fails}), skips


def git_status():
    return subprocess.run(["git", "status", "--porcelain"], cwd=str(BASE),
                          capture_output=True, text=True, encoding="utf-8").stdout


MUT = [
    ("M1  生成器重新寫死當期底線（字串常數分支）", "sub", "build_retirement_plan.py",
     "（保守底線 {div_c:,.0f} 判準）", "（保守底線 100,000 判準）", 1),
    ("M2  頁面少一個成對標籤", "sub", RETIRE, "當月實收 =", "當月實X =", 1),
    ("M3  RULE 盈餘值走鐘", "sub", "DAILY_REPORT_PIPELINE_RULE.md",
     "退休後盈餘 **+17,319**", "退休後盈餘 **+17,320**", 2),
    ("M4  差異分析配息值走鐘", "sub", DIFF, "保守基本值 100,000", "保守基本值 130,930", 1),
    ("M5  儀表板基準卡保守底線走鐘", "sub", "index.html", "現行保守底線 100,000", "現行保守底線 130,930", 1),
    ("M6  頁面單處覆蓋率值走鐘（已知界線，預期抓不到）", "sub", RETIRE, "110.6%", "999.9%", 0),
    ("M7  差異分析退役字樣回歸", "sub", DIFF,
     "<html", "保守配息：<!--x--></html><html", 1),
    ("M8  儀表板常態被動值走鐘", "sub", "index.html",
     'data-k="passive_norm">180,100</span>', 'data-k="passive_norm">999,999</span>', 1),
    ("M9  生成器數值常數寫死（數值常數分支）", "sub", "build_retirement_plan.py",
     'fire_cost = pi.get("monthly_expense") or snap.get("monthly_expense") or 0',
     'fire_cost = pi.get("monthly_expense", 162781)', 1),
    ("M10 未宣告程式檔（新硬擋路徑）", "create", "_mut_undeclared_probe.py", "", "", 1),
    ("M11 大義街月繳寫死（debt_schedule 真值 token）", "sub", "build_retirement_plan.py",
     "{rent - _dayi:,.0f}", "{rent - 26000:,}", 1),
    ("M12 拼接字面繞過（常數摺疊分支）", "append", "build_retirement_plan.py",
     "", '_probe_split = "110" + ".6"    # 變異測試用，finally 會還原\n', 1),
]

BEFORE = git_status()
base_rc, base_fails, base_skips = run()
print(f"基準：rc={base_rc} 既有紅={base_fails if base_fails else '（無）'}")
if base_skips:
    print("基準 SKIP（product 類案例可能因此 MISMATCH）：")
    for s in base_skips:
        print("   ", s)
print(f"產物：{RETIRE} ／ {DIFF}\n")

ok_all = 0
for name, kind, relpath, old, new, exp in MUT:
    if relpath is None:
        print(f"[{name}] 找不到對應產物 → 無法執行")
        continue
    p = BASE / relpath
    orig = p.read_bytes() if p.exists() else None
    hit = None
    try:
        if kind == "sub":
            txt = orig.decode("utf-8")
            hit = txt.count(old)
            if hit:
                p.write_text(txt.replace(old, new, 1), encoding="utf-8")
        elif kind == "append":
            txt = orig.decode("utf-8")
            hit = 1
            p.write_text(txt + new, encoding="utf-8")
        else:  # create
            hit = 0 if p.exists() else 1
            p.write_text("# 變異測試用\n", encoding="utf-8")
        rc, fails, _ = run()
        attr = [f for f in fails if f not in base_fails]
        good = (len(attr) == exp)
        ok_all += good
        print(f"[{name}] kind={kind} 錨點 x{hit} rc={rc} 注入後紅={len(fails)} 基準紅={len(base_fails)} "
              f"→ 可歸因 {len(attr)}（期望 {exp}）{'OK' if good else 'MISMATCH'}")
        for a in attr:
            print("      ❌", a)
    finally:
        if kind == "create":
            if orig is None and p.exists():
                p.unlink()
        elif orig is not None:
            p.write_bytes(orig)

print(f"\n結果：{ok_all}/{len(MUT)} 案例符合預期")
print("還原檢查：", "乾淨（與執行前相同）" if git_status() == BEFORE else "⚠️ 有殘留！\n" + git_status())
