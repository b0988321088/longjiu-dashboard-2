"""
龍九控股 Dashboard Review Gate
每次上傳儀表板前必須通過此檢查，否則中斷推送。
"""
import json
import sys
from pathlib import Path

SNAP_GLOB = "framework_snapshot_*.json"
MIN_RUNWAY = 1.0
MAX_DEBT_RATIO = 100.0
MIN_INSURANCE_VALUE = 1_000_000
MIN_MONTHLY_DIVIDEND = 1_000

REQUIRED_PAGE_KEYS = {
    "page1_wealth_baseline": [
        "runway_months", "debt_ratio_pct", "work_surplus", "retire_surplus",
        "monthly_income", "monthly_expense",
    ],
    "page2_strategic_risk": ["red_zone"],
    "page3_insurance_relay": ["yield_performance", "policies", "relay_progress"],
    "page4_liquidity_banking": ["accounts"],
    "page5_tactical_ops": [],
}

ERRORS = []
WARNINGS = []


def fail(msg: str):
    ERRORS.append(msg)


def warn(msg: str):
    WARNINGS.append(msg)


def check_page1(p1: dict):
    runway = p1.get("runway_months")
    if runway is None:
        fail("[Page1] runway_months 缺失")
    elif runway < MIN_RUNWAY:
        fail(f"[Page1] Runway {runway} 個月 < {MIN_RUNWAY}，流動性不足")

    debt = p1.get("debt_ratio_pct")
    if debt is None:
        fail("[Page1] debt_ratio_pct 缺失")
    elif debt > MAX_DEBT_RATIO:
        fail(f"[Page1] 負債比 {debt}% > {MAX_DEBT_RATIO}%，警戒")

    for key in ["work_surplus", "retire_surplus", "monthly_income", "monthly_expense"]:
        if p1.get(key) is None:
            warn(f"[Page1] {key} 為 None")

    acf = p1.get("actual_cash_flow", {})
    if not acf.get("income") and not acf.get("expense"):
        warn("[Page1] actual_cash_flow 無收入/支出明細")


def check_page3(p3: dict):
    yp = p3.get("yield_performance") or {}
    policies = p3.get("policies", []) or []

    pol_count = sum(1 for p in policies if isinstance(p, dict))
    if pol_count == 0:
        warn("[Page3] policies 為空")

    total_val = yp.get("total_current_value")
    if total_val is None and policies:
        total_val = sum(p.get("value", 0) for p in policies if isinstance(p, dict))

    if total_val is None or total_val == 0:
        fail(f"[Page3] 保單現值 = {total_val}，應 > {MIN_INSURANCE_VALUE}")
    elif total_val < MIN_INSURANCE_VALUE:
        warn(f"[Page3] 保單現值 {total_val:,.0f} 異常偏低")

    monthly_div = p3.get("monthly_dividend", yp.get("monthly_yield_twd", 0))
    if monthly_div is None or monthly_div == 0:
        fail(f"[Page3] 本月配息 = {monthly_div}，應 > {MIN_MONTHLY_DIVIDEND}")
    elif monthly_div < MIN_MONTHLY_DIVIDEND:
        warn(f"[Page3] 本月配息 {monthly_div:,.0f} 偏低")

    for relay in p3.get("relay_progress", []):
        if not isinstance(relay, dict):
            continue
        if not relay.get("station") or not relay.get("date"):
            warn(f"[Page3] relay_progress 缺欄位：{relay}")


def check_page2(p2: dict):
    if not p2.get("red_zone"):
        warn("[Page2] red_zone 為空，今日無異常個股")


def check_page4(p4: dict):
    accounts = p4.get("accounts", []) or []
    if not accounts:
        warn("[Page4] accounts 為空")


def check_page5(p5: dict):
    if not p5.get("p0_tasks"):
        warn("[Page5] p0_tasks 為空")
    if not p5.get("lifestyle"):
        warn("[Page5] lifestyle 為空")


def main():
    cwd = Path(__file__).parent
    snapshots = sorted(cwd.glob(SNAP_GLOB), reverse=True)
    if not snapshots:
        fail("找不到 framework_snapshot_*.json")
        _report()
        return 1

    snap_path = snapshots[0]
    try:
        data = json.loads(snap_path.read_text(encoding="utf-8"))
    except Exception as e:
        fail(f"snapshot JSON 解析失敗：{e}")
        _report()
        return 1

    snap = data.get("snapshot", data)
    pages = snap.get("pages", {})

    # 結構完整性
    for page_name, keys in REQUIRED_PAGE_KEYS.items():
        if page_name not in pages:
            fail(f"[{page_name}] 頁面完全缺失")
            continue
        page_data = pages[page_name]
        if not isinstance(page_data, dict):
            fail(f"[{page_name}] 型態錯誤（應為 dict）")
            continue
        for key in keys:
            if key not in page_data:
                fail(f"[{page_name}] 必要 key 缺失：{key}")

    # 頁面內容檢查
    check_page1(pages.get("page1_wealth_baseline", {}))
    check_page2(pages.get("page2_strategic_risk", {}))
    check_page3(pages.get("page3_insurance_relay", {}))
    check_page4(pages.get("page4_liquidity_banking", {}))
    check_page5(pages.get("page5_tactical_ops", {}))

    # generated_at
    gen = snap.get("generated_at", "N/A")
    print(f"📋 Review Gate 檢查：{snap_path.name}")
    print(f"   資料時間：{gen}")
    print(f"   檢查項目：{sum(len(v) for v in REQUIRED_PAGE_KEYS.values())} 個必要 key")
    _report()

    if ERRORS:
        return 1
    return 0


def _report():
    if ERRORS:
        print("\n❌ 審查失敗（下列問題必須修復）：")
        for e in ERRORS:
            print(f"   • {e}")
    if WARNINGS:
        print("\n⚠️  警告（建議修復）：")
        for w in WARNINGS:
            print(f"   • {w}")
    if not ERRORS and not WARNINGS:
        print("\n✅ 審查通過，可推送儀表板")
    elif not ERRORS:
        print("\n✅ 審查通過（有警告，建議修正後再推送）")


if __name__ == "__main__":
    sys.exit(main())
