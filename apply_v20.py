import json, re, sys

text = open("run_daily.py", encoding="utf-8").read()

# Read the v20 template
template = open("template_v20.html", encoding="utf-8").read()

# Escape f-string braces
template = template.replace("{", "{{").replace("}", "}}")
# Restore the f-string variables
vars_to_keep = [
    "TODAY", "total_assets:,", "total_liabilities:,", "net_worth:,",
    "passive_income:,", "insurance_total:,", "monthly_dividend:,",
    "allianz_dividend:", "firstjin_dividend:", "tv.get",
    "tw_pct:.1f", "tw_gap:+.1f", "tw_bar",
    "us_pct:.1f", "us_gap:+.1f", "us_bar",
    "def_pct:.1f", "def_gap:+.1f", "def_bar",
    "bond_cash_pct:.1f", "bond_cash_bar",
    "tw_change_text", "market_intel_text",
]
for v in vars_to_keep:
    template = template.replace("{{" + v + "}}", "{" + v + "}")
    template = template.replace("{{" + v + ":,}}", "{" + v + "}")
    template = template.replace("{{" + v + ":,}}", "{" + v + "}")

# Replace the old template section
start = 'html = f"""<!DOCTYPE html>'
end = '"""\n    return html'
s_idx = text.index(start)
e_idx = text.index(end, s_idx)

new_html = f'html = f"""{template}"""\n    return html'

text = text[:s_idx] + new_html + text[e_idx + len(end):]

open("run_daily.py", "w", encoding="utf-8").write(text)
print("done")
