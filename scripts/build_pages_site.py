#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_pages_site.py — 組裝 Pages 部署內容（INC-PAGES-DEPLOY-OPTIMIZATION）

本機與 GitHub Actions 共用同一支腳本，確保 `_site` 逐位元一致。

規則：
  1. index.html 必存在，缺 → exit 1
  2. 報表：檔名符合 --pattern（預設 2026-10-24 起的日報/報表樣式）→ 納入
  3. allowlist：scripts/pages_allowlist.txt 逐行複製，保留原目錄結構；缺檔 → exit 1 並列出
  4. 保留窗口（2026-11-28 使用者核准 A 案）：
       --keep-days（HTML，預設 28）／--keep-days-img（圖檔，預設 7）
       無日期檔（入口/設定/assets）一律保留。基準日＝picked 內最新檔名日期。
  5. 護欄：
       超過 --max-mb（預設 32）→ 先「整日封存」最舊日期直到回到上限內（印出清單、照常部署）；
       --no-trim 時改回舊行為（exit 2 不部署）。
       裁無可裁仍超 → exit 2（真正超限，需人工處理）。
  6. 收尾：寫 .nojekyll、404.html、manifest.json（path, bytes, sha256；含 archived 清單）

用法：
  python scripts/build_pages_site.py --out _site
  python scripts/build_pages_site.py --out _tmp_site --pattern '2026-(10-(2[4-9]|3[01])|11-)'
  python scripts/build_pages_site.py --out _site --keep-days 60 --keep-days-img 30
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATTERN = r"2026-(10-(2[4-9]|3[01])|11-)"
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")
DATE_RE_DASH = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
DATE_RE_PLAIN = re.compile(r"(20\d{2})(\d{2})(\d{2})")
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


def date_of(name: str) -> str | None:
    """檔名內的日期（YYYY-MM-DD）；無日期回 None（入口/設定/assets 類）。"""
    base = os.path.basename(name)
    m = DATE_RE_DASH.search(base) or DATE_RE_PLAIN.search(base)
    if not m:
        return None
    y, mo, d = m.groups()
    try:
        return date(int(y), int(mo), int(d)).isoformat()
    except ValueError:
        return None


def total_size(root: str, paths) -> int:
    return sum(os.path.getsize(os.path.join(root, p)) for p in paths)


def index_protected(root: str) -> set[str]:
    """index.html 直接引用的站內檔案 → 永久保留（不得被保留窗口或容量裁剪封存）。

    2026-11-28 實測案例：investment_structure_plan_card_2026-10-20.html 是常設入口卡，
    檔名帶日期但非日報，若被 28 天窗口封存 → 首頁點擊變 404。
    """
    idx = os.path.join(root, "index.html")
    if not os.path.exists(idx):
        return set()
    text = open(idx, encoding="utf-8", errors="ignore").read()
    out: set[str] = set()
    for m in re.finditer(r'(?:href|src)="([^"]+)"', text):
        u = m.group(1).strip()
        if not u or u.startswith(("http", "//", "#", "mailto:", "javascript:", "data:")):
            continue
        u = u.split("?")[0].split("#")[0].lstrip("./")
        if not u or u.endswith("/"):
            continue
        if os.path.exists(os.path.join(root, u.replace("\\", "/"))):
            out.add(u.replace("\\", "/"))
    return out


def apply_keep_days(picked: list[str], keep_html: int, keep_img: int, protect: set[str] | None = None):
    """按保留窗口過濾；回 (kept, dropped)。index.html、首頁引用檔與無日期檔永久保留。"""
    protect = protect or set()
    dates = [date_of(p) for p in picked]
    base_s = max((d for d in dates if d), default=None)
    if not base_s:
        return picked, []
    base = date.fromisoformat(base_s)
    cut_html = (base - timedelta(days=int(keep_html))).isoformat()
    cut_img = (base - timedelta(days=int(keep_img))).isoformat()
    kept, dropped = [], []
    for p in picked:
        d = date_of(p)
        if d is None or p == "index.html" or p in protect:
            kept.append(p)
            continue
        cut = cut_img if os.path.splitext(p)[1].lower() in IMG_EXTS else cut_html
        (kept if d >= cut else dropped).append(p)
    return kept, dropped


