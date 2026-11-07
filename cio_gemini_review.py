#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cio_gemini_review.py — Google Gemini 作為 CIO 審查者的落地工具

用途
    push 前對「含程式檔的 commit」做獨立審查，通過後自動寫入
    <git-dir>/CIO_APPROVED（綁 tree hash），供 .githooks/pre-push v5 放行。

設計原則
    1. 只負責「審查 + 落紀錄」，不 push、不 commit（推送仍由人/既有車道決定）。
    2. fail-closed：verdict 非 APPROVE 或 blocking 非空 → 一律不落紀錄、exit 1。
    3. 不印出 API key；憑證只從 Hermes 的 .env 讀。
    4. 真值背景由 snapshot.json 動態取，不寫死金額與比例。
    5. 模型備援鏈：3.1-pro-preview → 3.5-flash → 2.5-flash（實測 2.5-pro 對新用戶回 404）。

用法
    python cio_gemini_review.py --dry-run              # 只看審查結果，不落紀錄
    python cio_gemini_review.py                        # 審 origin/clean-main..HEAD 並落紀錄
    python cio_gemini_review.py --range HEAD~2..HEAD   # 指定範圍
    python cio_gemini_review.py --commits 52dfc1e4 aaef417a
    python cio_gemini_review.py --model gemini-3.5-flash --max-diff 60000
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENV_CANDIDATES = (
    Path(os.path.expanduser("~/AppData/Local/hermes/.env")),
    BASE / ".env",
)
MODEL_CHAIN = ("gemini-3.1-pro-preview", "gemini-3.5-flash", "gemini-2.5-flash")
REVIEW_OUT = BASE / "cio_review_gemini_latest.json"
RAW_OUT = BASE / "cio_review_gemini_latest_raw.txt"


def load_env() -> dict:
    cfg: dict[str, str] = {}
    for p in ENV_CANDIDATES:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            k, v = line.split("=", 1)
            cfg.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return cfg


