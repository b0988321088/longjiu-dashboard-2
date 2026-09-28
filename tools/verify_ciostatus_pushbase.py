# -*- coding: utf-8 -*-
"""唯讀驗證器：cio_approve.py --status 比較基準修正（push_base）

設計原則（2026-09-28 二審退回後重寫）：
  **全部狀態無關** — 不得假設 HEAD 已推送或已通過審查（交付前必然不成立）。
  - 基準正確性：直接呼叫 cio_approve.push_base() 驗優先序與 sha（不經 CLI）
  - CLI 行為：--status 的未推筆數必須等於 `git rev-list --count origin/clean-main..HEAD`
    現算值；被列的 commit 清單必須與該清單逐一對應（不多不少）
  - 舊基準（@{u}）規模：未推筆數 ≥ origin/main 落後量（假紅成因的量化證據）
  - 負向對照：釘 parent 匯出舊版；其標 ❌ 者必為「假紅（已在 clean-main 上）」
    ∪「真正未推」兩集合之聯集，且假紅集合非空
  - FAIL 時 exit 1（具閘門效力）
"""
import ast
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent   # repo 根
TMP = Path(tempfile.gettempdir())
os.chdir(BASE)
sys.path.insert(0, str(BASE))
PASS = FAIL = 0


def ck(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label} ｜{detail}")


def sh(*args):
    return subprocess.run(list(args), cwd=str(BASE), capture_output=True, text=True,
                          encoding="utf-8")


def count_unpushed() -> str:
    return sh("git", "rev-list", "--count", "origin/clean-main..HEAD").stdout.strip()


def unpushed_shorts() -> set:
    return {c[:12] for c in sh("git", "rev-list", "origin/clean-main..HEAD").stdout.split()}


print("[1] 語法閘門")
src = (BASE / "cio_approve.py").read_text(encoding="utf-8")
try:
    ast.parse(src)
    ck("cio_approve.py AST 可解析", True)
except SyntaxError as e:
    ck("cio_approve.py AST 可解析", False, str(e))
ck("含 push_base helper", "def push_base()" in src)
ck("--status 不再直接以 @{u} 當唯一基準",
   'up = git("rev-parse", "--verify", "--quiet", "@{u}") if has_upstream() else ""' not in src)

print("\n[2] 修正本體：push_base() 契約（狀態無關）")
import cio_approve as CA  # noqa: E402

ref, sha = CA.push_base()
expect_sha = sh("git", "rev-parse", "--verify", "origin/clean-main^{commit}").stdout.strip()
ck("基準 ref == origin/clean-main", ref == "origin/clean-main", ref)
ck("基準 sha == git rev-parse origin/clean-main", sha == expect_sha, f"{sha[:12]} vs {expect_sha[:12]}")
ck("_rev_quiet 對不存在 ref 回空字串（不 sys.exit）",
   CA._rev_quiet("origin/__nosuchref_for_verify__") == "")
ck("has_upstream 死碼已清除（無呼叫者時不應殘留）", "def has_upstream" not in src)

print("\n[3] CLI --status：與實際未推清單一致（狀態無關）")
actual = count_unpushed()
new = sh(sys.executable, str(BASE / "cio_approve.py"), "--status")
ck("顯示基準為 origin/clean-main", "相對 origin/clean-main" in new.stdout)
ck("不再出現『相對 @{u}』字樣", "@{u}" not in new.stdout)
m = re.search(r"未推送 commit（相對 origin/clean-main）：(\d+) 筆", new.stdout)
ck("未推筆數 == git rev-list 現算", bool(m) and m.group(1) == actual,
   f"CLI={m.group(1) if m else '-'}／rev-list={actual}")
listed = set(re.findall(r"^\s+[✅❌] ([0-9a-f]{12})  tree", new.stdout, re.M))
ck("列出的 commit 集合 == 實際未推集合（不多不少）", listed == unpushed_shorts(),
   f"only_in_cli={sorted(listed - unpushed_shorts())[:3]} only_in_git={sorted(unpushed_shorts() - listed)[:3]}")
ck("exit code 與未推筆數一致（0 筆才 0）",
   new.returncode == (0 if actual == "0" else 1), f"rc={new.returncode} actual={actual}")
if actual == "0":
    ck("（此刻 HEAD 已推）出現『無待推 commit』", "✅ 無待推 commit" in new.stdout)
else:
    ck(f"（此刻 HEAD 尚未推，{actual} 筆）未出現『無待推 commit』",
       "✅ 無待推 commit" not in new.stdout)

print("\n[4] 負向對照：舊版（基準 @{u}）重現假紅")
parent = sh("git", "rev-parse", "HEAD^").stdout.strip()
print(f"  （負向對照基準 parent = {parent[:12]}）")
old_src = sh("git", "show", f"{parent}:cio_approve.py").stdout
ck("舊版原始碼取自 parent（== 修正前）", "def push_base()" not in old_src and len(old_src) > 1000)
old_path = TMP / "cio_approve_old_forverify.py"
old_path.write_text(old_src, encoding="utf-8")
old = sh(sys.executable, str(old_path), "--status")
ck("舊版顯示基準 @{u}", "相對 @{u}" in old.stdout)
m2 = re.search(r"未推送 commit（相對 @\{u\}）：(\d+) 筆", old.stdout)
behind = sh("git", "rev-list", "--count", "origin/main..origin/clean-main").stdout.strip()
ck("舊版未推筆數 ≥ origin/main 落後量（假紅規模量化）",
   bool(m2) and int(m2.group(1)) >= int(behind), f"舊={m2.group(1) if m2 else '-'} 落後={behind}")
ck("舊版標 ❌ 者 ≥（落後量 − 其中已審的）> 0", "❌" in old.stdout)

print("\n[5] 假紅證據：舊版 ❌ 集合 == 假紅（已在 clean-main）× 真正未推")
bad_old = re.findall(r"❌ ([0-9a-f]{12})  tree", old.stdout)
unp = unpushed_shorts()
fake = [b for b in bad_old if b not in unp]
ck("舊版有標 ❌ 的 commit", len(bad_old) > 0, f"{len(bad_old)} 顆")
ck("假紅集合非空（本修正的標的）", len(fake) > 0, f"{len(fake)} 顆")
not_on_main = []
for short in fake:
    full = sh("git", "rev-parse", short).stdout.strip()
    if sh("git", "merge-base", "--is-ancestor", full, "origin/clean-main").returncode != 0:
        not_on_main.append(short)
ck(f"全部 {len(fake)} 顆假紅都確實在 origin/clean-main 上", not not_on_main, str(not_on_main))
ck("舊版 ❌ 集合 == 假紅 ∪ 真正未推（無其他類別）", set(bad_old) == set(fake) | unp,
   f"diff={sorted(set(bad_old) ^ (set(fake) | unp))[:3]}")

print(f"\n{'=' * 46}\n{PASS}/{PASS + FAIL} PASS" + ("" if FAIL == 0 else f" — FAIL {FAIL} 項"))
print("ALL PASS" if FAIL == 0 else "HAS FAIL")
sys.exit(1 if FAIL else 0)
