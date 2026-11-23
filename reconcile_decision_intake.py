#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reconcile_decision_intake.py — 「今日核准」vs「今日入庫」ID 集合對帳（CIO 復盤前必跑）。

CIO 2026-09-23 ② 的缺口本質是「時序不可靠」：核准有留下、程式有留下，但 dashboard_decisions
在 CIO 18:30 跑的時候是殘缺的，靠晚上人工補。這支把「有沒有漏」變成可判定的檢查：

  今日收據（decision_intake_receipts.jsonl；人工由 append_dashboard_decisions.py 產生、
            自動由 memory_helper.add_memory 產生）
        ↓
  今日 dashboard_decisions
        ↓
  ID 集合比對（**分兩條車道**：人工／自動）
        ↓
  人工一致 → PASS ／ 人工缺口 → exit 1 ／ 無人工證據 → exit 2

2026-11-23（CIO 18:30 ②）：舊版把「自動寫入無收據」與「人工決策無收據」混在同一個
unregistered 桶，且該桶**從不影響 rc** → 收據 0／人工 0 但檔案有 2 筆 auto 時，
對帳印了 ⚠️ 卻回 rc=0（CIO 讀成「通過」）。同一層機制出現兩種失明方向：
9/23 是「有真核准、檔案看不到」，11/23 是「有條目、收據看不到」。
本版把車道拆開：人工無收據 = 真缺口（rc=1，不得再靜默），自動無收據 = 覆蓋率資訊
（不動 rc，因為那不是裁決），且「今日無人工證據」一律 rc=2，不被 auto 條目稀釋。


另可加 --notion：向 Notion 分析 DB 查「今日建立的決策頁」數，與檔案今日 user 筆數對照
（獨立第二來源；Notion 不可達時明確標示「未查核」，不靜默通過）。

用法：
  python reconcile_decision_intake.py [--date 2026-10-02] [--notion] [--quiet]
退出碼：0 = PASS；1 = 有缺口（fail-loud，供閘門/復盤前置使用）；2 = 有來源未查核／無資料（完整性未驗證）
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


def empty_intake_diagnosis(day):
    """2026-11-04（CIO 排序 B）：rc=2 時補診斷，區分「今日確實沒有裁定」與「裁定沒被收成收據」。
    只輸出診斷，不改判定（0 筆永不得視為通過）。"""
    out = []
    n_rec_all, last_rec = 0, ""
    if RECEIPT_FILE.exists():
        for ln in RECEIPT_FILE.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
            except Exception:
                continue
            n_rec_all += 1
            ts = str(r.get("ts", ""))
            if ts > last_rec:
                last_rec = ts
    out.append(f"收據檔：累計 {n_rec_all} 筆，最後一筆 {last_rec or '（無）'}")
    n_dec_all, last_dec, dec = 0, "", {}
    try:
        dec = json.loads(DEC_FILE.read_text(encoding="utf-8"))
        for d in dec.get("decisions", []) or []:
            n_dec_all += 1
            ts = str(d.get("timestamp", "") or d.get("date", ""))
            if ts > last_dec:
                last_dec = ts
        out.append(f"決策檔：累計 {n_dec_all} 筆，最後一筆 {last_dec or '（無）'}")
    except Exception as e:
        out.append(f"決策檔讀取失敗：{type(e).__name__}")
    today_in_dec = any(
        str(d.get("timestamp", "") or d.get("date", "")).startswith(day)
        for d in (dec.get("decisions", []) or [])
    )
    if today_in_dec:
        out.append("→ 判定：決策檔已有今日決策但收據 0 → 漏收據（寫方未經 append_dashboard_decisions.py）")
        code = "MISSING_RECEIPT"
    elif not last_dec or last_dec[:10] < day:
        out.append("→ 判定：兩邊今日皆無新增 → 可能是『今日確實沒有裁定』，也可能是『對話中的裁定沒進入任何寫方』")
        out.append("   （後者本檢查無法識別：未經 append 工具的裁定不會留下痕跡，故 rc=2 保留）")
        code = "NO_RULING_TODAY"
    else:
        out.append("→ 判定：兩邊皆 0 但決策檔有今日紀錄 → 檢查日期格式與 source 欄位")
        code = "CALIBER_CHECK"
    return out, code


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
    out, srcs, all_today = [], {}, []
    for x in d.get("decisions", []):
        if not str(x.get("timestamp", "")).startswith(day):
            continue
        all_today.append(x)
        s = str(x.get("source") or "")
        if s in ("auto", "notion"):
            continue
        out.append(x)
        srcs[s or "(空)"] = srcs.get(s or "(空)", 0) + 1
    return out, srcs, all_today


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


