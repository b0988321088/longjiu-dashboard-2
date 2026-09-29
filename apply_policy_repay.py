#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保單/券商高息負債「分批清償」入帳器（冪等）。

用途：使用者以質押撥款（restricted_cash）分批清償高息負債時，逐筆把實際入帳反映到 snapshot。
每次執行一筆（一筆＝一天一筆）：現金 −amount、對應負債 −amount、指定用途款 −amount。
淨值不變（資產與負債同減）＝正確記帳；禁把還款當費用或當投資。

用法：
  python apply_policy_repay.py --date 2026-09-30 --amount 2000000 --target policy            # 保單質押借款
  python apply_policy_repay.py --date 2026-10-01 --amount 1000000 --target policy
  python apply_policy_repay.py --date 2026-10-02 --amount 1000000 --target securities        # 券商質押 100 萬
  python apply_policy_repay.py --dry-run --date ... --amount ... --target ...                # 只印不寫

冪等：以 (date, amount, target) 為鍵記在 snapshot.policy_repay_log；重跑同鍵直接跳過。
還原：錯誤入帳用 --undo --date D --amount N --target T（反向回沖，現金加回、負債加回、指定款加回）。
"""
import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
P = BASE / "snapshot.json"
ACC = "活期儲蓄存款"          # 國泰世華一般活存（末五碼 85061；撥款入帳帳戶）
FIELDS = {
    "policy": ("policy_pledge_loan", "policy_loan"),          # 保單質押借款（安聯A2＋B1＋第一金）
    "securities": ("pledge_loan",),                            # 券商質押借款
}


def apply(snap: dict, date: str, amount: int, target: str, undo: bool = False) -> dict:
    sign = -1 if undo else 1
    log = snap.setdefault("policy_repay_log", [])
    key = {"日期": date, "金額": amount, "對象": target}
    if not undo and any(all(x.get(k) == v for k, v in key.items()) for x in log):
        print(f"⚠️ 已記錄過：{key} → 跳過（冪等）")
        return snap

    for f in FIELDS[target]:
        cur = int(snap.get(f) or 0)
        snap[f] = max(0, cur - sign * amount)
    snap["cash_total"] = int(snap.get("cash_total") or 0) - sign * amount
    cd = snap.setdefault("cash_detail", {})
    cd[ACC] = int(cd.get(ACC) or 0) - sign * amount

    rc = snap.setdefault("restricted_cash", {})
    rc["金額"] = max(0, int(rc.get("金額") or 0) - sign * amount)
    rc["用途"] = ("清償 500 萬高息負債（保單質押 400 萬@4% ＋ 券商質押 100 萬@3.92%）"
                  f"｜本筆 {date} {'沖回' if undo else '清償'} {amount:,} {target}"
                  f"｜剩餘指定用途款 {rc['金額']:,}")
    rc["狀態"] = ("已全數清償完畢 → 隔離自動解除" if rc["金額"] == 0 else
                  ("部分清償中" if not undo else "部分清償沖回"))
    rc["最後更新"] = date

    log.append({**key, "動作": "undo" if undo else "repay"})

    # 同義鍵／負債拆解／淨值一律走 asset_sync 單一來源
    from asset_sync import sync_snapshot_keys, rebuild_liabilities   # noqa: E402
    snap["total_assets"] = int(snap.get("total_assets") or 0) - sign * amount
    snap = sync_snapshot_keys(snap)
    snap = rebuild_liabilities(snap)
    return snap


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="實際入帳日 YYYY-MM-DD")
    ap.add_argument("--amount", required=True, type=int, help="本筆金額")
    ap.add_argument("--target", required=True, choices=sorted(FIELDS))
    ap.add_argument("--undo", action="store_true", help="反向回沖（登錯帳用）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    snap = json.loads(P.read_text(encoding="utf-8"))
    before = {k: snap.get(k) for k in ("cash_total", "total_assets", "total_liabilities",
                                       "net_worth", "policy_pledge_loan", "pledge_loan",
                                       "fund_pledge_loan")}
    before["restricted"] = (snap.get("restricted_cash") or {}).get("金額")
    out = apply(snap, a.date, a.amount, a.target, undo=a.undo)

    print(f"=== {'[DRY-RUN] ' if a.dry_run else ''}{a.date} {a.target} "
          f"{'沖回' if a.undo else '清償'} {a.amount:,} ===")
    for k, v in before.items():
        now = (out.get(k) if k != "restricted" else (out.get("restricted_cash") or {}).get("金額"))
        flag = "  ←" if now != v else ""
        print(f"  {k:20s} {v:>12,} → {now:>12,}{flag}" if isinstance(v, int) and isinstance(now, int)
              else f"  {k:20s} {v} → {now}{flag}")
    if out.get("net_worth") != before.get("net_worth"):
        print("⚠️ 淨值變動＝記帳錯誤（還款同時減資產與負債，淨值必須不變）")

    if a.dry_run:
        print("(dry-run，未寫檔)")
        return 0
    P.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("✅ 已寫入 snapshot.json；接著請跑四源同步（sync_all.py 或 regenerate_report.py）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
