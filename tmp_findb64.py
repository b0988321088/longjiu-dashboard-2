import re, json
from pathlib import Path
s=Path('C:/Users/bot/Desktop/龍九系統/dashboard.py').read_text(encoding='utf-8')
m=re.search(r'^EMBEDDED_SNAPSHOT_B64 = (["\'])(.+?)\1', s, re.S)
print(bool(m))
if m:
    print(m.group(1))
    print('len', len(m.group(2)))
    inner=m.group(2)
    # print first 200 chars
    print(inner[:200])
    # print next 200
    print(inner[200:400])
    print(inner[400:600])
    print(inner[600:800])
    print(inner[800:1000])
    print('last50', inner[-50:])
else:
    print('not found')
