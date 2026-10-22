#!/usr/bin/env python3
"""evening_sync.py — 龍九晚報輕量版（2026-08-27 優化）

原晚報為 agent 任務（每天第 2 次跑完整 regenerate_report.py → 可能觸發 buffett/cto LLM）。
改為 no-agent 校準版：update_all（四源同步）+ asset_diff_monitor（差異）
+ pending_reconcile --apply（Pending 由真值自動重算／自動閉環）+ build_dashboard（儀表板連結）
→ 零 LLM 成本，輸出三連結由 cron 直接推送。

順序鐵則：pending_reconcile 會改寫 pending_decisions.json → 必須排在 build_dashboard 之前，
否則儀表板會用舊 Pending 產出（stale 產物）。本支同時是「唯一」讓 pending 落地的路徑。

晨間 07:00 仍為完整版（含 LLM 分析）。
"""
import hashlib
import subprocess, sys
from datetime import date
from pathlib import Path

BASE = Path(r"C:\Users\bot\Desktop\longjiu_system")
TODAY = date.today().isoformat()

# ── producer isolation（2026-10-08 治理 PEND-20261008-01 Phase B｜目標 1＝evening_sync）───────
# 核心規則：①只有「本輪真正產生」的檔可進 commit scope ②**執行前已 dirty 者一律不帶走**
#   ③禁止 git add -A（一律顯式 pathspec）④data／program 不混 commit ⑤失敗一律 fail-closed。
# 做法：跑子生產者前後各取一次「根目錄內容指紋」＋「git 既有 dirty 集合」；
#   produced = 內容真的變了(after−before) 且 執行前是乾淨的（不在 dirty_before）。
#   讀取失敗／不可快照 → _UNREADABLE → 一律排除（不得被當成本輪產物）。
# 註：不在本檔抽共用模組（Phase B 後續才做）；暫不改 dirty_gate.py／auto_push.py。
# 程式檔副檔名（defense-in-depth：與 _SNAP_EXT 目前不相交，實際由 _snap_root 就已排除；
# 保留此清單是為了 _SNAP_EXT 日後若放寬時，程式檔仍不會被誤納入 commit scope）。
_CODE_EXT = {'.py', '.sh', '.bat', '.ps1', '.cmd', '.toml', '.yml', '.yaml', '.js', '.ts', '.sql'}
_SNAP_EXT = {'.html', '.json', '.md', '.png', '.db', '.jsonl', '.csv', '.svg', '.txt', '.xml',
             '.webp', '.jpg', '.jpeg', '.gif', '.ico', '.pdf'}
_SNAP_MAX = 20 * 1024 * 1024
_UNREADABLE = "<UNREADABLE>"


def _scope_verdict(staged, keep):
    """commit 前驗證「staged 集合 vs 本輪產物」。

    不變式（安全性質只有一個方向）：**staged ⊄ produced → 整批不推**（不得把他班／他輪的檔帶走）。
    反向（produced 有、staged 沒有）**不是**違規：內容經 git 正規化（autocrlf／clean filter）後與
    HEAD 相同時，`git add` 不會產生 staged 變更。
    2026-10-12 實踩：原判定式 `sorted(_st) == sorted(_keep)`（要求完全相等）遇到這種情形整批
    fail-closed —— 當晚訊息是「多出 []」（沒有任何多餘檔卻判定不符）→ 晚報 22:00 連續不上線，
    且當輪產物整批留在工作區（收工稽核每晚判「已追蹤未提交」）。
    回傳 (verdict, extra, missing)；verdict ∈ {"ok", "extra_blocked"}。
    """
    st, kp = set(staged or []), set(keep or [])
    extra, missing = sorted(st - kp), sorted(kp - st)
    return ("extra_blocked" if extra else "ok"), extra, missing


