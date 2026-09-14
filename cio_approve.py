#!/usr/bin/env python
"""CIO 審查通過 → 落地紀錄（供 .githooks/pre-push v2 驗證）

閘門設計：**綁定 tree hash**（內容），不是 commit hash（訊息）。
  - 只改 commit message（例如補 [cioreviewed] 標籤）不會讓審查失效
  - 檔案內容任何改動 → tree 改變 → 舊紀錄失效 → 必須重新送審

紀錄檔：<git-dir>/CIO_APPROVED（tab 分隔、append-only）
  TS <TAB> TREE <TAB> COMMIT <TAB> VERDICT <TAB> REVIEWER <TAB> NOTE

用法：
  python cio_approve.py --status
      顯示目前 HEAD 是否已有此 tree 的 APPROVE 紀錄
  python cio_approve.py --verdict APPROVE --reviewer "CIO-Gemini" --note "匯率修正"
      寫入目前 HEAD tree 的通過紀錄（verdict 非 APPROVE 一律拒寫）
  python cio_approve.py --verdict APPROVE --reviewer "CIO-Gemini" --result review.json
      從 CIO 審查回傳的 JSON 讀 verdict（支援 {"verdict": ...} /
      {"results": [{"verdict": ...}]} / {"structured_output": {...}}），
      只有讀到 APPROVE 才會寫入；REJECT 會 exit 1 並印出 blocking 項目。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path


def clean(value: str, maxlen: int = 120) -> str:
    """紀錄檔是 tab 分隔的 append-only 文字檔 → 一律清掉 tab/CR/LF 與控制字元。
    避免 --reviewer/--note 被注入而破壞欄位結構（或偽造出多欄/多列紀錄）。"""
    out = "".join(ch if (ch.isprintable() and ch not in "\t\r\n") else " " for ch in str(value))
    return " ".join(out.split())[:maxlen]


def git(*args: str) -> str:
    p = subprocess.run(["git", *args], capture_output=True, text=True)
    if p.returncode != 0:
        print(f"❌ git {' '.join(args)} 失敗：{p.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return p.stdout.strip()


def git_dir() -> Path:
    return Path(git("rev-parse", "--git-dir")).resolve()


def approve_file() -> Path:
    return git_dir() / "CIO_APPROVED"


def head() -> tuple[str, str]:
    return git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")


def read_rows(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(line.split("\t"))
    return rows


def is_approved(tree: str) -> bool:
    return any(len(r) >= 4 and r[1] == tree and r[3] == "APPROVE" for r in read_rows(approve_file()))


def extract_verdict(obj) -> tuple[str | None, list[str]]:
    """從各種 CIO 回傳 JSON 形狀中挖出 verdict 與 blocking 項目。"""
    blocks: list[str] = []
    if isinstance(obj, dict):
        if isinstance(obj.get("verdict"), str):
            v = obj["verdict"]
            for k in ("required_fixes", "blocking", "required_changes"):
                if isinstance(obj.get(k), list):
                    blocks += [str(x) for x in obj[k]]
            return v.upper(), blocks
        for key in ("structured_output", "result", "results", "output"):
            if key in obj:
                v, b = extract_verdict(obj[key])
                if v:
                    return v, b + blocks
        return None, blocks
    if isinstance(obj, list):
        for item in obj:
            v, b = extract_verdict(item)
            if v:
                return v, b + blocks
    return None, blocks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="只顯示目前 HEAD 的審查狀態")
    ap.add_argument("--verdict", help="APPROVE / REJECT")
    ap.add_argument("--reviewer", default="CIO", help="審查者標記（例：CIO-Gemini）")
    ap.add_argument("--note", default="", help="備註（例：改動摘要）")
    ap.add_argument("--result", help="CIO 審查回傳的 JSON 檔路徑")
    ap.add_argument("--force", action="store_true", help="略過 result 檢查（僅供人工補登，需自行負責）")
    a = ap.parse_args()

    commit, tree = head()

    if a.status:
        rows = [r for r in read_rows(approve_file()) if len(r) >= 4 and r[1] == tree]
        print(f"HEAD commit = {commit}")
        print(f"HEAD tree   = {tree}")
        print(f"紀錄檔      = {approve_file()}")
        if is_approved(tree):
            r = rows[-1]
            print(f"✅ 已通過審查（{r[3]} by {r[4] if len(r) > 4 else '?'} @ {r[0]}）")
            return 0
        print("❌ 尚無此 tree 的 APPROVE 紀錄 → push 會被擋")
        return 1

    verdict = (a.verdict or "").upper() or None
    blocks: list[str] = []
    if a.result:
        data = json.loads(Path(a.result).read_text(encoding="utf-8"))
        v, blocks = extract_verdict(data)
        if not v:
            print("❌ 無法從 result 檔讀到 verdict，拒寫紀錄", file=sys.stderr)
            return 2
        verdict = v
        if a.verdict and a.verdict.upper() != v:
            print(f"❌ --verdict({a.verdict}) 與 result({v}) 不一致，拒寫紀錄", file=sys.stderr)
            return 2

    if not verdict and not a.force:
        print("❌ 需指定 --verdict 或 --result（或 --status）", file=sys.stderr)
        return 2
    if verdict != "APPROVE" and not a.force:
        print(f"⛔ 審查結論為 {verdict or '未提供'} → 不寫入通過紀錄。", file=sys.stderr)
        for b in blocks:
            print(f"   必修：{b}", file=sys.stderr)
        return 1

    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    reviewer = clean(a.reviewer) or "UNKNOWN"
    note = clean(a.note)
    line = "\t".join([ts, tree, commit, "APPROVE", reviewer, note])
    # 寫入前自我檢查：欄位數必須為 6（防注入破壞格式）
    if len(line.split("\t")) != 6:
        print("❌ 紀錄行欄位數異常，拒寫（sanitize 失效）", file=sys.stderr)
        return 2
    with approve_file().open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(f"✅ 已寫入審查紀錄：tree {tree[:12]} commit {commit[:12]} by {reviewer}")
    print(f"   {approve_file()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
