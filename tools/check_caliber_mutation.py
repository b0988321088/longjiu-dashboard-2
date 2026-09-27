# -*- coding: utf-8 -*-
"""配息口徑守門（check_dividend_caliber.py）變異測試 — 版控內、可重跑。

用途：證明守門真的抓得到缺陷，而不是永遠綠燈。逐案植入單一缺陷 → 跑守門
→ 比對「相對基準的紅點數」與預期 → 還原 → 逐檔用位元組斷言還原成功。

執行：python tools/check_caliber_mutation.py      （任何工作目錄皆可）
      注意：product 類案例（M2/M4/M6/M7）指向『最新一份』當日產物；若該產物過期
      （守門對它記 SKIP），這些案例會顯示 MISMATCH，屬預期 —— 先讓產物新鮮再跑。
      離開碼：0=全部符合預期、2=有案例 MISMATCH、3=還原失敗（位元組不符）。
副作用：會在 repo 內暫時改檔（全部 try/finally 還原，還原後逐檔比對 bytes）。

設計規則（CIO 審查要求，逐輪累積）：
  1. 先跑基準；可歸因紅＝本次紅 − 基準紅（否則「抓到 N 項」被基準噪音灌水）。
  2. 每案印「錨點命中數」；命中 0＝根本沒植入缺陷（曾是假通過的根因）。
  3. try/finally 還原，還原後逐檔**位元組**斷言（不只看 git）。
  4. **錨點與期望值一律由 snapshot 現算**（四審 N3）：不得寫死當期真值，
     否則真值一動（月初檢視保守底線、逐月覆蓋率）整批退化成「錨點 x0」。
  5. **開跑前後都報工作樹狀態**（四審 N4）：跑前非乾淨會警語；尾行不宣稱
     「乾淨」，只宣稱「與跑前狀態相同」，避免在被弄髒的樹上印出假綠燈。
kind: sub=字串取代 / append=追加一行 / create=新增檔案
已知界線：M6 預期 0 ＝ 守門的已知界線（同一頁重複值只驗存在與成對，見守門檔頭 ⑤）。
"""
import glob
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PY = sys.executable
CHECKER = "check_dividend_caliber.py"

# ── 真值一律現算（不得寫死；真值一動這裡跟著動，案例不會退化成錨點 x0）────────
S = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
PI = S.get("passive_income") or {}


def _q(v):
    return f"{float(v or 0):,.0f}"


def _bump(q, step=1):
    """同格式的『錯值』：把真值 +step，用來當變異後的字面值。"""
    return f"{float(str(q).replace(',', '')) + step:,.0f}"


Q_CON = _q(PI.get("fund_dividend_conservative"))
Q_TOT = _q(PI.get("total_conservative"))
Q_SUR = _q(S.get("retirement_surplus"))
Q_EXP_I = int(float(S.get("monthly_expense") or 0))
COV = float(PI.get("coverage_pct") or 0)
COV_STR = f"{COV:.1f}"
COV_INT, COV_FRAC = COV_STR.split(".")
DAYI_ITEM = next((str(e.get("項目") or "") for e in (S.get("debt_schedule") or [])
                  if "大義街" in str(e.get("項目") or "")), None)
DAYI_AMT = next((float(e.get("金額") or 0) for e in (S.get("debt_schedule") or [])
                 if "大義街" in str(e.get("項目") or "")), 0.0)


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
     "（保守底線 {div_c:,.0f} 判準）", f"（保守底線 {Q_CON} 判準）", 1),
    ("M2  頁面少一個成對標籤", "sub", RETIRE, "當月實收 =", "當月實X =", 1),
    ("M3  RULE 盈餘值走鐘", "sub", "DAILY_REPORT_PIPELINE_RULE.md",
     f"退休後盈餘 **+{Q_SUR}**", f"退休後盈餘 **+{_bump(Q_SUR)}**", 2),
    ("M4  差異分析配息值走鐘", "sub", DIFF,
     f"保守基本值 {Q_CON}", f"保守基本值 {_bump(Q_CON)}", 1),
    ("M5  儀表板基準卡保守底線走鐘", "sub", "index.html",
     f"現行保守底線 {Q_CON}", f"現行保守底線 {_bump(Q_CON)}", 1),
    ("M6  頁面單處覆蓋率值走鐘（已知界線，預期抓不到）", "sub", RETIRE,
     f"{COV_STR}%", f"{COV + 0.1:.1f}%", 0),
    ("M7  差異分析退役字樣回歸", "sub", DIFF,
     "<html", "保守配息：<!--x--></html><html", 1),
    ("M8  儀表板常態被動值走鐘", "sub", "index.html",
     f'data-k="passive_norm">{Q_TOT}</span>', f'data-k="passive_norm">{_bump(Q_TOT)}</span>', 1),
    ("M9  生成器數值常數寫死（數值常數分支）", "sub", "build_retirement_plan.py",
     'fire_cost = pi.get("monthly_expense") or snap.get("monthly_expense") or 0',
     f'fire_cost = pi.get("monthly_expense", {Q_EXP_I})', 1),
    ("M10 未宣告程式檔（新硬擋路徑）", "create", "_mut_undeclared_probe.py", "", "", 1),
    ("M11 大義街月繳寫死（debt_schedule 真值 token）", "sub", "build_retirement_plan.py",
     "{rent - _dayi:,.0f}", f"{{rent - {int(DAYI_AMT)}:,}}", 1),
    ("M12 拼接字面繞過（常數摺疊分支）", "append", "build_retirement_plan.py",
     "", f'_probe_split = "{COV_INT}" + ".{COV_FRAC}"    # 變異測試用，finally 會還原\n', 1),
    ("M13 V 對映來源式被改成常數（N1 來源式斷言）", "sub", "index_template.html",
     f"passive_norm: fmt(((s.passive_income||{{}}).total_conservative)||0)",
     "passive_norm: fmt(0)", 2),
    ("M14 大義街名稱查不到（R3 fail-closed 斷言）", "sub", "snapshot.json",
     DAYI_ITEM or "", (DAYI_ITEM or "").replace("房貸", "房X"), 2),
]

