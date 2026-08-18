"""
lj.py — longjiu_system CLI 入口
用法：
  python lj.py sync      # 四源同步 (safe_update.py + four_source_sync.py)
  python lj.py report    # 產出日報 (regenerate_report.py)
  python lj.py slide     # 產出簡報 (slide_engine.py)
  python lj.py alert     # 配置偏離檢查 (allocation_alert.py)
  python lj.py check     # 系統健康檢查 (preflight_check.py)
  python lj.py fix KEY=VALUE  # 快速修正單一欄位 (safe_update.py)
"""
import sys, os

BASE = os.path.dirname(os.path.abspath(__file__))

CMDS = {
    'sync':   f'python {BASE}/safe_update.py --plan && echo "先用 --plan 查看變更，再跑 python lj.py sync --apply"',
    'sync!':  f'python {BASE}/four_source_sync.py && python {BASE}/notion_backup.py asset && python {BASE}/notion_backup.py report',
    'report': f'python {BASE}/regenerate_report.py --deploy && python {BASE}/notion_backup.py report && python {BASE}/notion_backup.py asset',
    'slide':  f'python {BASE}/slide_engine.py {BASE}/content.json; python {BASE}/notion_backup.py snap 簡報 "簡報已產出: content.json"',
    'video':  f'python {BASE}/../video_studio/pipeline.py; python {BASE}/notion_backup.py snap 影片 "影片已產出"',
    'mail':   f'python {BASE}/gmail_cleanup.py; python {BASE}/notion_backup.py snap 信箱 "Gmail清理完成"',
    'cal':    f'python {BASE}/calendar_sync.py; python {BASE}/notion_backup.py snap 行事曆 "行事曆同步完成"',
    'emergency': f'echo "📡 美股緊急應變: python {BASE}/daily_intel.py + python {BASE}/emergency_1330.py"; python {BASE}/notion_backup.py snap 緊急 "緊急應變分析完成"',
    'hunter': f'echo "🔍 Hunter情報收集: 執行 daily_intel.py"; python {BASE}/notion_backup.py snap 情報 "Hunter情報收集完成"',
    'morning': f'python {BASE}/morning_briefing.py; python {BASE}/notion_backup.py snap 晨報 "晨間簡報完成"',
    'weekly': f'python {BASE}/weekly_report.py; python {BASE}/notion_backup.py snap 週報 "週報完成"',
    'cashflow': f'python {BASE}/cashflow_analysis.py; python {BASE}/notion_backup.py snap 現金流 "現金流分析完成"',
    'fire': f'python {BASE}/fire_progress.py; python {BASE}/notion_backup.py snap FIRE "FIRE進度更新"',
    'backup': f'python {BASE}/notion_backup.py snap',
    'alert':  f'python {BASE}/allocation_alert.py; python {BASE}/notion_backup.py snap 配置 "配置偏離偵測完成"',
    'check':  f'python {BASE}/preflight_check.py; python {BASE}/notion_backup.py snap 檢查 "系統檢查完成"',
    'status': f'python {BASE}/preflight_check.py && echo "---" && python {BASE}/allocation_alert.py 2>&1 | grep -v Simulation; python {BASE}/notion_backup.py snap 狀態 "系統狀態總覽完成"',
    'test':   f'python {BASE}/lj_test.py',
    'mb':     f'python {BASE}/mb_extract.py',
    'inc':    f'python {BASE}/lj_inc.py',
}

def fix_cmd(args):
    """lj.py fix key=value key=value ..."""
    pairs = [a for a in args if '=' in a]
    if not pairs:
        print('用法：python lj.py fix key1=value1 key2=value2')
        return
    cmd = f'python {BASE}/safe_update.py --plan ' + ' '.join(pairs)
    os.system(cmd)

def main():
    if len(sys.argv) < 2:
        print('longjiu_system CLI 入口')
        print()
        for k, v in CMDS.items():
            print(f'  python lj.py {k:12s}  →  {v.split("#")[-1].strip()}')
        print(f'  python lj.py fix ...  →  快速修正欄位')
        print()
        print('範例：')
        print('  python lj.py check')
        print('  python lj.py fix allianz_combined=7765339')
        return

    cmd = sys.argv[1]
    if cmd in ('--help', '-h') or cmd == '':
        os.system(f'python {sys.argv[0]}')
        return
    if cmd in CMDS:
        if cmd == 'backup' and len(sys.argv) > 2:
            # backup 支援動態參數
            args = ' '.join(f'"{a}"' for a in sys.argv[2:])
            os.system(f'python {BASE}/notion_backup.py snap {args}')
        else:
            os.system(CMDS[cmd])
    elif cmd == 'fix':
        fix_cmd(sys.argv[2:])
    else:
        print(f'未知指令：{cmd}')
        print('可用指令：sync, sync!, report, slide, alert, check, fix')

if __name__ == '__main__':
    main()
