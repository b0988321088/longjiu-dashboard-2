#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_bucket_attribution.py — 桶位異動歸因（2026-10-18 使用者核准施工）

為什麼要有：
    2026-10-16 台股桶單日 +966,757（7.8%→12.5%），同期證券市值 −229,820（方向相反）。
    週報只能把它寫成「疑似資料異常」。實際原因是保單 B 換基金（健康＋PIMCO → 元大台灣卓越50）
    使保單穿透 +1,009,467 —— 但因為桶值沒有組成明細，**沒人能對帳**，只好當異常。

本工具做三件事（皆唯讀，不改任何財務真值）：
    ① 逐桶比對「今日 vs 上一個已入庫的 snapshot」，列出 Δ。
    ② 單桶 |Δ| ≥ 300,000 且總資產 |Δ| < 1% → 標記「待解釋」（**不是**判定為重分類）。
    ③ 對有 components_twd 的桶，逐項列出 證券／平台基金／保單穿透 的增減與主導來源。

判準（依使用者 2026-10-18 裁決）：
    · 門檻觸發＝待解釋，必須列出「來源、前後數值、重分類金額、總資產變化」，不得自動判定重分類。
    · 缺組成資料 → 無法對帳（rc=1，fail-closed），不得因為缺資料而放行成「已解釋」。

用法：
    python tools/check_bucket_attribution.py            # 印出，不寫檔
    python tools/check_bucket_attribution.py --write    # 另寫 data/bucket_attribution.json（供週報引用）
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SNAP = BASE / "snapshot.json"
OUT = BASE / "data" / "bucket_attribution.json"

THRESH_TWD = 300_000          # 單桶異動門檻（元）
THRESH_TOTAL_PCT = 1.0        # 總資產異動門檻（%）— 低於此才視為「桶間移動」而非全面增減
BUCKETS = ("台股市值型成長", "美股市值型成長", "防守型配息", "債券", "現金/安全網")


def _pen(snap: dict) -> dict:
    return (snap or {}).get("penetration") or {}


def _twd(snap: dict) -> dict:
    return {k: float(v) for k, v in ((_pen(snap).get("actual_twd") or {}).items()) if isinstance(v, (int, float))}


def _comp(snap: dict) -> dict:
    return (_pen(snap).get("components_twd") or {})


def analyze(cur: dict, prev: dict, thresh_twd: float = THRESH_TWD,
            thresh_total_pct: float = THRESH_TOTAL_PCT) -> dict:
    """純函式：回傳 {'items': [...], 'unaccounted': [...], 'total_delta': …, ...}。

    items       = 觸發門檻的桶（待解釋），含組成明細與主導來源
    unaccounted = 觸發門檻但缺組成資料 → 無法對帳（fail-closed）
    """
    ct, pt = _twd(cur), _twd(prev)
    cur_total = float((cur or {}).get("total_assets") or 0)
    prev_total = float((prev or {}).get("total_assets") or 0)
    total_delta = cur_total - prev_total
    total_pct = (abs(total_delta) / prev_total * 100) if prev_total else 0.0

    items, unaccounted = [], []
    for b in BUCKETS:
        if b not in ct or b not in pt:
            continue
        d = ct[b] - pt[b]
        if abs(d) < thresh_twd:
            continue
        # 總資產同幅變動＝真的加減倉（或全面漲跌），不是桶間移動 → 不列待解釋。
        if total_pct >= thresh_total_pct:
            continue
        rec = {
            "bucket": b,
            "prev": round(pt[b]),
            "cur": round(ct[b]),
            "delta": round(d),
            "total_delta": round(total_delta),
            "total_delta_pct": round(total_pct, 2),
            "why_threshold": (f"單桶異動 {abs(d):,.0f} ≥ {thresh_twd:,.0f}"
                              f"；總資產異動 {total_pct:.2f}% < {thresh_total_pct}%"),
            "status": "待解釋",   # 刻意不是「重分類」：需人／下游解釋後才可如此敘述
        }
        cc, pc = _comp(cur).get(b), _comp(prev).get(b)
        if isinstance(cc, dict) and isinstance(pc, dict):
            parts = {}
            for k in set(cc) | set(pc):
                parts[k] = round(float(cc.get(k, 0)) - float(pc.get(k, 0)))
            rec["components"] = {k: {"prev": round(float(pc.get(k, 0))), "cur": round(float(cc.get(k, 0))),
                                     "delta": parts[k]} for k in parts}
            top = max(parts.items(), key=lambda kv: abs(kv[1])) if parts else None
            if top:
                rec["top_driver"] = {"name": top[0], "delta": top[1]}
                comp_sum = sum(parts.values())
                rec["reclassified"] = round(comp_sum)          # 組成合計變動（正＝流入該桶）
            # ④ 組成與桶值必須閉合：sum(components) 的變動要等於該桶 Δ（容許 ±1 元進位差）。
            #    不閉合＝組成資料本身有問題（漏列、重複、口徑不一致）→ 不得當成「已解釋」。
            _gap = round(sum(float(cc.get(k, 0)) for k in cc) - sum(float(pc.get(k, 0)) for k in pc) - d)
            if abs(_gap) > 1:
                rec["status"] = f"組成與桶值不符（差額 {_gap:+,}）"
                rec["missing"] = "components_twd 加總變動 ≠ 桶值變動 → 不得視為已解釋"
                rec["gap"] = _gap
                unaccounted.append(rec)
            else:
                items.append(rec)
        else:
            rec["status"] = "無法對帳"
            rec["missing"] = "缺少 components_twd（該日尚未持久化桶位組成）→ 不得視為已解釋"
            unaccounted.append(rec)
    return {
        "date": (cur or {}).get("date"),
        "prev_date": (prev or {}).get("date"),
        "total_assets": round(cur_total),
        "total_delta": round(total_delta),
        "total_delta_pct": round(total_pct, 2),
        "threshold_twd": thresh_twd,
        "threshold_total_pct": thresh_total_pct,
        "items": items,
        "unaccounted": unaccounted,
    }


