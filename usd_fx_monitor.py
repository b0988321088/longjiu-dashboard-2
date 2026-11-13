#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""usd_fx_monitor.py — 台幣匯率急升監控（2026-11-14 使用者核准）

背景：2025-04-02→06-26 台幣升值 13.4%，其中 5/4 單日 -4.38%、5/5 再 -5.03%（兩天 -9.2%）。
      該速度沒有任何反應時間，被動等日報看數字來不及 → 建獨立監控。
目的：advisory 只回報、不自動動作。真正能降匯率風險的只有「不再增加美元／台幣配息導流」，
      換匯與衍生品避險不在授權範圍（成本與工具限制，2026-11-14 裁決）。

規則（對稱）：
  L1 單日升值 ≥2%          → 立即推播（2025 實證兩天 -9.2%）
  L2 5 交易日累計升值 ≥4%  → 立即推播
  L3 升破 31.0（強端）      → 一次性推播（停止美元再投入／配息全走台幣）
  L4 貶破 33.0（弱端）      → 一次性推播（不在弱端加美元）
  latch：同一事件只推一次；狀態解除後重新武裝。
  無事件 → 靜默（cron 不洗版）。

資料源：Yahoo chart API TWD=X（range=3mo, interval=1d）；失敗不前進 state、不誤報。
輸出：stdout（cron no_agent 直接送 TG）＋ snapshot.usd_fx_monitor（日報／儀表板讀）
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATE = BASE / "usd_fx_state.json"
SNAP = BASE / "snapshot.json"

YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/TWD=X?range=3mo&interval=1d"

L1_DAY_PCT = 2.0      # 單日升值門檻（%）
L2_5D_PCT = 4.0       # 5 日累計升值門檻（%）
L3_STRONG = 31.0      # 台幣強端關卡
L4_WEAK = 33.0        # 台幣弱端關卡


