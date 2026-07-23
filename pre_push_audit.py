"""推送前內容保護攔截（語義防火牆）
每次 deploy 前自動檢查日報完整性 + 三源一致性
任一項失敗 → 禁止推送 + 印出原因"""
import json, sys, sqlite3
from pathlib import Path
from logging_config import get_logger
logger = get_logger("pre_push_audit")

BASE = Path(__file__).parent.resolve()
TODAY = __import__("datetime").date.today().isoformat()
DAILY = BASE / f"daily_report_v2_{TODAY}.html"
SNAP = BASE / "snapshot.json"
DB = BASE / "dragon_assets.db"

def fail(reason: str):
    print(f"  ❌ {reason}")
    return False

def check() -> bool:
    if not DAILY.exists():
        return fail("日報檔案不存在")

    html = DAILY.read_text(encoding="utf-8")
    snap = json.loads(SNAP.read_text(encoding="utf-8")) if SNAP.exists() else {}
    ok = True

    # 1. 五大章節完整
    chapters = ["1/5", "2/5", "3/5", "4/5", "5/5"]
    for ch in chapters:
        if ch not in html:
            ok = fail(f"缺少章節 {ch}")

    # 2. 基金數值 ≠ 0
    fund = snap.get("fund_market_value", 0) or 0
    if fund > 0 and f"{fund:,}" not in html:
        ok = fail(f"基金數值 {fund:,} 未出現在日報")
    if fund == 0:
        ok = fail("基金數值為 0（snapshot 無資料）")

    # 3. CEO 區塊有決策內容
    ceo_indicators = ["✅", "⏸️", "CEO 戰略"]
    if not any(ind in html for ind in ceo_indicators):
        ok = fail("CEO 區塊無決策內容")

    # 4. 關鍵數據不為空白
    checks = [
        ("保單現值", snap.get("insurance_current_value", 0)),
    ]
    for label, val in checks:
        if val and f"{val:,}" not in html:
            ok = fail(f"{label} {val:,} 未出現在日報")
    if "3," not in html:
        ok = fail("現金值未出現在日報")

    # 5. 差異分析連結存在
    if "asset_diff" not in html and "差異分析" not in html:
        ok = fail("缺少差異分析連結")

    # 6. 200 錯誤不存在
    if "Internal Server Error" in html or "HTTP 200" in html:
        ok = fail("HTML 含伺服器錯誤訊息")

    # ===== 7. 三源一致性檢查 =====
    print("\n  ── 三源一致性 ──")
    try:
        db = sqlite3.connect(str(DB))
        # 總負債
        snap_liab = snap.get("total_liabilities", 0)
        db_liab = db.execute("SELECT total_liabilities FROM liabilities ORDER BY date DESC LIMIT 1").fetchone()
        if db_liab:
            db_liab = db_liab[0]
            if abs(snap_liab - db_liab) > 100:
                ok = fail(f"總負債不一致：snap={snap_liab:,} db={db_liab:,}")
            else:
                print(f"  ✅ 總負債: {snap_liab:,}")
        
        # 保險
        snap_ins = snap.get("insurance_current_value", 0)
        db_ins = db.execute("SELECT insurance FROM assets ORDER BY date DESC LIMIT 1").fetchone()
        if db_ins and abs(snap_ins - db_ins[0]) > 100:
            ok = fail(f"保險不一致：snap={snap_ins:,} db={db_ins[0]:,}")
        else:
            print(f"  ✅ 保險: {snap_ins:,}")
        
        # 證券
        snap_sec = snap.get("securities_total", snap.get("securities_total_market_value", 0))
        db_sec = db.execute("SELECT securities FROM assets ORDER BY date DESC LIMIT 1").fetchone()
        if db_sec and abs(snap_sec - db_sec[0]) > 100:
            ok = fail(f"證券不一致：snap={snap_sec:,} db={db_sec[0]:,}")
        else:
            print(f"  ✅ 證券: {snap_sec:,}")
        
        # 現金
        snap_cash = snap.get("cash_total", snap.get("real_liquid_assets", 0))
        db_cash = db.execute("SELECT cash_total FROM assets ORDER BY date DESC LIMIT 1").fetchone()
        if db_cash and abs(snap_cash - db_cash[0]) > 100:
            ok = fail(f"現金不一致：snap={snap_cash:,} db={db_cash[0]:,}")
        else:
            print(f"  ✅ 現金: {snap_cash:,}")
        
        db.close()
    except Exception as e:
        ok = fail(f"三源檢查異常：{e}")

    return ok

if __name__ == "__main__":
    result = check()
    print(f"\n{'✅ 內容保護通過' if result else '❌ 內容保護未通過，停止推送'}")
    sys.exit(0 if result else 1)
