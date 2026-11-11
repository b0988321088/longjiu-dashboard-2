#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sanitize_snapshot_public.py — 產出可公開的 snapshot（P0 pages-01 收斂）

背景：前端 index.html 需要 fetch snapshot.json 做即時渲染（18 處），所以不能整個下架；
      但原檔含帳號、保單號、身分證片段與內部註記，任何人都能直接下載。

做法：結構與數字全部保留（前端只吃數字），只把「字串值」中的識別碼洗掉：
      銀行帳號、保單號、身分證、卡號、已遮蔽片段。不刪 key、不改型別，避免前端壞掉。

用法：python scripts/sanitize_snapshot_public.py --src snapshot.json --dst _site/snapshot.json
"""
import argparse
import json
import re
import sys

REDACT = "[已遮蔽]"
PATTERNS = [
    re.compile(r"\d{2,3}[-\u2013\uff0d]\d{6,}"),              # 812-000123456789
    re.compile(r"[A-Z]{2}\d{8}"),                              # QL18610694 保單號
    re.compile(r"[A-Z]\d{9}"),                                 # B121835155 身分證
    re.compile(r"\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}"),        # 卡號
    re.compile(r"\d{6,}[*]{2,}\d*"),                           # 000123******55
    re.compile(r"[A-Za-z0-9]{0,6}[*]{3,}[0-9A-Za-z]*"),        # B121***155
]
NAMES = ("梁世寶",)


def scrub_str(s: str) -> str:
    out = s
    for rx in PATTERNS:
        out = rx.sub(REDACT, out)
    for n in NAMES:
        out = out.replace(n, REDACT)
    return out


def walk(o):
    if isinstance(o, str):
        return scrub_str(o)
    if isinstance(o, list):
        return [walk(x) for x in o]
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            nk = scrub_str(k) if isinstance(k, str) else k
            if nk in out:  # 兩把 key 洗成同一個 → 加序號，避免覆蓋
                i = 2
                while f"{nk}#{i}" in out:
                    i += 1
                nk = f"{nk}#{i}"
            out[nk] = walk(v)
        return out
    return o


def count_hits(o, acc=None) -> int:
    acc = acc if acc is not None else [0]
    if isinstance(o, str):
        if REDACT in o:
            acc[0] += o.count(REDACT)
    elif isinstance(o, list):
        for x in o:
            count_hits(x, acc)
    elif isinstance(o, dict):
        for v in o.values():
            count_hits(v, acc)
    return acc[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="snapshot.json")
    ap.add_argument("--dst", required=True)
    a = ap.parse_args()
    with open(a.src, encoding="utf-8") as f:
        snap = json.load(f)
    before_keys = len(snap)
    clean = walk(snap)
    hits = count_hits(clean)
    with open(a.dst, "w", encoding="utf-8", newline="\n") as f:
        json.dump(clean, f, ensure_ascii=False)
    # fail-loud：洗後仍留識別碼就中止
    leaked = []
    for rx in PATTERNS[:4]:
        if rx.search(open(a.dst, encoding="utf-8").read()):
            leaked.append(rx.pattern)
    if leaked:
        print(f"❌ 仍有識別碼殘留，patterns={leaked}")
        return 1
    print(f"✅ 公開版 snapshot：{before_keys} 個頂層 key 全保留｜遮蔽 {hits} 處識別碼")
    return 0


if __name__ == "__main__":
    sys.exit(main())
