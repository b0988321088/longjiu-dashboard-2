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
    if not (_before and _after and _d1_ok and _d2_ok):
        lines.append("⛔ producer 邊界快照不完整 → 本次不 commit／不 push（fail-closed）")
    elif not _ig_ok:
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
            if _add.returncode == 0 and sorted(_st) == sorted(_keep):
                lines.append(f"📦 本輪產物 {len(_keep)} 檔入 commit scope：{', '.join(_keep[:8])}"
                             + ("…" if len(_keep) > 8 else ""))
                ap = subprocess.run([sys.executable, str(BASE / "auto_push.py"), "--script", "evening_sync.py",
                                     "--commit", f"auto: 晚報校準 {TODAY}"],
                                    cwd=BASE, capture_output=True, text=True, timeout=900)
                _pushed = ap.returncode == 0
                for _l in (((ap.stdout or "") + (ap.stderr or "")).strip()).splitlines()[-4:]:
                    lines.append("  " + _l)
            else:
                _extra = sorted(set(_st) - set(_keep))
                lines.append(f"⛔ staged 與本輪產物不符（git add rc={_add.returncode}｜多出 {_extra}）"
                             "→ 不 commit／不 push（fail-closed）")
    _dropped = sorted(set(_drop) - set(_keep))
    if _d2_ok and _dropped:
        lines.append(f"🚫 排除 {len(_dropped)} 檔（非本輪產物／執行前已 dirty）：{', '.join(_dropped[:8])}"
                     + ("…" if len(_dropped) > 8 else ""))
    lines.append("✅ 已推送並驗證（clean-main）" if _pushed
                 else "⚠️ 未推送上線 — 線上可能仍是舊版，詳見上方訊息")
    lines.append("")
    lines.append(f"📰 日報：https://b0988321088.github.io/longjiu-dashboard-2/daily_report_v2_{TODAY}.html")
    lines.append(f"📊 差異：https://b0988321088.github.io/longjiu-dashboard-2/asset_diff_{TODAY}.html")
    lines.append("🏠 儀表板：https://b0988321088.github.io/longjiu-dashboard-2/")
    lines.append("")
    lines.append("（晚報已改輕量校準模式：零 LLM 成本；完整 LLM 分析在晨間 07:00）")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
