#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""schedule_events_weekly_clean.py — 每週行事曆事件收尾（2026-09-04 使用者核准建立）

背景：schedule_events.json 過期事件無人收尾（8/22 清到 61 筆又長回 108+），
8/31、9/3「待確認」事件躺 3-4 天才被發現。本腳本每週日 08:00 cron 自動跑：

1. 自動刪除（git 可回溯，靜默）：
   - date < today 且 status 含完成語意（✅/已入帳/已完成/已核准/已進帳/已送出/已收）
   - date < today 且 status 為純提醒類（📋 行程 / 📋 節日 / 📋 例行 / 📅 配息 / ❌ 取消）
2. 保留並提醒（不自動刪，等使用者裁決）：
   - 過期但 status 有追蹤語意（🔴 重要 / ⏸️ 暫緩 / ⏳ 待 / 🟡 評估 / 📌 / pipeline / 📋 重要 / 空白）
   - 去重：只推「新增」的過期未完成（state 檔比對），同一批不重複吵（8/25 定案：僅狀態切換才推）
3. 有刪除 → git commit + push 雙分支（PUSH_FORCE_OK 預先核准）；無新增提醒 → 靜默 0 輸出

用法：
  python scripts/schedule_events_weekly_clean.py          # 正式執行（刪除+commit+push）
  python scripts/schedule_events_weekly_clean.py --dry-run  # 只印分類不動檔
"""
import json, subprocess, sys, datetime
from pathlib import Path

BASE = Path("C:/Users/bot/Desktop/longjiu_system")
EVENTS = BASE / "schedule_events.json"
STATE = BASE / "data" / "calendar_overdue_state.json"
TODAY = datetime.date.today()

# 完成語意（date<today 即刪）
DONE_MARK = ("✅", "已入帳", "已完成", "已核准", "核准完成", "已進帳", "已送出", "已收")
# 純提醒類 status 前綴（過期即無追蹤價值）
PURE_PREFIX = ("📋 行程", "📋 節日", "📋 例行", "📅 ", "❌ 取消", "📋 行程")
PURE_EXACT = ("📋 行程", "📋 節日", "📋 例行")
# 追蹤語意（永不自動刪，進提醒清單）
TRACK_MARK = ("🔴", "⏸️", "⏳", "🟡", "📌", "pipeline", "📋 重要")


def load_events():
    return json.load(open(EVENTS, encoding="utf-8"))


def fmt_date(d):
    try:
        return datetime.date.fromisoformat(str(d)[:10])
    except Exception:
        return None


def classify(evs):
    """回傳 (auto_del, review) 兩份事件清單"""
    auto_del, review = [], []
    for e in evs:
        d = str(e.get("date", ""))[:10]
        status = str(e.get("status", "")).strip()
        item = str(e.get("item", ""))
        ed = fmt_date(d)
        if ed is None or ed >= TODAY:
            continue  # 無日期 or 未過期 → 不動
        if any(m in status for m in DONE_MARK):
            auto_del.append(e)
        elif any(m in status for m in TRACK_MARK):
            review.append(e)
        elif status in PURE_EXACT or status.startswith(("📅", "❌")):
            auto_del.append(e)
        else:
            # 保守：無法歸類的過期 → 進提醒不自動刪
            review.append(e)
    return auto_del, review


def load_state():
    if STATE.exists():
        try:
            return json.load(open(STATE, encoding="utf-8"))
        except Exception:
            return []
    return []


def key_of(e):
    return f"{e.get('date','')}|{e.get('item','')}"


def save_state(keys):
    STATE.parent.mkdir(exist_ok=True)
    json.dump(sorted(keys), open(STATE, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


def git(op, *args):
    return subprocess.run(["git", op, *args], capture_output=True, text=True,
                          cwd=str(BASE), timeout=60)


def main():
    dry = "--dry-run" in sys.argv
    evs = load_events()
    auto_del, review = classify(evs)
    prev_keys = set(load_state())
    cur_review_keys = {key_of(e) for e in review}
    new_review = [e for e in review if key_of(e) not in prev_keys]

    if dry:
        print(f"📋 [dry-run] 過期 {len(auto_del) + len(review)} 筆 | "
              f"將自動刪 {len(auto_del)} | 待裁決 {len(review)}（新增 {len(new_review)}）")
        print("\n-- 將自動刪除 --")
        for e in auto_del:
            print(f"  {e.get('date')} | {e.get('status')} | {e.get('item','')[:50]}")
        print("\n-- 保留待裁決（新增才推） --")
        for e in review:
            tag = "🆕" if key_of(e) in cur_review_keys - prev_keys else "  "
            print(f"  {tag} {e.get('date')} | {e.get('status')} | {e.get('item','')[:50]}")
        return

    # 正式執行
    changed = False
    if auto_del:
        del_keys = {key_of(e) for e in auto_del}
        evs = [e for e in evs if key_of(e) not in del_keys]
        json.dump(evs, open(EVENTS, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        changed = True

    save_state(cur_review_keys)  # 更新 state = 本次保留全集（含已解決的自動消失）

    # commit + push（僅有變更時）
    if changed:
        r = git("commit", "-am",
                f"[cron] 每週事件清理：刪除 {len(auto_del)} 筆過期事件（git 可回溯）")
        if r.returncode == 0:
            env_push = {"PUSH_FORCE_OK": "1"}
            p1 = git_env("push", "origin", "clean-main", env=env_push)
            p2 = git_env("push", "origin", "clean-main:main", "--force", env=env_push)
            push_note = ""
            if p1.returncode != 0:
                push_note += f"\n⚠️ push clean-main 失敗: {p1.stderr.strip()[:200]}"
            if p2.returncode != 0:
                push_note += f"\n⚠️ push main 失敗: {p2.stderr.strip()[:200]}"
        else:
            push_note = f"\n⚠️ commit 失敗: {r.stderr.strip()[:200]}"

    # 輸出：只推「新增的過期未完成」；無新增則靜默（空輸出）
    if new_review:
        lines = [f"📅 行事曆過期未完成（新增 {len(new_review)} 筆，需你裁決 ✅完成/⏸️保留/刪除）："]
        for e in new_review:
            lines.append(f"  • {e.get('date')}｜{e.get('status')}｜{e.get('item','')[:70]}")
        if auto_del:
            lines.append(f"\n🧹 已自動清理 {len(auto_del)} 筆過期事件（已完成/純提醒，git 可回溯）")
        print("\n".join(lines))


def git_env(op, *args, env=None):
    import os
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(["git", op, *args], capture_output=True, text=True,
                          cwd=str(BASE), timeout=120, env=full_env)


if __name__ == "__main__":
    main()
