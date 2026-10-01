"""
dragon_assets.db 讀取／寫入層 — 單一真值來源：snapshot.json

2026-10-01 去硬編碼（使用者核准）：
原本 load_tv()／seed_from_snapshot() 內含多個寫死金額，與 snapshot 真值長期分歧 ——
  - working_surplus／retirement_surplus 以 162,781（舊月支出口徑）派生
  - allianz_ab 7,808,297／firstjin 1,979,676／monthly_dividend 69,044／real_estate 34,000,000…
現在所有衍生值與寫入值一律由 snapshot 派生；找不到鍵就寫 None 並列 WARN（不編造金額）。

註：本模組目前沒有 .py 呼叫點（全 repo grep 僅自身），保留 API 供未來使用。
"""
import json
import sqlite3
from pathlib import Path
from datetime import date

BASE = Path(__file__).parent
DB = BASE / "dragon_assets.db"
SNAP = BASE / "snapshot.json"


def _snap() -> dict:
    try:
        return json.loads(SNAP.read_text(encoding="utf-8"))
    except Exception as e:                      # 缺檔／壞檔時不編造數字
        print(f"[db_loader] ⚠️ snapshot 讀取失敗：{e}")
        return {}


def _deep(obj, key, _depth=0):
    """在巢狀結構內找同名鍵（snapshot 有深層同名鍵，如 mortgage_xz）。回傳首個命中值。"""
    if _depth > 8:
        return None
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            got = _deep(v, key, _depth + 1)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _deep(v, key, _depth + 1)
            if got is not None:
                return got
    return None


def _rent_split(snap: dict):
    """房租結構：大義街店面 = rent_1f，其餘（二三樓／洲際W／管理費）= rent_other。"""
    rb = snap.get("rent_breakdown") or {}
    if not rb:
        return None, None
    first = rb.get("大義街店面")
    other = sum(v for k, v in rb.items() if k != "大義街店面" and isinstance(v, (int, float)))
    return first, other


def load_tv(date_str: str = None) -> dict:
    """從 DB 載入指定日期真值；衍生欄位一律以 snapshot 為單一來源（缺值 None）。"""
    if date_str is None:
        date_str = str(date.today())
    db = sqlite3.connect(str(DB))
    db.row_factory = sqlite3.Row
    tv = {}
    for tbl in ("assets", "liabilities", "income"):
        row = db.execute(f"SELECT * FROM {tbl} WHERE date = ?", (date_str,)).fetchone()
        if row:
            for k in row.keys():
                tv[k] = row[k]
    db.close()

    s = _snap()
    pi = s.get("passive_income") or {}
    pen = (s.get("penetration") or {}).get("actual_twd") or {}
    _f, _o = _rent_split(s)

    tv["allianz_ab"] = s.get("allianz_ab_current_value") or s.get("allianz_ab")
    tv["firstjin"] = s.get("firstjin_current_value") or s.get("firstjin")
    if _f is not None:
        tv["rent_1f"] = _f
    if _o is not None:
        tv["rent_other"] = _o
    tv["rent_monthly"] = (tv.get("rent_1f") or 0) + (tv.get("rent_other") or 0)
    tv["monthly_dividend"] = pi.get("fund_dividend_conservative")   # 常態保守基本值（唯一常態口徑）
    tv["allianz_dividend"] = s.get("allianz_ab_monthly")            # 常態月配（保單 A+B）
    tv["firstjin_dividend"] = s.get("firstjin_monthly")             # 常態月配（第一金）
    if pen.get("債券") is not None and pen.get("現金/安全網") is not None:
        tv["bonds_cash"] = pen.get("債券") + pen.get("現金/安全網")
    tv["monthly_income"] = s.get("monthly_income") or tv.get("monthly_income")
    tv["monthly_expense"] = s.get("monthly_expense")
    _inc, _exp = tv.get("monthly_income"), tv.get("monthly_expense")
    tv["working_surplus"] = ((_inc - _exp) if (_inc is not None and _exp is not None)
                             else s.get("working_surplus"))
    tv["retirement_surplus"] = s.get("retirement_surplus")
    return tv


