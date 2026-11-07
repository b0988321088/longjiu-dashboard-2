#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""natfund_trigger_watch.py — 機會子彈 T2–T6 觸發監控（2026-11-07 使用者核准）

用途：盯 snapshot.opportunity_bullet_20261107.分批計畫_v2_20261107 的觸發條件，
      達標就輸出訊息（cron no_agent 模式 → stdout 直接送到 Telegram）。
      沒觸發 → 完全不輸出（靜默，不製造噪音）。

資料源：
  加權指數      Yahoo chart ^TWII（1d/1mo）
  三大法人金額  TWSE BFI82U（rwd/zh，需 Referer）
  標的與張數    snapshot.json（不寫死）
  門檻          data/natfund_watch.json（改門檻不改程式）

狀態：data/natfund_watch_state.json（已觸發批次、法人歷史）→ 冪等，不重複推播。

用法：
  python natfund_trigger_watch.py            # 正常檢查（cron 用）
  python natfund_trigger_watch.py --dry-run  # 只印判斷過程，不寫狀態
  python natfund_trigger_watch.py --self-test  # 用模擬指數驗證觸發與訊息格式
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
CFG = BASE / "data" / "natfund_watch.json"
STATE = BASE / "data" / "natfund_watch_state.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def _get(url: str, referer: str | None = None) -> bytes:
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    if referer:
        h["Referer"] = referer
    req = urllib.request.Request(url, headers=h)
    return urllib.request.urlopen(req, timeout=40).read()


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def twii() -> dict:
    """回傳 {dates[], closes[], lows[], last_close, ma5, prev_close}"""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?interval=1d&range=1mo"
    d = json.loads(_get(url))
    r = d["chart"]["result"][0]
    ts = r["timestamp"]
    q = r["indicators"]["quote"][0]
    dates, closes, lows, highs = [], [], [], []
    for i, c in enumerate(q["close"]):
        if c is None:
            continue
        dates.append(dt.datetime.utcfromtimestamp(ts[i] + 8 * 3600).date().isoformat())
        closes.append(float(c))
        lows.append(float(q["low"][i] or c))
        highs.append(float(q["high"][i] or c))
    if not closes:
        raise RuntimeError("^TWII 無資料")
    ma = sum(closes[-5:]) / min(5, len(closes))
    return {
        "dates": dates, "closes": closes, "lows": lows, "highs": highs,
        "last_date": dates[-1], "last_close": closes[-1], "ma5": ma,
        "prev_close": closes[-2] if len(closes) > 1 else closes[-1],
    }


def inst_net_money(date_str: str) -> float | None:
    """三大法人買賣超金額（元）；休市／無資料回 None。date_str = YYYYMMDD"""
    url = f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?dayDate={date_str}&response=json&dayDate={date_str}"
    try:
        j = json.loads(_get(url, referer="https://www.twse.com.tw/zh/trading/foreign/bfi82u.html"))
    except Exception:
        return None
    if str(j.get("stat")) != "OK":
        return None
    total = 0.0
    seen = False
    for row in j.get("data") or []:
        if len(row) < 4:
            continue
        name = str(row[0])
        if "合計" in name:
            continue
        try:
            v = float(str(row[3]).replace(",", ""))
        except Exception:
            continue
        total += v
        seen = True
    return total if seen else None


def fmt_wan(v: float) -> str:
    return f"{v / 1e4:,.0f} 萬"


def build_message(tag: str, batch: dict, snap_idx: dict, reason: str, cfg: dict) -> str:
    chg = (snap_idx["last_close"] - snap_idx["prev_close"]) / snap_idx["prev_close"] * 100
    price = float(batch.get("參考價") or 0)
    shares = int(batch.get("股數") or 0)
    est = int(batch.get("估計合計") or 0)
    lines = [
        f"🎯 機會子彈 {tag} 觸發（{batch.get('ticker', '')} {batch.get('名稱', '')}）",
        f"📉 加權 {snap_idx['last_close']:,.0f}（{chg:+.2f}%）｜{snap_idx['last_date']}",
        f"觸發原因：{reason}",
        f"買：{batch.get('ticker', '')} {shares:,} 股 @ 約 {price:.2f}（估 {est:,} 含手續費）",
        f"理由：{batch.get('理由', '')}",
    ]
    g = cfg.get("guards") or {}
    guard_bits = []
    if chg >= float(g.get("skip_gap_up_pct", 2.0)):
        guard_bits.append(f"今日漲 {chg:.1f}%，追高不宜 → 掛限價或等回測")
    if chg <= -float(g.get("skip_day_drop_pct", 3.0)):
        guard_bits.append(f"今日跌 {abs(chg):.1f}%，流動性差 → 明日再進")
    if guard_bits:
        lines.append("⚠️ " + "；".join(guard_bits))
    lines.append("成交後回我成交價，我立刻入帳並重算五桶／曝險。")
    return "\n".join(lines)