def git(*args: str) -> str:
    p = subprocess.run(["git", *args], cwd=BASE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise SystemExit(f"❌ git {' '.join(args)} 失敗：{(p.stderr or '').strip()[:300]}")
    return p.stdout


def snapshot_brief() -> str:
    """動態取真值背景，避免 prompt 內寫死金額。"""
    try:
        d = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    except Exception as e:
        return f"（snapshot 讀取失敗：{type(e).__name__}）"
    pen = d.get("penetration") or {}
    pct = pen.get("actual_pct") or {}
    cl = d.get("cash_layers") or {}
    gold = "; ".join(f"{k} {v}%" for k, v in pct.items())
    return (
        f"總資產 {d.get('total_assets', 0):,.0f}｜現金 {cl.get('cash_total', 0):,.0f}"
        f"（可動用 {cl.get('unrestricted_cash', 0):,.0f}／乾粉 {cl.get('dry_powder', 0):,.0f}）\n"
        f"五桶：{gold}\n"
        f"證券市值 {((d.get('securities') or {}).get('total_market_value') or 0):,.0f}"
        f"（{(d.get('securities') or {}).get('price_date') or '—'}，"
        f"{len((d.get('securities') or {}).get('holdings') or [])} 檔）"
    )


def collect(args) -> tuple[list[str], str, str]:
    if args.commits:
        shas = args.commits
    elif args.range:
        shas = [s for s in git("rev-list", "--reverse", args.range).split() if s]
    else:
        shas = [s for s in git("rev-list", "--reverse", "origin/clean-main..HEAD").split() if s]
    if not shas:
        raise SystemExit("❌ 沒有待審 commit（範圍為空）")

    blocks = []
    for sha in shas:
        stat = git("show", "--stat", "--format=%h %s", sha).strip()
        body = git("log", "-1", "--format=%B", sha).strip()
        blocks.append(f"### {sha}\n{stat}\n\n訊息：\n{body[:1200]}")
    stat_all = "\n\n".join(blocks)
    diff = git("show", "--unified=2", *shas)
    if len(diff) > args.max_diff:
        diff = diff[: args.max_diff] + f"\n\n…（diff 超過 {args.max_diff} 字元已截斷）"
    return shas, stat_all, diff


def build_prompt(shas: list[str], stat_all: str, diff: str) -> str:
    return f"""你是龍九控股的 CIO，對下列 commit 做獨立審查（審查者＝Gemini，非產出者自查）。

## 待審 commit（{len(shas)} 筆）
{stat_all}

## diff（過長會截斷）
{diff}

## 目前真值（由 snapshot 動態讀取）
{snapshot_brief()}

## 審查項目（逐項判定，發現即列入 blocking）
1. 真值一致性：同義欄位、五桶加總、總資產是否閉合
2. 口徑正確性：現金／可動用／乾粉／在途／指定款是否被混用
3. 程式改動：是否有未覆蓋分支、硬寫會過期的金額或日期、fail-open 風險
4. 下游影響：日報／儀表板／穿透／決策紀錄是否同步
5. 安全性：是否新增敏感資料（帳號、身分證、金鑰、個資）
6. 語言規範：繁體中文（台灣用語），不得有簡體字或韓日文
7. 治理：是否繞過閘門、是否把授權寫成事實

## 輸出（只輸出 JSON，不要其他文字）
{{"verdict":"APPROVE 或 REJECT","blocking":["必須修才能上線"],"required_fixes":["非阻擋但應修"],"summary":"三到五句","risks":["殘留風險"]}}
沒有阻擋問題時，blocking 必須是 []。"""


def call_gemini(prompt: str, chain: tuple[str, ...], cfg: dict, timeout: int = 240) -> tuple[dict, str, str]:
    base = cfg.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
    key = cfg.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("❌ 找不到 GEMINI_API_KEY（檢查 ~/AppData/Local/hermes/.env）")
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 512},
        },
    }
    payload = json.dumps(body).encode()
    last = ""
    for model in chain:
        url = f"{base}/models/{model}:generateContent?key={key}"
        req = urllib.request.Request(url, data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
            cand = (resp.get("candidates") or [{}])[0]
            txt = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
            if not txt.strip():
                last = f"{model}: 空回應（finishReason={cand.get('finishReason')}）"
                print(f"  ⚠️ {last}")
                continue
            print(f"  ✅ {model}｜{time.time() - t0:.1f}s｜{len(txt)} 字"
                  f"｜finish={cand.get('finishReason')}")
            return _parse_json(txt), model, txt
        except urllib.error.HTTPError as e:
            last = f"{model}: HTTP {e.code} {e.read().decode(errors='replace')[:160]}"
        except Exception as e:
            last = f"{model}: {type(e).__name__} {str(e)[:160]}"
        print(f"  ❌ {last}")
    raise SystemExit("❌ 全部模型失敗：" + last)


def _parse_json(txt: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        raise SystemExit("❌ 回應不是合法 JSON（原始內容見 cio_review_gemini_latest_raw.txt）")


def approve(rev: dict, model: str, shas: list[str], note: str) -> int:
    cmd = [sys.executable, "cio_approve.py", "--verdict", "APPROVE",
           "--reviewer", "CIO-Gemini", "--result", str(REVIEW_OUT),
           "--note", f"{model}｜{len(shas)} 筆｜{note}"[:120]]
    p = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = ((p.stdout or "") + (p.stderr or "")).strip()
    print(out[-500:] if out else "（cio_approve 無輸出）")
    return p.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="Gemini CIO 審查（commit range → APPROVE 落紀錄）")
    ap.add_argument("--range", help="git range，如 origin/clean-main..HEAD")
    ap.add_argument("--commits", nargs="+", help="指定 commit（預設 origin/clean-main..HEAD）")
    ap.add_argument("--model", default=MODEL_CHAIN[0], help=f"主模型（預設 {MODEL_CHAIN[0]}）")
    ap.add_argument("--max-diff", type=int, default=45000, help="diff 字元上限")
    ap.add_argument("--dry-run", action="store_true", help="只審查，不落紀錄")
    ap.add_argument("--no-approve", action="store_true", help="同 --dry-run")
    ap.add_argument("--note", default="", help="備註（寫入紀錄）")
    ap.add_argument("--timeout", type=int, default=240, help="單次 API 逾時秒數")
    args = ap.parse_args()

    cfg = load_env()
    chain = (args.model,) + tuple(m for m in MODEL_CHAIN if m != args.model)

    shas, stat_all, diff = collect(args)
    print(f"📋 待審 {len(shas)} 筆：" + "、".join(s[:8] for s in shas))
    print(f"📏 diff {len(diff):,} 字元｜真值背景已載入")
    rev, model, raw = call_gemini(build_prompt(shas, stat_all, diff), chain, cfg, args.timeout)

    if isinstance(rev, list):
        rev = rev[0] if rev and isinstance(rev[0], dict) else {}
    if not isinstance(rev, dict):
        print("❌ 審查回應非 JSON 物件 → fail-closed（不落紀錄）")
        return 2
    rev["reviewer_model"] = model
    rev["commits"] = shas
    rev["tree"] = git("rev-parse", "HEAD^{tree}").strip()[:12]
    rev["reviewed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    REVIEW_OUT.write_text(json.dumps(rev, ensure_ascii=False, indent=2), encoding="utf-8")
    RAW_OUT.write_text(raw, encoding="utf-8")

    print("─" * 52)
    print("verdict :", rev.get("verdict"))
    print("blocking:", rev.get("blocking"))
    print("required:", rev.get("required_fixes"))
    print("risks   :", rev.get("risks"))
    print("summary :", rev.get("summary"))

    blocking = rev.get("blocking")
    if rev.get("verdict") != "APPROVE" or (isinstance(blocking, list) and blocking):
        print("\n⛔ 未通過 → 不落紀錄（fail-closed）")
        return 1
    if isinstance(blocking, list) is False:
        print("\n⛔ blocking 欄位缺失或格式錯誤 → 不落紀錄（fail-closed）")
        return 1

    if args.dry_run or args.no_approve:
        print(f"\n🔍 dry-run：未落紀錄（結果已存 {REVIEW_OUT.name}）")
        return 0

    print("\n📝 落 CIO_APPROVED 紀錄：")
    return approve(rev, model, shas, args.note or "Gemini 自動審查")


if __name__ == "__main__":
    args_timeout = 240
    raise SystemExit(main())
