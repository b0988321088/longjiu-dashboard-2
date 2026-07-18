from pathlib import Path

lines = Path('run_daily.py').read_text(encoding='utf-8').splitlines()

# Find insert point: right after "    return html" and before "    # ====="
insert_idx = None
for i, l in enumerate(lines):
    if l.rstrip() == '    return html' and i+1 < len(lines) and lines[i+1].strip().startswith('# ===='):
        insert_idx = i + 1
        break

if insert_idx is None:
    print('ERROR: insert point not found')
    exit(1)

print(f'inserting at line {insert_idx+1}')

fn_text = Path('render_daily_report_fn.py').read_text(encoding='utf-8')
fn_lines = fn_text.splitlines()

new_lines = lines[:insert_idx] + fn_lines + ['', ''] + lines[insert_idx:]
Path('run_daily.py').write_text('\n'.join(new_lines), encoding='utf-8')
print(f'inserted {len(fn_lines)} lines, total now {len(new_lines)}')
