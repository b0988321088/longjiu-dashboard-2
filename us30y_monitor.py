#!/usr/bin/env python3
"""us30y_monitor.py — 30年美債殖利率模式監控（龍九再平衡規則）

規則：
- 模式A 防禦：連續2交易日 US30Y ≥ 5.20%
- 模式B 布局：連續2交易日 US30Y ≤ 4.90%
- 宏觀風險警示（v1.2，2026-10-14 使用者裁決 TD-20261015-02）：連續2交易日 US30Y ≥ 5.30%
  → 長期債券相關新增買單凍結（本規則獨立保留；原為「永久凍結」）＋科技部位上限維持或收緊；
  **不再單獨否決台股分批**（台股分批改由現金／質押 LTV／還本安全閥共同判定，見 sot_targets.unfreeze_conditions）。
  單一切換點＝thresholds_2026_0915.US30Y閘門模式（advisory｜hard_veto＝回復 v1.1）。
- 檢視頻率：每日（由 cron 觸發）；狀態有變化才輸出，無變化靜默

資料源（2026-09-11 修）：
- FRED DGS30 為官方收盤，但有 1-2 交易日落差 → 改為 FRED + Yahoo ^TYX 合併，
  取「最近已收盤」的兩個交易日判門檻。
- 事故紀錄（2026-09-11）：9/10、9/11 皆 ≥5.30，但 08:45 cron 只看到 FRED 9/9 的
  5.28 → 靜默漏報。兩個原因：① 只讀 FRED（落後）② 紅線檢查寫在模式切換分支，
  模式維持時直接 return，永遠不會觸發。
"""
import json, subprocess, sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATE = BASE / "us30y_state.json"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS30"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETYX?range=1mo&interval=1d"
ET = timezone(timedelta(hours=-4))  # 美東（夏令時間）

A_THRESHOLD = 5.20   # 模式A 防禦
B_THRESHOLD = 4.90   # 模式B 布局
RED_LINE = 5.30      # 宏觀風險警示（v1.2）：長期債券新增買單凍結（原「永久凍結」措辭；不否決台股分批）
CONSECUTIVE_DAYS = 2  # 連續交易日

MODE_LABELS = {
    "A": "模式A｜防禦（警戒區 5.20-5.30）",
    "B": "模式B｜布局（≤4.90 放寬）",
}


def _curl(url, headers=None):
    cmd = ["curl", "-s", "--max-time", "20"]
    for h in (headers or []):
        cmd += ["-H", h]
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception:
        return ""
    return r.stdout if r.returncode == 0 else ""


def fetch_us30y_fred() -> list:
    """FRED DGS30 官方收盤，回傳 [(日期, 殖利率), ...] 由新到舊"""
    out = _curl(FRED_URL)
    if not out:
        return []
    rows = []
    for line in out.strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) == 2 and parts[1] not in (".", ""):
            try:
                rows.append((parts[0], float(parts[1])))
            except ValueError:
                continue
    return list(reversed(rows))


def fetch_us30y_yahoo() -> list:
    """Yahoo ^TYX 日線，只取「已收盤」交易日（美東 17:00 後視為完成）"""
    out = _curl(YAHOO_URL, headers=["User-Agent: Mozilla/5.0"])
    if not out:
        return []
    try:
        res = json.loads(out)["chart"]["result"][0]
    except Exception:
        return []
    ts = res.get("timestamp", [])
    quote = (res.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close", [])
    now_et = datetime.now(timezone.utc).astimezone(ET)
    rows = []
    for i, t in enumerate(ts):
        if i >= len(closes) or closes[i] is None:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).astimezone(ET).date()
        if d < now_et.date() or (d == now_et.date() and now_et.hour >= 17):
            rows.append((d.isoformat(), round(float(closes[i]), 3)))
    return list(reversed(rows))


