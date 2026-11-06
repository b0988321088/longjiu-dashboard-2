#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_pages_allowlist.py — 掃描站內引用，產生 Pages 允許清單（INC-PAGES-DEPLOY-OPTIMIZATION）

用途：Pages 部署只帶「真的會被用到的檔案」。清單由掃描產生，不由人工挑選。
輸出：scripts/pages_allowlist.txt（每行一個 repo 相對路徑，排序去重）

掃描來源：所有 .html/.js 的
  · src|href 屬性
  · fetch('...')／fetch("...")
  · CSS url(...)
忽略：http(s)://、// 開頭的 protocol-relative、mailto:、data:、javascript:、純 anchor

--report：印出「被引用但 repo 內不存在」清單（施工前必須為空）
"""
from __future__ import annotations

import argparse
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAT_ATTR = re.compile(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', re.I)
PAT_FETCH = re.compile(r'fetch\(\s*["\']([^"\']+)["\']')
PAT_URL = re.compile(r'url\(\s*["\']?([^)"\']+)')
SKIP_PREFIX = ("http://", "https://", "//", "mailto:", "data:", "javascript:", "#")


def iter_sources(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                        if d not in ("node_modules", "_site", "_tmp_site", "__pycache__")
                        and not d.startswith(".")]
        for fn in filenames:
            if fn.endswith((".html", ".js")):
                yield os.path.join(dirpath, fn)


def collect(root: str) -> tuple[set[str], list[str]]:
    refs: set[str] = set()
    for path in iter_sources(root):
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for rx in (PAT_ATTR, PAT_FETCH, PAT_URL):
            for m in rx.finditer(text):
                u = m.group(1).strip()
                if not u or u.startswith(SKIP_PREFIX):
                    continue
                u = u.split("?")[0].split("#")[0].lstrip("./")
                if os.path.splitext(u)[1] and not u.endswith("/"):
                    refs.add(u.replace("\\", "/"))
    # 分類：站內目錄底下的缺檔＝真斷鏈；首段不是站內目錄者＝外部／存檔頁殘留（忽略）
    internal_dirs = {d for d in os.listdir(root)
                     if os.path.isdir(os.path.join(root, d)) and not d.startswith(".")}
    missing, external = [], []
    for u in refs:
        if os.path.exists(os.path.join(root, u)):
            continue
        first = u.split("/")[0]
        (missing if (first in internal_dirs or "/" not in u) else external).append(u)
    return refs, sorted(missing), sorted(external)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=BASE)
    ap.add_argument("--out", default=os.path.join(BASE, "scripts", "pages_allowlist.txt"))
    ap.add_argument("--report", action="store_true", help="只印出被引用但不存在的清單")
    a = ap.parse_args()

    refs, missing, external = collect(a.root)
    if a.report:
        print(f"站內引用資產：{len(refs)} 檔")
        print(f"被引用但不存在（站內）：{len(missing)}")
        print(f"外部／存檔頁殘留（忽略）：{len(external)}")
        for m in missing:
            print("  MISS", m)
        return 0 if not missing else 3

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 由 gen_pages_allowlist.py 自動產生，勿手改（INC-PAGES-DEPLOY-OPTIMIZATION）\n")
        for u in sorted(x for x in refs if os.path.exists(os.path.join(a.root, x))):
            f.write(u + "\n")
    print(f"✅ allowlist: {a.out}（{len(refs)} 檔）｜缺檔 {len(missing)}")
    if missing:
        for m in missing:
            print("  MISS", m)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
