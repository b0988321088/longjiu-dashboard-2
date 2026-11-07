#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""natfund_trigger_watch.py — 建倉分批觸發監控（2026-11-08 規則 v1）

盯 snapshot.opportunity_bullet_20261107.建倉計畫_v3_20261108 的每一批：
  index_le   → 加權指數收盤 ≤ 門檻即觸發
  force_by   → 時間保底日到期即觸發（不管指數）
  gates      → after / cash_min / tw_pct_max 三個前置條件全過才可能觸發
無 index_le 也無 force_by（B1 即刻）→ 首次執行即觸發一次。

輸出即推播（cron no_agent）；沒觸發完全靜默。狀態寫 data/natfund_watch_state.json（冪等）。

用法：
  python natfund_trigger_watch.py              # 正常（cron 用）
  python natfund_trigger_watch.py --dry-run    # 只印判斷，不寫狀態
  python natfund_trigger_watch.py --self-test  # 模擬指數驗證門檻與訊息格式
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
CFG = BASE / "data" / "natfund_watch.json"
STATE = BASE / "data" / "natfund_watch_state.json"
PLAN_KEY = "建倉計畫_v3_20261108"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, text/plain, */*"})
    return urllib.request.urlopen(req, timeout=40).read()


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def twii() -> dict:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?interval=1d&range=1mo"
    d = json.loads(_get(url))
    r = d["chart"]["result"][0]
    ts, q = r["timestamp"], r["indicators"]["quote"][0]
    dates, closes = [], []
    for i, c in enumerate(q["close"]):
        if c is None:
            continue
        dates.append(dt.datetime.utcfromtimestamp(ts[i] + 8 * 3600).date().isoformat())
        closes.append(float(c))
    if not closes:
        raise RuntimeError("^TWII 無資料")
    return {"dates": dates, "closes": closes, "last_date": dates[-1], "last_close": closes[-1],
            "prev_close": closes[-2] if len(closes) > 1 else closes[-1],
            "ma5": sum(closes[-5:]) / min(5, len(closes))}


def build_message(batch: dict, idx: dict, reason: str, cfg: dict) -> str:
    chg = (idx["last_close"] - idx["prev_close"]) / idx["prev_close"] * 100
    est = int(batch.get("估計合計") or 0)
    lines = [
        f"🎯 建倉 {batch.get('批次','')}（{batch.get('段','')}）觸發｜{batch.get('ticker','')} {batch.get('名稱','')}",
        f"📉 加權 {idx['last_close']:,.0f}（{chg:+.2f}%）｜{idx['last_date']}",
        f"觸發原因：{reason}",
        f"買：{batch.get('ticker','')} {int(batch.get('股數') or 0):,} 股 @ 約 {float(batch.get('參考價') or 0):.2f}（估 {est:,} 含手續費）",
    ]
    caps = cfg.get("caps_note")
    if caps:
        lines.append(caps)
    g = cfg.get("guards") or {}
    bits = []
    if chg >= float(g.get("skip_gap_up_pct", 2.0)):
        bits.append(f"今日漲 {chg:.1f}%，不追價 → 掛限價或等回測")
    if chg <= -float(g.get("skip_day_drop_pct", 3.0)):
        bits.append(f"今日跌 {abs(chg):.1f}%，流動性差 → 明日再進")
    if bits:
        lines.append("⚠️ " + "；".join(bits))
    lines.append("成交後回我成交價，我立刻入帳並重算五桶／曝險。")
    return "\n".join(lines)


def evaluate(snap: dict, cfg: dict, state: dict, idx: dict, dry: bool):
    ob = snap.get("opportunity_bullet_20261107") or {}
    plan = ob.get(PLAN_KEY) or {}
    fired = state.setdefault("fired", {})
    cash = float(((snap.get("penetration") or {}).get("actual_twd") or {}).get("現金/安全網") or 0)
    ta = float(snap.get("total_assets") or 0)
    tw = float(((snap.get("penetration") or {}).get("actual_twd") or {}).get("台股市值型成長") or 0)
    tw_pct = (tw / ta * 100) if ta else 0.0
    close = idx["last_close"]
    out = []
    for b in plan.get("批次") or []:
        tag = b.get("批次")
        if not tag or tag in fired:
            continue
        sec_cap = float(((snap.get("opportunity_bullet_20261107") or {}).get("建倉規則_v1_20261108") or {}).get("證券市值上限", {}).get("上限") or 0)
        sec_val = float((snap.get("securities") or {}).get("total_market_value") or 0)
        if sec_cap and sec_val + float(b.get("估計合計") or 0) > sec_cap:
            if dry:
                print(f"[dry] {tag} 跳過：證券 {sec_val:,.0f} + 本批 {float(b.get('估計合計') or 0):,.0f} > 上限 {sec_cap:,.0f}")
            continue
        gates = b.get("gates") or {}
        if gates:
            after = str(gates.get("after") or "")
            if after and idx["last_date"] < after:
                continue
            if cash < float(gates.get("cash_min") or 0):
                continue
            if tw_pct > float(gates.get("tw_pct_max") or 99):
                continue
        reason = ""
        if b.get("force_by") and idx["last_date"] >= str(b["force_by"]):
            reason = f"時間保底 {b['force_by']} 到期"
        elif b.get("index_le") and close <= float(b["index_le"]):
            reason = f"加權 {close:,.0f} ≤ {float(b['index_le']):,.0f}"
        elif not b.get("index_le") and not b.get("force_by"):
            reason = "即刻批次（大盤已在回檔 20% 區）"
        if reason:
            out.append((tag, b, reason))
    if dry:
        print(f"[dry] {idx['last_date']} close={close:,.0f} tw_pct={tw_pct:.2f}% cash={cash:,.0f} fired={sorted(fired)}")
    return out


def last_price(sym: str) -> float | None:
    """Yahoo 單檔最後收盤（台股加 .TW）。抓不到回 None（不阻擋買入提醒）。"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
        d = json.loads(_get(url))
        closes = [c for c in d["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
        return float(closes[-1]) if closes else None
    except Exception:
        return None


def exits(snap: dict, state: dict, dry: bool):
    """波段部位出場：目標價／停損價／期限，三者任一成立就推播。"""
    ob = snap.get("opportunity_bullet_20261107") or {}
    plan = ob.get("波段計畫_v1_20261108") or {}
    fired = state.setdefault("exit_fired", {})
    today = dt.date.today().isoformat()
    out = []
    for p in plan.get("部位") or []:
        tag = str(p.get("ticker") or "")
        if not tag or fired.get(tag):
            continue
        q = last_price(f"{tag}.TW")
        if q is None:
            if dry:
                print(f"[dry] {tag} 取價失敗 → 本期不判斷出場")
            continue
        target, stop, due = float(p.get("目標價") or 0), float(p.get("停損價") or 0), str(p.get("期限") or "")
        hit = None
        if target and q >= target:
            hit = f"🎯 到價 {q:.2f} ≥ 目標 {target:.2f}"
        elif stop and q <= stop:
            hit = f"🛑 破停損 {q:.2f} ≤ {stop:.2f}"
        elif due and today > due:
            hit = f"⏰ 期限 {due} 已到（現價 {q:.2f}）"
        if hit:
            shares = int(p.get("股數") or 0)
            gross = q * shares
            fee = max(20, round(gross * 0.001425))
            tax = round(gross * 0.001)
            net = round(gross - fee - tax)
            cost = int(p.get("進場成本") or 0)
            out.append(
                f"🔔 波段出場：{tag} {p.get('名稱','')}\n"
                f"{hit}\n"
                f"賣出 {shares:,} 股 @ {q:.2f} → 估淨額 {net:,}（手續費 {fee:,}＋證交稅 {tax:,}）\n"
                f"估算損益 {net - cost:+,}｜進場成本 {cost:,}\n"
                f"賣出後回我成交價，我入帳並回補現金池（不自動轉買）。"
            )
            if not dry:
                fired[tag] = today
    return out


def trim_watch(snap: dict, state: dict, dry: bool):
    """證券市值達減碼線 → 推播減碼建議（冪等）。"""
    rules = ((snap.get("opportunity_bullet_20261107") or {}).get("建倉規則_v1_20261108") or {}).get("證券市值上限") or {}
    cap, trim, target = float(rules.get("上限") or 0), float(rules.get("減碼線") or 0), float(rules.get("減碼後目標") or 0)
    sec = float((snap.get("securities") or {}).get("total_market_value") or 0)
    if not (cap and trim) or sec < trim:
        return []
    key = f"trim_{dt.date.today().isoformat()}"
    if state.setdefault("trim_fired", {}).get(key):
        return []
    if not dry:
        state["trim_fired"][key] = True
    need = round(sec - target)
    return [f"⚠️ 證券市值 {sec:,.0f} ≥ 減碼線 {trim:,.0f}\n"
            f"減碼至 {target:,.0f}：需賣約 {need:,}\n"
            f"優先序：00713／0056／00918／00984A（無護盤關聯且有獲利）→ 其次部分減 006208／0050\n"
            f"賣出後資金回現金池，不自動轉買；成交後回我價位，我入帳。"]


def main(argv) -> int:
    dry = "--dry-run" in argv
    self_test = "--self-test" in argv
    cfg, state, snap = load_json(CFG, {}), load_json(STATE, {}), load_json(SNAP, {})
    today = dt.date.today().isoformat()
    if today > str(cfg.get("valid_until") or "9999-12-31") and not (dry or self_test):
        return 0
    try:
        idx = twii()
    except Exception as e:
        print(f"⚠️ 建倉監控：指數抓取失敗（{type(e).__name__}）→ 本班跳過")
        return 0

    if self_test:
        for name, c, prev in (("跌破 B5 線", 36000.0, 37000.0), ("深跌 B9 線", 32800.0, 33500.0)):
            sim = dict(idx); sim.update({"last_close": c, "prev_close": prev, "last_date": "2026-12-10"})
            st = {"fired": {t: today for t in ("B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8")}}
            snap_gate = json.loads(json.dumps(snap))
            snap_gate["penetration"]["actual_twd"]["現金/安全網"] = 2400000  # 模擬 12/05 後現金回流
            for tag, b, why in evaluate(snap_gate, cfg, st, sim, True):
                print(build_message(b, sim, why, cfg)); print("-" * 40)
        return 0

    trig = evaluate(snap, cfg, state, idx, dry)
    exit_msgs = exits(snap, state, dry)
    trim_msgs = trim_watch(snap, state, dry)
    if not trig and not exit_msgs and not trim_msgs:
        if not dry:
            state.update({"last_run": dt.datetime.now().isoformat(timespec="seconds"), "last_index": idx["last_close"]})
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        return 0

    msgs = list(exit_msgs) + list(trim_msgs)
    for tag, b, why in trig:
        msgs.append(build_message(b, idx, why, cfg))
        state.setdefault("fired", {})[tag] = today
    state.update({"last_run": dt.datetime.now().isoformat(timespec="seconds"), "last_index": idx["last_close"]})
    if not dry:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print("\n\n".join(msgs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
