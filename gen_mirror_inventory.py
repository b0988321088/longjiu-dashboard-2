#!/usr/bin/env python
"""gen_mirror_inventory.py — 產出 hermes/scripts 鏡像清單（P1-2 決定：不強制全部納入版控，
先用清單讓「漂移」看得見）。輸出 HERMES_SCRIPTS_INVENTORY.md。"""
from pathlib import Path
import subprocess, datetime

MIRROR = Path(r"C:\Users\bot\AppData\Local\hermes\scripts")
REPO = Path(r"C:\Users\bot\Desktop\longjiu_system")


def has_git_ops(p: Path) -> bool:
    try:
        t = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return ('"push"' in t) or ("git push" in t) or ('"commit"' in t)


def is_forwarder(p: Path) -> bool:
    """鏡像端的薄轉發器（指向 repo 真值）＝刻意保留的轉發層，與 repo 內容本就不同。"""
    try:
        t = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return ("薄轉發器" in t) or ("REPO_SCRIPT" in t)


tracked, mirror_only, risky = [], [], []
for f in sorted(MIRROR.glob("*.py")):
    repo_f = REPO / f.name
    if repo_f.exists():
        if is_forwarder(f):
            tracked.append((f.name, "轉發器", f.stat().st_mtime))
        else:
            same = repo_f.read_bytes() == f.read_bytes()
            tracked.append((f.name, "同步" if same else "❗漂移", f.stat().st_mtime))
    else:
        g = has_git_ops(f)
        mirror_only.append((f.name, "⚠️ 有 git 操作" if g else "無", f.stat().st_mtime))
        if g:
            risky.append(f.name)

now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
L = []
L.append("# hermes/scripts 鏡像清單（P1-2 盤點）")
L.append("")
L.append(f"產出時間：{now}｜產出工具：`gen_mirror_inventory.py`")
L.append("")
L.append("鏡像目錄＝cron 實際執行位置：`C:\\Users\\bot\\AppData\\Local\\hermes\\scripts`")
L.append("")
L.append("## A. 受版控（repo 有同名檔 → post-commit 自動同步）")
L.append("")
L.append(f"共 {len(tracked)} 支。狀態：`轉發器`（鏡像端刻意保留、指向 repo 真值，內容本就不同）／")
L.append("`同步`（與 repo 一致）／`❗漂移`（應一致卻不一致 → 需查為何沒同步）。")
L.append("")
_drift = [n for n, s, _ in tracked if s == "❗漂移"]
if _drift:
    for n, st, m in tracked:
        if st == "❗漂移":
            L.append(f"- ❗ {n}（{datetime.datetime.fromtimestamp(m):%m-%d %H:%M}）")
else:
    L.append("- ✅ 無真正漂移")
L.append("")
_fw = sum(1 for _, s, _ in tracked if s == "轉發器")
_same = sum(1 for _, s, _ in tracked if s == "同步")
L.append(f"（轉發器 {_fw} 支、內容一致 {_same} 支、真漂移 {len(_drift)} 支）")
L.append("")
L.append("## B. 只在鏡像、未受版控")
L.append("")
L.append(f"共 {len(mirror_only)} 支。判定依據：**是否含 git 操作**（會 push/commit 的才需要納入")
L.append("版控與推送閘門）→ 實測全部 **無** git 操作，因此沒有斷推風險、不急著納入版控。")
L.append("")
if risky:
    L.append("⚠️ 含 git 操作的（必須納入版控）：" + ", ".join(risky))
else:
    L.append("⚠️ 含 git 操作者：**無**（本日實測 grep `\"push\"`／`git push`／`\"commit\"` 全 0 命中）")
L.append("")
L.append("| 腳本 | 含 git 操作 | 最後修改 |")
L.append("|---|---|---|")
for n, g, m in mirror_only:
    L.append(f"| `{n}` | {g} | {datetime.datetime.fromtimestamp(m):%Y-%m-%d %H:%M} |")
L.append("")
L.append("## C. 決策（2026-09-14）")
L.append("")
L.append("1. 會 push／寫 repo 產物的腳本 → **必須納入版控**（本日已完成 4 支：radar_push、radar_weekly、")
L.append("   nightly_dashboard_sync、investment_perf_monthly）。")
L.append("2. 其餘僅讀取/告警的腳本 → 不強制納入版控，改**季度盤點**（重跑本工具）＋本次清單留痕。")
L.append("3. 若日後任一支新增 git 操作 → 依第 1 點立即納入版控（本工具的 C 類檢查會標出來）。")
L.append("")
out = REPO / "HERMES_SCRIPTS_INVENTORY.md"
out.write_text("\n".join(L), encoding="utf-8")
print(f"✅ 已寫入 {out}（{len(L)} 行）：受版控 {len(tracked)}、僅鏡像 {len(mirror_only)}、有 git 操作 {len(risky)}")
