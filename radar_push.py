# -*- coding: utf-8 -*-
"""radar_push.py — 機構流向雷達 cron 推送 wrapper（週一/三 16:15 用）
流程：institutional_flow.py（更新 radar_state.json）→ build_radar_report.py（報告頁）
      → build_dashboard.py（儀表板雷達區塊同步）→ git commit（僅自身產物）
      → 需真 CIO 才審查（cio_lane）→ auto_push.py（唯一推送出口）
黃/紅燈才輸出（stdout 非空 → TG 推）；全綠 = 安靜（watchdog 模式）

2026-09-04 使用者指示：每天產出的機構流向雷達必須即時更新儀表板內雷達區塊（不能再等 22:00 晚報）

退出碼契約（2026-10-19 使用者裁決「一次到好」：rc 必須一路傳回 cron，不再全回 0）
    0 = 完成（已推並驗證遠端 sha）或「無事可做」（本輪沒有新 commit、推送範圍本來就空）
    1 = 產線步驟失敗（雷達／報告頁／儀表板／git add／git commit）
    3 = 發布授權未取得（真 CIO 審查未通過、閘門拒推）
    4 = push 重試後仍失敗（auto_push 原碼）
    5 = push 回 0 但遠端 sha 與 HEAD 不符（auto_push 原碼）
    6 = 環境問題（auto_push 原碼）
    7 = refspec 治理拒推（auto_push 原碼）
    8 = 審查車道例外／不可用（未取得有效審查意見，fail-closed）
"""
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

BASE = r"C:\Users\bot\Desktop\longjiu_system"
TODAY = date.today().isoformat()


# 2026-10-19（排程阻斷修復）：cron 從 ~/AppData/Local/hermes/scripts 啟動本腳本，sys.path[0]
# 只有該目錄；閘門／審查車道的模組（publish_gate／cio_lane／review_chain／cio_approve）
# 只存在 repo → 直接 import 會 ModuleNotFoundError（實測 review_lane 回「審查車道例外」→ rc=8，
# 排程每次必敗）。因此把 repo 根目錄加進 sys.path；以 publish_gate.py 存在為「BASE 真的是
# 正式 repo」的標記，避免把錯誤目錄插進搜尋路徑。
if BASE not in sys.path and (Path(BASE) / "publish_gate.py").exists():
    sys.path.insert(0, BASE)

EXIT_OK = 0
EXIT_PROD_FAIL = 1
EXIT_REVIEW_REFUSED = 3
EXIT_REVIEW_ERROR = 8


def run(cmd, env=None, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=BASE,
                          timeout=timeout, env=env)


def _tail(text, n=300):
    return (text or "").strip()[-n:]


def build_products():
    """產線三步。回 (ok, radar_stdout, err_msg)；測試可整支替換。"""
    r = run([sys.executable, "institutional_flow.py"], timeout=600)
    out = r.stdout or ""
    if r.returncode != 0:
        return False, out, f"機構流向雷達執行失敗：{_tail(r.stderr)}"

    rr = run([sys.executable, "build_radar_report.py"], timeout=120)
    if rr.returncode != 0:
        return False, out, f"雷達報告頁產生失敗：{_tail(r.stderr, 200)}"

    d = run([sys.executable, "build_dashboard.py"], timeout=180)
    if d.returncode != 0:
        return False, out, f"儀表板雷達同步失敗：{_tail(d.stderr)}"

    rb = run([sys.executable, "build_rebalance_dashboard.py"], timeout=180)
    if rb.returncode != 0:
        return False, out, f"再平衡儀表板同步失敗：{_tail(rb.stderr)}"

    return True, out, ""


def gate_requires_cio(files):
    """閘門單一真值（publish_gate.classify_paths）：這批檔能否走 AUTO 通道？

    True＝必須真 CIO 審查。判定失敗一律回 True（fail-closed）。
    2026-10-19：不寫死「每天都要審查」——是否審查由閘門判定，白名單日後調整也不需改本檔。
    """
    try:
        import publish_gate as _pg
        r = _pg.classify_paths(Path(BASE), files, ref="HEAD")
        return bool(r.get("must_cio")) or str(r.get("mode")) != "AUTO"
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 閘門判定不可用（{type(e).__name__}: {str(e)[:80]}）→ 保守視為必須真 CIO")
        return True


