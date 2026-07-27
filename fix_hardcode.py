"""取代 run_daily.py 中的硬編碼"""
code = open("C:/Users/bot/Desktop/longjiu_system/run_daily.py").read()

# 動態 DBS note
dbs_note_def = '''    # 動態 DBS note
    _dbs_cash = tv.get("cash", 0)
    if _dbs_cash > 30000:
        _dbs_status = "\\u9918\\u88d5\\u5145\\u8db3 \\u2705"
    else:
        _dbs_status = "\\u26a0\\ufe0f \\u9700\\u88dc\\u8cc7\\u91d1"
    _dbs_note_str = f"\\u4e00\\u822c\\u623f\\u8cb8\\u5df2\\u6e05\\u511f \\u2705 \\u661f\\u5c55\\u9918\\u984d {_dbs_cash:,}\\uff0c\\u6263\\u7406\\u8ca1\\u578b\\u5229\\u606f ~10,000\\uff0c{_dbs_status}"
'''

code = code.replace(
    '# template \\u6b98\\u7559\\u786c\\u7de8\\u78bc\\u6ce8\\u5165',
    dbs_note_def + '    # template \\u6b98\\u7559\\u786c\\u7de8\\u78bc\\u6ce8\\u5165'
)

# 動態取代
replacements = [
    ('html.replace("__CATHAT_SETTLEMENT__", "4,893,529")', 'html.replace("__CATHAT_SETTLEMENT__", f"{tv.get("mortgage_yy",0):,.0f}")'),
    ('html.replace("__CATHAY_DEPOSIT__", "5,300,000")', 'html.replace("__CATHAY_DEPOSIT__", f"{tv.get("mortgage_yydu",0):,.0f}")'),
    ('html.replace("__DBS_BALANCE__", "17,000")', 'html.replace("__DBS_BALANCE__", f"{tv.get("cash",0):,.0f}")'),
    ('html.replace("__SINOPAC_BALANCE__", "230,000")', 'html.replace("__SINOPAC_BALANCE__", f"{tv.get("cash",0):,.0f}")'),
    ('html.replace("__SINOPAC_MORTGAGE__", "65,734")', 'html.replace("__SINOPAC_MORTGAGE__", f"{tv.get("mortgage_monthly_total",0):,.0f}")'),
    ('html.replace("__RESERVE_POOL__", "2,000,000+")', 'html.replace("__RESERVE_POOL__", f"{tv.get("financial_mortgage",0):,.0f}+")'),
    ('html.replace("__SALARY__", "82,265")', 'html.replace("__SALARY__", f"{tv.get("salary",43144):,.0f}")'),
]
for old, new in replacements:
    code = code.replace(old, new)

# DBS note 取代
code = code.replace(
    '"{_dbs_note}", "\\u4e00\\u822c\\u623f\\u8cb8\\u5df2\\u6e05\\u511f \\u2705 \\u50c5\\u6263\\u7406\\u8ca1\\u578b\\u5229\\u606f ~10,000\\uff0c\\u9918\\u88d5\\u5145\\u8db3"',
    '"{_dbs_note}", _dbs_note_str'
)

open("C:/Users/bot/Desktop/longjiu_system/run_daily.py", "w").write(code)
print("\\u2705 \\u5168\\u90e8\\u786c\\u7de8\\u78bc\\u5df2\\u52d5\\u614b\\u5316")