def seed_from_snapshot(snap_path: str = "snapshot.json") -> int:
    """從 snapshot.json 寫入一筆真值到 dragon_assets.db（缺鍵寫 None 並列 WARN）。"""
    s = json.loads(Path(snap_path).read_text(encoding="utf-8"))
    today = str(date.today())
    pen = (s.get("penetration") or {}).get("actual_twd") or {}
    _f, _o = _rent_split(s)
    cash = s.get("cash_total")
    _bonds, _safe = pen.get("債券"), pen.get("現金/安全網")
    bonds_cash = (_bonds + _safe) if (_bonds is not None and _safe is not None) else None
    bonds = max(0, bonds_cash - cash) if (bonds_cash is not None and cash is not None) else None

    assets_row = {
        "cash_total": cash,
        "bonds": bonds,
        "securities": s.get("securities_total_market_value"),
        "insurance": s.get("insurance_total"),
        "funds": s.get("fund_market_value"),
        "real_estate": s.get("real_estate_value") or s.get("real_estate"),
        "total_assets": s.get("total_assets"),
    }
    liab_row = {
        "mortgage_yy": _deep(s, "mortgage_yy"),
        "mortgage_yydu": _deep(s, "mortgage_yydu"),
        "mortgage_xz": _deep(s, "mortgage_xz"),
        "policy_loan": s.get("policy_pledge_loan"),
        "credit_card": s.get("credit_card"),
        "total_liabilities": s.get("total_liabilities"),
    }
    income_row = {
        "salary": s.get("salary") or s.get("monthly_salary"),
        "travel_allowance": s.get("travel_allowance"),
        "rent_1f": _f,
        "rent_other": _o,
        "interest": s.get("interest_income"),
        "dividend_total": (s.get("passive_income") or {}).get("fund_dividend_conservative"),
    }
    missing = [f"{t}.{k}"
               for t, r in (("assets", assets_row), ("liabilities", liab_row), ("income", income_row))
               for k, v in r.items() if v is None]
    if missing:
        print(f"[db_loader] ⚠️ snapshot 缺鍵（寫入 None，不用常數頂替）：{', '.join(missing)}")

    db = sqlite3.connect(str(DB))
    db.execute("""INSERT OR REPLACE INTO assets
        (date, cash_total, bonds, securities, insurance, funds, real_estate, total_assets)
        VALUES (?,?,?,?,?,?,?,?)""",
               (today, assets_row["cash_total"], assets_row["bonds"], assets_row["securities"],
                assets_row["insurance"], assets_row["funds"], assets_row["real_estate"],
                assets_row["total_assets"]))
    db.execute("""INSERT OR REPLACE INTO liabilities
        (date, mortgage_yy, mortgage_yydu, mortgage_xz, policy_loan, credit_card, total_liabilities)
        VALUES (?,?,?,?,?,?,?)""",
               (today, liab_row["mortgage_yy"], liab_row["mortgage_yydu"], liab_row["mortgage_xz"],
                liab_row["policy_loan"], liab_row["credit_card"], liab_row["total_liabilities"]))
    db.execute("""INSERT OR REPLACE INTO income
        (date, salary, travel_allowance, rent_1f, rent_other, interest, dividend_total)
        VALUES (?,?,?,?,?,?,?)""",
               (today, income_row["salary"], income_row["travel_allowance"], income_row["rent_1f"],
                income_row["rent_other"], income_row["interest"], income_row["dividend_total"]))
    db.commit()
    db.close()
    return today


if __name__ == "__main__":
    tv = load_tv()
    for k, v in sorted(tv.items()):
        if isinstance(v, (int, float)) and abs(v) > 1000:
            print(f"  {k}: {v:,}")
        else:
            print(f"  {k}: {v}")
