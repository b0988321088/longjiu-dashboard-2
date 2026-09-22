#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""set_cost_baseline.py — 建立／更新「治理後累計」基準日快照。

何時跑：完成一次會影響成本的治理性修改後（例：pii-gate/CER 額度、備援鏈順序、
日耗口徑）。跑完後 `daily_token_account.py` 與 `ai_cost_watch.py` 的「治理後累計」
自動從基準日隔天起算，之前的污染期只留在歷史、不併入。

安全：只寫 `data/cost_baseline.json`（會先備份舊檔為 .bak），不動任何帳本。
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import shutil
import sys
from pathlib import Path

LJ = Path.home() / "Desktop" / "longjiu_system"
BASELINE = LJ / "data" / "cost_baseline.json"


def load_dta():
    p = LJ / "daily_token_account.py"
    spec = importlib.util.spec_from_file_location("daily_token_account", p)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    sys.path.insert(0, str(LJ))
    from cost_baseline import ds_topup_history, prior_totals  # noqa: E402

    dta = load_dta()
    now = dt.datetime.now()
    today = now.date()
    today_s = today.isoformat()

    days = {(today - dt.timedelta(days=i)).isoformat() for i in range(0, 15)}
    per_range = dta.scan_agent_log_range(days)
    per_today = per_range.get(today_s, {})
    ds_usd, gem_usd = dta.day_split(per_today)
    free_usd = sum(dta.cost_usd(m, t) for m, t in per_today.items()
                   if not m.startswith("deepseek") and not m.startswith("gemini"))
    free_calls = sum(t["calls"] for m, t in per_today.items()
                     if not m.startswith("deepseek") and not m.startswith("gemini"))
    cer, q429, _err = dta.scan_failures(today_s)

    bal, bal_src = dta.ds_balance_live()
    if bal is None:
        bal, bal_src = dta.ds_balance_csv()

    up_date, up_amt, up_hhmm = dta.gemini_topup()
    gm_used_twd = None
    if up_amt > 0:
        gm_used_twd = round(dta.gemini_used_since(up_date, up_hhmm, per_range) * dta.USD_TWD, 1)

    prev = None
    if BASELINE.exists():
        try:
            prev = json.loads(BASELINE.read_text(encoding="utf-8"))
            shutil.copy2(BASELINE, BASELINE.with_suffix(".json.bak"))
        except Exception:  # noqa: BLE001
            prev = None

    snap = {
        "baseline_date": today_s,
        "cutover_at": now.strftime("%Y-%m-%dT%H:%M"),
        "reason": "wallet_status 日耗動態化（寫死 ¥15.5 → 近 7 日中位數）＋ CER/備援治理後重新起算",
        "rule": "累計自基準日隔日 00:00 起算；基準日當天仍含修改前數字故整日剔除",
        "ds_balance_cny": round(float(bal), 2) if bal is not None else None,
        "ds_balance_source": bal_src,
        "gemini_topup": {"date": up_date, "amount_twd": up_amt} if up_amt > 0 else None,
        "gemini_used_twd_since_topup": gm_used_twd,
        "gemini_left_twd_est": (round(up_amt - gm_used_twd, 1) if (up_amt > 0 and gm_used_twd is not None) else None),
        "day_of_baseline_pre_cutover": {
            "ds_twd": round(ds_usd * dta.USD_TWD), "gemini_twd": round(gem_usd * dta.USD_TWD),
            "free_calls": free_calls, "cer": cer, "q429": q429,
            "note": "基準日整日剔除，這裡只是留檔說明當天（含修改前）的規模",
        },
        "excluded_history_before_baseline": prior_totals(today_s),
        "ds_topups_all_time": ds_topup_history(),
        "previous_baseline": prev.get("baseline_date") if prev else None,
    }
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")

    nxt = (today + dt.timedelta(days=1)).isoformat()
    print(f"✅ 基準日已設定：{today_s}（累計自 {nxt} 00:00 起算）")
    print(f"　DS 餘額 ¥{snap['ds_balance_cny']}（{bal_src}）")
    if gm_used_twd is not None:
        print(f"　Gemini {up_date} 儲 NT${up_amt:,.0f}｜基準日已用 ≈NT${gm_used_twd:,.0f}"
              f"｜推定剩 NT${snap['gemini_left_twd_est']:,.0f}")
    ex = snap["excluded_history_before_baseline"]
    print(f"　剔除的歷史：{ex['days']} 天｜CER {ex['cer']} 次｜DS NT${ex['ds_twd']:,.0f}"
          f"／Gemini NT${ex['gem_twd']:,.0f}")
    print(f"　寫入 {BASELINE}（舊檔備份 .bak）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