def _snap_root(base: Path) -> dict:
    """根目錄候選檔的內容指紋；存在卻無法快照者記 _UNREADABLE（不是略過）。"""
    d = {}
    for p in base.iterdir():
        try:
            if not p.is_file() or p.suffix.lower() not in _SNAP_EXT:
                continue
            if p.stat().st_size > _SNAP_MAX:
                d[p.name] = _UNREADABLE
                continue
            d[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
        except Exception:
            try:
                d[p.name] = _UNREADABLE
            except Exception:
                pass
    return d


def _dirty_set(base: Path) -> tuple[set, bool]:
    """「與 HEAD 不同或未追蹤」的根目錄檔集合。
    #1（2026-10-08）：改用 NUL 分隔（`-z`）——舊版 `splitlines()` ＋ `ln[3:].strip().strip('"')`
    遇到**空白／C-quoted 檔名**或 rename（`R  a -> b`）都會解析錯；解析失敗仍 fail-closed。
    """
    try:
        r = subprocess.run(["git", "status", "--porcelain", "-z", "--untracked-files=all"],
                           cwd=base, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return set(), False
        out, toks, i = set(), (r.stdout or "").split("\0"), 0
        while i < len(toks):
            e = toks[i]
            if not e:
                i += 1
                continue
            xy, path = e[:2], e[3:]
            if path and "/" not in path and "\\" not in path:   # 只看根目錄
                out.add(path)
            if "R" in xy or "C" in xy:      # rename／copy：來源路徑是下一個裸 token
                src = toks[i + 1] if i + 1 < len(toks) else ""
                if src and "/" not in src and "\\" not in src:
                    out.add(src)
                i += 2
            else:
                i += 1
        return out, True
    except Exception:
        return set(), False


def _ignored(base: Path, paths: list) -> tuple[set, bool]:
    """回傳 paths 中「被 .gitignore／exclude 排除」者（#2，2026-10-08）。
    ignored 產物必須在 **scope 判定階段**就排除：否則 `git add -- <ignored>` 會 rc≠0，
    讓整批合法產物一起 fail-closed、夜跑靜默不發布。判定失敗 → ok=False（fail-closed）。
    """
    if not paths:
        return set(), True
    try:
        r = subprocess.run(["git", "check-ignore", "-z", "--stdin"], cwd=base,
                           input="\0".join(paths) + "\0",
                           capture_output=True, text=True, timeout=60)
        if r.returncode not in (0, 1):      # 0=有命中、1=都沒被 ignore；其他＝失敗
            return set(), False
        return {p for p in (r.stdout or "").split("\0") if p}, True
    except Exception:
        return set(), False


def _produced(before: dict, after: dict, dirty_before: set) -> tuple[list, list]:
    """本輪真正產生＝內容變了(after−before) 且 執行前乾淨；其餘一律排除。"""
    keep, drop = [], []
    for f, h in after.items():
        if h == _UNREADABLE or f in dirty_before or before.get(f) == _UNREADABLE:
            drop.append(f)
            continue
        if before.get(f) is None or before.get(f) != h:
            keep.append(f)
        else:
            drop.append(f)
    return sorted(keep), sorted(drop)


def run(name: str, timeout: int = 600) -> bool:
    r = subprocess.run([sys.executable, str(BASE / name)], cwd=BASE,
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode == 0


def run_capture(name: str, timeout: int = 600, args: list | None = None) -> tuple[bool, str]:
    r = subprocess.run([sys.executable, str(BASE / name)] + (args or []), cwd=BASE,
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).strip()


def _git_head() -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=BASE, capture_output=True, text=True)
    return (r.stdout or "").strip()


def _publish(message, lines, own_commit=True, runner=None, lane=None):
    """commit（可選）→ 必要時走真 CIO 車道 → 推送。回傳是否真的推上線。

    2026-10-20 A 案：21:xx 產線常產生「強制真 CIO 類」commit（pending_decisions.json 等），
    auto_push 會以 rc=3 拒絕 → 舊版只印「未推送上線」但整體 rc=0，留下毒藥 commit，
    22:15 nightly 因此 fail-closed。現改為：rc=3 時呼叫 cio_lane.review_and_record 取 APPROVE
    並落 RECORD，再以 --record skip 推送；車道失敗則撤回本步驟 commit（內容留工作區）並回 False。
    """
    runner = runner or (lambda args, **kw: subprocess.run(args, cwd=BASE, **kw))
    head0 = _git_head()
    cmd = [sys.executable, str(BASE / "auto_push.py"), "--script", "evening_sync.py", "--record", "auto"]
    if message:
        cmd += ["--commit", message]
    ap = runner(cmd, capture_output=True, text=True, timeout=900)
    out = ((ap.stdout or "") + (ap.stderr or "")).strip()
    for _l in out.splitlines()[-4:]:
        lines.append("  " + _l)
    if ap.returncode == 3:
        lines.append("🔐 閘門判定必須真 CIO → 走真審查車道（cio_lane）")
        if lane is None:
            # 2026-10-21 A 案修復：cron 從 hermes/scripts 啟動本檔時 sys.path 只有該目錄，
            # in-process `import cio_lane` 會因 review_chain 無鏡像而 ModuleNotFoundError
            # （實踩 22:00 晚報：commit 成立、無 RECORD、不推送）。改走 cio_lane 既有 CLI，
            # 與 run()/run_capture() 同一模式（腳本路徑在 BASE → sys.path[0]=BASE，模組可見）。
            # 契約：exit 0＝OK、非 0＝不要 push；stdout 末行 `✅ OK | …` / `❌ FAIL | …`。
            try:
                _r = runner([sys.executable, str(BASE / "cio_lane.py"), "--tag", "evening_sync"],
                            capture_output=True, text=True, timeout=1800)
                _o = ((_r.stdout or "") + (_r.stderr or "")).strip()
                _last = _o.splitlines()[-1].strip() if _o else ""
                if _r.returncode == 0 and _last.startswith("✅ OK | "):
                    ok, msg = True, _last[len("✅ OK | "):].strip()
                elif _last.startswith("❌ FAIL | "):
                    ok, msg = False, _last[len("❌ FAIL | "):].strip()
                else:
                    ok = False
                    msg = (f"車道 rc={_r.returncode} 無可解析輸出 → fail-closed"
                           + (f"｜{_last[:120]}" if _last else ""))
            except (Exception, SystemExit) as _e:  # noqa: BLE001
                ok, msg = False, f"車道例外（{type(_e).__name__}: {str(_e)[:120]}）→ fail-closed"
        else:
            ok, msg = lane()
        lines.append(f"真 CIO 審查：{msg}")
        if not ok:
            if own_commit and _git_head() != head0:
                rb = runner(["git", "reset", "--soft", "HEAD~1"], capture_output=True, text=True)
                lines.append("↩ 已撤回本步驟 commit（內容留在工作區，下一輪可重試）："
                             + (rb.stdout or rb.stderr).strip()[:100])
            return False
        ap2 = runner([sys.executable, str(BASE / "auto_push.py"), "--script", "evening_sync.py",
                      "--record", "skip"], capture_output=True, text=True, timeout=900)
        for _l in (((ap2.stdout or "") + (ap2.stderr or "")).strip()).splitlines()[-3:]:
            lines.append("  " + _l)
        if ap2.returncode != 0:
            lines.append(f"⚠️ 審查通過但推送失敗（rc={ap2.returncode}）")
            return False
        return True
    if ap.returncode != 0:
        lines.append(f"⚠️ 推送失敗（rc={ap.returncode}）")
        return False
    return True


def main():
    lines = ["📊 **龍九晚報（自動校準版 22:00）**"]
    # producer 邊界：跑子生產者「之前」先取內容指紋＋既有 dirty 集合（本輪產物＝after−before）
    _before = _snap_root(BASE)
    _dirty_before, _d1_ok = _dirty_set(BASE)
    lines.append(f"🧾 邊界快照：{len(_before)} 檔｜執行前既有 dirty {len(_dirty_before)} 檔"
                 if _d1_ok else "⛔ 邊界快照異常（git status 讀取失敗）→ 本次將不推送（fail-closed）")
    ok1 = run("update_all.py", 600)
    lines.append("✅ 四源同步（snapshot→DB→HTML→穿透）" if ok1 else "⚠️ update_all 異常")
    ok2 = run("asset_diff_monitor.py", 120)
    lines.append("✅ 資產差異分析更新" if ok2 else "⚠️ 差異分析異常")
    # 3) Pending 由真值自動重算／自動閉環（唯一落地路徑；必須在 build_dashboard 之前）
    ok_pr, pr_out = run_capture("pending_reconcile.py", 120, ["--apply"])
    _pr_line = next((_l.strip() for _l in pr_out.splitlines() if _l.startswith("Pending ")), "")
    if ok_pr:
        lines.append(f"✅ Pending 自動回收（真值→狀態）｜{_pr_line}" if _pr_line
                     else "✅ Pending 自動回收（真值→狀態）")
    else:
        lines.append(f"⚠️ Pending 自動回收異常（rc≠0）｜{_pr_line}")
    for _l in pr_out.splitlines():
        if _l.strip().startswith("⚠️"):
            lines.append("  " + _l.strip())
    ok3 = run("build_dashboard.py", 120)
    lines.append("✅ 儀表板連結更新" if ok3 else "⚠️ 儀表板異常")
    # 4) producer 邊界 → 只 stage「本輪產物」→ commit + 推送（走 auto_push.py，**不用 --auto-stage**）
    #    2026-10-08 治理：原 `--auto-stage` 會先 `git add -A`，把工作區**所有**變更（含他班既有 dirty）
    #    掃進本 job 的 commit。改為：produced = after−before 且執行前乾淨；顯式 pathspec stage；
    #    commit 前驗證「staged 集合 == produced 集合」，多一個就整批 fail-closed 不推。
    _after = _snap_root(BASE)
    _dirty_after, _d2_ok = _dirty_set(BASE)
    _keep, _drop = _produced(_before, _after, _dirty_before) if (_before and _after) else ([], [])
    # #4（defense-in-depth）：_CODE_EXT 與 _SNAP_EXT 不相交 → 程式檔本來就不會被快照；
    #     保留此過濾是為了「日後 _SNAP_EXT 若放寬也不會誤納程式檔」，不為 dead code 改架構。
    _keep = [f for f in _keep if Path(f).suffix.lower() not in _CODE_EXT]
    # #2：ignored 產物在「scope 判定階段」排除 —— 不能先判 produced 再等 `git add` 失敗，
    #     否則一個 ignored artifact（如 snapshot.backup.json）會讓整批合法產物一起靜默不發布。
    _ig, _ig_ok = _ignored(BASE, _keep)
    _keep = [f for f in _keep if f not in _ig]
    _pushed = False
    _fail = False
    # 2026-10-22 P1：提交暫停旗標（只擋 commit/push，不擋資料更新）
    _hold = (Path(BASE) / ".git" / "PUSH_HOLD").exists()
    if _hold:
        lines.append("⏸️ PUSH_HOLD 生效：資料已更新，跳過 commit/push 與收尾提交；發布待另行授權")
    elif not (_before and _after and _d1_ok and _d2_ok):
        _fail = True
        lines.append("⛔ producer 邊界快照不完整 → 本次不 commit／不 push（fail-closed）")
    elif not _ig_ok:
        _fail = True
        lines.append("⛔ 無法判定 ignored 產物（git check-ignore 失敗）→ 不 commit／不 push（fail-closed）")
    else:
        if _ig:
            lines.append(f"🚫 排除 {len(_ig)} 個「本輪產生但被 .gitignore 排除」的檔（不納入發布 scope）："
                         f"{', '.join(sorted(_ig))}")
        if not _keep:
            lines.append("⏭️ 本輪無可發布產物 → 不 commit／不 push")
        else:
            _add = subprocess.run(["git", "add", "--"] + _keep, cwd=BASE,
                                  capture_output=True, text=True, timeout=300)
            _st = [p for p in subprocess.run(["git", "diff", "--cached", "--name-only", "-z"], cwd=BASE,
                                             capture_output=True, text=True, timeout=120).stdout.split("\0") if p]
            _verdict, _extra, _missing = _scope_verdict(_st, _keep)
            if _add.returncode == 0 and _verdict == "ok":
                lines.append(f"📦 本輪產物 {len(_keep)} 檔入 commit scope：{', '.join(_keep[:8])}"
                             + ("…" if len(_keep) > 8 else ""))
                if _missing:
                    lines.append(f"ℹ️ {len(_missing)} 檔 staged 無差異（git 正規化後與 HEAD 相同，"
                                 f"不影響本次發布）：{', '.join(_missing[:8])}"
                                 + ("…" if len(_missing) > 8 else ""))
                _pushed = _publish(f"auto: 晚報校準 {TODAY}", lines)
                if not _pushed:
                    _fail = True
            else:
                _extra = sorted(set(_st) - set(_keep))
                _fail = True
                lines.append(f"⛔ staged 與本輪產物不符（git add rc={_add.returncode}｜多出 {_extra}）"
                             "→ 不 commit／不 push（fail-closed）")
    # 5) 資料產物收尾提交（2026-10-15 P1-2 修復；責任邊界＝此步驟，唯一且明確）
    #    背景：asset_diff_history.json 原本靠 emergency_1330._commit_own() 提交；該出口依 §4
    #    裁決預設停用後，此檔永久停在 dirty（本檔 producer 規則「執行前已 dirty 者不帶走」永遠排除它）。
    #    修法：改由 artifact_commit.py 認領 —— 只提交 artifact_commit.DECLARED 宣告清單（顯式
    #    pathspec、commit 前驗證 staged ⊆ 宣告清單、禁 add -A）→ 不擴大提交範圍、不暗中夾帶他班
    #    dirty；失敗一律非零 rc 且在晚報逐字揭露（失敗可見），無變更則明說「無變更」。
    #    ★ 2026-10-15 使用者裁決（方案 b）：提交與發布分離 —— 本步驟**只提交、不推送**
    #      （不帶 --push；artifact_commit 亦不得呼叫 auto_push）。推送交由獨立審查車道
    #      （真 CIO 審查 → RECORD → auto_push），故晚報必須分開講「提交完成、推送待審」，
    #      不得把兩件事合併報告成「已發布」。
    if _hold:
        lines.append("📦 資料產物收尾提交：⏸️ PUSH_HOLD 生效，已略過（發布待另行授權）")
    else:
        _head_art0 = _git_head()
        _ok_art, _art_msg = run_capture("artifact_commit.py", 300)
        if _ok_art and _git_head() != _head_art0:
            # 2026-10-20 A 案：收尾提交（只提交不推送，依 2026-10-15 裁決 b 不改其職責）
            # 會留下一顆未審 commit → 在本檔內接續送真 CIO 車道並推送，否則 22:15 必被擋。
            _p_art = _publish(None, lines, own_commit=False)
            _pushed = _pushed or _p_art
            if not _p_art:
                _fail = True
                lines.append("⚠️ 收尾提交未能完成審查／推送 → 已保留待審（不偽造成功）")
        lines.append(("📦 資料產物收尾提交（只提交、不推送）：" + ("✅ " if _ok_art else "❌ "))
                     + (_art_msg.splitlines()[0] if _art_msg else "（無輸出）")
                     + ("｜推送待獨立審查" if _ok_art else ""))
    _dropped = sorted(set(_drop) - set(_keep))
    if _d2_ok and _dropped:
        lines.append(f"🚫 排除 {len(_dropped)} 檔（非本輪產物／執行前已 dirty）：{', '.join(_dropped[:8])}"
                     + ("…" if len(_dropped) > 8 else ""))
    # ★ 2026-10-15 裁決 b：收尾提交（步 5）**不算推送**——只有步 4 真的推成功才宣稱已上線，
    #   否則一律明示「未推送上線」（殘留本機 commit 由獨立審查車道處理）。
    lines.append("✅ 已推送並驗證（clean-main）" if _pushed
                 else "⚠️ 未推送上線 — 線上可能仍是舊版，詳見上方訊息（收尾提交僅完成本機 commit）")
    lines.append("")
    lines.append(f"📰 日報：https://b0988321088.github.io/longjiu-dashboard-2/daily_report_v2_{TODAY}.html")
    lines.append(f"📊 差異：https://b0988321088.github.io/longjiu-dashboard-2/asset_diff_{TODAY}.html")
    lines.append("🏠 儀表板：https://b0988321088.github.io/longjiu-dashboard-2/")
    lines.append("")
    lines.append("（晚報已改輕量校準模式：零 LLM 成本；完整 LLM 分析在晨間 07:00）")
    print("\n".join(lines))
    # 2026-10-22：內部失敗必須反映到 cron 退出碼（原本 _fail 累積但永遠 exit 0）
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
