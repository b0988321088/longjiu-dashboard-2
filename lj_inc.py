import sys, os
f = os.path.join(os.path.dirname(__file__), 'error_register.md')
if os.path.exists(f):
    print(open(f, encoding='utf-8').read())
else:
    print('無異常記錄')
