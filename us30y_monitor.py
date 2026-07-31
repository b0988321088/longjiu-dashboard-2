#!/usr/bin/env python3
"""us30y_monitor.py — 30年美債殖利率模式監控（龍九再平衡規則）

規則：
- 模式A 防禦：連續2交易日 US30Y ≥ 5.20%
- 模式B 布局：連續2交易日 US30Y ≤ 4.90%
- 檢視頻率：每日（由 cron 觸發）；模式切換時輸出通知，無變化靜默

輸出：模式切換 → 印出通知文字（cron no_agent 送 TG）；無變化 → 空輸出
"""
import json, subprocess, sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATE = BASE / "us30y_state.json"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS30"

A_THRESHOLD = 5.20   # 模式A 防禦
B_THRESHOLD = 4.90   # 模式B 布局
RED_LINE = 5.30      # 風控紅線：長期債券新增買單永久凍結
CONSECUTIVE_DAYS = 2  # 連續交易日

def fetch_us30y() -> list[tuple[str, float]]:
    """抓取 DGS30，回傳 [(日期, 殖利率), ...] 由新到舊"""
    r = subprocess.run(["curl", "-s", "--max-time", "20", FRED_URL],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"FRED 抓取失敗: {r.stderr[:100]}")
    rows = []
    for line in r.stdout.strip().splitlines()[1:]:  # 跳過標頭
        parts = line.split(",")
        if len(parts) == 2 and parts[1] not in (".", ""):
            try:
                rows.append((parts[0], float(parts[1])))
            except ValueError:
                continue
    return list(reversed(rows))  # 新→舊

def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"mode": None, "streak": 0, "last_rate": None, "last_date": None}

def main():
    rows = fetch_us30y()
    if not rows:
        print("⚠️ US30Y 無資料，略過")
        return
    latest_date, latest_rate = rows[0]
    # 連續2交易日：取最近2筆不同日期的值
    last2 = rows[:2]
    state = load_state()
    today = date.today().isoformat()

    # 判斷最近2筆是否符合門檻
    def all_above(vals, thr):
        return len(vals) >= CONSECUTIVE_DAYS and all(v >= thr for _, v in vals)

    def all_below(vals, thr):
        return len(vals) >= CONSECUTIVE_DAYS and all(v <= thr for _, v in vals)

    if all_above(last2, A_THRESHOLD):
        new_mode = "A"
        mode_label = "模式A｜防禦模式"
    elif all_below(last2, B_THRESHOLD):
        new_mode = "B"
        mode_label = "模式B｜布局模式"
    else:
        new_mode = None
        mode_label = None

    old_mode = state.get("mode")
    streak = state.get("streak", 0)

    if new_mode is None:
        # 未達任何模式門檻
        if old_mode is None:
            return  # 初次執行且未觸發 → 靜默，不寫 state
        # 既有模式落入中間區間 → 維持現有模式，連續計數歸零
        state.update({"mode": old_mode, "streak": 0, "last_rate": latest_rate,
                      "last_date": latest_date, "checked_at": today})
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    # 模式維持（連續達標）
    if new_mode == old_mode:
        streak += 1
        state.update({"mode": new_mode, "streak": streak, "last_rate": latest_rate,
                      "last_date": latest_date, "checked_at": today})
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return  # 無變化 → 靜默

    # 模式切換 / 初次建立
    action = "觸發" if old_mode is not None else "啟用"
    state.update({"mode": new_mode, "streak": 1, "last_rate": latest_rate,
                  "last_date": latest_date, "checked_at": today})
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    msgs = [f"🚨 龍九再平衡模式切換：{mode_label} {action}"]
    msgs.append(f"📈 US30Y 連續{CONSECUTIVE_DAYS}日達標（最近: {last2[1][0]} {last2[1][1]}% → {latest_date} {latest_rate}%）")
    if new_mode == "A":
        msgs.append("🎯 執行策略：配息導流優先 → 逢反彈分批減碼美股科技 → 資金轉台股高股息")
        msgs.append("⛔ 禁令：不加碼美股長久期科技、不新增債券（00983D/PIMCO 維持底倉）")
    else:
        msgs.append("🎯 執行策略：放寬減碼限制，可分批回補優質美股科技、開放債券布局")
    # 風控紅線檢查：連續2日 ≥5.30% → 債券新增永久凍結
    if new_mode == "A" and all(v >= RED_LINE for _, v in last2):
        msgs.append(f"🚫 風控紅線觸發：US30Y 連續{CONSECUTIVE_DAYS}日 ≥{RED_LINE}% — 長期債券相關新增買單【永久凍結】（不受階段影響）")
    print("\n".join(msgs))
    return

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠️ US30Y 監控失敗: {e}")
