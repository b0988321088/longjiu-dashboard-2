import sqlite3, json

conn = sqlite3.connect('dragon_assets.db')
c = conn.cursor()

# 原始保單值（asset_diff_原本的數據）
orig_insurance = {
    '2026-07-19': 11611072 - 1977799,  # 我加過FL65，減回去
    '2026-07-20': 11611072 - 1977799,
    '2026-07-21': 9633273,
    '2026-07-23': 9766626,
    '2026-07-24': 9802872,
    '2026-07-25': 9802872,
    '2026-07-26': 9802872,
    '2026-07-27': 9802872,
    '2026-07-28': 7765339 + 1977799,  # A+B新值 + FL65
}

for date, ins in orig_insurance.items():
    row = c.execute('SELECT cash_total, securities, funds FROM assets WHERE date=?', (date,)).fetchone()
    if row:
        total = (row[0] or 0) + (row[1] or 0) + ins + (row[2] or 0)
        c.execute('UPDATE assets SET insurance=?, total_assets=? WHERE date=?', (ins, total, date))
        print(f'{date}: 保單{ins:,}  總資產{total:,}')

conn.commit()
conn.close()
