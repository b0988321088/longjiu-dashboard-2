#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""policy_switch_watch.py — 保單轉換「跌幅收斂」量化觸發（2026-11-02 使用者核准）

為什麼要有這支：
    使用者 2026-11-02 定版規則＝保單轉換不按月固定，淨值大幅回落期暫停。
    但「回穩」不能靠感覺 → 本支把它量化成可監控條件，達到就提醒「可以重新評估轉換」。
    注意：本支只提示「時機到了、可評估」，**不代為決定轉哪一檔**（轉換標的屬使用者裁示）。

監控序列（口徑＝App 帳戶價值，TWD，含匯率）：
    ① 安聯 A ② 安聯 B ③ 第一金（9/16 起 100% ID05 M&G入息A）
    為何用帳戶價值而非單檔淨值：使用者看的是 App 帳戶價值；單檔在 9/16 轉換後成分已變，
    跨轉換日比較會失真（實測 9/03 保單B 的 M&G 只有 163,815，現在 626,019）。

觸發條件（任一成立即提醒）：
    A. 自近 N 日低點回升 ≥ X%（X 預設 3，N 預設 60，皆讀 snapshot.policy_switch.trigger）
    B. 20 日均線由下轉上（今日 ma20 > 5 日前 ma20）且現值 ≥ ma20
輸出：無觸發 → 空 stdout（no_agent cron 不推播）；有觸發 → 一段提醒文字。
防噪音：同一天只推一次；序列不足（<10 筆）時明確說「樣本不足，僅記錄」而不是假觸發。

用法：
    python policy_switch_watch.py            # 記錄今天＋評估（cron 用）
    python policy_switch_watch.py --seed     # 由 龍九備份/*_snapshot.json 回填歷史序列
    python policy_switch_watch.py --always   # 人工查看（忽略觸發/靜默，必定輸出）
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
SERIES = BASE / "data" / "policy_switch_watch.json"
STATE = BASE / "policy_switch_watch_state.json"
BACKUP_DIR = Path("C:/Users/bot/龍九備份")

DEFAULT_TRIGGER = {"回升_pct": 3.0, "低點_window": 60, "均線_window": 20}

SERIES_DEF = (
    ("安聯A", ("allianz_policy_a_value", "allianz_a_current_value", "policy_a_total")),
    ("安聯B", ("allianz_policy_b_value", "allianz_b_current_value", "policy_b_total")),
    ("第一金", ("firstjin_current_value", "firstjin")),
)


def _load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def _pick(snap: dict, keys) -> float | None:
    for k in keys:
        v = snap.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v:
            return float(v)
    return None


def _row_from_snap(snap: dict, day: str) -> dict:
    row = {"date": day}
    for label, keys in SERIES_DEF:
        v = _pick(snap, keys)
        if v is not None:
            row[label] = round(v)
    return row


def seed_from_backups() -> int:
    """由每日備份 snapshot 回填序列（只補歷史，不覆蓋同日既有值）。"""
    doc = _load(SERIES, {"series": []})
    have = {r["date"] for r in doc.get("series", [])}
    added = 0
    for f in sorted(BACKUP_DIR.glob("*_snapshot.json")):
        day = f.name.split("_")[0]
        if day in have:
            continue
        snap = _load(f, None)
        if not isinstance(snap, dict):
            continue
        row = _row_from_snap(snap, day)
        if len(row) > 1:
            doc.setdefault("series", []).append(row)
            added += 1
    doc["series"] = sorted(doc["series"], key=lambda r: r["date"])
    _save(SERIES, doc)
    return added


def upsert_today(snap: dict, day: str) -> None:
    doc = _load(SERIES, {"series": []})
    series = [r for r in doc.get("series", []) if r.get("date") != day]
    series.append(_row_from_snap(snap, day))
    doc["series"] = sorted(series, key=lambda r: r["date"])
    _save(SERIES, doc)


