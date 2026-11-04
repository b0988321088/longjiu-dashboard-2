#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""site_sync.py — 由白名單建置 Pages 專用公開產物目錄（P0 公開面隔離）。

為什麼存在（2026-10-15）：
  實測 2205 個版控檔案中 2202 個可從 Pages 直接下載（含 dragon_assets.db、388 個 .py、
  396 個 .md、備份與簡報）。根因＝repo 根目錄 `.nojekyll` 使 Jekyll 排除失效，
  Pages 成為「整個 repo 的原樣鏡像」。本模組把發布面收斂成 `site/`：只放白名單檔案，
  並在 `site/` 內放 `.nojekyll`，使 Pages 以專用目錄為來源時原樣提供、不經 Jekyll。

不變量（fail-closed）：
  · deny 規則（副檔名／前綴／glob）優先於任何 include。
      - 明文 include_exact 命中 deny → **整批失敗**（不得被悄悄吞掉）。
      - glob 命中 deny → 略過並列為 skipped（樣式仍須有可用命中，否則失敗）。
  · 逐字路徑不存在 → 失敗；glob 可用命中 0 檔 → 失敗。
  · 產出後自掃描：`site/` 內不得出現任何 deny 命中。
  · 鏈結閉包：入口（index.html）可達範圍內的本地引用必須全部落在 `site/` 內；
    未落在其中的引用會被列出（可能是排程尚未產出或刻意撤下），不靜默。

用法：
    python -X utf8 site_sync.py            # 建置並驗證
    python -X utf8 site_sync.py --check    # 只檢查不寫入

本模組不 commit、不 push、不碰遠端。
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG = BASE / "site_whitelist.json"
OUT_DIR = BASE / "site"
MANIFEST = BASE / "site_manifest.json"
WEB_EXT = {".html", ".htm", ".css", ".js", ".json", ".jsonl", ".csv", ".png", ".jpg", ".jpeg",
           ".svg", ".webp", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".txt", ".md", ".mp4", ".mp3"}
REF = re.compile(r"""(?:href|src)\s*=\s*["']([^"'>]+)["']|fetch\(\s*["']([^"']+)["']|"""
                 r"""open\(\s*["']([^"']+)["']""")


def tracked() -> list[str]:
    r = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=str(BASE),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [p for p in r.stdout.split("\n") if p.strip()]


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def denied(rel: str, cfg: dict) -> str | None:
    low = rel.lower()
    for ext in cfg["deny_extensions"]:
        if low.endswith(ext):
            return f"副檔名 {ext}"
    for pre in cfg["deny_prefixes"]:
        if rel.startswith(pre):
            return f"前綴 {pre}"
    for pat in cfg["deny_globs"]:
        if fnmatch.fnmatch(Path(rel).name, pat):
            return f"樣式 {pat}"
    return None


def resolve(cfg: dict, files: list[str]) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    """回傳（選中, 錯誤, 略過清單）。"""
    errs: list[str] = []
    skipped: list[tuple[str, str]] = []
    sel: list[str] = []
    for rel in cfg["include_exact"]:
        if rel not in files:
            errs.append(f"include_exact 指到不存在的檔案：{rel}")
            continue
        why = denied(rel, cfg)
        if why:
            errs.append(f"🔴 include_exact 與 deny 衝突（{why}）：{rel}")
            continue
        sel.append(rel)
    for rel in cfg.get("required_exact", []):
        if rel not in files:
            errs.append(f"必要檔案不存在：{rel}")
    for entry in cfg.get("include_latest", []):
        pat, keep = entry["pattern"], int(entry.get("keep", 1))
        hits = sorted((f for f in files if fnmatch.fnmatch(Path(f).name, pat)), reverse=True)
        usable: list[str] = []
        for f in hits:
            why = denied(f, cfg)
            if why:
                skipped.append((f, f"{why}（樣式 {pat}）"))
                continue
            usable.append(f)
        if not usable:
            errs.append(f"include_latest 樣式無可用命中：{pat}")
            continue
        sel.extend(usable[:keep])
    for pat in cfg.get("include_globs", []):
        hits = [f for f in files if fnmatch.fnmatch(Path(f).name, pat)]
        usable = []
        for f in hits:
            why = denied(f, cfg)
            if why:
                skipped.append((f, f"{why}（樣式 {pat}）"))
                continue
            usable.append(f)
        if not usable:
            errs.append(f"include_globs 樣式無可用命中：{pat}")
        sel.extend(usable)
    return sorted(set(sel)), errs, skipped


def link_check(sel: list[str], files: list[str]) -> tuple[list[str], list[str]]:
    """走訪入口可達的本地引用，回傳（落在 site/ 內, 未落在其中）。

    只走訪「已選中且為網頁／樣式／指令碼」的檔案，避免把歷史報表的舊鏈結當成缺失。
    """
    pub = set(sel)
    need: set[str] = set()
    frontier = [p for p in sel if p == "index.html"]
    seen: set[str] = set()
    while frontier:
        cur = frontier.pop()
        if cur in seen:
            continue
        seen.add(cur)
        src = BASE / cur
        if not src.exists() or src.suffix.lower() not in {".html", ".htm", ".js", ".css"}:
            continue
        txt = src.read_text(encoding="utf-8", errors="ignore")
        for m in REF.finditer(txt):
            u = next((x for x in m.groups() if x), None)
            if not u:
                continue
            u = u.split("?")[0].split("#")[0].strip().lstrip("./")
            if not u or u.startswith(("http://", "https://", "data:", "mailto:", "javascript:", "//")):
                continue
            if Path(u).suffix.lower() not in WEB_EXT:
                continue
            need.add(u)
            if u in pub:
                frontier.append(u)
    inside = sorted(n for n in need if n in pub)
    outside = sorted(n for n in need if n not in pub)
    return inside, outside


