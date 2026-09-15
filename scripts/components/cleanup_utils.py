#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cleanup_utils.py — 專案深度清理與日誌歸檔工具 (從 _cleanup_past_0915.py 升級)

此模組提供以下清理功能：
1. 歸檔 work_log.json 的舊條目。
2. 歸檔 error_register.md 的舊 INC 報告。
3. 保留備份檔每類最新 N 個。
4. 刪除過時日期文件。
5. 刪除淘汰的產線腳本與一次性 ad-hoc 腳本。
6. 智能清理 .archive 目錄中過期的歸檔檔案。
7. 識別並刪除未被引用的 .py 檔案（待實作）。
8. 清理其他臨時/快取檔案（待實作）。
"""
import json
import sys
import pathlib
import re
import shutil
import datetime
from datetime import date, datetime, timedelta
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.resolve()))
from logging_config import get_logger

logger = get_logger("cleanup_utils")

ROOT = pathlib.Path(__file__).parent.parent.parent.resolve() # 假設 scripts/components 在龍九系統根目錄下
ARCHIVE_DIR = ROOT / '.archive'

def _ensure_archive_dir():
    ARCHIVE_DIR.mkdir(exist_ok=True)

def _arch_write_json(name, obj):
    _ensure_archive_dir()
    (ARCHIVE_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding='utf-8')

def _arch_write_text(name, content):
    _ensure_archive_dir()
    (ARCHIVE_DIR / name).write_text(content, encoding='utf-8', newline='\n')

def load_json(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"{filepath} not found.")
        return []
    except json.JSONDecodeError:
        logger.error(f"Failed to decode JSON from {filepath}. Skipping.")
        return []

def save_json(filepath, data, indent=1):
    with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)

def load_text(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"{filepath} not found.")
        return ""

def save_text(filepath, content):
    with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)

# --- 清理功能 A-F (從 _cleanup_past_0915.py 搬移與重構) ---

def _cleanup_schedule_events(apply_changes: bool, current_date_iso: str):
    logger.info("執行 A. 清理 schedule_events.json...")
    p = ROOT / 'schedule_events.json'
    ev = load_json(p)
    
    if not ev:
        logger.info("schedule_events.json 為空或無法讀取，跳過清理。")
        return 0, 0

    # 移除早於 2026-08-01 的過期事件
    keep = [e for e in ev if str(e.get('date', ''))[:10] >= '2026-08-01']
    gone = [e for e in ev if str(e.get('date', ''))[:10] < '2026-08-01']
    
    if gone:
        logger.info(f'A. schedule_events: {len(ev)} → {len(keep)}（移除 {len(gone)} 筆 7 月過期事件）')
        for e in gone:
            logger.debug(f'    - {e.get("date")} {str(e.get("item"))[:52]}')
        if apply_changes:
            _arch_write_json('removed_schedule_events_2026h1.json', gone)
            save_json(p, keep, indent=2) # schedule_events.json 縮排為 2
            logger.info("schedule_events.json 已更新並歸檔舊條目。")
        return len(gone), len(keep)
    else:
        logger.info("沒有 schedule_events 舊條目需要清理。")
        return 0, len(ev)

def _cleanup_pending_decisions(apply_changes: bool, current_date_iso: str):
    logger.info("執行 B. 清理 pending_decisions.json / dashboard_decisions.json...")
    CLOSED = re.compile(r'^\s*(✅|❌|⛔|🔚)|已結案|已完成|已取消|已作廢|作廢|已送出|已核准|已生效|維持不轉換|已延後|已暫緩|已更正')
    cleaned_count = 0
    retained_count = 0

    for f, key in (('pending_decisions.json', None), ('dashboard_decisions.json', 'pending_decisions')):
        pp = ROOT / f
        d = load_json(pp)
        if not d and d != []: # 考慮空列表情況
            logger.info(f"{f} 為空或無法讀取，跳過清理。")
            continue

        arr = d if key is None else d[key]
        keep2, gone2 = [], []
        for it in arr:
            st = str(it.get('status', ''))
            dt = str(it.get('date', ''))[:10]
            # 移除「已結案/已完成/已取消/作廢」且日期早於 2026-09-01 的條目
            if CLOSED.search(st) and dt < '2026-09-01':
                gone2.append(it)
            else:
                keep2.append(it)

        if gone2:
            logger.info(f'B. {f}{"[" + key + "]" if key else ""}: {len(arr)} → {len(keep2)}（移除 {len(gone2)} 筆已結案且 9/1 前）')
            for it in gone2:
                logger.debug(f'    - {it.get("date")} {str(it.get("title") or it.get("action"))[:50]} ｜ {str(it.get("status"))[:22]}')
            if apply_changes:
                _arch_write_json(f'removed_{f.replace(".json", "")}' + (f'_{key}' if key else '') + '.json', gone2)
                if key is None:
                    save_json(pp, keep2, indent=2)
                else:
                    d[key] = keep2
                    # pending_decisions.json/dashboard_decisions.json 縮排為 2，其他為 1
                    ind = 2 if f in ('dashboard_decisions.json', 'pending_decisions.json') else 1
                    save_json(pp, d, indent=ind)
                logger.info(f"{f} 已更新並歸檔舊條目。")
            cleaned_count += len(gone2)
            retained_count += len(keep2)
        else:
            logger.info(f"沒有 {f} 舊條目需要清理。")
            retained_count += len(arr)
    return cleaned_count, retained_count

def _cleanup_html_banners(apply_changes: bool, current_date_iso: str):
    logger.info("執行 C. 清理/更新 HTML 報告橫幅...")
    BANNER = (
        '<div style="background:#fff7ed;border:1px solid #fdba74;border-left:5px solid #f97316;'
        'border-radius:8px;padding:10px 12px;margin:10px 0;font-size:13px;color:#7c2d12">'
        f'<b>⛔ {current_date_iso} 更正</b>：本報告原寫「9/11 對保完成」有誤 — 9/11 僅完成<b>質押額度核定</b>（整池 1,200 萬×4.5 成＝540 萬 @2.77%），'
        '<b>尚未對保</b>（使用者 9/12 更正、2026-09-15 查證無銀行對保通知）。撥款預估 ~9/25。現行口徑見官網儀表板。</div>'
    )
    updated_count = 0
    for f, anchor in (('daily_report_v2_2026-09-13.html', '<body'),
                      ('dynamic_weekly_review_2026-09-13.html', '<body')):
        fp = ROOT / f
        if not fp.exists():
            logger.warning(f"C. {f}: 不存在，略過"); continue
        t = load_text(fp)
        # 檢查是否已加註過，避免重複
        if f'<b>⛔ {current_date_iso} 更正</b>' in t:
            logger.info(f"C. {f}: 已加註過，略過"); continue

        # 替換硬編碼的日期檢查
        if '2026-09-15 更正' in t or '9/13 衝突加註' in t:
            logger.info(f"C. {f}: 偵測到舊版橫幅，將移除並重新加註最新橫幅。")
            # 移除舊橫幅，這裡需要更精確的正則表達式來匹配和移除
            t = re.sub(r'<div style=\"background:#fff7ed;.*?</div>', '', t, flags=re.DOTALL)

        idx = t.find('>', t.find(anchor)) + 1
        new = t[:idx] + '\n' + BANNER + t[idx:]
        logger.info(f'C. {f}: 加註更正橫幅（{len(t)} → {len(new)} bytes）')
        if apply_changes:
            save_text(fp, new)
            updated_count += 1
    return updated_count

def _cleanup_old_backups(apply_changes: bool):
    logger.info("執行 D. 清理舊備份檔 (保留最新 2 個)...")
    pats = ['snapshot.json.bak-*', 'snapshot*.bak', '*.bak-*', '*.pre_*']
    cleaned_count = 0

    for pat in pats:
        # 針對每個模式，根據檔案名詞幹 (stem) 分組
        stems = {re.sub(r'\d.*$', '', f.name) for f in ROOT.glob(pat)}
        for stem in stems:
            # 篩選出屬於當前詞幹的檔案，並按修改時間倒序排列
            fs = sorted([f for f in ROOT.glob(pat) if f.name.startswith(stem)], key=lambda x: x.stat().st_mtime, reverse=True)
            old = fs[2:] # 保留最新兩個
            if old:
                logger.info(f'D. {pat} (stem={stem}): 保留最新 {min(2, len(fs))}，刪除 {len(old)} 個。刪除範例：' + ', '.join(x.name for x in old[:6]) + (' …' if len(old) > 6 else ''))
                if apply_changes:
                    for x in old:
                        x.unlink()   # 不歸檔：備份檔本身即 snapshot/work_log 的副本，git 歷史已有
                        cleaned_count += 1
    return cleaned_count

def _cleanup_stale_docs(apply_changes: bool):
    logger.info("執行 E. 清理過時日期文件...")
    STALE_DOCS = ['DAILY_CHECKLIST_20260713.md', 'EVOLUTION_PLAN_2026-07-16.md', 'CIO_EVOLUTION_2026-07-16.md',
                  'FIXLOG_2026-07-18.md', 'framework_snapshot_2026-07-10.json', 'asset_pledge_plan.txt',
                  '國泰世華辦事指引_20260713.md']
    cleaned_count = 0

    for f_name in STALE_DOCS:
        fp = ROOT / f_name
        if fp.exists():
            logger.info(f'E. 刪除 {f_name}（{fp.stat().st_size} bytes，已入 git 歷史）')
            if apply_changes:
                # 移動到 .archive，而非直接刪除
                shutil.move(str(fp), str(ARCHIVE_DIR / f_name))
                cleaned_count += 1
    return cleaned_count

def _cleanup_stale_py_scripts(apply_changes: bool):
    logger.info("執行 F. 清理淘汰的產線腳本與一次性 ad-hoc 腳本...")
    # 這些是明確知道要淘汰的腳本
    STALE_PY = ['build_pptx.py', 'build_rate_hike_dashboard.py', 'gen_emergency_us_0914.py', 'gen_emergency_us_0915.py']
    
    # 一次性 ad-hoc 腳本：所有以 _ 開頭且不在白名單內的 .py 檔案
    ADHOC_WHITELIST = ('_audit_closeout.py', '_inspect_structures.py', 'cleanup_utils.py')
    adhoc_scripts = sorted(x.name for x in ROOT.glob('_*.py') if x.name not in ADHOC_WHITELIST)
    
    cleaned_count = 0
    to_move = []

    if STALE_PY:
        logger.info(f'F. 淘汰產線腳本 {len(STALE_PY)} 支：' + ', '.join(STALE_PY))
        to_move.extend(STALE_PY)
    if adhoc_scripts:
        logger.info(f'F. 一次性 ad-hoc 腳本 {len(adhoc_scripts)} 支：' + ', '.join(adhoc_scripts))
        to_move.extend(adhoc_scripts)

    if apply_changes and to_move:
        _ensure_archive_dir()
        for f_name in to_move:
            fp = ROOT / f_name
            if fp.exists():
                # 移動到 .archive/deprecated_scripts/ 子目錄
                deprecated_dir = ARCHIVE_DIR / 'deprecated_scripts'
                deprecated_dir.mkdir(exist_ok=True)
                shutil.move(str(fp), str(deprecated_dir / f_name))
                cleaned_count += 1
        _arch_write_text('deleted_py_list.txt', '\n'.join(STALE_PY + adhoc_scripts))
        logger.info(f"已移動 {cleaned_count} 支舊 .py 腳本至 .archive/deprecated_scripts/。")
    return cleaned_count

# --- 整合 archive_logs.py 的功能 ---

def _archive_work_log_integrated(apply_changes: bool):
    logger.info("執行整合的 work_log.json 歸檔...")
    p = ROOT / 'work_log.json'
    current_logs = load_json(p)
    
    if not current_logs:
        logger.info("work_log.json 為空或無法讀取，跳過歸檔。")
        return 0, 0

    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    recent_logs = []
    old_logs = []

    for log_entry in current_logs:
        log_date_str = log_entry.get('date')
        if log_date_str:
            try:
                log_date = datetime.strptime(log_date_str, '%Y-%m-%d')
                if log_date < thirty_days_ago:
                    old_logs.append(log_entry)
                else:
                    recent_logs.append(log_entry)
            except ValueError:
                logger.warning(f"work_log 中無效的日期格式 '{log_date_str}'，保留此條目。")
                recent_logs.append(log_entry)
        else:
            logger.warning(f"work_log 缺少 'date' 鍵，保留此條目。")
            recent_logs.append(log_entry)

    if old_logs:
        logger.info(f"歸檔 {len(old_logs)} 條 work_log 舊條目。")
        if apply_changes:
            archive_filename = datetime.now().strftime('work_log_archive_%Y%m%d.json')
            _arch_write_json(archive_filename, old_logs)
            save_json(p, recent_logs, indent=1) # work_log.json 縮排為 1
            logger.info(f"work_log.json 已更新，保留 {len(recent_logs)} 條最新條目。")
        return len(old_logs), len(recent_logs)
    else:
        logger.info("沒有 work_log 舊條目需要歸檔。")
        return 0, len(current_logs)

def _archive_error_register_integrated(apply_changes: bool):
    logger.info("執行整合的 error_register.md 歸檔...")
    p = ROOT / 'error_register.md'
    content = load_text(p)

    if not content:
        logger.info("error_register.md 為空或無法讀取，跳過歸檔。")
        return 0, 0

    sections = re.split(r'(^## INC-\d+.*?$)', content, flags=re.MULTILINE | re.DOTALL)
    
    resolved_old_sections = []
    remaining_content_parts = []
    
    # sections[0] 可能是開頭的非 INC 內容或空字串
    if sections and sections[0].strip() and not sections[0].strip().startswith('## INC-'):
        # 如果開頭是有效內容但不是 INC，則保留
        remaining_content_parts.append(sections[0])

    for i in range(1, len(sections), 2):
        header = sections[i] # 這是 "## INC-xxx..." 那一行
        body = sections[i+1] if i+1 < len(sections) else "" # INC 內容
        full_section = header + body

        resolved_match = re.search(r'- \*\*日期\*\*：(\d{4}-\d{2}-\d{2}).*?\b已解決\b', full_section, re.DOTALL)
        
        if resolved_match:
            resolved_date_str = resolved_match.group(1)
            try:
                resolved_date = datetime.strptime(resolved_date_str, '%Y-%m-%d')
                sixty_days_ago = datetime.now() - timedelta(days=60)
                if resolved_date < sixty_days_ago:
                    resolved_old_sections.append(full_section)
                    continue # 不保留此部分
            except ValueError:
                logger.warning(f"error_register 中無效的解決日期格式 '{resolved_date_str}'，保留此 INC。")
        
        remaining_content_parts.append(full_section)
    
    # 計算實際保留的 INC 數量 (從 remaining_content_parts 中數 ## INC- 開頭的行)
    retained_inc_count = sum(1 for part in remaining_content_parts if part.strip().startswith('## INC-'))

    if resolved_old_sections:
        logger.info(f"歸檔 {len(resolved_old_sections)} 條 error_register 舊條目。")
        if apply_changes:
            archive_filename = datetime.now().strftime('error_register_archive_%Y%m%d.md')
            _arch_write_text(archive_filename, "\n".join(resolved_old_sections).strip())
            # 合併所有保留的部分，確保正確的間隔
            final_content = "\n".join(remaining_content_parts).strip()
            save_text(p, final_content)
            logger.info(f"error_register.md 已更新，保留 {retained_inc_count} 條最新 INC。")
        return len(resolved_old_sections), retained_inc_count
    else:
        logger.info("沒有 error_register 舊條目需要歸檔。")
        return 0, retained_inc_count

# --- 其他深度清理功能（待實作）---
def _cleanup_archive_dir_smart(apply_changes: bool, days_to_keep: int = 365):
    logger.info(f"執行智能清理 .archive 目錄 (保留 {days_to_keep} 天內的歸檔檔)...")
    cleaned_count = 0
    # 遍歷 .archive 目錄下的所有檔案
    for f_path in ARCHIVE_DIR.glob('*'):
        if f_path.is_file():
            # 嘗試從檔名解析日期 (e.g., work_log_archive_YYYYMMDD.json, error_register_archive_YYYYMMDD.md)
            match = re.search(r'_archive_(\d{8})\.', f_path.name)
            if match:
                file_date_str = match.group(1)
                try:
                    file_date = datetime.strptime(file_date_str, '%Y%m%d')
                    if (datetime.now() - file_date).days > days_to_keep:
                        logger.info(f"刪除過期歸檔檔案: {f_path.name} (超過 {days_to_keep} 天)")
                        if apply_changes:
                            f_path.unlink()
                            cleaned_count += 1
                except ValueError:
                    logger.warning(f"無法解析歸檔檔 {f_path.name} 的日期，跳過清理。")
            else:
                logger.debug(f"歸檔檔 {f_path.name} 不符合日期命名模式，跳過自動清理。")
    return cleaned_count

def _cleanup_unreferenced_py_scripts(apply_changes: bool):
    logger.info("執行識別並刪除未被引用的 .py 檔案 (待實作)...")
    # 這需要靜態分析所有 .py 檔案的 import 語句，複雜度較高，先跳過
    return 0

def _cleanup_temp_and_cache_files(apply_changes: bool):
    logger.info("執行清理臨時/快取檔案 (待實作)...")
    # 掃描常見的臨時檔後綴或快取目錄 (e.g., *.tmp, *.log, __pycache__)
    cleaned_count = 0
    # 範例：清理 __pycache__ 目錄
    for pycache_dir in ROOT.glob('**/__pycache__'):
        if pycache_dir.is_dir():
            logger.info(f"刪除 __pycache__ 目錄: {pycache_dir}")
            if apply_changes:
                shutil.rmtree(pycache_dir)
                cleaned_count += 1
    # 範例：清理專案根目錄下的 .log 檔案 (非標準日誌)
    for log_file in ROOT.glob('*.log'):
        if log_file.is_file() and log_file.name != 'hermes_agent.log': # 排除Hermes自己的主要log
            logger.info(f"刪除臨時 .log 檔案: {log_file.name}")
            if apply_changes:
                log_file.unlink()
                cleaned_count += 1
    # 更多臨時文件類型可以添加...
    return cleaned_count

# --- 主清理入口函數 ---
def run_full_cleanup(apply_changes: bool = False):
    logger.info(f"=== 開始執行龍九系統深度清理 (apply_changes={apply_changes}) ===")
    
    current_date_iso = date.today().isoformat()
    
    results = {
        'schedule_events': {'cleaned': 0, 'retained': 0},
        'pending_decisions': {'cleaned': 0, 'retained': 0},
        'html_banners': {'updated': 0},
        'old_backups': {'cleaned': 0},
        'stale_docs': {'cleaned': 0},
        'stale_py_scripts': {'cleaned': 0},
        'work_log': {'cleaned': 0, 'retained': 0},
        'error_register': {'cleaned': 0, 'retained': 0},
        'archive_dir_smart': {'cleaned': 0},
        'unreferenced_py_scripts': {'cleaned': 0},
        'temp_and_cache_files': {'cleaned': 0},
    }

    # 從 _cleanup_past_0915.py 整合的清理功能
    gone_se, keep_se = _cleanup_schedule_events(apply_changes, current_date_iso)
    results['schedule_events'] = {'cleaned': gone_se, 'retained': keep_se}
    
    gone_pd, keep_pd = _cleanup_pending_decisions(apply_changes, current_date_iso)
    results['pending_decisions'] = {'cleaned': gone_pd, 'retained': keep_pd}

    updated_banners = _cleanup_html_banners(apply_changes, current_date_iso)
    results['html_banners'] = {'updated': updated_banners}

    cleaned_backups = _cleanup_old_backups(apply_changes)
    results['old_backups'] = {'cleaned': cleaned_backups}

    cleaned_docs = _cleanup_stale_docs(apply_changes)
    results['stale_docs'] = {'cleaned': cleaned_docs}

    cleaned_py_scripts = _cleanup_stale_py_scripts(apply_changes)
    results['stale_py_scripts'] = {'cleaned': cleaned_py_scripts}

    # 從 archive_logs.py 整合的清理功能
    gone_wl, keep_wl = _archive_work_log_integrated(apply_changes)
    results['work_log'] = {'cleaned': gone_wl, 'retained': keep_wl}

    gone_er, keep_er = _archive_error_register_integrated(apply_changes)
    results['error_register'] = {'cleaned': gone_er, 'retained': keep_er}

    # 新增的深度清理功能
    cleaned_archive_smart = _cleanup_archive_dir_smart(apply_changes)
    results['archive_dir_smart'] = {'cleaned': cleaned_archive_smart}

    cleaned_unreferenced_py = _cleanup_unreferenced_py_scripts(apply_changes)
    results['unreferenced_py_scripts'] = {'cleaned': cleaned_unreferenced_py}

    cleaned_temp_cache = _cleanup_temp_and_cache_files(apply_changes)
    results['temp_and_cache_files'] = {'cleaned': cleaned_temp_cache}

    logger.info("=== 龍九系統深度清理完成 ===")
    return results

if __name__ == '__main__':
    # 預設為乾跑模式，除非傳入 --apply 參數
    _apply = '--apply' in sys.argv
    run_full_cleanup(apply_changes=_apply)