def _curl(url: str) -> str:
    try:
        r = subprocess.run(["curl", "-s", "--max-time", "20", "-H", "User-Agent: Mozilla/5.0", url],
                           capture_output=True, text=True, timeout=30)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def fetch_series() -> list[tuple[str, float]]:
    """回傳 [(YYYY-MM-DD, close), ...] 由舊到新；失敗回 []"""
    raw = _curl(YAHOO)
    if not raw:
        return []
    try:
        d = json.loads(raw)["chart"]["result"][0]
        ts = d["timestamp"]
        close = d["indicators"]["quote"][0]["close"]
    except Exception:
        return []
    out = []
    for t, v in zip(ts, close):
        if v is None:
            continue
        out.append((datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"), float(v)))
    return out


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(st: dict) -> None:
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def pct(a: float, b: float) -> float:
    return (a / b - 1.0) * 100.0 if b else 0.0


def evaluate(series: list[tuple[str, float]], st: dict) -> tuple[list[str], dict]:
    """回傳 (messages, new_state)。負值＝台幣升值。

    latch 語意（2026-11-14）：值存「觸發日」字串，不再存 bool。
      同一波只推一次；距觸發日 >5 個交易日或價格回到中性區 → 重新武裝。
      避免兩種病：① 同一天重跑洗版 ② 長期卡死漏掉第二次急升。
    """
    dates = [d for d, _ in series]
    vals = [v for _, v in series]
    last_d, last_v = series[-1]
    prev_v = vals[-2] if len(vals) >= 2 else last_v
    d5 = vals[-6] if len(vals) >= 6 else vals[0]
    r1 = pct(last_v, prev_v)
    r5 = pct(last_v, d5)

    def _fresh(key: str) -> bool:
        """該 latch 是否已失效（可重新觸發）。"""
        d = latches.get(key)
        if not d:
            return True
        if d not in dates:
            return True
        return (len(dates) - 1) - dates.index(d) > 5

    msgs: list[str] = []
    latches = dict(st.get("latches") or {})

    # L1 單日急升
    if r1 <= -L1_DAY_PCT and _fresh("L1"):
        msgs.append(f"🔴 台幣單日急升 {r1:+.2f}%（{last_d}）")
        latches["L1"] = last_d
    elif r1 > -L1_DAY_PCT / 2 and latches.get("L1"):
        latches.pop("L1", None)

    # L2 五日急升
    if r5 <= -L2_5D_PCT and _fresh("L2"):
        msgs.append(f"🟠 台幣 5 日累計升值 {r5:+.2f}%（{last_d}）")
        latches["L2"] = last_d
    elif r5 > -L2_5D_PCT / 2 and latches.get("L2"):
        latches.pop("L2", None)

    # L3 強端關卡（升破 31.0）
    if last_v <= L3_STRONG and _fresh("L3"):
        msgs.append(f"🟡 台幣升破 {L3_STRONG:.1f}（{last_v:.3f}）→ 停止美元再投入、配息全走台幣")
        latches["L3"] = last_d
    elif last_v > L3_STRONG + 0.15 and latches.get("L3"):
        latches.pop("L3", None)

    # L4 弱端關卡（貶破 33.0）
    if last_v >= L4_WEAK and _fresh("L4"):
        msgs.append(f"🟡 台幣貶破 {L4_WEAK:.1f}（{last_v:.3f}）→ 不在弱端加碼美元")
        latches["L4"] = last_d
    elif last_v < L4_WEAK - 0.15 and latches.get("L4"):
        latches.pop("L4", None)

    new_state = {
        "last_date": last_d,
        "last_value": round(last_v, 3),
        "r1_pct": round(r1, 2),
        "r5_pct": round(r5, 2),
        "latches": latches,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return msgs, new_state


def usd_exposure_twd(snap: dict) -> float:
    cur = (snap.get("usd_exposure_monitor") or {}).get("current") or {}
    amt = (cur.get("金額明細") or {})
    try:
        total = float(amt.get("分母_總資產") or 0)
        pctv = float(cur.get("匯率曝險合計") or 0)
        return total * pctv / 100.0
    except (TypeError, ValueError):
        return 0.0


def update_snapshot(new_state: dict, series: list[tuple[str, float]]) -> None:
    """就地更新 snapshot.usd_fx_monitor（保留既有 latch 說明以外的欄位不動）。"""
    try:
        snap = json.loads(SNAP.read_text(encoding="utf-8"))
    except Exception:
        return
    hi = max(v for _, v in series[-60:]) if series else None
    lo = min(v for _, v in series[-60:]) if series else None
    exp = usd_exposure_twd(snap)
    snap["usd_fx_monitor"] = {
        "updated_at": new_state["updated_at"],
        "last_date": new_state["last_date"],
        "usd_twd": new_state["last_value"],
        "r1_pct": new_state["r1_pct"],
        "r5_pct": new_state["r5_pct"],
        "high_60d": round(hi, 3) if hi else None,
        "low_60d": round(lo, 3) if lo else None,
        "usd_exposure_twd": round(exp),
        "每升值1%_帳面影響_twd": round(exp * 0.01),
        "門檻": {"單日升值_pct": L1_DAY_PCT, "五日升值_pct": L2_5D_PCT,
                 "強端_usd_twd": L3_STRONG, "弱端_usd_twd": L4_WEAK},
        "性質": "advisory 只回報；真正能降風險者＝不再增加美元／台幣配息導流（2026-11-14 裁決）",
        "source": "usd_fx_monitor.py（Yahoo TWD=X）",
    }
    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    force = "--force" in argv
    series = fetch_series()
    if not series:
        print("⚠️ usd_fx_monitor：Yahoo 匯率抓取失敗，未更新 state、不推播")
        return 1

    st = load_state()
    msgs, new_state = evaluate(series, st)

    # 同一天重跑不重複推播（除非 --force）
    if not force and st.get("last_date") == new_state["last_date"] and st.get("pushed"):
        msg_guard = st.get("pushed") or {}
        msgs = [m for m in msgs if m not in msg_guard]

    if msgs:
        exp = None
        try:
            snap = json.loads(SNAP.read_text(encoding="utf-8"))
            exp = usd_exposure_twd(snap)
        except Exception:
            pass
        head = f"USD/TWD {new_state['last_value']:.3f}（單日 {new_state['r1_pct']:+.2f}%／5日 {new_state['r5_pct']:+.2f}%）｜{new_state['last_date']}"
        tail = (f"\n美元曝險約 {exp:,.0f} 元，台幣每升值 1% → 帳面 -{exp*0.01:,.0f} 元" if exp else "")
        print("\n".join(msgs) + "\n" + head + tail + "\n（僅回報，不自動動作；換匯與衍生品避險未授權）")
        new_state["pushed"] = msgs
    else:
        new_state["pushed"] = []
        # 靜默：cron no_agent 無輸出即不推播

    save_state(new_state)
    update_snapshot(new_state, series)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
