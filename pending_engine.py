#!/usr/bin/env python3
"""Pending 期限管理引擎（第 3 批｜使用者 2026-10-02 裁示③）。

Schema（每一筆 pending 都有）：
    due_date           到期／檢視日（None＝未提供 → **不猜、不推算**）
    last_confirmed     最後確認日（None＝未提供）
    owner              內部責任人（一律 "CEO"）
    external_owner     外部對口（銀行／理專／技師／業務…；None＝未提供，不猜）
    status             狀態機旗標：待處理／已確認／已完成／關案（原字串保留於 status_raw）

狀態機（以 due_date 為基準）：
    到期日 → 「今日到期」；+1 日 → 第一次升級；+3 日 → 第二次升級；+7 日 → CEO 強制處理

鐵則：
  * 只提醒，**不下任何交易指令**（不提買賣／加減碼／質押／借款）。
  * 無 due_date 者不提醒、不推算；HOLD／已確認／已完成／關案 不進提醒（避免「已定案不動作」的項目反覆佔用決策空間）。
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
FILE = BASE / "pending_decisions.json"

STATUS_ENUM = ("待處理", "已確認", "已完成", "關案")
ALERT_STATUSES = ("待處理",)

# ── 期限 schema 自癒（2026-10-05 PEND-20261005-03）──────────────────────
# 症狀（10/05 07:00 實例）：新增的 pending 卡漏了 needs_due_date（或整組 schema 鍵）→ 產線末端
# check_dividend_caliber 的『無 due_date 者標記 needs_due_date』亮紅 → Task1+2 驗證器第 5 類擋關
# → 日報產出但不推送（連 3 次失敗）。根因是「新增卡靠人手複製模板」，缺欄當下沒有任何守門。
# 修法：提供一個**無損**正規化函式，讓唯一計算層（pending_engine）同時提供「自癒」能力；
#       由產線在產出與閘門之前呼叫（regenerate_report 3b2），不自癒「不可無損推得」的欄位。
SCHEMA_FIELDS = ("due_date", "last_confirmed", "owner", "external_owner", "status")
SCHEMA_DEFAULTS = {"due_date": None, "last_confirmed": None, "owner": "CEO",
                   "external_owner": None, "status": "待處理"}


def normalize_cards(items: list) -> list[str]:
    """無損自癒：只補「不猜、不推算」就能推得的欄位，回傳修正紀錄（就地修改 items）。

    可自癒：
      ① 缺 schema 鍵 → 補 honest 預設（owner 一律 "CEO"；status 預設 "待處理"＝最保守、會進提醒）
      ② due_date 為空 → needs_due_date = True（schema 不變式：沒有日期就必須標記「待提供」）
      ③ 有 status 但缺 status_raw → 以 status 回填（原字串不存在時唯一誠實的取值）
    刻意**不可**自癒（留給閘門 fail-closed，不得代改、不得代刪）：
      · due_date 有值但 due_date_source 不以「既有文字」開頭（推算／臆測出來的日期）
    """
    fixes: list[str] = []
    for x in items:
        tag = str(x.get("id") or x.get("title") or "?")[:36]
        for k in SCHEMA_FIELDS:
            if k not in x:
                x[k] = SCHEMA_DEFAULTS[k]
                fixes.append(f"{tag}: 補 schema 鍵 {k}={SCHEMA_DEFAULTS[k]!r}")
        if not x.get("due_date") and not x.get("needs_due_date"):
            x["needs_due_date"] = True
            fixes.append(f"{tag}: 無 due_date → needs_due_date=True")
        if "status_raw" not in x:
            x["status_raw"] = x.get("status") or ""
            fixes.append(f"{tag}: 缺 status_raw → 以 status 回填")
    return fixes

def norm_status(raw: str) -> str:
    """原字串 → 狀態機旗標（只看開頭語境，避免敘事中出現「已達標」被誤判為完成）。"""
    s = str(raw or "").strip()
    head = s[:40]
    if s.startswith("✅") or any(k in head for k in ("已完成", "已結清", "已入帳完成")):
        return "已完成"
    if any(k in head for k in ("關案", "作廢")):
        return "關案"
    if any(k in head for k in ("HOLD", "NO ACTION", "暫停", "條件未成立", "凍結", "不動作",
                               "不追問", "執行中", "核准", "已定案")):
        return "已確認"
    return "待處理"
          # 只有「待處理」會進提醒；其餘為已定案或資訊性
_ESC = ((0, "今日到期"), (1, "第一次升級（+1）"), (3, "第二次升級（+3）"), (7, "CEO 強制處理（+7）"))


def load_items(path: Path | None = None) -> list:
    d = json.loads((path or FILE).read_text(encoding="utf-8"))
    return d["pending_decisions"] if isinstance(d, dict) and "pending_decisions" in d else d


def escalation_stage(due_iso: str | None, today: dt.date | None = None) -> dict:
    """回傳 {stage, label, overdue_days}；無 due_date → stage=-1（不提醒）。"""
    if not due_iso:
        return {"stage": -1, "label": "無到期日（不提醒）", "overdue_days": None}
    try:
        d = dt.date.fromisoformat(str(due_iso)[:10])
    except Exception:
        return {"stage": -1, "label": "到期日格式無法解析（不提醒）", "overdue_days": None}
    t = today or dt.date.today()
    days = (t - d).days
    if days < 0:
        return {"stage": 0, "label": "到期前（不提醒）", "overdue_days": days}
    stage = 1
    label = "今日到期"
    for th, lb in _ESC:
        if days >= th:
            stage, label = (1 if th == 0 else (2 if th == 1 else (3 if th == 3 else 4))), lb
    return {"stage": stage, "label": label, "overdue_days": days}


def pending_digest(today: dt.date | None = None, path: Path | None = None) -> dict:
    """當日 Pending 摘要：只突出『真正今日到期』，其餘依升級階段分組。"""
    t = today or dt.date.today()
    due_today, escalating, upcoming, no_due = [], [], [], []
    for x in load_items(path):
        st = str(x.get("status") or "")
        if not any(s in st for s in ALERT_STATUSES):
            continue                                   # 已定案或資訊性 → 不提醒
        due = x.get("due_date")
        if not due:
            no_due.append(x)
            continue
        e = escalation_stage(due, t)
        row = {"title": x.get("title"), "due_date": due, "owner": x.get("owner") or "CEO",
               "external_owner": x.get("external_owner"), "階段": e["label"],
               "逾期天數": e["overdue_days"], "動作": "僅提醒（不產生任何交易指令）"}
        if e["stage"] == 1:
            due_today.append(row)
        elif e["stage"] >= 2:
            escalating.append(row)
        else:
            upcoming.append(row)
    return {"今日到期": due_today, "升級中": escalating, "到期前": upcoming,
            "無到期日_不提醒": [x.get("title") for x in no_due],
            "source": "pending_engine.pending_digest（裁示③ 2026-10-02）"}


def pending_line(today: dt.date | None = None, path: Path | None = None) -> str:
    """決定卡／日報用單行文字（無事則靜默為『今日無到期』）。"""
    try:
        g = pending_digest(today, path)
    except Exception as e:
        return "📌 Pending：無法判定（" + str(e) + "）"
    parts = []
    if g["今日到期"]:
        parts.append("今日到期 <b>" + str(len(g["今日到期"])) + "</b> 件："
                     + "、".join(str(x["title"])[:22] for x in g["今日到期"][:3]))
    else:
        parts.append("今日無到期")
    if g["升級中"]:
        parts.append("升級中 " + str(len(g["升級中"])) + " 件（最高："
                     + str(max(x["階段"] for x in g["升級中"])) + "）")
    if g["無到期日_不提醒"]:
        parts.append("未提供到期日 " + str(len(g["無到期日_不提醒"])) + " 件（不提醒）")
    return "📌 Pending：" + "｜".join(parts)


if __name__ == "__main__":
    import argparse as _ap
    _p = _ap.ArgumentParser()
    _p.add_argument("--normalize", action="store_true",
                    help="檢查 Pending 期限 schema、列出可無損自癒項（有自癒項時 exit 1）")
    _p.add_argument("--apply", action="store_true", help="與 --normalize 併用：把自癒結果寫回檔案")
    _a = _p.parse_args()
    if _a.normalize:
        _items = load_items()
        _fx = normalize_cards(_items)
        if not _fx:
            print("✅ Pending 期限 schema 合規（無可自癒項）")
            sys.exit(0)
        for _f in _fx:
            print("  🔧 " + _f)
        if _a.apply:
            FILE.write_text(json.dumps(_items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"✅ 已寫回 {FILE.name}（{len(_fx)} 筆自癒）")
            sys.exit(0)
        print("（預覽模式，未寫回；加 --apply 才寫入）")
        sys.exit(1)
    g = pending_digest()
    print(pending_line())
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in g.items()},
                     ensure_ascii=False, indent=1))
