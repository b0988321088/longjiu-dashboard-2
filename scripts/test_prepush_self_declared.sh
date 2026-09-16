#!/usr/bin/env bash
# 沙箱驗測：pre-push v4.3 的「自宣告紀錄不得替程式檔背書」規則（INC-204）
#
# 用法：bash scripts/test_prepush_self_declared.sh      （在 repo 根目錄執行；唯讀、不動本 repo）
#
# 沙箱結構：本 repo 的 .githooks/ 複製到 TMP 的暫存 repo，配上本機 bare remote，
# 每個案例用 orphan branch（＝單一 commit、無共同祖先）單獨推，互不干擾。
#
# 五個案例：
#   A 程式檔 + 舊式自寫紀錄（note 空、無標記）      → 應放行（維持 v4.2 行為，不溯及既往）
#   B 程式檔 + SELF-DECLARED 紀錄                    → 應擋（新規則）
#   C 資料檔 + SELF-DECLARED 紀錄                    → 應放行（純資料不受影響）
#   D 程式檔 + SELF-DECLARED ＋ 真審查紀錄各一筆     → 應放行（優先採非自宣告者）
#   E 程式檔 + 無任何紀錄                            → 應擋（原有 fail-closed）
#   G 程式檔 + 真審查但 note 文字提到 SELF-DECLARED      → 應放行（回歸測試：標記不得用 note 子字串判定）
set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
TMPBASE="$(cygpath -m "${LOCALAPPDATA:-$HOME/AppData/Local}")/Temp"
SB="$TMPBASE/prepush_sandbox_$$"
rm -rf "$SB"; mkdir -p "$SB/remote.git" "$SB/work"
git init -q --bare "$SB/remote.git" || exit 1
git init -q "$SB/work" || exit 1

cd "$SB/work" || exit 1
git config user.email sandbox@test.local
git config user.name sandbox
git config commit.gpgsign false
# 鉤子放在 worktree 之外（$SB/hooks）：若放進 worktree，.githooks/pre-push 本身是程式檔，
# 會被算進每個案例的變更清單 → 所有案例都「含程式檔」，測試就失去意義（本次實踩）。
HOOKDIR="$SB/hooks"
mkdir -p "$HOOKDIR"
cp "$REPO"/.githooks/pre-push "$HOOKDIR/pre-push"
git config core.hooksPath "$HOOKDIR"
git remote add origin "$SB/remote.git"

PASS=0; FAIL=0

_rec() { # _rec <tree> <commit> <reviewer> <note>
  printf '%s\t%s\t%s\tAPPROVE\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$3" "$4" >> .git/CIO_APPROVED
}

_case() { # _case <name> <expect pass|block> <branch> <grep-key-or-->
  local name="$1" expect="$2" branch="$3" key="$4" out rc verdict
  out=$(git push origin "$branch" 2>&1); rc=$?
  if [ "$expect" = "pass" ]; then
    if [ $rc -eq 0 ]; then verdict="PASS(放行)"; else verdict="FAIL(被擋 rc=$rc)"; fi
  else
    if [ $rc -ne 0 ] && { [ "$key" = "-" ] || printf '%s' "$out" | grep -q "$key"; }; then
      verdict="PASS(已擋)"
    else
      verdict="FAIL(未擋 rc=$rc)"
    fi
  fi
  case "$verdict" in PASS*) PASS=$((PASS+1));; *) FAIL=$((FAIL+1));; esac
  printf '  %-58s %s\n' "$name" "$verdict"
  case "$verdict" in
    FAIL*)
      printf '      ── 診斷（hook 輸出節錄）──\n'
      printf '%s\n' "$out" | grep -E "commit |僅有|無審查|AUTO-checker|\[cioreviewed\]|SELF-DECLARED" | head -4 | sed 's/^/      /'
      ;;
  esac
}

_new_branch() { # _new_branch <branch> <file> <content>
  git checkout -q --orphan "$1" 2>/dev/null || git checkout -q "$1"
  git rm -rq --cached . 2>/dev/null
  rm -rf app.py data.json
  printf '%s\n' "$3" > "$2"
  git add -A
  git commit -qm "sandbox $1" || true
}

echo "沙箱：$SB"
echo "--- 五個案例 ---"

# A 程式檔 + 舊式紀錄（無 SELF-DECLARED 標記）
_new_branch caseA app.py "print('a')"
S=$(git rev-parse HEAD); _rec "$(git rev-parse HEAD^{tree})" "$S" "CIO-Gemini" ""
_case "A 程式檔+舊式紀錄(無標記) → 應放行" pass caseA -

# B 程式檔 + SELF-DECLARED
_new_branch caseB app.py "print('b')"
S=$(git rev-parse HEAD); _rec "$(git rev-parse HEAD^{tree})" "$S" "SELF-DECLARED:CIO-Gemini" "自寫"
_case "B 程式檔+SELF-DECLARED → 應擋" block caseB "僅有自宣告紀錄"

# C 資料檔 + SELF-DECLARED
_new_branch caseC data.json '{"k":1}'
S=$(git rev-parse HEAD); _rec "$(git rev-parse HEAD^{tree})" "$S" "SELF-DECLARED:CIO-Gemini" "自寫"
_case "C 資料檔+SELF-DECLARED → 應放行" pass caseC -

# D 程式檔 + SELF-DECLARED ＋ 真審查（優先採非自宣告）
_new_branch caseD app.py "print('d')"
S=$(git rev-parse HEAD); T=$(git rev-parse HEAD^{tree})
_rec "$T" "$S" "SELF-DECLARED:CIO-Gemini" "自寫"
_rec "$T" "$S" "CIO-DeepSeek-V4Pro" "實跑審查 APPROVE"
_case "D 程式檔+自宣告&真審查各一 → 應放行" pass caseD -

# E 程式檔 + 無紀錄
_new_branch caseE app.py "print('e')"
_case "E 程式檔+無紀錄 → 應擋" block caseE "無審查紀錄"

# F 一般（有 parent）程式檔 commit + SELF-DECLARED → 驗常規推送路徑
git checkout -q caseA
printf "print('f')\n" > app.py
git add -A; git commit -qm "sandbox caseF"
S=$(git rev-parse HEAD); _rec "$(git rev-parse HEAD^{tree})" "$S" "SELF-DECLARED:CIO-Gemini" "自寫"
_case "F 一般(有parent)程式檔+SELF-DECLARED → 應擋" block caseA "僅有自宣告紀錄"

# G 程式檔 + 真審查，但 **note 文字裡剛好寫到 SELF-DECLARED** → 應放行
#   （回歸測試：第一版把標記寫在 note、用子字串比對，導致這顆真審查紀錄被誤擋）
_new_branch caseG app.py "print('g')"
S=$(git rev-parse HEAD); _rec "$(git rev-parse HEAD^{tree})" "$S" "CIO-DeepSeek-V4Pro" "pre-push v4.3 SELF-DECLARED 規則;複審 APPROVE"
_case "G 程式檔+真審查(note 提到 SELF-DECLARED) → 應放行" pass caseG -

echo "--- 結果 ---"
echo "PASS=$PASS  FAIL=$FAIL"
if [ "$FAIL" -eq 0 ]; then echo "SANDBOX ALL PASS"; else echo "SANDBOX FAILED"; fi
rm -rf "$SB"
exit $(( FAIL > 0 ? 1 : 0 ))