def evaluate(doc: dict, trig: dict) -> list[dict]:
    """回傳觸發清單；每筆含 序列名／現值／低點／回升%/均線狀態。"""
    hits = []
    win_low = int(trig.get("低點_window", 60))
    win_ma = int(trig.get("均線_window", 20))
    need_pct = float(trig.get("回升_pct", 3.0))
    for label, _ in SERIES_DEF:
        pts = [(r["date"], float(r[label])) for r in doc.get("series", []) if r.get(label)]
        if len(pts) < 10:
            hits.append({"序列": label, "狀態": "樣本不足", "筆數": len(pts)})
            continue
        cur = pts[-1][1]
        window = pts[-win_low:]
        low = min(v for _, v in window)
        rebound = (cur / low - 1) * 100 if low else 0.0
        ma_now = sum(v for _, v in pts[-win_ma:]) / len(pts[-win_ma:]) if len(pts) >= win_ma else None
        ma_prev = (sum(v for _, v in pts[-win_ma - 5:-5]) / len(pts[-win_ma - 5:-5])
                   if len(pts) >= win_ma + 5 else None)
        ma_up = bool(ma_now and ma_prev and ma_now > ma_prev and cur >= ma_now)
        hit = rebound >= need_pct or ma_up
        hits.append({
            "序列": label, "狀態": "觸發" if hit else "未觸發",
            "現值": round(cur), "區間低點": round(low),
            "回升_pct": round(rebound, 2),
            "ma20": round(ma_now) if ma_now else None,
            "ma20_5日前": round(ma_prev) if ma_prev else None,
            "ma20_轉正": ma_up,
            "筆數": len(pts),
            "低點日": min(window, key=lambda t: t[1])[0],
        })
    return hits


def render(hits: list[dict], trig: dict) -> str:
    fired = [h for h in hits if h.get("狀態") == "觸發"]
    if not fired:
        lines = ["🟢 保單轉換時機：未觸發（跌幅尚未收斂）"]
    else:
        lines = ["🟡 保單轉換時機到了 — 可重新評估（僅提醒，不代為決定轉哪一檔）"]
    lines.append(f"門檻：自 {int(trig.get('低點_window',60))} 日低點回升 ≥{trig.get('回升_pct',3.0)}%"
                 f" 或 {int(trig.get('均線_window',20))} 日均線轉正｜口徑＝App 帳戶價值（TWD，含匯率）")
    for h in hits:
        if h.get("狀態") == "樣本不足":
            lines.append(f"· {h['序列']}：樣本不足（{h['筆數']} 筆）→ 僅記錄，不判定")
            continue
        flag = "✅" if h["狀態"] == "觸發" else "・"
        lines.append(
            f"{flag} {h['序列']} {h['現值']:,}（自低點 {h['低點日']} {h['區間低點']:,} 回升 {h['回升_pct']:+.2f}%）"
            f"｜ma20 {h['ma20']:,}（5 日前 {h['ma20_5日前']:,}，{'轉正' if h['ma20_轉正'] else '未轉正'}）")
    if fired:
        lines.append("下一步：先確認最新淨值與匯率，再決定是否轉換（轉換標的與金額由你裁示）")
    return "\n".join(lines)


def main() -> int:
    always = "--always" in sys.argv
    if "--seed" in sys.argv:
        n = seed_from_backups()
        print(f"✅ 回填 {n} 筆歷史序列 → {SERIES}")
        return 0
    snap = _load(SNAP, None)
    if not isinstance(snap, dict):
        print("⚠️ policy_switch_watch：讀不到 snapshot.json", file=sys.stderr)
        return 1
    today = date.today().isoformat()
    upsert_today(snap, today)
    doc = _load(SERIES, {"series": []})
    trig = dict(DEFAULT_TRIGGER)
    trig.update((snap.get("policy_switch", {}) or {}).get("trigger") or {})
    hits = evaluate(doc, trig)
    fired = [h for h in hits if h.get("狀態") == "觸發"]
    st = _load(STATE, {})
    if not always:
        if not fired:
            st.update({"last_date": today, "last_fired": False})
            _save(STATE, st)
            return 0                                  # 未觸發 → 不推播
        if st.get("last_alert_date") == today:
            return 0                                  # 同日只推一次
    print(render(hits, trig))
    if not always:
        st.update({"last_date": today, "last_fired": bool(fired), "last_alert_date": today})
        _save(STATE, st)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
