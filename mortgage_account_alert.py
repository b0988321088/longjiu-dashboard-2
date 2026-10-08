#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mortgage_account_alert.py — 房貸扣款行水位每日提醒（2026-10-09 使用者裁決：SI 第一批 ①）

口徑（與顯示層同源，禁硬編碼）：
- 安全線＝「自身房貸月繳 × 3」（3 個月扣款）。2026-09-28 使用者裁示：
  國泰（大義街）、永豐（洲際W）各自用房貸月繳×3；台新薪轉戶仍用月支出×3。
- 國泰月繳採派生真值 mortgage_rate.cathay_monthly（本金×利率/12），利率一動安全線跟著動。
- 永豐月繳讀 snapshot.mortgage_sinopac_monthly。
- 扣款日（國泰 20 日）為**排程常數、非門檻值**：僅用於顯示「距今 N 天」，不參與任何判斷；
  snapshot 目前僅以 mortgage_cathay_payment_note 文字記述，尚未結構化（列為後續改善候選）。

Fail-closed（2026-10-09 CIO 對抗性審查 REJECT 之阻斷項修正）：
- 「缺值／為 0 不得退成 0 門檻」的防護必須覆蓋**整條 fallback 鏈**與**非有限值**：
  ①月繳可用 → 月繳×3；②月繳不可用但月支出可用 → 月支出×3；
  ③**兩者皆不可用** → 不得靜默：輸出告警至 stdout 並 rc=2（watchdog 必須推播）。
- NaN 特別危險：`not NaN`=False、`NaN<=0`=False 會穿過舊防線，且 `bal < NaN` 恆 False → 靜默 🟢。
  一律以 math.isfinite 判定「可用」。Inf 方向天然安全，但仍一併視為不可用、走 fail-closed。
- 餘額鍵非數值（如 'abc'）不得讓行程 traceback：以 0 計並在輸出中明確標示。

行為：餘額低於安全線 → 提醒補足（目標水位式：只補差額）；全部達標 → 不輸出任何內容
      （no_agent watchdog：空 stdout＝不推播，零噪音）。

用法：python mortgage_account_alert.py               # 直接跑（cron no_agent）
      python mortgage_account_alert.py --always      # 強制輸出（人工檢查用）
      python mortgage_account_alert.py --snapshot X  # 指定 snapshot（測試用）

exit code：0＝達標或正常輸出；1＝snapshot／參數問題（技術失敗）；2＝安全線不可得（fail-closed）
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
RC_OK, RC_TECH, RC_FAILCLOSED = 0, 1, 2


def _num(x):
    """轉有限數；不可轉／非有限（NaN、Inf）→ None。"""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _usable(x):
    """可作為安全線來源：有限且 > 0；否則 None。"""
    v = _num(x)
    return v if (v is not None and v > 0) else None


def _cathay_monthly(snap: dict):
    """國泰房貸月繳（派生真值；不可用回 None）。"""
    try:
        from mortgage_rate import cathay_monthly
        return _num(cathay_monthly(snap))
    except Exception:
        return _num(snap.get("mortgage_cathay_monthly"))


def _sinopac_monthly(snap: dict):
    """永豐房貸月繳（snapshot；不可用回 None）。"""
    return _num(snap.get("mortgage_sinopac_monthly"))


def _cathay_use_text(snap: dict) -> str:
    """國泰用途文字由 mortgage_rate 派生（禁硬編碼金額／利率字面）。"""
    try:
        from mortgage_rate import cathay_rate_pct, cathay_wan
        return (f"{cathay_wan(snap)}萬@{cathay_rate_pct(snap)}% 寬限期付息，"
                f"每月 20 日繳款")
    except Exception:
        return "寬限期付息，每月 20 日繳款"


def _sinopac_use_text(snap: dict) -> str:
    return "3 筆房貸月付合計，扣款帳戶分佈於市政分行＋營業部DAWHO"


def _days_to_due(due_day, today: date):
    """距下一次扣款日天數（今天已過該日 → 算下個月，不為負）。"""
    for add in (0, 1):
        y, m = today.year, today.month + add
        while m > 12:
            y, m = y + 1, m - 12
        try:
            cand = date(y, m, due_day)
        except ValueError:          # 該月無此日（例如 31 日）
            continue
        if cand >= today:
            return (cand - today).days
    return None


# (顯示名, cash_detail 鍵清單, 月繳來源, 扣款日, 用途文字來源)
ACCOUNTS = (
    ("國泰世華（大義街房貸扣款行）", ("活期儲蓄存款",), _cathay_monthly, 20, _cathay_use_text),
    ("永豐銀行（洲際W 房貸扣款行）",
     ("市政分行活期儲蓄存款", "營業部DAWHO活期儲蓄存款"),
     _sinopac_monthly, None, _sinopac_use_text),
)


