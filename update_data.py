#!/usr/bin/env python3
"""update_data.py — 龍九一鍵資料更新（2026-08-24 建立，優化「每次更新一直檢查」）
用法：
  python update_data.py --cash=817539 --securities=2825170 --funds=12773181 --insurance=9766831
  python update_data.py --funds_cathay=11974337   # 只更新國泰基金市值
  python update_data.py --check                    # 只檢查同義欄位

自動完成：
  ① 更新分類值 → 同步全部同義欄位（含 funds_cathay/securities_current_value/funds）
  ② 重算 total_assets（保險+證券+基金+現金）
  ③ 重算穿透五桶（calc_penetration → snapshot.penetration）
  ④ asset_sync 驗證（同義欄位一致）
  ⑤ 提示下一步：python sync_all.py [date] 產報表
更新前自動備份 snapshot.backup.json
"""
import json, sys, shutil, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"

def main():
    args = {}
    for a in sys.argv[1:]:
        if "=" in a:
            k, v = a.split("=", 1)
            args[k.strip("-")] = v
    if "--check" in sys.argv or not args:
        # 檢查模式
        from asset_sync import verify_synonyms
        snap = json.loads(SNAP.read_text(encoding="utf-8"))
        issues = verify_synonyms(snap)
        if issues:
            print("❌ 同義欄位不一致：")
            for i in issues:
                print(f"  {i}")
            return 1
        print("✅ 所有同義欄位一致")
        print(f"  總資產: {snap.get('total_assets'):,}")
        return 0

    # 備份
    shutil.copy(SNAP, BASE / "snapshot.backup.json")
    snap = json.loads(SNAP.read_text(encoding="utf-8"))

    # ① 更新主 key
    KEYMAP = {
        "cash": "cash_total", "securities": "securities_total",
        "funds": "funds_total", "insurance": "insurance_total",
        "funds_cathay": "funds_cathay",
        "allianz": "allianz_combined", "firstjin": "firstjin_fl65_current_value",
    }
    changed = []
    for k, v in args.items():
        if k in KEYMAP and v.replace(",", "").replace("-", "").isdigit():
            snap[KEYMAP[k]] = int(v.replace(",", ""))
            changed.append(f"{KEYMAP[k]}={int(v.replace(',', '')):,}")

    # ② 同步同義欄位 + 重算總資產
    from asset_sync import sync_snapshot_keys
    snap = sync_snapshot_keys(snap)

    # 2026-08-26 檢討修正：--allianz/--firstjin 更新時 → 保險總值自動重算（不需另傳 --insurance）
    if args.get("allianz") or args.get("firstjin"):
        _az = snap.get("allianz_combined", 0) or 0
        _fj = snap.get("firstjin_fl65_current_value", snap.get("firstjin_current_value", 0)) or 0
        snap["insurance_total"] = _az + _fj
        snap = sync_snapshot_keys(snap)
        print(f"✅ 保險總值自動重算: {_az:,} + {_fj:,} = {snap['insurance_total']:,}")

    # 2026-08-26 血淚：--securities 更新時必須同步縮放 holdings dict（否則 4 源比對 DB 舊值覆蓋）
    if args.get("securities"):
        _sec = snap.get("securities", {})
        if isinstance(_sec, dict):
            _holds = _sec.get("holdings", [])
            _hsum = sum(h.get("shares", 0) * h.get("price", 0) for h in _holds)
            if _hsum > 0:
                _scale = float(args["securities"]) / _hsum
                for h in _holds:
                    if h.get("shares"):
                        h["price"] = round(h.get("price", 0) * _scale, 4)
                _sec["holdings"] = _holds
                snap["securities"] = _sec

    # 2026-08-26：securities 必須是 dict（含 holdings），勿設成 int（會讓 calc_penetration 崩潰）
    if not isinstance(snap.get("securities"), dict):
        print("⚠️ securities 非 dict（結構受損），已忽略數值覆寫；請用 git 恢復 snapshot.json")

    # 2026-08-26 血淚：--funds_cathay 更新時必須同步 funds_breakdown.國泰直購（穿透報告讀 breakdown 逐檔）
    # 用法：--cathay_funds='{"富達全球動能多元B股C月配息美元":5969297,"聯博全球多元收益AD美元月配":999779,"國泰台灣貨幣市場基金":5000904}'
    if args.get("cathay_funds"):
        try:
            _cf = json.loads(args["cathay_funds"])
            _fb = snap.get("funds_breakdown", {})
            _cat = _fb.get("國泰直購", {})
            for _k, _v in _cf.items():
                _cat[_k] = _v
            _fb["國泰直購"] = _cat
            snap["funds_breakdown"] = _fb
            print(f"✅ funds_breakdown 國泰直購已同步（{len(_cf)} 檔）")
        except Exception as _e:
            print(f"⚠️ cathay_funds 解析失敗: {_e}")
    snap["total_assets"] = (snap.get("insurance_total", 0) or 0) + (snap.get("securities_total_market_value", 0) or 0) \
        + (snap.get("fund_market", 0) or 0) + (snap.get("cash_total", 0) or 0)

    # ③ 重算穿透（保留既有 keys，如科技拆解）
    from update_all import calc_penetration
    pen = calc_penetration(snap["cash_total"], snap["insurance_total"], snap["securities_total_market_value"],
                           snap["fund_market"], bond_portion=None, fund_ratios=None, snap=snap)
    total = snap["total_assets"]
    _old_pen = snap.get("penetration", {}) or {}
    _new_pen = {
        "actual_twd": {k: pen[k] for k in ["台股市值型成長", "美股市值型成長", "防守型配息", "債券", "現金/安全網"]},
        "actual_pct": {k: round(pen[k] / total * 100, 1) for k in ["台股市值型成長", "美股市值型成長", "防守型配息", "債券", "現金/安全網"]},
        "targets": _old_pen.get("targets", {"台股市值型目標": 10, "美股市值型目標": 40, "配息型目標": 20, "債券型目標": 25, "現金目標": 5}),
    }
    # 保留既有延伸 key（科技拆解/防禦維度等）
    for _k in ["美股市值型成長_科技", "美股市值型成長_非科技"]:
        if _k in _old_pen.get("actual_pct", {}):
            _new_pen["actual_pct"][_k] = _old_pen["actual_pct"][_k]
    snap["penetration"] = _new_pen

    # ④ 驗證
    from asset_sync import verify_synonyms
    issues = verify_synonyms(snap)
    if issues:
        print("❌ 同義欄位不一致：")
        for i in issues:
            print(f"  {i}")
        shutil.copy(BASE / "snapshot.backup.json", SNAP)
        print("⚠️ 已還原 snapshot.backup.json")
        return 1

    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")

    # 2026-08-26 檢討修正：同步 DB assets 當日列（4 源比對根因：snapshot 更新但 DB 舊 → sync_all 失敗還原）
    try:
        import sqlite3
        _db = sqlite3.connect(BASE / "dragon_assets.db")
        _today = datetime.date.today().isoformat()
        _tot = snap.get("total_assets", 0) or 0
        _row = (_today, snap.get("cash_total", 0), 0, snap.get("securities_total", 0),
                snap.get("insurance_total", 0), snap.get("funds_total", 0), _tot, snap.get("total_liabilities", 0))
        # 2026-08-28 防呆：檢查「昨天列」是否已被誤寫成今天值（資產變動基準被覆蓋的根因）
        _ytd = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        _yrow = _db.execute("SELECT total_assets FROM assets WHERE date=?", (_ytd,)).fetchone()
        if _yrow and abs(_yrow[0] - _tot) < 1000 and _ytd != _today:
            print(f"⚠️ 警示：DB {_ytd} 列 = 今天值（{_yrow[0]:,.0f}）→ 歷史基準可能被覆蓋！asset_diff 對比會失真")
        _cur = _db.execute("SELECT 1 FROM assets WHERE date=?", (_today,)).fetchone()
        if _cur:
            _db.execute("UPDATE assets SET cash_total=?, securities=?, insurance=?, funds=?, total_assets=?, total_liabilities=? WHERE date=?",
                        (_row[1], _row[3], _row[4], _row[5], _row[6], _row[7], _today))
        else:
            _db.execute("INSERT INTO assets (date, cash_total, bonds, securities, insurance, funds, total_assets, total_liabilities) VALUES (?,?,?,?,?,?,?,?)", _row)
        _db.commit()
        print(f"✅ DB assets {_today} 已同步（4 源一致）")
    except Exception as _e:
        print(f"⚠️ DB 同步失敗: {_e}")

    print("✅ 資料更新完成：")
    for c in changed:
        print(f"  {c}")
    print(f"  總資產: {snap['total_assets']:,}")
    print("  穿透: " + " / ".join(f"{k}{v}%" for k, v in snap["penetration"]["actual_pct"].items()))
    print("  備份: snapshot.backup.json")
    print("\n➡️ 下一步：python sync_all.py " + snap.get("date", datetime.date.today().isoformat()) + "（產全部報表）")
    return 0

if __name__ == "__main__":
    sys.exit(main())