def prev_snapshot_from_git() -> dict | None:
    """抓最近一個「資料日 ≠ 今日」的已入庫 snapshot（git 內版本，唯讀）。"""
    try:
        out = subprocess.run(["git", "log", "--format=%h", "-25", "--", "snapshot.json"],
                             cwd=str(BASE), capture_output=True, text=True, encoding="utf-8").stdout
        cur_date = json.loads(SNAP.read_text(encoding="utf-8")).get("date")
        for sha in [x.strip() for x in out.splitlines() if x.strip()]:
            raw = subprocess.run(["git", "show", f"{sha}:snapshot.json"], cwd=str(BASE),
                                 capture_output=True).stdout
            if not raw:
                continue
            try:
                d = json.loads(raw)
            except Exception:
                continue
            if d.get("date") and d.get("date") != cur_date:
                return d
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ 取不到上一個 snapshot：{exc}")
    return None


def main() -> int:
    write = "--write" in sys.argv
    cur = json.loads(SNAP.read_text(encoding="utf-8"))
    prev = prev_snapshot_from_git()
    if prev is None:
        print("ℹ️ 找不到可比的上一日 snapshot → 本日不做歸因")
        return 0
    res = analyze(cur, prev)
    print(f"🧭 桶位異動歸因 {res['date']} vs {res['prev_date']}｜"
          f"總資產 {res['total_delta']:+,}（{res['total_delta_pct']:+.2f}%）")
    if not res["items"] and not res["unaccounted"]:
        print(f"  ✅ 無桶位異動超過門檻（±{res['threshold_twd']:,.0f} 且總資產變動 <{res['threshold_total_pct']}%）")
    for it in res["items"]:
        print(f"  ⚠️ {it['bucket']}：{it['prev']:,} → {it['cur']:,}（Δ{it['delta']:+,}）— {it['status']}")
        print(f"     觸發條件：{it['why_threshold']}")
        for name, v in (it.get("components") or {}).items():
            print(f"     · {name}: {v['prev']:,} → {v['cur']:,}（Δ{v['delta']:+,}）")
        if it.get("top_driver"):
            print(f"     主導來源：{it['top_driver']['name']}（Δ{it['top_driver']['delta']:+,}）"
                  f"｜組成合計變動 {it.get('reclassified', 0):+,}")
    for it in res["unaccounted"]:
        print(f"  ⛔ {it['bucket']}：{it['prev']:,} → {it['cur']:,}（Δ{it['delta']:+,}）— 無法對帳")
        print(f"     {it['missing']}")
    if write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  ↳ 已寫出 {OUT}")
    return 1 if res["unaccounted"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
