"""Gemini 餘額提醒（每3天）— no_agent 版。
每次執行必定輸出一則簡短提醒（每3天一則，不洗版）。
資料源：longjiu_system/data/gemini_cost_log.json + 2026-08-01 查得之常數。
"""
import json
from datetime import date, timedelta
from pathlib import Path

LJ = Path.home() / "Desktop" / "longjiu_system"
LOG = LJ / "data" / "gemini_cost_log.json"

# 最後已知狀態 fallback（log 缺該月份資料時才用）
BALANCE_TWD = 399
BALANCE_DATE = date(2026, 8, 1)
DAILY_BURN_TWD = 34
TOPUP_SUGGEST_TWD = 1000


def main():
    today = date.today()
    bal = BALANCE_TWD
    bal_date = BALANCE_DATE
    log_note = "log 無新異動"
    if LOG.exists():
        try:
            data = json.loads(LOG.read_text(encoding="utf-8"))
            # 月份動態化：讀最新有餘額的月份 key
            _mm = [k for k in data.keys() if isinstance(k, str) and len(k) == 7]
            if _mm:
                aug = None
                for _k in sorted(_mm, reverse=True):
                    _d = data.get(_k, {})
                    if isinstance(_d, dict):
                        for _bk in ("credit_balance_twd", "balance_twd"):
                            if _d.get(_bk) is not None:
                                aug = _d
                                break
                    if aug:
                        break
                if aug is None:
                    aug = data.get(max(_mm), {})
                # 餘額 key 名稱：credit_balance_twd（9/5 起 log 用）或 balance_twd
                for _bk in ("credit_balance_twd", "balance_twd"):
                    if isinstance(aug, dict) and aug.get(_bk) is not None:
                        bal = float(aug[_bk])
                        break
                # 錨定日期：該月份條目自帶的 date；缺省用當月 1 日
                if isinstance(aug, dict) and aug.get("date"):
                    try:
                        bal_date = date.fromisoformat(str(aug["date"]))
                    except ValueError:
                        pass
                else:
                    bal_date = date(int(max(_mm)[:4]), int(max(_mm)[5:7]), 1)
            upd = data.get("updated", "")
            if upd:
                log_note = f"log 更新於 {upd}"
        except Exception as e:
            log_note = f"log 讀取失敗：{e}"

    # 估算：剩餘天數以「餘額 / 日耗」為準，末日 = 錨定日期 + 天數（不再從 8/1 起算）
    days_total = max(int(bal / DAILY_BURN_TWD), 0)
    end_date = bal_date + timedelta(days=days_total)
    remaining = max((end_date - today).days, 0)

    lines = [f"💰 Gemini 費用提醒（{today.month}/{today.day}）："]
    lines.append(f"- 餘額 NT${bal:.0f}（{bal_date.month}/{bal_date.day} 查得，{log_note}）")
    lines.append(f"- 日耗約 NT${DAILY_BURN_TWD} → 預估 {end_date.month}/{end_date.day} 用完（剩約 {remaining} 天）")
    if remaining <= 5:
        lines.append(f"- ⚠️ 快用完了！建議盡快儲值 NT${TOPUP_SUGGEST_TWD}（約可撐 1 個月）")
    elif remaining <= 20:
        lines.append(f"- 接近尾聲，可考慮儲值 NT${TOPUP_SUGGEST_TWD}（約可撐 1 個月）")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
