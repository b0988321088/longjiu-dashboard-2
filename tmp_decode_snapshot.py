import re, base64, json
from pathlib import Path
p=Path('C:/Users/bot/Desktop/龍九系統/dashboard.py')
s=p.read_text(encoding='utf-8')
start=s.find('EMBEDDED_SNAPSHOT_B64 = ')
start2=s.find(' ', start+len('EMBEDDED_SNAPSHOT_B64 = '))
quote=s[start2]
i=start2+1
end=start2
while end < len(s):
    if s[end]==quote:
        # check escaped
        back=0
        j=end-1
        while j>=0 and s[j]=='\\':
            back+=1
            j-=1
        if back%2==0:
            break
    end+=1
b64=s[i:end]
# Remove spaces/newlines if any
b64=''.join(b64.split())
print('len', len(b64))
try:
    data=json.loads(base64.b64decode(b64+'==',altchars=None,validate=False).decode('utf-8'))
    print(json.dumps(data, ensure_ascii=False, indent=2)[:20000])
except Exception as e:
    # Maybe already exact base64 string, try direct decode
    try:
        data=json.loads(base64.b64decode(b64).decode('utf-8'))
        print(json.dumps(data, ensure_ascii=False, indent=2)[:20000])
    except Exception as e2:
        print('ERR',e,e2)