def load_all_receipts():
    """整個收據檔（不分日）——用於判定「收據制起算時點」。"""
    if not RECEIPT_FILE.exists():
        return []
    out = []
    for ln in RECEIPT_FILE.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def _ts_of(obj):
    """取 ISO 時戳（收據用 'ts'、決策用 'timestamp'）；無法解析回 None。

    2026-10-18（實際踩到 TypeError）：收據寫入時帶時區（`+08:00`，tz-aware），
    dashboard_decisions 的 timestamp 是 naive → `t < start` 直接比較會拋
    「can't compare offset-naive and offset-aware datetimes」，整支對帳掛掉，
    收工檢查就變「決策入庫缺口」的假紅。
    修法：一律換算成本地 naive（同一時區語意）再比較，不改任何既有判定邏輯。
    """
    if not isinstance(obj, dict):
        return None
    try:
        dt = datetime.fromisoformat(str(obj.get("ts") or obj.get("timestamp") or ""))
    except Exception:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def receipt_regime_start():
    """收據制（單一入庫入口）的起算時點＝收據檔最早一筆 ts；無有效時戳回 None。

    為什麼要有時間邊界（2026-10-02 INC-280）：收據制是 10/2 20:53 才上線的制度。
    比它更早進檔的決策**結構上不可能**有收據 → 每跑一次對帳就被當「未經單一入口」警示一次
    （實例：mem-20261002195408-1056 每晚假缺口）。判準要有生效邊界，不是每筆都一視同仁。
    """
    ts = [t for t in (_ts_of(r) for r in load_all_receipts()) if t]
    return min(ts) if ts else None


def _is_auto(x, key="source"):
    """自動寫入（非人工裁決）：source=auto（memory_helper／cron）或 notion（bridge 自動寫）。"""
    return str(x.get(key) or "") in ("auto", "notion")


def compare(day, rec, intake_all):
    """回傳 (missing, unreg_manual, unreg_auto, legacy) 四個 id 清單。

    missing      = 有收據但沒進檔 → 真缺口（rc=1）
    unreg_manual = 收據制上線**之後**進檔的人工決策卻沒有收據 → 未經單一入口（rc=1）
    unreg_auto   = 收據制上線**之後**進檔的自動寫入沒有收據 → 覆蓋率資訊（不動 rc）
    legacy       = 收據制上線**之前**的歷史入庫 → 不列警示（制度當時不存在）
    fail-closed：收據檔無有效時戳（空／不存在）時無法判定起點 → 人工類一律歸 unreg_manual。

    2026-11-23（CIO ②）：舊版只回三個桶且 unregistered 從不影響 rc；人工與自動混在一起，
    使「人工核准走別的路徑進來」與「cron 快照」長得一樣 → 真缺口被 auto 噪音蓋掉。
    """
    rec_ok = [r for r in rec if r.get("ok")]
    rec_ids = {str(r.get("id")) for r in rec_ok if r.get("id")}
    file_ids = {str(x.get("id")) for x in intake_all if x.get("id")}
    missing = sorted(rec_ids - file_ids)
    start = receipt_regime_start()
    rec_src = {str(r.get("id")): str(r.get("source") or "") for r in rec_ok if r.get("id")}
    unreg_manual, unreg_auto, legacy = [], [], []
    for i in sorted(file_ids - rec_ids):
        x = next((x for x in intake_all if str(x.get("id")) == i), {})
        t = _ts_of(x)
        if start is not None and t is not None and t < start:
            legacy.append(i)
        elif _is_auto(x):
            unreg_auto.append(i)
        else:
            unreg_manual.append(i)
    # 車道一致性：人工決策的收據不得記成自動（否則可用「auto 收據」掩蓋手工寫入，
    # 等於繞過單一入口還能通過對帳）→ 視為人工未經單一入口，fail-closed。
    for i in sorted(file_ids & rec_ids):
        x = next((x for x in intake_all if str(x.get("id")) == i), {})
        if not _is_auto(x) and _is_auto({"source": rec_src.get(i)}):
            unreg_manual.append(i)
    return missing, sorted(set(unreg_manual)), unreg_auto, legacy



