import ast
from pathlib import Path

src = Path('run_daily.py').read_text(encoding='utf-8')
try:
    ast.parse(src)
    print('AST OK')
except SyntaxError as e:
    print(f'SyntaxError at line {e.lineno}: {e.msg}')
    print(f'text: {e.text}')
    # Show lines around the error
    lines = src.splitlines()
    start = max(0, e.lineno-10)
    end = min(len(lines), e.lineno+5)
    for i in range(start, end):
        marker = '>>>' if i+1 == e.lineno else '   '
        print(f'{marker} {i+1}: {lines[i][:120]}')