def evaluate(snap: dict, cfg: dict, state: dict, idx: dict, net_today, dry: bool):
    """回傳 [(tag, batch, reason)]"""
    ob = snap.get("opportunity_bullet_20261107") or {}
    plan = ob.get("分批計畫_v2_20261107") or {}
    batches = {b.get("批次"): b for b in plan.get("批次") or []}
    fired = state.setdefault("fired", {})
    hist = state.setdefault("inst_history", [])

    # 法人歷史（同日去重）
    if net_today is not None:
        hist[:] = [h for h in hist if h.get("date") != idx["last_date"]]
        hist.append({"date": idx["last_date"], "net": float(net_today)})
        hist.sort(key=lambda h: h["date"])
        del hist[:-8]
    buy_streak = 0
    for h in reversed(hist):
        if float(h.get("net") or 0) > 0:
            buy_streak += 1
        else:
            break

    close = idx["last_close"]
    out = []

    def fire(tag, reason):
        if tag in fired or tag not in batches:
            return
        out.append((tag, batches[tag], reason))

    t2 = cfg.get("t2") or {}
    if close <= float(t2.get("index_le") or 0):
        fire("T2", f"加權 {close:,.0f} ≤ {float(t2.get('index_le')):,.0f}")
    elif buy_streak >= int(t2.get("inst_buy_days") or 3):
        fire("T2", f"三大法人連 {buy_streak} 日買超（{fmt_wan(sum(h['net'] for h in hist[-buy_streak:]))}）")

    if "T2" in fired:
        fire("T3", "T2 已觸發，隔日買第二檔")

    t4 = cfg.get("t4") or {}
    retest = float(t4.get("retest_low") or 0)
    # 回測條件必須「晚於」參考低點當日，否則 11/06 自己創低會誤觸
    ref_date = str((cfg.get("index_ref") or {}).get("date") or "")
    retest_valid = bool(retest) and idx["last_date"] > ref_date and bool(idx["lows"])
    if close <= float(t4.get("index_le") or 0):
        fire("T4", f"加權 {close:,.0f} ≤ {float(t4.get('index_le')):,.0f}")
    elif retest_valid and retest * 0.995 <= idx["lows"][-1] <= retest * 1.002 and close > retest * 1.005:
        fire("T4", f"回測 {retest:,.0f} 未破（今低 {idx['lows'][-1]:,.0f}、收 {close:,.0f}）")

    if "T4" in fired:
        fire("T5", "T4 已觸發，隔日買第二檔")

    t6 = cfg.get("t6") or {}
    if idx["last_date"] >= str(t6.get("after") or "9999-12-31") and close > idx["ma5"]:
        fire("T6", f"現金回流日後且收盤站上 {int(t6.get('ma_days') or 5)} 日線（{idx['ma5']:,.0f}）")

    if dry:
        print(f"[dry] close={close:,.0f} ma5={idx['ma5']:,.0f} buy_streak={buy_streak} fired={sorted(fired)}")
    return out


def main(argv):
    dry = "--dry-run" in argv
    self_test = "--self-test" in argv
    cfg = load_json(CFG, {})
    state = load_json(STATE, {})
    snap = load_json(SNAP, {})
    today = dt.date.today().isoformat()

    valid_until = str(cfg.get("valid_until") or "9999-12-31")
    if today > valid_until and not (dry or self_test):
        return 0  # 計畫到期 → 靜默

    try:
        idx = twii()
    except Exception as e:
        print(f"⚠️ 機會子彈監控：指數抓取失敗（{type(e).__name__}）→ 本班跳過")
        return 0

    net_today = None
    if idx["last_date"].replace("-", "") == today.replace("-", ""):
        net_today = inst_net_money(today.replace("-", ""))
    else:
        # 今天還沒收盤資料 → 取最近交易日的法人金額補歷史（僅一次）
        net_today = inst_net_money(idx["last_date"].replace("-", ""))

    if self_test:
        tests = [("跌破 T2", 37700.0, 37500.0, 100.0, 39500.0),
                 ("深跌 T4", 36400.0, 36000.0, 100.0, 37000.0)]
        for name, close, low, ma, prev in tests:
            sim = dict(idx); sim.update({"last_close": close, "lows": [low], "ma5": ma,
                                         "prev_close": prev, "last_date": "2026-11-10"})
            st = {"fired": {}, "inst_history": []}
            res = evaluate(snap, cfg, st, sim, None, True)
            print(f"== 模擬：{name} → 觸發 {[r[0] for r in res]}")
            for tag, b, why in res:
                print(build_message(tag, b, sim, why, cfg))
                print("-" * 40)
        return 0

    triggers = evaluate(snap, cfg, state, idx, net_today, dry)
    if not triggers:
        if not dry:
            state["last_run"] = dt.datetime.now().isoformat(timespec="seconds")
            state["last_index"] = idx["last_close"]
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        return 0

    msgs = []
    for tag, batch, why in triggers:
        msgs.append(build_message(tag, batch, idx, why, cfg))
        state.setdefault("fired", {})[tag] = today
    state["last_run"] = dt.datetime.now().isoformat(timespec="seconds")
    state["last_index"] = idx["last_close"]
    if not dry:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print("\n\n".join(msgs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