def build(sel: list[str], cfg: dict, *, check_only: bool) -> tuple[int, dict]:
    hashes: dict[str, str] = {}
    total = 0
    for rel in sel:
        src = BASE / rel
        if not src.is_file():
            print(f"❌ 來源非檔案：{rel}", file=sys.stderr)
            return 1, {}
        data = src.read_bytes()
        hashes[rel] = hashlib.sha256(data).hexdigest()[:12]
        total += len(data)
    bad = [(p, denied(p, cfg)) for p in sel if denied(p, cfg)]
    if bad:
        print(f"❌ 產出自掃描失敗（含 deny 命中）：{bad}", file=sys.stderr)
        return 1, {}
    if not check_only:
        if OUT_DIR.exists():
            try:
                shutil.rmtree(OUT_DIR)
            except PermissionError:
                # Windows：目錄被其他程序開啟（例如本機驗證用的 http.server cwd）
                # → 只清內容物，不刪目錄本身；語意相同（發布面必須與白名單一致）。
                for child in OUT_DIR.iterdir():
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                    else:
                        child.unlink()
        else:
            OUT_DIR.mkdir(parents=True)
        for rel in sel:
            dst = OUT_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(BASE / rel, dst)
        (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    man = {"generated_by": "site_sync.py", "entry": cfg["entry"], "count": len(sel),
           "bytes": total, "files": hashes}
    if not check_only:
        MANIFEST.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0, man


def commit_site(sel: list[str], cfg: dict) -> tuple[int, str]:
    """只提交 site/ 與 site_manifest.json（逐字 pathspec；staged 超出即 fail-closed）。不推送。

    為什麼不能 add -A：工作區同時有其他車道（程式修復、備份、證據）的變更，
    任何一次 `git add -A` 都會把它們夾進本輪提交並一起上線 —— 這正是 2026-10-15 以前
    反覆發生的「變相發布」根因。site 車道只認領自己產出的檔案。
    """
    allow = {f"site/{p}" for p in sel} | {"site_manifest.json"}
    paths = sorted(allow)
    r = subprocess.run(["git", "add", "--", *paths], cwd=str(BASE), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return 1, f"git add 失敗：{(r.stderr or '').strip()[:160]}"
    st = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=str(BASE),
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    staged = [x for x in st.stdout.split("\n") if x.strip()]
    beyond = [s for s in staged if s not in allow]
    if beyond:
        return 1, f"staged 超出 site 車道（fail-closed，未提交）：{beyond[:5]}"
    if not staged:
        return 0, "site/ 已同步（無變更）"
    c = subprocess.run(["git", "commit", "-m", f"build(site): 公開產物目錄同步（{len(sel)} 檔）"],
                       cwd=str(BASE), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if c.returncode != 0:
        return 1, f"commit 失敗：{(c.stderr or '').strip()[:160]}"
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(BASE),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace").stdout.strip()
    return 0, f"已提交（推送待獨立審查）：{head}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只檢查不寫入")
    ap.add_argument("--commit", action="store_true",
                    help="建置後只提交 site/ 與 site_manifest.json（不推送）")
    ap.add_argument("--json", action="store_true", help="輸出 JSON 摘要")
    a = ap.parse_args()
    cfg = load_config()
    files = tracked()
    sel, errs, skipped = resolve(cfg, files)
    if errs:
        print("❌ 白名單解析失敗（fail-closed，未產出）：", file=sys.stderr)
        for e in errs:
            print(f"   · {e}", file=sys.stderr)
        return 1
    rc, man = build(sel, cfg, check_only=a.check)
    if rc:
        return rc
    inside, outside = link_check(sel, files)
    man["link_check"] = {"inside": inside, "outside": outside}
    if not a.check:
        MANIFEST.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"版控檔案 {len(files)} 檔 → 白名單 {len(sel)} 檔、{man['bytes']:,} bytes"
          f"（{'檢查' if a.check else '已建置到 ' + str(OUT_DIR)}）")
    print(f"deny 略過 {len(skipped)} 檔" + (f"｜樣本 {skipped[:3]}" if skipped else ""))
    print(f"入口鏈結閉包：落在 site/ 內 {len(inside)} 個引用｜未落在其中 {len(outside)} 個"
          + (f" → {outside}" if outside else ""))
    if a.json:
        print(json.dumps({k: man[k] for k in ("count", "bytes")}, ensure_ascii=False))
    if a.commit:
        rc2, msg = commit_site(sel, cfg)
        print(("✅ " if rc2 == 0 else "❌ ") + f"site 車道提交：{msg}")
        if rc2:
            return rc2
    return 0


if __name__ == "__main__":
    sys.exit(main())