# ── 跨檔案例：需要同時改兩檔才成形的「假修好」（五審 N6）────────────────────
# V_PN 是來源式字串（不是當期真值），用來當誘餌與原式比對。
V_PN = "fmt(((s.passive_income||{}).total_conservative)||0)"

CROSS = [
    ("M15 誘餌註解（V 物件外）＋V 餵 fmt(0)（兩檔同步；整檔 re.search 會被騙）",
     [("index_template.html", f"passive_norm: {V_PN}", "passive_norm: fmt(0)"),
      ("index.html", f"passive_norm: {V_PN}", "passive_norm: fmt(0)"),
      ("index_template.html", "var V = {", f"// passive_norm: {V_PN}\nvar V = {{"),
      ("index.html", "var V = {", f"// passive_norm: {V_PN}\nvar V = {{")],
     1),
]

BEFORE = git_status()
base_rc, base_fails, base_skips = run()
print(f"基準：rc={base_rc} 既有紅={base_fails if base_fails else '（無）'}")
if BEFORE.strip():
    print("⚠️ 跑前工作樹非乾淨（下列為跑前既有異動；若含本工具會觸碰的檔案，"
          "該案基準紅可能已受污染 —— 判讀時請一併看『錨點 xN』）：")
    for _ln in BEFORE.splitlines():
        print("   ", _ln)
if base_skips:
    print("基準 SKIP（product 類案例可能因此 MISMATCH）：")
    for s in base_skips:
        print("   ", s)
print(f"真值（現算）：保守底線 {Q_CON}／常態被動 {Q_TOT}／盈餘 {Q_SUR}／覆蓋率 {COV_STR}%／大義街 {_q(DAYI_AMT)}")
print(f"產物：{RETIRE} ／ {DIFF}\n")

ok_all = 0
restore_fail = []
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
                p.write_bytes(txt.replace(old, new, 1).encode("utf-8"))
        elif kind == "append":
            txt = orig.decode("utf-8")
            hit = 1
            p.write_bytes((txt + new).encode("utf-8"))
        else:  # create
            hit = 0 if p.exists() else 1
            p.write_bytes("# 變異測試用\n".encode("utf-8"))
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
        same = (p.read_bytes() == orig) if orig is not None else (not p.exists())
        if not same:
            restore_fail.append(relpath)

for name, edits, exp in CROSS:
    saved, hit = {}, 0
    try:
        for rel, old, new in edits:
            p = BASE / rel
            if rel not in saved:
                saved[rel] = p.read_bytes()
            txt = p.read_bytes().decode("utf-8")
            c = txt.count(old)
            hit += c
            if c:
                p.write_bytes(txt.replace(old, new, 1).encode("utf-8"))
        rc, fails, _ = run()
        attr = [f for f in fails if f not in base_fails]
        good = (len(attr) == exp)
        ok_all += good
        print(f"[{name}] kind=cross 錨點 x{hit} rc={rc} 注入後紅={len(fails)} 基準紅={len(base_fails)} "
              f"→ 可歸因 {len(attr)}（期望 {exp}）{'OK' if good else 'MISMATCH'}")
        for a in attr:
            print("      ❌", a)
    finally:
        for rel, _b in saved.items():
            (BASE / rel).write_bytes(_b)
            if (BASE / rel).read_bytes() != _b:
                restore_fail.append(rel)

print(f"\n結果：{ok_all}/{len(MUT) + len(CROSS)} 案例符合預期")
if restore_fail:
    print("❌ 還原失敗（位元組不符）：", restore_fail)
    sys.exit(3)
if ok_all != len(MUT) + len(CROSS):
    print(f"❌ 有 {len(MUT) + len(CROSS) - ok_all} 個案例不符合預期（MISMATCH）→ 離開碼 2")
    sys.exit(2)
print("工具觸碰檔還原：" + ("與跑前逐位元組相同 ✓（逐檔斷言通過）"
      + ("；跑前這些檔就有異動，見上方清單" if BEFORE.strip() else "") ))
_now = git_status()
print("   工作樹狀態：" + ("與跑前逐字相同 ✓" if _now == BEFORE
      else "⚠️ 與跑前不同（可能為其他排程同時寫入，非本工具觸碰檔；請自行判讀）：\n" + _now))
