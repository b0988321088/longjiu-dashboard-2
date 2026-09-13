"""DeepSeek 餘額警報 — no_agent watchdog（2026-09-13 門檻改版 v2）。

先跑 cost_monitor.py 更新 cost_log.csv / daily_analysis.json（維持歷史記錄），
再依門檻決定輸出：**餘額 <= 12 CNY 或自算剩餘天數 <= 2** → 印出警報（傳送）；
否則靜默（不發訊息）。

2026-09-13 改版理由（省錢分流方案 D）：
- 舊門檻 50 CNY / 7 天 → 天天發（9/8 起 job 被 pause），變噪音後反而沒人看。
- 新門檻對準「還有 ~2 天可用」才提醒，目標是「永遠不斷線」——DS 一斷線，所有
  對話被迫走 Gemini，成本立刻從 ~NT$18/日跳到 NT$40-60/日（9/13 實測）。
- 剩餘天數自己算：cost_log.csv 近期平均日耗（不再信 cost_monitor 的 0 天哨兵值）。
- 門檻可用環境變數覆寫（測試用）：LJ_DS_BAL_THRESHOLD / LJ_DS_DAYS_THRESHOLD。
"""
import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

LJ = Path.home() / "Desktop" / "longjiu_system"
COST = LJ / "cost_monitor.py"
DA = LJ / "daily_analysis.json"
LOG = LJ / "cost_log.csv"

THRESHOLD_BALANCE_CNY = float(os.environ.get("LJ_DS_BAL_THRESHOLD", 12.0))
THRESHOLD_DAYS = float(os.environ.get("LJ_DS_DAYS_THRESHOLD", 2.0))
MONTHLY_BUDGET_CNY = 400.0
BUDGET_WARN_RATIO = 0.8
TOPUP_CNY = 100


def read_cost_log():
    """回傳 [(date, balance, daily_cost)]（舊→新）。"""
    rows = []
    if not LOG.exists():
        return rows
    try:
        rd = csv.reader(LOG.open(encoding="utf-8"))
        for r in rd:
            if len(r) < 2:
                continue
            try:
                rows.append((r[0].strip(), float(r[1]), float(r[2] or 0)))
            except Exception:
                continue
    except Exception:
        pass
    return rows


def avg_daily(rows, window=3):
    """近期平均日耗（用餘額差額，比 daily_cost 欄可靠）。"""
    if len(rows) < 2:
        return 0.0
    tail = rows[-(window + 1):]
    try:
        d0 = datetime.strptime(tail[0][0], "%Y-%m-%d")
        d1 = datetime.strptime(tail[-1][0], "%Y-%m-%d")
        span = max(1, (d1 - d0).days)
        spent = tail[0][1] - tail[-1][1]
        return max(0.0, spent) / span
    except Exception:
        return 0.0


def monthly_spend(rows):
    month = datetime.now().strftime("%Y-%m")
    return sum(r[2] for r in rows if r[0].startswith(month))


def main():
    # 1) 跑 cost_monitor.py：更新 cost_log.csv 與 daily_analysis.json
    try:
        p = subprocess.run([sys.executable, str(COST)], cwd=str(LJ),
                           capture_output=True, timeout=120)
        if p.returncode != 0:
            print(f"⚠️ DeepSeek 餘額檢查：cost_monitor 失敗（rc={p.returncode}）")
            return
    except Exception as e:
        print(f"⚠️ DeepSeek 餘額檢查失敗（cost_monitor 執行錯誤）：{e}")
        return

    # 2) 讀最新餘額（以 cost_log 尾筆為準，daily_analysis 為備）
    rows = read_cost_log()
    bal = rows[-1][1] if rows else None
    if bal is None:
        if not DA.exists():
            print("⚠️ DeepSeek 餘額檢查：找不到任何餘額記錄")
            return
        try:
            bal = float(json.loads(DA.read_text(encoding="utf-8"))
                        .get("deepseek_cost", {}).get("balance", 0) or 0)
        except Exception as e:
            print(f"⚠️ DeepSeek 餘額檢查失敗：{e}")
            return
    if bal <= 0:
        # 查詢失敗時 cost_monitor 會保留上次值；真的 0 才可能到這裡
        print(f"🚨 DeepSeek 餘額為 {bal:.2f} CNY — 請立即確認/儲值（否則對話將全走 Gemini，成本 ×2-3）")
        return

    rate = avg_daily(rows)
    days = (bal / rate) if rate > 0 else 999

    msgs = []
    if bal <= THRESHOLD_BALANCE_CNY or days <= THRESHOLD_DAYS:
        msgs.append(
            f"⚠️ DeepSeek 餘額 {bal:.2f} CNY（約 NT${bal*4.2:.0f}），"
            f"近期日耗 {rate:.1f} CNY → 約剩 {days:.1f} 天。\n"
            f"建議儲值 ¥{TOPUP_CNY}（約 NT${TOPUP_CNY*4.2:.0f}，可撐約 {TOPUP_CNY/max(rate,0.1):.0f} 天）。\n"
            f"理由：DS 快取價幾乎免費（$0.007/M），同 token 走 Gemini 約貴 8 倍 —— "
            f"DS 一斷線，所有對話被迫走 Gemini，日成本會從 ~NT$18 跳到 NT$40-60。")
    spent = monthly_spend(rows)
    if spent > BUDGET_WARN_RATIO * MONTHLY_BUDGET_CNY:
        msgs.append(f"📊 本月 DS 已用 {spent:.0f}/{MONTHLY_BUDGET_CNY:.0f} CNY"
                    f"（{spent/MONTHLY_BUDGET_CNY*100:.0f}%），接近月預算上限，建議檢討任務清單。")
    if msgs:
        print("\n\n".join(msgs))
    # 未達門檻 → 無輸出（靜默）


if __name__ == "__main__":
    main()
