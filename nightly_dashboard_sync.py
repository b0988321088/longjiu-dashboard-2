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

# ── 2026-10-13（台股緊急應變發布故障共同根因）──────────────────────────────
# 本任務 7 檔全部落在閘門「強制真 CIO」集合（snapshot.json／pending_decisions.json／
# dashboard_decisions.json／work_log.json＝特殊類別；radar_state.json／schedule_events.json／
# us30y_state.json＝未命中白名單）→ auto_record 一律拒落 AUTO 章 → 舊版會留下一顆「永遠推不出去」
# 的 commit，把整條推送範圍連同 22:30 成本帳一起卡死（2026-10-12 22:15 實例）。
# 新行為：先問閘門（單一真值 publish_gate）；必須真 CIO → 走真審查車道 cio_lane.py 取 APPROVE 並落 RECORD；
#   審查未過 → 撤回本步驟 commit（內容留工作區）＋非零退出 → 保留阻塞、不偽造通過。
_changed = [ln.split()[-1] for ln in st.stdout.strip().splitlines() if ln.strip()]
sys.path.insert(0, REPO)
try:
    import publish_gate as _pg
    from pathlib import Path as _P
    _r = _pg.classify_paths(_P(REPO), _changed, ref="HEAD")
    _cio = bool(_r.get("must_cio")) or str(_r.get("mode")) != "AUTO"
except Exception as _e:  # noqa: BLE001
    print(f"⚠️ gate 判定不可用（{type(_e).__name__}: {str(_e)[:80]}）→ 保守視為必須真 CIO")
    _cio = True
_rec = "auto"
if _cio:
    print(f"🔐 閘門判定必須真 CIO（本次變更 {len(_changed)} 檔）→ 走真審查車道")
    try:
        import cio_lane as _lane
        _ok, _mmsg = _lane.review_and_record(tag="nightly_dashboard_sync")
    except (Exception, SystemExit) as _e:  # noqa: BLE001
        # 2026-10-13：車道本身例外（例：cwd 不在 repo → cio_approve import 期 sys.exit(2)）
        # 也必須走同一條「撤回 commit、保留阻塞」路徑，否則會留下毒藥 commit。
        # 註：SystemExit 不是 Exception 子類，必須明列，否則攔不到 sys.exit(2)。
        _ok, _mmsg = False, f"真審查車道例外（{type(_e).__name__}: {str(_e)[:120]}）→ fail-closed"
    print(f"真 CIO 審查：{_mmsg}")
    if not _ok:
        _rb = git("reset", "--soft", "HEAD~1")
        print(f"↩ 已撤回本步驟 commit（內容留在工作區，下一輪可重試）：{(_rb.stdout or _rb.stderr).strip()[:120]}")
        sys.exit(1)
    _rec = "skip"

# 2026-09-14：紀錄＋推送統一走 auto_push.py —— 確保「推送範圍內每顆 commit 都有審查紀錄」、
# push 失敗自動重試 3 次、並用 git ls-remote 驗證遠端 sha 真的前進（不再是「按了就算成功」）。
# 未完成 → 非零退出（cron 才看得到失敗，不會靜默地以為推上去了）。
r = subprocess.run([sys.executable, "auto_push.py", "--script", "nightly_dashboard_sync.py", "--record", _rec],
                   cwd=REPO, capture_output=True, text=True, encoding="utf-8")
print((r.stdout or "").strip() or (r.stderr or "").strip())
if r.returncode != 0:
    print(f"未推送上線（rc={r.returncode}）"); sys.exit(1)

print(f"OK: 已推送並驗證 {today} 儀表板同步")
