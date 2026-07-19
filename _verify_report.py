#!/usr/bin/env python3
"""Verify daily report state and fix market intel injection."""
from pathlib import Path

BASE = Path(__file__).parent.resolve()
REPORT = BASE / 'daily_report_v2_2026-07-20.html'
SNAP = BASE / 'snapshot.json'

# Check report sections
html = REPORT.read_text(encoding='utf-8')
print('Has title:', '龍九控股日報' in html and '2026-07-20' in html)
print('Has Asset Penetration:', '資產結構 Asset Penetration' in html or '資產穿透' in html)
print('Has 2/5 card:', '<h2>2/5' in html)
print('Has market intel:', '市場動態' in html or 'Hunter' in html or '情報' in html)
print('Report size:', len(html))

# Read intel files
intel_dir = BASE / 'hunter_logs'
intel_files = sorted(intel_dir.glob('intel_20260720*.txt'))
print(f'Intel files today: {len(intel_files)}')
for f in intel_files:
    print(f'  {f.name}: {len(f.read_text(encoding="utf-8"))} bytes')

# Check snapshot for income fields
import json
snap = json.loads(SNAP.read_text(encoding='utf-8'))
print('Passive income block:', snap.get('passive_income'))
print('Rent actual:', snap.get('rent_monthly_actual'))
print('Monthly dividend:', snap.get('monthly_dividend'))
