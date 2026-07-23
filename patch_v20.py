import json

text = open("run_daily.py", encoding="utf-8").read()

# Read v20 template
tpl = open("template_v20.html", encoding="utf-8").read()

# Escape { for f-string
import re

# Define vars to preserve as f-string placeholders
keep_vars = {
    "TODAY", "total_assets:,", "total_liabilities:,", "net_worth:,",
    "passive_income:,", "insurance_total:,", "monthly_dividend:,",
    "allianz_dividend:", "firstjin_dividend:",
    "tw_pct:.1f", "tw_gap:+.1f", "tw_bar",
    "us_pct:.1f", "us_gap:+.1f", "us_bar",
    "def_pct:.1f", "def_gap:+.1f", "def_bar",
    "bond_cash_pct:.1f", "bond_cash_bar",
    "tw_change_text", "market_intel_text",
}

# Build regex to find all {var} patterns
def protect_fstring(m):
    full = m.group(0)
    inner = m.group(1)
    if inner in keep_vars:
        return full  # Keep as f-string
    # Escape the braces
    return "{{" + inner + "}}"

tpl = re.sub(r'\{([^}]+)\}', protect_fstring, tpl)

# Replace template in run_daily.py
start = 'html = f"""<!DOCTYPE html>'
end = '"""\n    return html'

s_idx = text.index(start)
e_idx = text.index(end, s_idx)

new_html = f"html = f'''{tpl}'''\n    return html"
text = text[:s_idx] + new_html + text[e_idx:]

# Update render function to include penetration vars
old_assign = """    allianz = tv["allianz_ab"] or 7_881_584
    firstjin = tv["firstjin"] or 1_994_698
    insurance_total = tv["insurance_total"] or allianz + firstjin
    monthly_dividend = tv.get("monthly_dividend", 107_116)
    allianz_dividend = tv.get("allianz_dividend", 73_167)
    firstjin_dividend = tv.get("firstjin_dividend", 22_949)"""

new_assign = """    allianz = tv["allianz_ab"] or 7_881_584
    firstjin = tv["firstjin"] or 1_994_698
    insurance_total = tv["insurance_total"] or allianz + firstjin
    monthly_dividend = tv.get("monthly_dividend", 107_116)
    allianz_dividend = tv.get("allianz_dividend", 73_167)
    firstjin_dividend = tv.get("firstjin_dividend", 22_949)
    
    total_assets = tv.get("total_assets", 0) or 0
    total_liabilities = tv.get("total_liabilities", 0) or 0
    net_worth = tv.get("net_worth", 0) or max(total_assets - total_liabilities, 0)
    passive_income = (tv.get("rent_monthly", 80100) or 80100) + monthly_dividend
    
    tw_pct = 14.0; tw_gap = -21.0; tw_bar = 40
    us_pct = 35.3; us_gap = 5.3; us_bar = 100
    def_pct = 10.2; def_gap = -14.8; def_bar = 41
    bond_cash_pct = 40.5; bond_cash_bar = 100"""

text = text.replace(old_assign, new_assign)

open("run_daily.py", "w", encoding="utf-8").write(text)
print("done")
