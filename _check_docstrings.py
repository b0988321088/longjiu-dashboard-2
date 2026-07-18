import re
from pathlib import Path

text = Path('run_daily.py').read_text(encoding='utf-8')
lines = text.splitlines()

# Count all docstring patterns
count = 0
for i, line in enumerate(lines, 1):
    stripped = line.strip()
    if stripped.startswith('"""') and stripped.endswith('"""') and stripped != '"""':
        count += 1
    elif stripped == '"""':
        count += 1
        
print(f'Total docstring markers: {count}')

# Show all docstrings with context
for i, line in enumerate(lines, 1):
    if '"""' in line:
        print(f'{i}: {line.strip()[:100]}')