def main() -> int:
    always = "--always" in sys.argv
    snap_path = BASE / "snapshot.json"
    if "--snapshot" in sys.argv:
        i = sys.argv.index("--snapshot")
        if i + 1 < len(sys.argv):
            snap_path = Path(sys.argv[i + 1])
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
    except Exception as e:      # 讀不到就安靜退出（別在 08:35 推技術錯誤）
        print(f"⚠️ mortgage_account_alert：無法讀 snapshot（{type(e).__name__}: {e}）",
              file=sys.stderr)
        return RC_TECH

    cd = snap.get("cash_detail") or {}
    expense = _usable(snap.get("monthly_expense"))
    today = date.today()

    rows = []
    for name, keys, fn, due_day, usefn in ACCOUNTS:
        parts, bad_keys = [], []
        for k in keys:
            v = _num(cd.get(k))
            if v is None:
                bad_keys.append(k)
                v = 0.0
            parts.append(v)
        bal = sum(parts)

        monthly, src = _usable(fn(snap)), "月繳"
        if monthly is None and expense is not None:
            monthly, src = expense, "月支出（月繳不可用，退回月支出口徑）"
        line = None
        if monthly is not None:
            line = monthly * 3
            if not (math.isfinite(line) and line > 0):   # 防禦斷言
                line, monthly, src = None, None, None
        use = usefn(snap) if callable(usefn) else usefn
        rows.append({"name": name, "bal": bal, "line": line, "due_day": due_day,
                     "use": use, "src": src, "monthly": monthly, "bad_keys": bad_keys})

    alerts, ok_rows, failclosed = [], [], False
    for r in rows:
        if r["line"] is None:
            failclosed = True
            alerts.append(
                f"❓ {r['name']} 安全線不可得（月繳與月支出皆缺值／非有限）→ **無法判定是否達標**")
            alerts.append("   → 請人工檢視 snapshot 的 mortgage_cathay_monthly／"
                          "mortgage_sinopac_monthly／monthly_expense（不得視為達標）")
            continue
        if r["bad_keys"]:
            alerts.append(f"   ⚠️ {r['name']}：餘額鍵 {'、'.join(r['bad_keys'])} "
                          f"非數值／缺值，已以 0 計")
        if "退回" in str(r["src"]):
            # 月繳不可用（缺值／為 0／NaN／Inf）→ 安全線基礎已改變，必須可追溯
            print(f"  ⚠️ {r['name']}：月繳不可用（缺值／為 0／非有限）→ "
                  f"安全線退回月支出口徑（{r['monthly']:,.0f}×3）", file=sys.stderr)
            if r["bal"] < r["line"]:
                alerts.append(f"   ⚠️ {r['name']}：月繳不可用，安全線已退回月支出口徑"
                              f"（{r['monthly']:,.0f}×3）")
        if r["bal"] < r["line"]:
            dday = ""
            if r["due_day"]:
                n = _days_to_due(r["due_day"], today)
                dday = f"｜扣款日 每月 {r['due_day']} 日（距今 {n} 天）" if n is not None else ""
            alerts.append(f"🔴 {r['name']} {r['bal']:,.0f} < 安全線 {r['line']:,.0f}"
                          f"｜缺口 {r['line'] - r['bal']:,.0f}{dday}")
            alerts.append(f"   → 建議自台新薪轉／國泰活存轉入，補至 {r['line']:,.0f}"
                          f"（目標水位式，只補差額）")
            alerts.append(f"   （用途：{r['use']}；扣款失敗會影響信用紀錄與銀行關係）")
        else:
            ok_rows.append(r)

    if not alerts and not always:
        return RC_OK                 # 達標 → 不推播

    out = [f"🏦 房貸扣款行水位提醒（{snap.get('date', '')}）"]
    out.extend(alerts)
    if not alerts:
        out.append("🟢 房貸扣款行皆高於各自安全線")
        for r in ok_rows:
            dday = f"（扣款日 {r['due_day']} 日）" if r["due_day"] else ""
            fb = "｜⚠️ 月繳不可用，退回月支出口徑" if "退回" in str(r["src"]) else ""
            out.append(f"   ✅ {r['name']} {r['bal']:,.0f} / 安全線 {r['line']:,.0f}{dday}{fb}")
    out.append("（口徑：安全線＝自身房貸月繳×3；國泰月繳取派生真值 rate×本金/12；"
               "永豐讀 snapshot.mortgage_sinopac_monthly；月繳不可用時退月支出×3；"
               "兩者皆不可用→告警不靜默）")
    print("\n".join(out))
    return RC_FAILCLOSED if failclosed else RC_OK


if __name__ == "__main__":
    raise SystemExit(main())
