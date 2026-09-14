# -*- coding: utf-8 -*-
"""nightly_dashboard_sync.py — 每晚 22:15 行動儀表板 JSON 自動 commit+push（2026-09-05 建立）

行動儀表板為 client-side（讀 radar_state/schedule_events/work_log/snapshot/pending/decisions），
JSON 變更需 commit+push 到 GitHub 才會上線。此腳本把當天變更收斂一次：
- 無變更 → 印 SKIP，exit 0（供 cron [SILENT]）
- 有變更 → commit → 落 RECORD（auto_record，P2 起） → push clean-main + main
設計：從 hermes/scripts 執行（cron 慣例），用 git -C 指向 repo，不依賴 cwd。
"""
import subprocess, sys, datetime

REPO = r"C:/Users/bot/Desktop/longjiu_system"
FILES = [
    "radar_state.json",       # 雷達/本週該做（行動儀表板②）
    "schedule_events.json",   # 行事曆 今天/未來3天（行動儀表板③）
    "work_log.json",          # 系統工作日誌卡
    "snapshot.json",          # 儀表板數字主源
    "pending_decisions.json", # 決策待辦
    "dashboard_decisions.json",  # 決策追蹤/審計
    "us30y_state.json",       # US30Y 模式燈號
]

def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, encoding="utf-8")

today = datetime.date.today().isoformat()
git("add", "--", *FILES)
st = git("status", "--porcelain", "--", *FILES)
if not st.stdout.strip():
    # 本任務 7 檔無變更即 SKIP；其他檔案的髒狀態（如 dragon_assets.db 被夜間維護
    # 清理後未 commit）不屬本任務，不觸發也不阻擋（2026-09-06 修：原先全樹
    # porcelain 會被髒檔誤觸發 → 只 stage 7 檔 → "no changes added to commit" 失敗）
    sys.exit(0)
print("變更檔:\n" + st.stdout)

msg = f"nightly dashboard sync {today}"
c = git("commit", "-m", msg)
print(c.stdout.strip() or c.stderr.strip())
if c.returncode != 0:
    print("COMMIT FAIL"); sys.exit(1)

# P2（2026-09-14）：改走 RECORD 通道 —— commit 後先落紀錄再 push。
# 本檔只 stage 7 個 JSON 資料檔 → auto_record 的 deterministic 檢查（不得含程式檔／
# JSON 可解析／工作區守門）正好對得上；未過 → 不落紀錄 → 閘門擋下（寧可斷、不要無審上線）。
r = subprocess.run([sys.executable, "auto_record.py", "--script", "nightly_dashboard_sync.py"],
                   cwd=REPO, capture_output=True, text=True, encoding="utf-8")
print((r.stdout or "").strip() or (r.stderr or "").strip())
if r.returncode != 0:
    print("RECORD FAIL（不推送）"); sys.exit(1)

for ref in ("clean-main", "clean-main:main"):
    p = git("push", "origin", ref)
    print(f"push {ref}: {p.stdout.strip()[:120] or p.stderr.strip()[:120]}")
    if p.returncode != 0:
        print("PUSH FAIL", ref); sys.exit(1)

print(f"OK: 已推送 {today} 儀表板同步")