def review_lane():
    """真 CIO 審查＋落 RECORD（單一實作：cio_lane.py）。回 (ok, msg)；測試可整支替換。"""
    try:
        import cio_lane as _lane
        return _lane.review_and_record(tag="radar_push")
    except (Exception, SystemExit) as e:  # noqa: BLE001
        # SystemExit 不是 Exception 子類（cio_approve 於 cwd 不在 repo 時會 sys.exit(2)）
        return False, f"審查車道例外（{type(e).__name__}: {str(e)[:120]}）→ fail-closed"


def rollback_created_commit():
    """撤回本輪剛建立的 commit（只 reset --soft，內容保留在工作區）。"""
    try:
        import cio_lane as _lane
        return _lane.rollback_head_soft()
    except (Exception, SystemExit) as e:  # noqa: BLE001
        r = run(["git", "reset", "--soft", "HEAD~1"], timeout=60)
        if r.returncode == 0:
            return True, "已撤回本輪 commit（fallback git reset --soft）"
        return False, f"撤回失敗（{type(e).__name__}: {str(e)[:80]}／git rc={r.returncode}）"


def push_lane(own_files):
    """唯一推送出口：auto_push.py（範圍紀錄覆蓋／重試／遠端 sha 驗證）。

    own_files 必須是「推送範圍內實際變更的自家產物」；空清單時不傳 --own
    （nargs='+' 不帶值會讓 argparse 直接失敗）。
    """
    cmd = [sys.executable, os.path.join(BASE, "auto_push.py"), "--script", "radar_push.py"]
    if own_files:
        cmd += ["--own"] + list(own_files)
    return run(cmd, timeout=600)


def commit_range_count():
    """待推 commit 數；讀不到遠端回 -1（呼叫端保守處理）。"""
    r = run(["git", "rev-list", "--count", "origin/clean-main..HEAD"], timeout=60)
    if r.returncode != 0:
        return -1
    try:
        return int((r.stdout or "0").strip() or 0)
    except ValueError:
        return -1


def _print_summary(out: str, mode: str = "alerts") -> None:
    """摘要輸出模式（2026-10-31 單一實作）。

    alerts＝只有出現「⚠️ ALERTS」才輸出（週一/三 watchdog，全綠安靜）
    full  ＝永遠輸出完整摘要（週六 COT/Fed 版，cron 直送 TG）
    """
    body = (out or "").strip()
    if mode == "full":
        if body:
            print(f"📋 週六再平衡 — 機構流向雷達\n{body}")
        return
    if "⚠️ ALERTS" in (out or ""):
        print(out)


