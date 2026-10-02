#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reconcile_decision_intake.py — 「今日核准」vs「今日入庫」ID 集合對帳（CIO 復盤前必跑）。

CIO 2026-09-23 ② 的缺口本質是「時序不可靠」：核准有留下、程式有留下，但 dashboard_decisions
在 CIO 18:30 跑的時候是殘缺的，靠晚上人工補。這支把「有沒有漏」變成可判定的檢查：

  今日收據（decision_intake_receipts.jsonl，由 append_dashboard_decisions.py 產生）
        ↓
  今日 dashboard_decisions（source=user）
        ↓
  ID 集合比對
        ↓
  一致 → PASS ／ 不一致 → 印出缺口筆數與明細（exit 1）

另可加 --notion：向 Notion 分析 DB 查「今日建立的決策頁」數，與檔案今日 user 筆數對照
（獨立第二來源；Notion 不可達時明確標示「未查核」，不靜默通過）。

用法：
  python reconcile_decision_intake.py [--date 2026-10-02] [--notion] [--quiet]
退出碼：0 = PASS；1 = 有缺口（fail-loud，供閘門/復盤前置使用）；2 = 有來源未查核
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent
DEC_FILE = REPO / "dashboard_decisions.json"
RECEIPT_FILE = REPO / "data" / "decision_intake_receipts.jsonl"
TPE = timezone(timedelta(hours=8))


def _today(arg=None):
    if arg:
        return arg
    return datetime.now(TPE).strftime("%Y-%m-%d")


def load_receipts(day):
    if not RECEIPT_FILE.exists():
        return []
    out = []
    for ln in RECEIPT_FILE.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if str(r.get("ts", "")).startswith(day):
            out.append(r)
    return out


def load_intake(day):
    """今日入庫的「人工決策」＝ source 非 auto/notion（歷史寫方用過 'user'、'Hermes Telegram Gate' 等字串，
    語意都是人核准的決策；納入才不會漏看）。"""
    d = json.loads(DEC_FILE.read_text(encoding="utf-8"))
    out, srcs = [], {}
    for x in d.get("decisions", []):
        if not str(x.get("timestamp", "")).startswith(day):
            continue
        s = str(x.get("source") or "")
        if s in ("auto", "notion"):
            continue
        out.append(x)
        srcs[s or "(空)"] = srcs.get(s or "(空)", 0) + 1
    return out, srcs


def notion_today_titles(day):
    """獨立第二來源：Notion 分析 DB 今日建立的頁面標題清單。回傳 (titles, note)。"""
    try:
        sys.path.insert(0, str(REPO))
        from notion_bridge import notion_post  # noqa
        db = ""
        for p in (Path.home() / "AppData/Local/hermes/.env", REPO / ".env"):
            if p.exists():
                for ln in p.read_text(encoding="utf-8").splitlines():
                    if ln.startswith("NOTION_ANALYSIS_DB_ID="):
                        db = ln.split("=", 1)[1].strip()
        if not db:
            return None, "找不到 NOTION_ANALYSIS_DB_ID（未查核）"
        payload = {"filter": {"timestamp": "created_time", "created_time": {"on_or_after": day}},
                   "page_size": 100}
        r = notion_post(f"/databases/{db}/query", payload)
        res = r.get("results")
        if res is None:
            return None, f"Notion 回應無 results（未查核）: {str(r)[:120]}"
        titles = []
        for pg in res:
            tt = ""
            for prop in (pg.get("properties") or {}).values():
                if prop.get("type") == "title":
                    tt = "".join(x.get("plain_text", "") for x in prop.get("title", []))
            titles.append(tt.strip())
        return [t for t in titles if t], f"Notion 今日建立 {len(titles)} 頁"
    except Exception as e:
        return None, f"Notion 查核失敗（未查核）: {e}"


def _norm_title(s):
    """標題正規化：只留中文與英數字（去掉空白、全形/半形標點與裝飾符號），用於寬鬆比對。"""
    return "".join(ch for ch in str(s or "") if ch.isalnum()).lower()


def _title_of(x):
    """取決策項的標題：新 schema 用 task；舊 decisions 模板寫在 name/action。"""
    for k in ("task", "name", "action", "title"):
        v = x.get(k)
        if v:
            return str(v)
    return ""


