"""
lj_test.py — longjiu_system自我測試
python lj.py test
"""
import sys, os, importlib

BASE = os.path.dirname(os.path.abspath(__file__))
FAIL = 0
PASS = 0

def test(name, fn):
    global PASS, FAIL
    try:
        fn()
        print(f'  ✅ {name}')
        PASS += 1
    except Exception as e:
        print(f'  ❌ {name}: {e}')
        FAIL += 1

def can_import(mod):
    importlib.import_module(mod)

def file_exists(f):
    full = os.path.join(BASE, f)
    assert os.path.exists(full), f'{f} 不存在'

def main():
    print('🔍 longjiu_system測試')
    print()
    
    print('📦 核心腳本可匯入：')
    for mod in ['slide_engine', 'notion_backup', 'allocation_alert', 'preflight_check', 'safe_update']:
        test(mod, lambda m=mod: can_import(m))
    
    print()
    print('📁 必要檔案存在：')
    for f in ['snapshot.json', 'content.json', '龍九簡報模板.pptx', 'four_source_sync.py', 'lj.py']:
        test(f, lambda fn=f: file_exists(fn))
    
    print()
    print('🔗 GitHub Pages 可連線：')
    try:
        import urllib.request
        r = urllib.request.urlopen('https://b0988321088.github.io/longjiu-dashboard-2/', timeout=5)
        test(f'儀表板 ({r.status})', lambda: None)
    except:
        test('儀表板連線', lambda: (_ for _ in ()).throw(Exception('無法連線')))
    
    print()
    print(f'{"="*30}')
    print(f'✅ {PASS} 通過  ❌ {FAIL} 失敗')
    return 0 if FAIL == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