def trim_oldest_days(root: str, picked: list[str], max_bytes: int, protect: set[str] | None = None):
    """整日封存：由最舊日期開始整組移出，直到總量 <= max_bytes。回 (kept, dropped, bytes)。"""
    protect = protect or set()
    groups: dict[str | None, list[str]] = {}
    for p in picked:
        groups.setdefault(date_of(p), []).append(p)
    cur = total_size(root, picked)
    dropped: list[str] = []
    for d in sorted((k for k in groups if k), key=lambda x: x):
        if cur <= max_bytes:
            break
        for p in groups[d]:
            if p == "index.html" or p in protect:
                continue
            cur -= os.path.getsize(os.path.join(root, p))
            dropped.append(p)
    drop_set = set(dropped)
    kept = [p for p in picked if p not in drop_set]
    return kept, dropped, cur


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=BASE)
    ap.add_argument("--out", required=True)
    ap.add_argument("--allowlist", default=None)
    ap.add_argument("--pattern", default=DEFAULT_PATTERN)
    ap.add_argument("--max-mb", type=float, default=32.0,
                    help="站點總容量上限（MB）。2026-11-28 由 25.0 提高：allowlist 依站內引用自動展開，"
                         "歷史日報/圖檔逐日累積，07:00 產線新增後 25.33MB 觸頂 → Pages build exit 2。")
    ap.add_argument("--keep-days", type=int, default=28,
                    help="HTML 報表保留天數（預設 28；以最新檔名日期為基準）")
    ap.add_argument("--keep-days-img", type=int, default=7,
                    help="圖檔保留天數（預設 7；圖的歷史參考價值低、體積占比最高）")
    ap.add_argument("--no-trim", action="store_true",
                    help="停用自動整日封存；超限一律 exit 2（舊 fail-loud 行為）")
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

    # 4) 保留窗口（首頁直接引用的常設頁永久保留）
    protect = index_protected(root)
    before_n = len(picked)
    picked, archived_by_window = apply_keep_days(picked, a.keep_days, a.keep_days_img, protect)
    if archived_by_window:
        print(f"🗂 保留窗口：HTML {a.keep_days} 天／圖 {a.keep_days_img} 天"
              f" → 封存 {len(archived_by_window)} 檔（{before_n} → {len(picked)}）")

    # 5) 護欄：超限先整日封存最舊，仍超才失敗
    max_bytes = int(a.max_mb * 1048576)
    cur = total_size(root, picked)
    archived_by_size: list[str] = []
    if cur > max_bytes:
        if a.no_trim:
            print(f"❌ 超過上限 {a.max_mb} MB（{cur/1048576:.2f} MB）→ --no-trim，中止（exit 2，不部署）")
            return 2
        picked, archived_by_size, cur = trim_oldest_days(root, picked, max_bytes, protect)
        print(f"⚠️ 超限 {a.max_mb} MB → 自動整日封存最舊 {len(set(date_of(p) for p in archived_by_size))} 天"
              f"／{len(archived_by_size)} 檔 → 現 {cur/1048576:.2f} MB（照常部署）")
        if archived_by_size:
            for d in sorted({date_of(p) for p in archived_by_size if date_of(p)}):
                print(f"   · 封存至 {d}")

    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out, exist_ok=True)

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

    # P0 pages-01（2026-11-11）：前端要 fetch snapshot.json 做即時渲染（不能下架），
    # 但原檔含帳號/保單號/身分證片段 → 發布前一律換成淨化版；淨化失敗即中止（fail-loud）。
    if "snapshot.json" in picked:
        rc = subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "sanitize_snapshot_public.py"),
             "--src", os.path.join(root, "snapshot.json"),
             "--dst", os.path.join(out, "snapshot.json")],
            capture_output=True, text=True,
        )
        if rc.returncode != 0:
            print("❌ 公開版 snapshot 淨化失敗 → 中止部署（fail-loud）")
            print(rc.stdout.strip() or rc.stderr.strip())
            return 1
        print("  " + (rc.stdout.strip() or "snapshot.json 已淨化"))
        _p2 = os.path.join(out, "snapshot.json")
        for _m in manifest:
            if _m["path"] == "snapshot.json":
                _m["bytes"] = os.path.getsize(_p2)
                _m["sha256"] = sha256(_p2)
                _m["sanitized"] = True
        total = sum(_m["bytes"] for _m in manifest)

    open(os.path.join(out, ".nojekyll"), "w").close()
    with open(os.path.join(out, "404.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(NOT_FOUND_HTML)
    archived = sorted(set(archived_by_window) | set(archived_by_size))
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"files": manifest, "count": len(manifest), "bytes": total,
                   "keep_days": {"html": a.keep_days, "img": a.keep_days_img},
                   "archived_count": len(archived),
                   "archived": archived}, f,
                  ensure_ascii=False, indent=1)

    mb = total / 1048576
    print(f"✅ _site 完成：{len(manifest)} 檔 / {mb:.2f} MB → {out}")
    if mb > a.max_mb:
        print(f"❌ 裁無可裁仍超過上限 {a.max_mb} MB → 中止（exit 2，不部署）")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
