import os
import sys
import json
import sqlite3
import shutil
from datetime import datetime

REPO_PATH = "C:/Users/bot/Desktop/longjiu_system"
DB_PATH = os.path.join(REPO_PATH, "dragon_assets.db")
ASSET_DIFF_HISTORY_PATH = os.path.join(REPO_PATH, "asset_diff_history.json")
DASHBOARD_DECISIONS_PATH = os.path.join(REPO_PATH, "dashboard_decisions.json")
DAILY_REPORT_CHECK_HTML = os.path.join(REPO_PATH, "daily_report_v2_--check.html")
NOTION_BRIDGE_CHECK_MD = os.path.join(REPO_PATH, "notion_bridge", "--check_strategy_handbook.md")
ERROR_REGISTER_PATH = os.path.join(REPO_PATH, "error_register.md")

def backup_file(filepath):
    if os.path.exists(filepath):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = f"{filepath}.bak-{timestamp}"
        shutil.copy2(filepath, backup_path)
        print(f"  備份 {filepath} 到 {backup_path}")
        return True
    return False

def _iter_task_records(node, path="$"):
    """遞迴走訪巢狀結構，產出 (路徑, 含 task 字串的 dict)。"""
    if isinstance(node, dict):
        if isinstance(node.get("task"), str):
            yield path, node
        for k, v in node.items():
            yield from _iter_task_records(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _iter_task_records(v, f"{path}[{i}]")


def _find_check_tasks(data):
    return [f"{p} → {n['task']}" for p, n in _iter_task_records(data) if "--check" in n["task"]]


def _walk_lists(node):
    if isinstance(node, list):
        yield node
        for v in node:
            yield from _walk_lists(v)
    elif isinstance(node, dict):
        for v in node.values():
            yield from _walk_lists(v)


def _purge_check_tasks(data):
    removed = []
    for lst in _walk_lists(data):
        keep = [x for x in lst if not (isinstance(x, dict) and "--check" in str(x.get("task", "")))]
        if len(keep) != len(lst):
            removed += [str(x.get("task", x)) for x in lst if x not in keep]
            lst[:] = keep
    return removed


def clean_db(apply_changes):
    print("\n--- 清理 dragon_assets.db 的 '--check' 列 ---")
    if not os.path.exists(DB_PATH):
        print(f"  ⚠️ {DB_PATH} 不存在，跳過。")
        return
    
    if not apply_changes:
        print("  [Dry-run] 將檢查 dragon_assets.db 中是否存在 date='--check' 的列。")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM assets WHERE date = '--check'")
        rows = c.fetchall()
        conn.close()
        if rows:
            print(f"  🔎 發現 {len(rows)} 筆 date='--check' 的列。")
        else:
            print("  🔎 未發現 date='--check' 的列。")
    else:
        print("  [Apply] 刪除 dragon_assets.db 中 date='--check' 的列。")
        if backup_file(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM assets WHERE date = '--check'")
            conn.commit()
            conn.close()
            print("  ✅ 已刪除 date='--check' 的列。")
        else:
            print("  ❌ 無法備份或刪除 dragon_assets.db。")

def clean_asset_diff_history(apply_changes):
    print("\n--- 清理 asset_diff_history.json 的 '--check' key ---")
    if not os.path.exists(ASSET_DIFF_HISTORY_PATH):
        print(f"  ⚠️ {ASSET_DIFF_HISTORY_PATH} 不存在，跳過。")
        return
    
    if not apply_changes:
        print("  [Dry-run] 將檢查 asset_diff_history.json 中是否存在 '--check' key。")
        try:
            with open(ASSET_DIFF_HISTORY_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if "--check" in data:
                print("  🔎 發現 '--check' key。")
            else:
                print("  🔎 未發現 '--check' key。")
        except json.JSONDecodeError:
            print("  ❌ 無法解析 asset_diff_history.json。")
    else:
        print("  [Apply] 移除 asset_diff_history.json 中的 '--check' key。")
        if backup_file(ASSET_DIFF_HISTORY_PATH):
            try:
                with open(ASSET_DIFF_HISTORY_PATH, 'r+', encoding='utf-8') as f:
                    data = json.load(f)
                    if "--check" in data:
                        del data["--check"]
                        f.seek(0)
                        json.dump(data, f, ensure_ascii=False, indent=2)
                        f.truncate()
                        print("  ✅ 已移除 '--check' key。")
                    else:
                        print("  🔎 未發現 '--check' key，無需操作。")
            except json.JSONDecodeError:
                print("  ❌ 無法解析 asset_diff_history.json。")
        else:
            print("  ❌ 無法備份或修改 asset_diff_history.json。")

def clean_dashboard_decisions(apply_changes):
    print("\n--- 清理 dashboard_decisions.json 內含 '--check' 的任務字串 ---")
    if not os.path.exists(DASHBOARD_DECISIONS_PATH):
        print(f"  ⚠️ {DASHBOARD_DECISIONS_PATH} 不存在，跳過。")
        return
    
    if not apply_changes:
        print("  [Dry-run] 將檢查 dashboard_decisions.json 內含 '--check' 的任務字串。")
        try:
            with open(DASHBOARD_DECISIONS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            hits = _find_check_tasks(data)
            for path in hits:
                print(f"  🔎 發現任務字串: {path}")
            if not hits:
                print("  🔎 未發現含 '--check' 的任務字串。")
        except json.JSONDecodeError:
            print("  ❌ 無法解析 dashboard_decisions.json。")
    else:
        print("  [Apply] 清除 dashboard_decisions.json 內含 '--check' 的任務字串。")
        if backup_file(DASHBOARD_DECISIONS_PATH):
            try:
                with open(DASHBOARD_DECISIONS_PATH, 'r+', encoding='utf-8') as f:
                    data = json.load(f)
                    removed = _purge_check_tasks(data)
                    modified = bool(removed)
                    for item in removed:
                        print(f"  🗑️ 移除任務字串: {item}")
                    
                    if modified:
                        f.seek(0)
                        json.dump(data, f, ensure_ascii=False, indent=2)
                        f.truncate()
                        print("  ✅ 已清除含 '--check' 的任務字串。")
                    else:
                        print("  🔎 未發現含 '--check' 的任務字串，無需操作。")
            except json.JSONDecodeError:
                print("  ❌ 無法解析 dashboard_decisions.json。")
        else:
            print("  ❌ 無法備份或修改 dashboard_decisions.json。")

def delete_file(filepath, apply_changes):
    print(f"\n--- 刪除檔案: {filepath} ---")
    if not os.path.exists(filepath):
        print(f"  ⚠️ {filepath} 不存在，跳過。")
        return
    
    if not apply_changes:
        print(f"  [Dry-run] 將刪除檔案: {filepath}。")
    else:
        print(f"  [Apply] 刪除檔案: {filepath}。")
        try:
            os.remove(filepath)
            print(f"  ✅ 已刪除 {filepath}。")
        except OSError as e:
            print(f"  ❌ 刪除 {filepath} 失敗: {e}")

def advise_error_register():
    print("\n--- error_register.md 清理建議 ---")
    if not os.path.exists(ERROR_REGISTER_PATH):
        print(f"  ⚠️ {ERROR_REGISTER_PATH} 不存在。")
        return
    
    print("  📄 error_register.md 舊格式條目仍會被記錄，但新的將會使用 inc_events.jsonl 機制。")
    print(f"  建議手動審查 {ERROR_REGISTER_PATH}，移除所有與 '--check' 相關的條目，")
    print("  並考慮定期清理重複或已解決的舊條目。")

def main():
    apply_changes = '--apply' in sys.argv
    
    print(f"✨ 啟動污染清理腳本 (Apply changes: {apply_changes}) ✨")

    clean_db(apply_changes)
    clean_asset_diff_history(apply_changes)
    clean_dashboard_decisions(apply_changes)
    delete_file(DAILY_REPORT_CHECK_HTML, apply_changes)
    delete_file(NOTION_BRIDGE_CHECK_MD, apply_changes)
    advise_error_register()
    
    print("\n✨ 清理腳本執行完畢。")

if __name__ == "__main__":
    main()