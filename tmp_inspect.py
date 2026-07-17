from pathlib import Path
s=Path('C:/Users/bot/Desktop/龍九系統/dashboard.py').read_text(encoding='utf-8')
r=s.find('EMBEDDED_SNAPSHOT_B64')
print('AFTER:', s[r-30:r+70])
