"""
dragon_assets.db 單一真值來源 — 取代散落多處的 calibrate_sources()
"""
import sqlite3
from pathlib import Path
from datetime import date

DB = Path(__file__).parent / "dragon_assets.db"

def load_tv(date_str: str = None) -> dict:
    """從 DB 載入指定日期的真值，回傳與 render_daily_report 相容的 flat dict."""
    if date_str is None:
        date_str = str(date.today())
    db = sqlite3.connect(str(DB))
    db.row_factory = sqlite3.Row
    tv = {}
    for tbl in ['assets', 'liabilities', 'income']:
        row = db.execute(f"SELECT * FROM {tbl} WHERE date = ?", (date_str,)).fetchone()
        if row:
            for k in row.keys():
                tv[k] = row[k]
    db.close()
    # 衍生欄位
    tv['allianz_ab'] = 7_808_297
    tv['firstjin'] = 1_979_676
    tv['rent_monthly'] = tv.get('rent_1f', 0) + tv.get('rent_other', 0)
    tv['monthly_dividend'] = 69_044
    tv['allianz_dividend'] = 55_451
    tv['firstjin_dividend'] = 13_593
    tv['bonds_cash'] = tv.get('bonds', 5_843_211) + tv.get('cash_total', 3_884_620)
    tv['monthly_income'] = (
        tv.get('salary', 0) + tv.get('travel_allowance', 0)
        + tv.get('rent_1f', 0) + tv.get('rent_other', 0)
        + tv.get('dividend_total', 0) + tv.get('interest', 0)
    )
    tv['working_surplus'] = tv.get('monthly_income', 218_102) - 141_958
    tv['retirement_surplus'] = (
        tv.get('dividend_total', 69_044) + tv.get('rent_1f', 0) + tv.get('rent_other', 0)
        - 141_958
    )
    return tv

def seed_from_snapshot(snap_path: str = "snapshot.json") -> int:
    """從 snapshot.json 寫入一筆到 dragon_assets.db，回傳 date。"""
    import json
    snap = json.loads(Path(snap_path).read_text(encoding='utf-8'))
    today = str(date.today())
    pen = snap.get('penetration', {}).get('actual_twd', {})
    cash = snap.get('cash', 3_853_985)
    bonds_cash = pen.get('債券及安全現金', 9_697_196)
    bonds = max(0, bonds_cash - cash)

    db = sqlite3.connect(str(DB))
    db.execute('''INSERT OR REPLACE INTO assets
        (date, cash_total, bonds, securities, insurance, funds, real_estate, total_assets)
        VALUES (?,?,?,?,?,?,?,?)''',
        (today, cash, bonds, pen.get('證券市值',2_205_230),
         snap.get('insurance_total',11_791_280), pen.get('基金市值',783_700),
         34_000_000, snap.get('total_assets',50_689_930)))

    liab = snap.get('liabilities', {})
    db.execute('''INSERT OR REPLACE INTO liabilities
        (date, mortgage_yy, mortgage_yydu, mortgage_xz, policy_loan, credit_card, total_liabilities)
        VALUES (?,?,?,?,?,?,?)''',
        (today, liab.get('mortgage_yy',2_792_470), liab.get('mortgage_yydu',4_607_578),
         liab.get('mortgage_xz',5_759_374), liab.get('policy_loan',4_000_000),
         liab.get('credit_card',39_865), snap.get('total_liabilities',17_199_287)))

    db.execute('''INSERT OR REPLACE INTO income
        (date, salary, travel_allowance, rent_1f, rent_other, interest, dividend_total)
        VALUES (?,?,?,?,?,?,?)''',
        (today, 43_144, 12_000, 24_000, 56_100, liab.get('interest',0), 69_044))
    db.commit()
    db.close()
    return today


if __name__ == "__main__":
    tv = load_tv()
    for k, v in sorted(tv.items()):
        if isinstance(v, int) and v > 1000:
            print(f"  {k}: {v:,}")
        else:
            print(f"  {k}: {v}")
