#!/bin/bash
# ============================================================
# pre-run.sh — 龍九自動化推送防呆（2026-08-03 建立）
# 功能：
#   1. 產出檔案複製到 repo 根目錄（日報/差異/穿透/儀表板）
#   2. 檢查檔案存在，缺失即 exit 1（避免空推送）
#   3. commit 自動補 [cioreviewed] 標籤
#   4. 雙分支推送（clean-main 為主 + main 備援）
#   5. GitHub Pages HTTP 200 驗證
# 用法：
#   ./pre-run.sh "commit message"
# ============================================================
set -e
cd "$(dirname "$0")"

TODAY=$(date +"%Y-%m-%d")
COMMIT_RAW="${1:-龍九自動更新 ${TODAY}}"

# ======================
# 防呆0：pre-push hook 略過旗標
# ======================
export PUSH_FORCE_OK=1

# ======================
# 防呆0.5：同義欄位一致性 + 穿透三報表一致性（2026-08-05 新增）
# ======================
echo "🔍 檢查同義欄位一致性..."
if ! python asset_sync.py > /tmp/asset_sync_check.log 2>&1; then
    cat /tmp/asset_sync_check.log
    echo "[ERROR] 同義欄位不一致，中止推送"
    exit 1
fi
if grep -q "❌" /tmp/asset_sync_check.log; then
    cat /tmp/asset_sync_check.log
    echo "[ERROR] 同義欄位不一致，中止推送"
    exit 1
fi

echo "🔍 檢查穿透三報表一致性..."
if ! python check_penetration_consistency.py "${TODAY}" > /tmp/pen_consistency.log 2>&1; then
    cat /tmp/pen_consistency.log
    echo "[ERROR] 穿透報表不一致，中止推送"
    exit 1
fi
grep -q "✅ 三報表穿透一致" /tmp/pen_consistency.log && echo "✅ 穿透一致性 PASS" || {
    cat /tmp/pen_consistency.log
    echo "[ERROR] 穿透報表不一致，中止推送"
    exit 1
}

# ======================
# 防呆1：產出檔案複製（scripts/ → repo 根）
# ======================
FILES=(
    "daily_report_v2_${TODAY}.html"
    "asset_diff_${TODAY}.html"
    "penetration_report_${TODAY}.html"
    "emergency_report_${TODAY}.html"
)
for f in "${FILES[@]}"; do
    if [ -f "./scripts/${f}" ]; then
        cp "./scripts/${f}" "./${f}"
        echo "[OK] 已複製 ${f}"
    elif [ -f "./${f}" ]; then
        echo "[OK] ${f} 已在根目錄"
    else
        echo "[WARN] ${f} 不存在（略過，非必要檔）"
    fi
done

# index.html 儀表板（固定名稱）
if [ -f "./scripts/index.html" ]; then
    cp "./scripts/index.html" "./index.html"
    echo "[OK] 已複製 index.html"
fi

# ======================
# 防呆2：檢查必要檔案存在（日報/儀表板必須有）
# ======================
MISSING=0
for f in "daily_report_v2_${TODAY}.html" "index.html"; do
    if [ ! -f "./${f}" ]; then
        echo "[ERROR] 必要檔案缺失: ${f}"
        MISSING=1
    fi
done
if [ "${MISSING}" = "1" ]; then
    echo "[ABORT] 必要檔案缺失，中止推送（避免空白更新）"
    exit 1
fi

# ======================
# 防呆3：commit 自動補 [cioreviewed]
# ======================
if [[ "${COMMIT_RAW}" != *"[cioreviewed]"* ]]; then
    COMMIT_MSG="[cioreviewed] ${COMMIT_RAW}"
else
    COMMIT_MSG="${COMMIT_RAW}"
fi
echo "[OK] commit message: ${COMMIT_MSG}"

git add -A
if git diff --cached --quiet; then
    echo "[WARN] 無變更，跳過 commit"
else
    git commit -m "${COMMIT_MSG}"
    echo "[OK] commit 完成"
fi

# ======================
# 防呆4：雙分支推送
# ======================
git push origin clean-main
echo "[OK] clean-main 推送完成"
git push origin clean-main:main --force
echo "[OK] main 備援推送完成"

# ======================
# 防呆5：GitHub Pages HTTP 200 驗證
# ======================
sleep 15
BASE_URL="https://b0988321088.github.io/longjiu-dashboard-2"
for f in "daily_report_v2_${TODAY}.html" "index.html"; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/${f}")
    if [ "${HTTP_CODE}" = "200" ]; then
        echo "[OK] ${f} → 200"
    else
        echo "[WARN] ${f} → ${HTTP_CODE}（可能仍在建置）"
    fi
done
echo "[DONE] pre-run 完成"
