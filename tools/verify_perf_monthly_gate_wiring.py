# -*- coding: utf-8 -*-
"""verify_perf_monthly_gate_wiring.py — 每日管線「自動化防守」接線閘門（唯讀，含負測）

目的（使用者 2026-10-03 裁示，定位＝自動化防守，非績效功能）：
  確認 07:00 `regenerate_report.py` 真的會在「月度比較頁數字 ≠ performance_core 輸出」時**擋住推送**，
  且不修改任何績效計算邏輯／頁面／口徑。

檢查：
  1. AST：regenerate_report.py 可解析
  2. 接線存在：呼叫 tools/verify_performance_monthly.py（且該檔存在）
  3. fail-closed：推送條件含閘門旗標；閘門 rc≠0 與例外兩條路徑都會把旗標設 False；行程 exit 含閘門旗標
  4. 行為負測：把頁面植入 9,999,999 → 同一條指令必須 rc≠0；還原後必須 rc=0 且檔案位元完全還原
  5. 範圍：本次 commit 只動本批檔案（regenerate_report.py ＋本驗證器），未碰績效計算層與頁面

用法：python tools/verify_perf_monthly_gate_wiring.py [<commit-sha>=HEAD]
"""
import ast
import hashlib
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
GEN = BASE / "regenerate_report.py"
GATE = BASE / "tools" / "verify_performance_monthly.py"
PAGE = BASE / "performance_monthly.html"

FAIL = 0


def chk(ok: bool, label: str, detail: str = "") -> None:
    global FAIL
    if not ok:
        FAIL += 1
    print(f"  {'✅' if ok else '❌'} {label}" + (f" — {detail}" if detail else ""))


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(BASE), **kw)


SHA = (sys.argv[1] if len(sys.argv) > 1 else "HEAD")
sha = run(["git", "rev-parse", f"{SHA}^{{commit}}"]).stdout.strip()
src = GEN.read_text(encoding="utf-8")

print("== 1. AST ==")
try:
    ast.parse(src)
    chk(True, "regenerate_report.py AST 可解析")
except SyntaxError as e:
    chk(False, "regenerate_report.py AST 可解析", str(e))

print("== 2. 接線存在 ==")
chk("tools" in src and "verify_performance_monthly.py" in src, "管線有呼叫 tools/verify_performance_monthly.py")
chk(GATE.exists(), "驗證器檔案存在")

print("== 3. fail-closed（結構）==")
chk(re.search(r"_gate_ok\s*=\s*True", src) is not None, "閘門旗標有初始化（預設 True）")
chk(re.search(r"if _push_files and _gate_ok:", src) is not None, "推送條件含閘門旗標（FAIL 不推）")
_rc_path = re.search(r"_gate_ok\s*=\s*_vg\.returncode\s*==\s*0", src) is not None
_exc_path = re.search(r"except[^\n]*:\s*\n(?:\s*#[^\n]*\n)*\s*_gate_ok\s*=\s*False", src) is not None
chk(_rc_path and _exc_path, "閘門 FAIL 的兩條路徑都會把旗標設 False（rc≠0 ／ 例外）",
    f"rc_path={_rc_path} exc_path={_exc_path}")
chk("_pages_ok and _gate_ok" in src, "行程 exit 含閘門旗標")

print("== 4. 行為負測（閘門指令真的會擋）==")
orig_bytes = PAGE.read_bytes()
orig_sha = hashlib.sha256(orig_bytes).hexdigest()
neg_rc = pos_rc = None
try:
    r0 = run([sys.executable, str(GATE)])
    pos_rc = r0.returncode
    chk(pos_rc == 0, "還原狀態下閘門 PASS（rc=0）", f"rc={pos_rc}")
    PAGE.write_bytes(orig_bytes.replace("◆ 資本基準月".encode(), "◆ 資本基準月 <span>9,999,999</span>".encode(), 1))
    r1 = run([sys.executable, str(GATE)])
    neg_rc = r1.returncode
    chk(neg_rc != 0, "植入硬編數字後閘門 FAIL（rc≠0 → 管線會擋推）", f"rc={neg_rc}")
finally:
    PAGE.write_bytes(orig_bytes)
chk(hashlib.sha256(PAGE.read_bytes()).hexdigest() == orig_sha, "負測後頁面位元完全還原")

print("== 5. 範圍（本次只動本批檔案）==")
if sha:
    st = run(["git", "show", "--stat", "--format=", sha]).stdout.strip()
    files = sorted({ln.split("|")[0].strip() for ln in st.splitlines() if "|" in ln})
    allow = {"regenerate_report.py", "tools/verify_perf_monthly_gate_wiring.py"}
    chk(set(files) <= allow, "commit 只動本批檔案", ", ".join(files))
    chk("performance_core.py" not in files and "build_performance_monthly.py" not in files,
        "未碰績效計算層")
    chk("performance_monthly.html" not in files, "未碰頁面產物（口徑/頁面皆未改）")

print(f"\n=== 接線閘門：{'PASS' if FAIL == 0 else 'FAIL'}（FAIL {FAIL}）===")
sys.exit(1 if FAIL else 0)