def merge_rows(*series) -> list:
    """合併多來源（同日以較後傳入者為準），回傳新→舊"""
    table = {}
    for rows in series:
        for d, v in rows:
            table[d] = v
    return sorted(table.items(), key=lambda kv: kv[0], reverse=True)


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"mode": None, "streak": 0, "last_rate": None, "last_date": None,
            "red_line": False}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def sync_snapshot_gate() -> None:
    """state 落地後，同一行程內立即同步 snapshot 真值層（US30Y 閘門／紅線政策）。

    2026-10-14 US30Y 同源工單（使用者裁決）— 問題與修法：
      本行程式是 us30y_state.json 的唯一寫入者，但 snapshot.us30y_gate 只在
      update_data.py 被其他腳本順帶呼叫時才派生 → 若當日無 update_data 執行，
      snapshot 會停在**前一日**讀值。實測（10-14）：gate 5.598@2026-10-12
      對 state 5.563@2026-10-13 → check_thresholds.py 的「as_of 同源」斷言 FAIL。

      修法＝建立唯一因果鏈：state 寫入者（本行程式）在寫入後立刻觸發真值層重算。
      ① 不新增 cron；② 不改讀值來源（FRED DGS30 ＋ Yahoo ^TYX）；③ **不得手改
      日期或利率** —— 閘門一律由 state 派生（sot_targets.us30y_gate）；④ 呼叫
      update_data 的既有自癒入口，寫入邏輯仍唯一（不在此複製派生規則）。

    fail-closed：同步失敗**不得**讓 monitor 失敗（state 已落地；閘門本身對缺漏／
    落後會回 STALE／UNKNOWN 且 unfreeze_allowed=False），僅印警告供追蹤。
    """
    try:
        sys.path.insert(0, str(BASE))
        import update_data as _ud
        snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        changed = _ud.sync_truth_blocks(snap, write=True)
        if changed:
            print("🔁 snapshot 真值層同步：" + "、".join(changed.keys()))
        _g = snap.get("us30y_gate") or {}
        if _g.get("status") != "OK" or not _g.get("unfreeze_allowed"):
            print(f"⚠️ US30Y 閘門：status={_g.get('status')}｜value={_g.get('value')}%"
                  f"@{_g.get('as_of')}｜解凍{'許可' if _g.get('unfreeze_allowed') else '不許可'}"
                  f"（{_g.get('reason')}）")
    except Exception as e:
        print(f"⚠️ snapshot 真值層同步失敗（{type(e).__name__}: {e}）→ "
              "snapshot.us30y_gate 可能落後 state；下次 update_data 執行時自癒",
              file=sys.stderr)


def red_line_hit(rows) -> bool:
    """最近 CONSECUTIVE_DAYS 個交易日皆 ≥ RED_LINE"""
    last2 = rows[:CONSECUTIVE_DAYS]
    return len(last2) >= CONSECUTIVE_DAYS and all(v >= RED_LINE for _, v in last2)


def red_line_streak(rows) -> int:
    """紅線連續天數（2026-10-14 v1.2：原本只有模式A streak，紅線天數無真值
    → 儀表板把模式A 的 32 日誤標成紅線連續 32 日，P3 標示失真）。"""
    n = 0
    for _d, _v in rows:
        if isinstance(_v, (int, float)) and _v >= RED_LINE:
            n += 1
        else:
            break
    return n


def all_above(vals, thr) -> bool:
    return len(vals) >= CONSECUTIVE_DAYS and all(v >= thr for _, v in vals)


def all_below(vals, thr) -> bool:
    return len(vals) >= CONSECUTIVE_DAYS and all(v <= thr for _, v in vals)


