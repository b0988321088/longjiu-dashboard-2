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
from pathlib import Path

BASE = Path(__file__).resolve().parent
FILE = BASE / "pending_decisions.json"

STATUS_ENUM = ("待處理", "已確認", "已完成", "關案")
ALERT_STATUSES = ("待處理",)

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
    g = pending_digest()
    print(pending_line())
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in g.items()},
                     ensure_ascii=False, indent=1))