def match_notion(titles, intake):
    """回傳 (未匹配的 Notion 標題, 未匹配的檔案項目)。用 difflib 相似度寬鬆比對
    （標題常有日期前綴、狀態後綴、用字微差，例如 memories/backups vs backups）。"""
    import difflib
    f_norm = [(_norm_title(_title_of(x)), x) for x in intake]
    matched_f = set()
    unmatched_n = []
    for t in titles:
        tn = _norm_title(t)
        best, best_r = None, 0.0
        matched = False
        for i, (fn, _x) in enumerate(f_norm):
            if not fn or not tn:
                continue
            if fn in tn or tn in fn:
                best, best_r, matched = i, 1.0, True
                break
            r = difflib.SequenceMatcher(None, fn, tn).ratio()
            if r > best_r:
                best, best_r = i, r
        if matched or (best is not None and best_r >= 0.6):
            matched_f.add(best)
        else:
            unmatched_n.append(f"{t}（最相近 {best_r:.2f}）" if best is not None else t)
    unmatched_f = [x for i, (_fn, x) in enumerate(f_norm) if i not in matched_f]
    return unmatched_n, unmatched_f


def main():
    ap = argparse.ArgumentParser(description="今日核准 vs 今日入庫 對帳")
    ap.add_argument("--date")
    ap.add_argument("--notion", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    day = _today(a.date)

    rec = load_receipts(day)
    intake, srcs = load_intake(day)
    rec_ok = [r for r in rec if r.get("ok")]
    rec_ids = {str(r.get("id")) for r in rec_ok if r.get("id")}
    file_ids = {str(x.get("id")) for x in intake if x.get("id")}
    noid = [x for x in intake if not x.get("id")]

    missing = sorted(rec_ids - file_ids)          # 收了收據但沒進檔 → 真缺口
    unregistered = sorted(file_ids - rec_ids)     # 進檔但沒有收據 → 未經單一入口（人工/舊路徑）

    if not a.quiet:
        print(f"=== 決策入庫對帳（{day}）===")
        print(f"  收據（單一入口）：{len(rec)} 筆（成功 {len(rec_ok)}）")
        print(f"  檔案（人工決策）：{len(intake)} 筆" + (f"｜source 分布 {srcs}" if srcs else ""))
        print(f"  收據 ∩ 檔案：{len(rec_ids & file_ids)} 筆")

    rc = 0
    if missing:
        print(f"  ❌ 缺口 {len(missing)} 筆：核準已留收據但未入庫 →")
        for i in missing:
            t = next((r.get("task") for r in rec_ok if r.get("id") == i), "")
            print(f"     - {i}｜{str(t)[:44]}")
        rc = 1
    if unregistered:
        print(f"  ⚠️ {len(unregistered)} 筆入庫沒有收據（未經 append_dashboard_decisions.py，可能是舊路徑或人工補）：")
        for i in unregistered:
            t = next((x.get("task") for x in intake if x.get("id") == i), "")
            print(f"     - {i}｜{str(t)[:44]}")
    if not missing and not unregistered:
        print(f"  ✅ 一致（{len(file_ids)} 筆；今日無缺口）")

    if a.notion:
        titles, note = notion_today_titles(day)
        print(f"  （第二來源）{note}")
        if titles is None:
            rc = rc or 2
        else:
            un_n, un_f = match_notion(titles, intake)
            if not un_n and not un_f:
                print(f"  ✅ 第二來源一致（Notion {len(titles)} 頁 ↔ 檔案 {len(intake)} 筆，標題寬鬆比對全數對上）")
            else:
                if un_n:
                    print(f"  ⚠️ Notion 有 {len(un_n)} 頁在檔案找不到對應決策（可能漏入庫）：")
                    for t in un_n:
                        print(f"     - {t[:52]}")
                if un_f:
                    print(f"  ⚠️ 檔案有 {len(un_f)} 筆在 Notion 找不到對應頁（可能漏記 Notion／或 Notion 標題不同）：")
                    for x in un_f:
                        print(f"     - {_title_of(x)[:52]}")
                rc = rc or 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