def main():
    ap = argparse.ArgumentParser(description="今日核准 vs 今日入庫 對帳")
    ap.add_argument("--date")
    ap.add_argument("--notion", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    day = _today(a.date)

    rec = load_receipts(day)
    intake, srcs, intake_all = load_intake(day)
    rec_ok = [r for r in rec if r.get("ok")]
    rec_ids = {str(r.get("id")) for r in rec_ok if r.get("id")}
    # 人工收據＝寫入時 source 非 auto/notion（收據沿用入庫當下的 source）
    rec_manual_ids = {str(r.get("id")) for r in rec_ok
                      if r.get("id") and not _is_auto(r)}
    # 2026-10-31 修正：缺口比對用「今日全部決策」（含 source=auto）；原本用人工集合，
    # source=auto 的正常入庫（cron 修復紀錄）會被誤判為「有收據未入庫」的真缺口。
    file_ids = {str(x.get("id")) for x in intake_all if x.get("id")}
    file_manual_ids = {str(x.get("id")) for x in intake if x.get("id")}

    missing, unreg_manual, unreg_auto, legacy = compare(day, rec, intake_all)
    start = receipt_regime_start()

    def _task_of(i, pool):
        x = next((x for x in pool if str(x.get("id")) == i), {})
        return str(_title_of(x))[:44]

    if not a.quiet:
        print(f"=== 決策入庫對帳（{day}）===")
        print(f"  收據（單一入口）：{len(rec)} 筆（成功 {len(rec_ok)}；人工 {len(rec_manual_ids)}"
              f"／自動 {len(rec_ids) - len(rec_manual_ids)}）")
        print(f"  檔案（人工決策）：{len(intake)} 筆" + (f"｜source 分布 {srcs}" if srcs else ""))
        print(f"  檔案（含自動寫入）：{len(intake_all)} 筆")
        print(f"  收據 ∩ 檔案：{len(rec_ids & file_ids)} 筆")


    rc = 0
    if missing:
        print(f"  ❌ 缺口 {len(missing)} 筆：核準已留收據但未入庫 →")
        for i in missing:
            t = next((r.get("task") for r in rec_ok if r.get("id") == i), "")
            print(f"     - {i}｜{str(t)[:44]}")
        rc = 1
    if legacy:
        print(f"  ℹ️ 收據制上線前（{start:%Y-%m-%d %H:%M}）的歷史入庫 {len(legacy)} 筆，不列警示：")
        for i in legacy:
            print(f"     - {i}｜{_task_of(i, intake_all)}")
    if unreg_manual:
        # 2026-11-23（CIO ②）：人工決策繞過單一入口 → 必須 fail-loud。
        # 舊版只印 ⚠️、rc 仍 0，等於「真核准走別條路進來」永遠查不出來（11/22 實例）。
        print(f"  ❌ {len(unreg_manual)} 筆人工決策未經單一入口（收據制上線後進檔卻沒有收據）→ 列為缺口 rc=1：")
        for i in unreg_manual:
            print(f"     - {i}｜{_task_of(i, intake_all)}")
        print("     → 修法：人工核准一律 python append_dashboard_decisions.py --source user（會留收據）")
        if start is None:
            print("     （收據檔無有效時戳 → 無法判定收據制起點，一律列缺口）")
        rc = 1
    if unreg_auto:
        # 自動寫入（cron／memory_helper／notion bridge）不是裁決 → 只報覆蓋率，不動 rc。
        print(f"  ℹ️ {len(unreg_auto)} 筆自動寫入沒有收據（覆蓋率缺口，非人工裁決；不影響 rc）：")
        for i in unreg_auto:
            print(f"     - {i}｜{_task_of(i, intake_all)}")
        print("     → 2026-11-23 起 memory_helper.add_memory 也會留收據；此類持續出現＝有寫方繞過工具")
    matched_manual = file_manual_ids - set(legacy)
    no_id = [x for x in intake if not x.get("id")]
    if no_id:
        # 沒有 id 的人工決策無法與收據做集合比對（歷史寫方未帶 id）→ 只能列示，不得當成 PASS 依據
        print(f"  ⚠️ {len(no_id)} 筆人工決策沒有 id（無法與收據比對，不計入一致判定）：")
        for x in no_id:
            print(f"     - {str(_title_of(x))[:44]}｜{str(x.get('timestamp'))[:19]}")
    if not missing and not unreg_manual:
        if not rec_manual_ids and not matched_manual:
            # 2026-10-21（使用者核准，範圍限本檔）：空集合不得算「一致性 PASS」。
            #   收據 0／檔案 0 只證明「今天沒有可比對的資料」，無法證明今日裁定都已入庫
            #   （實證：10/21 有兩項裁定、兩邊皆 0 筆，舊版仍印「✅ 一致」rc=0）。
            #   語意改為「未驗證」，rc=2 沿用既有契約（CIO 18:30 job 已把 rc=2 視為
            #   「對帳未完成」而不得當成通過），不動 rc=0 的既有成功語意。
            # 2026-11-23 補：這段原本只在「三個桶全空」時才走到，只要檔案有 auto 條目就整段被跳過
            #   → 收據 0／人工 0 仍回 rc=0。改為只依「有無人工證據」判定，auto 不得稀釋。
            _dl, _code = empty_intake_diagnosis(day)
            if _code == "NO_RULING_TODAY":
                print("  ℹ️ 今日無裁定（收據 0／檔案 0）→ rc=2 是契約保守語意，不是缺口陳述")
            else:
                print("  🔴 有今日決策但收據 0 → 漏收據（真實缺口）")
            print("  ⚠️ 完整性未驗證 → 不得視為通過（rc 仍 2，不放寬）")
            for _l in _dl:
                print(f"     {_l}")
            print(f"  RESULT={_code}")
            rc = max(rc, 2)
        else:
            print(f"  ✅ 一致（人工 {len(matched_manual)} 筆 ↔ 人工收據 {len(rec_manual_ids)} 筆；今日無缺口）")


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