def main(summary_mode: str = "alerts"):
    # 1) 雷達主程式＋報告頁＋儀表板同步
    ok, out, err = build_products()
    if not ok:
        print(f"⚠️ {err}")
        return EXIT_PROD_FAIL

    # 2) 只提交本 job 自身產物
    # 2026-09-13 INC-159：原 `git add -A` 會把工作區「所有」變更掃進本 job 的 commit
    # （實證：一次掃入 582 個無關的 data/ 快取刪除 + 其他流程 6 個檔案，commit 訊息卻掛
    #  「雷達儀表板同步」）→ 改白名單，只提交本 job 自身產物。
    own_files = ["radar_state.json", f"radar_report_{TODAY}.html", "index.html",
                 f"rebalance_dashboard_{TODAY}.html"]
    own_files = [f for f in own_files if os.path.exists(os.path.join(BASE, f))]
    # 2026-10-22 P1：提交暫停旗標（只擋 commit/push，不擋產出）
    if os.path.exists(os.path.join(BASE, ".git", "PUSH_HOLD")):
        print("⏸️ PUSH_HOLD 生效：雷達已更新，跳過 commit/push；發布待另行授權")
        return 0
    g = run(["git", "add", "--"] + own_files, timeout=60)
    if g.returncode != 0:
        print(f"⚠️ git add 失敗（{own_files}）：{_tail(g.stderr, 200)}")
        return EXIT_PROD_FAIL

    # 3) commit（限制在自身產物路徑，避免吃掉別班已 stage 的內容）
    #    2026-10-19：先看 staged 是否真有差異 —— `git commit -- <paths>` 在無差異時回 rc=1
    #    且訊息是「no changes added to commit」，與「nothing to commit」不同字串，靠字串比對會誤判失敗。
    staged = run(["git", "diff", "--cached", "--name-only", "--"] + own_files, timeout=60)
    created = False
    if (staged.stdout or "").strip():
        c = run(["git", "commit", "-m", f"auto: 雷達儀表板同步 {TODAY}", "--"] + own_files, timeout=60)
        created = c.returncode == 0
        if not created:
            print(f"⚠️ git commit 失敗：{_tail((c.stdout or '') + (c.stderr or ''), 200)}")
            return EXIT_PROD_FAIL

    # 4) 無事可做：本輪沒有新 commit，且推送範圍本來就空 → 0（不是失敗）
    #    2026-10-19：原版無論有無變更都呼叫 auto_push，閘門回 RANGE_EMPTY → rc=3 誤報。
    n_range = commit_range_count()
    if created and n_range == 0:
        # 極端情形（commit 成功但範圍仍為 0，例如 remote 已含同 tree）→ 視為完成
        _print_summary(out, summary_mode)
        return EXIT_OK
    if not created and n_range == 0:
        _print_summary(out, summary_mode)
        return EXIT_OK

    # 5) 需要真 CIO 才審查（本輪新建的 commit 才做，不動別人的 commit）
    if created:
        files = [p for p in (run(["git", "show", "--name-only", "--format=", "HEAD"],
                                 timeout=60).stdout or "").splitlines() if p.strip()]
        if gate_requires_cio(files or own_files):
            ok_r, msg_r = review_lane()
            print(f"🔐 真 CIO 審查：{msg_r}")
            if not ok_r:
                _code = (EXIT_REVIEW_ERROR if msg_r.startswith("審查車道例外")
                         else EXIT_REVIEW_REFUSED)
                ok_b, msg_b = rollback_created_commit()
                # reset --soft 會把本輪產物留在 index（staged）；這裡只還原 staged 狀態，
                # 不動工作區內容（產物保留、下一輪可重試，且不干擾別班的 stage）。
                if ok_b:
                    run(["git", "restore", "--staged", "--"] + own_files, timeout=60)
                print(f"⚠️ 未推送上線（審查未通過，rc={_code}）：{msg_r}")
                print(f"   撤回本輪 commit：{msg_b}")
                return _code

    # 6) 推送（唯一出口）
    # --own 只做字面路徑比對（publish_gate 不展開 glob）→ 一律傳實際檔名。
    # 2026-10-19（INC）：原傳 glob「radar_report_*.html」會被判 OWN_OUTSIDE 越權，10-12／10-19 兩次因此推不出去。
    # 2026-10-31（INC）：改成「本次推送範圍內實際變更」的自家檔 —— 傳候選清單時，本次沒動到的
    #   index.html 會被判 OWN_OUTSIDE（越權）而整批拒推（當日實踩：rc=3 blocking 1）。
    _rng = run(["git", "diff", "--name-only", "origin/clean-main", "HEAD"], timeout=60)
    _rng_files = {p.strip() for p in (_rng.stdout or "").splitlines() if p.strip()}
    push_own = [f for f in own_files if f in _rng_files]
    ap = push_lane(push_own)
    ap_out = _tail((ap.stdout or "") + (ap.stderr or ""))
    if ap.returncode != 0:
        print(f"⚠️ 未推送上線（rc={ap.returncode}）：{ap_out}")
        return ap.returncode

    # 7) 摘要輸出（週一/三 watchdog 只印警示；週六 full 印完整摘要，cron 直送 TG）
    _print_summary(out, summary_mode)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