def main():
    fred = fetch_us30y_fred()
    yahoo = fetch_us30y_yahoo()
    rows = merge_rows(fred, yahoo)  # Yahoo 覆蓋同日（較即時）
    if not rows:
        # 2026-10-14 W2/RF-1（使用者裁決）：記錄全來源抓取失敗的**連續次數**並分級告警。
        # 原版只印一行「略過本日檢查」就 return，不寫 state、不計次、無落後告警；
        # 而 gate 在 lag ≤3 天仍判 OK → 1～3 天落後完全沒有升級告警（缺口本體）。
        # 只 FRED 失敗但 Yahoo 成功 → rows 非空，不走本分支（不算全失敗）。
        _st = load_state()
        _n = int(_st.get("fetch_fail_streak") or 0) + 1
        _st["fetch_fail_streak"] = _n
        _st.setdefault("fetch_fail_since", date.today().isoformat())
        save_state(_st)
        _last = _st.get("last_date") or "（無）"
        try:
            _lag = (date.today() - date.fromisoformat(str(_last)[:10])).days
        except Exception:
            _lag = "?"
        if _n >= 3:
            print(f"🔴 US30Y 連續 {_n} 次抓取失敗（FRED／Yahoo 皆無資料）"
                  f"—— 讀值停留在 {_last}（落後 {_lag} 日）；"
                  "投資決策不得依賴現有 US30Y 讀值，請檢查資料源")
        elif _n == 2:
            print(f"⚠️⚠️ US30Y 連續 2 次抓取失敗 —— 讀值停留在 {_last}（落後 {_lag} 日），"
                  "解凍／凍結判定已不可靠")
        else:
            print(f"⚠️ US30Y 無資料（FRED／Yahoo 皆失敗）—— 第 1 次失敗，"
                  f"讀值停留在 {_last}；略過本日檢查")
        return

    last2 = rows[:CONSECUTIVE_DAYS]
    latest_date, latest_rate = rows[0]
    state = load_state()
    today = date.today().isoformat()

    # 2026-10-14 W2/RF-1：抓取成功即歸零連續失敗計數，且必須落在**任何 early return 之前**
    # （下方有「初次執行且未觸發 → 靜默不寫 state」的分支；若在那之後才歸零，
    #   streak 會殘留，下次失敗會被誤計為連續）。
    _pf = int(state.get("fetch_fail_streak") or 0)
    if _pf:
        state.pop("fetch_fail_streak", None)
        state.pop("fetch_fail_since", None)
        save_state(state)
        print(f"✅ US30Y 抓取已恢復（先前連續失敗 {_pf} 次）")

    if all_above(last2, A_THRESHOLD):
        new_mode = "A"
    elif all_below(last2, B_THRESHOLD):
        new_mode = "B"
    else:
        new_mode = None

    old_mode = state.get("mode")
    streak = state.get("streak", 0)

    if new_mode is None and old_mode is None:
        return  # 初次執行且未觸發 → 靜默，不寫 state

    msgs = []

    # ── 模式判定 ──
    if new_mode is None:
        new_mode = old_mode          # 落入中間區間 → 維持既有模式，計數歸零
        streak = 0
    elif new_mode == old_mode:
        # 模式維持 → 靜默。同日重跑不重複累加（2026-09-11：原本每跑一次就 +1，
        # 手動重跑會把 streak 灌水，改成「日期前進才累加」）
        if state.get("last_date") != latest_date:
            streak += 1
    else:
        action = "觸發" if old_mode is not None else "啟用"
        streak = 1
        label = MODE_LABELS.get(new_mode, new_mode)
        msgs.append(f"🚨 龍九再平衡模式切換：{label} {action}")
        msgs.append(f"📈 US30Y 連續{CONSECUTIVE_DAYS}日達標"
                    f"（{last2[1][0]} {last2[1][1]}% → {latest_date} {latest_rate}%）")
        if new_mode == "A":
            msgs.append("🎯 執行策略：配息導流優先 → 逢反彈分批減碼美股科技 → 資金轉台股高股息")
            msgs.append("⛔ 禁令：不加碼美股長久期科技、不新增債券（00983D/PIMCO 維持底倉）")
        else:
            msgs.append("🎯 執行策略：放寬減碼限制，可分批回補優質美股科技、開放債券布局")

    # ── 宏觀風險警示（>=5.30；長債新增凍結；v1.2 不否決台股分批）──
    # 2026-09-11 修：原本只在「模式切換」分支檢查，模式維持時 L90-95 直接 return
    # → 紅線警示在穩態下永遠不會響（紅線凍結規則形同未生效）。改為每條路徑都檢查，
    # 並用 state.red_line 記住是否已警示，跨日只發一次。
    rl_now = red_line_hit(rows)
    rl_prev = bool(state.get("red_line", False))
    if rl_now and not rl_prev:
        msgs.append(f"⚠️ 宏觀風險警示：US30Y 連續{CONSECUTIVE_DAYS}日 ≥{RED_LINE}%"
                    f"（{last2[1][0]} {last2[1][1]}% / {last2[0][0]} {last2[0][1]}%）"
                    f" — 長期債券相關新增買單【凍結】（不受階段影響）")
        msgs.append("⛔ 同步生效：禁新增質押／擴倉；僅配息被動再平衡 + 還債"
                    "｜v1.2（2026-10-14 使用者裁決）：本警示**不單獨否決台股分批**，"
                    "台股分批改由現金／質押 LTV／還本安全閥共同判定")
    elif (not rl_now) and rl_prev:
        msgs.append(f"✅ 宏觀風險警示解除：US30Y 已脫離 ≥{RED_LINE}%"
                    f"（最新 {latest_date} {latest_rate}%），債券新增買單可重新評估")

    # ── 寫 state ──
    fred_dates = {d for d, _ in fred}
    src = "FRED" if all(d in fred_dates for d, _ in last2) else "FRED+Yahoo"
    rl_streak = red_line_streak(rows)
    label = MODE_LABELS.get(new_mode, "—")
    if rl_now:
        label += (f"｜⚠️ 宏觀風險警示 ≥{RED_LINE}%（連續 {rl_streak} 交易日；"
                  f"長天期債券新增買單凍結，不否決台股分批 v1.2）")
    state.update({
        "mode": new_mode,
        "streak": streak,
        "mode_a_streak": streak,          # 模式A（≥5.20）連續天數
        "red_line_streak": rl_streak,     # 紅線（≥5.30）連續天數（v1.2 P3 修正）
        "last_rate": latest_rate,
        "last_date": latest_date,
        "checked_at": today,
        "mode_label": label,
        "red_line": rl_now,
        "data_source": src,
    })
    state.pop("updated_at", None)  # 2026-09-11：移除殘留的舊時間戳（會被誤讀為最後更新日）
    if rl_now:
        state.setdefault("red_line_since", last2[1][0])
    else:
        state.pop("red_line_since", None)
    save_state(state)
    sync_snapshot_gate()   # 2026-10-14：state 落地後立即同步 snapshot（唯一因果鏈）

    if msgs:
        print("\n".join(msgs))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"⚠️ US30Y 監控失敗: {e}")
