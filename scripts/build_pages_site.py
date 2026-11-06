#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_pages_site.py — 組裝 Pages 部署內容（INC-PAGES-DEPLOY-OPTIMIZATION）

本機與 GitHub Actions 共用同一支腳本，確保 `_site` 逐位元一致。

規則：
  1. index.html 必存在，缺 → exit 1
  2. 報表：檔名符合 --pattern（預設 2026-10-24 起的日報/報表樣式）→ 納入
  3. allowlist：scripts/pages_allowlist.txt 逐行複製，保留原目錄結構；缺檔 → exit 1 並列出
  4. 護欄：總量 > --max-mb（預設 25）→ exit 2
  5. 收尾：寫 .nojekyll、404.html、manifest.json（path, bytes, sha256）

用法：
  python scripts/build_pages_site.py --out _site
  python scripts/build_pages_site.py --out _tmp_site --pattern '2026-(10-(2[4-9]|3[01])|11-)'
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATTERN = r"2026-(10-(2[4-9]|3[01])|11-)"
NOT_FOUND_HTML = """<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>頁面已封存</title>
<style>body{font:16px/1.8 -apple-system,"Noto Sans TC",sans-serif;max-width:640px;margin:12vh auto;padding:0 20px;color:#1d1d1f}
a{color:#0a7d32}h1{font-size:22px}</style></head><body>
<h1>這個頁面已封存</h1>
<p>為了讓每日報告的部署維持穩定，較舊的報表已移至封存分支，不再隨站台發布。</p>
<p>· <a href="/longjiu-dashboard-2/">回首頁（最新儀表板）</a><br>
· 封存查詢：GitHub 分支 <code>archive-media</code>（保留原始路徑）</p>
</body></html>
"""


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=BASE)
    ap.add_argument("--out", required=True)
    ap.add_argument("--allowlist", default=None)
    ap.add_argument("--pattern", default=DEFAULT_PATTERN)
    ap.add_argument("--max-mb", type=float, default=25.0)
    a = ap.parse_args()

    root = os.path.abspath(a.root)
    out = os.path.abspath(a.out)
    allow = a.allowlist or os.path.join(root, "scripts", "pages_allowlist.txt")

    if not os.path.exists(os.path.join(root, "index.html")):
        print("❌ index.html 不存在 → 中止（exit 1）")
        return 1
    if not os.path.exists(allow):
        print(f"❌ allowlist 不存在：{allow} → 先跑 gen_pages_allowlist.py（exit 1）")
        return 1

    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out, exist_ok=True)

    picked: list[str] = ["index.html"]
    rx = re.compile(a.pattern)
    for fn in sorted(os.listdir(root)):
        if fn.endswith(".html") and rx.search(fn) and fn not in picked:
            picked.append(fn)

    missing: list[str] = []
    with open(allow, encoding="utf-8") as f:
        for line in f:
            p = line.strip()
            if not p or p.startswith("#"):
                continue
            if not os.path.exists(os.path.join(root, p)):
                missing.append(p)
                continue
            if p not in picked:
                picked.append(p)

    if missing:
        print("❌ allowlist 內檔案不存在（fail-loud，不靜默跳過）：")
        for m in missing:
            print("   -", m)
        return 1

    manifest = []
    total = 0
    for p in picked:
        src = os.path.join(root, p)
        dst = os.path.join(out, p)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        size = os.path.getsize(dst)
        total += size
        manifest.append({"path": p, "bytes": size, "sha256": sha256(dst)})

    open(os.path.join(out, ".nojekyll"), "w").close()
    with open(os.path.join(out, "404.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(NOT_FOUND_HTML)
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"files": manifest, "count": len(manifest), "bytes": total}, f,
                  ensure_ascii=False, indent=1)

    mb = total / 1048576
    print(f"✅ _site 完成：{len(manifest)} 檔 / {mb:.2f} MB → {out}")
    if mb > a.max_mb:
        print(f"❌ 超過上限 {a.max_mb} MB → 中止（exit 2，不部署）")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
