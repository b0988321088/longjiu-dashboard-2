"""
Cron 健康狀態儀表板
每日產出 cron 運作摘要
"""
import subprocess, json, re
from datetime import datetime

def check():
    output = subprocess.run(["hermes", "cron", "list"], capture_output=True, text=True, timeout=15)
    lines = output.stdout.splitlines()
    
    total = 0
    ok = 0
    warn = 0
    err = 0
    skipped = 0
    names = []
    errors = []
    
    for i, line in enumerate(lines):
        if 'Name:' in line:
            total += 1
            name = line.split('Name:')[1].strip()
            names.append(name)
        if 'last_status:' in line:
            s = line.split('last_status:')[1].strip()
            if s == 'ok':
                ok += 1
            elif s == 'error':
                err += 1
                # 找上方的 name
                for j in range(i-5, i):
                    if j >= 0 and 'Name:' in lines[j]:
                        err_name = lines[j].split('Name:')[1].strip()
                        errors.append(err_name)
                        break
            elif s == 'skipped' or 'model drift' in line:
                skipped += 1
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    summary = f"📊 Cron 健康狀態 @ {now}\n"
    summary += f"✅ 正常: {ok} | ⚠️ 錯誤: {err} | ⏸️ 跳過: {skipped} | 總計: {total}\n"
    
    if errors:
        summary += "\n❌ 異常 cron:\n"
        for e in errors:
            summary += f"  • {e}\n"
    
    return summary

