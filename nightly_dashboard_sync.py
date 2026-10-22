# -*- coding: utf-8 -*-
"""nightly_dashboard_sync.py — 每晚 22:15 行動儀表板 JSON 自動 commit+push（2026-09-05 建立）

行動儀表板為 client-side（讀 radar_state/schedule_events/work_log/snapshot/pending/decisions），
JSON 變更需 commit+push 到 GitHub 才會上線。此腳本把當天變更收斂一次：
- 無變更 → 印 SKIP，exit 0（供 cron [SILENT]）
- 有變更 → commit → 落 RECORD（auto_record，P2 起） → push clean-main + main
設計：從 hermes/scripts 執行（cron 慣例），用 git -C 指向 repo，不依賴 cwd。
"""
import subprocess, sys, datetime, os

REPO = r"C:/Users/bot/Desktop/longjiu_system"
FILES = [
    "radar_state.json",       # 雷達/本週該做（行動儀表板②）
    "schedule_events.json",   # 行事曆 今天/未來3天（行動儀表板③）
    "work_log.json",          # 系統工作日誌卡
    "snapshot.json",          # 儀表板數字主源
    "pending_decisions.json", # 決策待辦
    "dashboard_decisions.json",  # 決策追蹤/審計
    "us30y_state.json",       # US30Y 模式燈號
    # 2026-10-22：asset_diff_history.json 原由 22:00 artifact_commit 認領；22:00 若跳過
    #   commit，07:00 與本檔都不認領 → 永久孤兒。納入本任務（22:00 之後、22:40 之前），
    #   沿用真 CIO 車道；無變更時上方 status 為空即 sys.exit(0)，不產生空 commit。
    "asset_diff_history.json",
]
# 2026-10-21（TD-20261013-01／使用者裁決）：事件帳本補上明確提交出口。
#   這兩檔由 four_source_sync.py（22:00 晚報，新 INC append）與 lj_inc.py（list／close 改寫）
#   以及週一 03:00 深清（cleanup_utils）寫入，但兩檔在 publish_gate.NEVER_AUTO_EXACT →
#   任何 AUTO 車道都拿不到章、自身也不 commit → 每晚必髒、22:40 收工檢查反覆紅。
#   修法：納入本任務提交集（22:15 在 22:00 之後、22:40 之前），沿用既有「強制真 CIO →
#   cio_lane 真審查 → auto_push」車道與「審查失敗撤回 commit、內容留工作區」語意。
#   只 stage 有實際變更的檔（git add 無變更即無 staged）→ 不產生空 commit、不擴大提交集。
LEDGERS = [
    "error_register.md",      # 事件登記（four_source_sync append／週深清歸檔改寫）
    "inc_events.jsonl",       # 事件殘留帳本（lj_inc／four_source_sync 改寫）
]
FILES += LEDGERS

def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, encoding="utf-8")

today = datetime.date.today().isoformat()
# 2026-10-22 P1：提交暫停旗標（本任務不生成資料，跳過即無事可做）
if os.path.exists(os.path.join(REPO, ".git", "PUSH_HOLD")):
    print("⏸️ PUSH_HOLD 生效：跳過 nightly commit/push；發布待另行授權")
    sys.exit(0)
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
        # 2026-10-21 A 案（擴大）：cron 從 hermes/scripts 啟動本檔時 sys.path 只有該目錄，
        # in-process `import cio_lane` 會在 cio_lane 的延遲 import review_chain 時 ModuleNotFoundError
        # （2026-10-21 22:00 晚報實踩同型）。改走 cio_lane 既有 CLI：腳本路徑在 REPO →
        # sys.path[0]=REPO，repo 根目錄的 review_chain 可見（與 92 行 auto_push 同模式）。
        # 契約：exit 0＝OK、非 0＝不要 push；stdout 末行 `✅ OK | …` / `❌ FAIL | …`。
        _r2 = subprocess.run([sys.executable, "cio_lane.py", "--tag", "nightly_dashboard_sync"],
                             cwd=REPO, capture_output=True, text=True, encoding="utf-8", timeout=1800)
        _out2 = ((_r2.stdout or "") + (_r2.stderr or "")).strip()
        _last2 = _out2.splitlines()[-1].strip() if _out2 else ""
        if _r2.returncode == 0 and _last2.startswith("✅ OK | "):
            _ok, _mmsg = True, _last2[len("✅ OK | "):].strip()
        elif _last2.startswith("❌ FAIL | "):
            _ok, _mmsg = False, _last2[len("❌ FAIL | "):].strip()
        else:
            _ok = False
            _mmsg = (f"真審查車道 rc={_r2.returncode} 無可解析輸出 → fail-closed"
                     + (f"｜{_last2[:120]}" if _last2 else ""))
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
