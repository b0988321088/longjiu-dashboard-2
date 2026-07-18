import re
from pathlib import Path

text = Path('run_daily.py').read_text(encoding='utf-8')
starts = [(m.start(), m.group()) for m in re.finditer(r'f"""', text)]
print('f-string triple starts:', len(starts))
for pos, _ in starts:
    c = text.find('"""', pos+4)
    status = 'UNCLOSED' if c == -1 else f'closed at {c}'
    print(f'  open at {pos}: {status}')
