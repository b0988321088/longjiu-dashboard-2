#!/usr/bin/env python3
"""salary_tracker.py — 台電薪資入帳自動追蹤（Moneybook 明細 → snapshot.salary_records）

為什麼有這支（事故根因 2026-10-06）：
    台電薪資 10/06 入帳 39,777，資產面完全正確（cash_detail 逐位元相同），
    但 `salary_records` 缺 2026-10 → 收入視圖顯示薪水 0、被動安全月收少一整筆。
    補記是**文字手術**（commit 95f2b517），全庫沒有任何程式寫入者 → 每月都要人工補。
    本模組＝唯一自動寫入者。

契約（違反即 fail-closed，不得靜默退化）：
    ① 唯一來源 `mb_source.load_or_raise('明細')`（不落地、AES ZIP 記憶體解壓、禁自建路徑）
    ② 辨識：**明細描述同時含「台電」與「薪資」**（樣式：媒體轉入 - 薪資 台電）。
       ⚠️ 不得只認 `分類 == '薪資'` —— Moneybook 的分類是使用者自訂，實測 2026/08/07
       「上境工程設計顧問有限公司 332,342」也被歸在「薪資」類，只認分類會把它當薪資。
       分類＝薪資但摘要非台電者 → 一行 ℹ️ 揭露（不寫入、不告警）。
    ③ 寫入 `salary_records[YYYY-MM]`（月份＝**入帳月**），欄位 amount / date / note / source=mb_auto
    ④ 去重與異常（皆為「不寫入＋WARN」，交由人工確認）：
       - 同月偵測到 ≥2 筆台電薪資 → 不寫（可能是獎金/補發，不靜默累加）
       - 既有紀錄 amount/date 與偵測值不同 → 不覆蓋（人工補記優先，本模組不推翻既有事實）
       - 既有紀錄 amount/date 完全相同 → no-op（idempotent，重跑不產生變更）
    ⑤ 金額異常：與前 ≤3 個月既有金額中位數差 > 30% → **仍寫入**（MB 有列＝事實已發生）
       但必列 WARN，避免年終/補發被當常態。
    ⑥ 本模組**只寫實收事實層**：不動 monthly_salary / salary / monthly_income /
       working_surplus（常態模型口徑屬 PEND-20261010-02，另行處理）。

用法：
    python salary_tracker.py            # dry-run（預設）：只印計畫，不改檔
    python salary_tracker.py --apply    # 寫入 snapshot.json（先備份、先 dumps 再開檔）
Exit code：0＝正常（含 no-op 與 WARN）；2＝契約失敗（無來源／讀取失敗／無密碼）；1＝寫檔失敗
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import mb_source

BASE = Path(__file__).resolve().parent
SNAP_PATH = BASE / "snapshot.json"
DEVIATION_PCT = 30.0          # 金額異常門檻（±%）
BASELINE_MONTHS = 3           # 常態基準取樣月數

_MEMO_KEY = "台電"
_MEMO_KEY2 = "薪資"
_DATE_PATTERNS = (
    re.compile(r"^(?P<y>\d{4})/(?P<m>\d{1,2})/(?P<d>\d{1,2})$"),
    re.compile(r"^(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>\d{4})$"),
)


def _norm_date(s: str) -> str:
    """Moneybook 日期 → ISO（YYYY-MM-DD）。無法解析回空字串（呼叫端須揭露）。"""
    t = str(s or "").strip()
    if not t:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}$", t):
        return t
    for pat in _DATE_PATTERNS:
        m = pat.match(t)
        if m:
            g = m.groupdict()
            return f"{int(g['y']):04d}-{int(g['m']):02d}-{int(g['d']):02d}"
    return ""


def _amount(v) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def is_tpc_salary(row: dict) -> bool:
    """台電薪資列判定：摘要須同時含「台電」與「薪資」（不得只認分類，見檔頭契約②）。"""
    memo = str(row.get("明細描述") or "")
    return _MEMO_KEY in memo and _MEMO_KEY2 in memo


def salary_category_but_other(row: dict) -> bool:
    """分類＝薪資但非台電樣式（例：上境工程設計顧問有限公司）→ 供 ℹ️ 揭露。"""
    return str(row.get("分類") or "").strip() == _MEMO_KEY2 and not is_tpc_salary(row)


def detect(rows: list) -> tuple[list, list]:
    """回傳 (detected, others)。detected 每筆＝{month,date,amount,memo,org,account}。"""
    detected, others = [], []
    for r in rows or []:
        amt = _amount(r.get("金額"))
        if amt is None:
            continue
        if salary_category_but_other(r):
            others.append({"date": _norm_date(r.get("入帳日") or r.get("消費日")),
                           "amount": amt,
                           "memo": str(r.get("明細描述") or "")[:60]})
            continue
        if not is_tpc_salary(r):
            continue
        if amt <= 0:
            continue
        d = _norm_date(r.get("入帳日") or r.get("消費日"))
        if not d:
            others.append({"date": "", "amount": amt,
                           "memo": "無法解析日期：" + str(r.get("明細描述") or "")[:40]})
            continue
        detected.append({
            "month": d[:7], "date": d, "amount": amt,
            "memo": str(r.get("明細描述") or ""),
            "org": str(r.get("機構名稱") or ""),
            "account": str(r.get("帳戶名稱") or ""),
        })
    detected.sort(key=lambda x: (x["date"], x["amount"]))
    return detected, others


def _baseline_median(records: dict, target_month: str) -> float | None:
    """前 ≤3 個月（目標月之前）既有金額的中位數；樣本 <2 筆回 None（不做異常判定）。"""
    vals = []
    for m, rec in (records or {}).items():
        if not re.match(r"^\d{4}-\d{2}$", str(m)) or str(m) >= target_month:
            continue
        a = _amount((rec or {}).get("amount"))
        if a:
            vals.append((str(m), a))
    if len(vals) < 2:
        return None
    vals.sort()
    recent = [v for _, v in vals[-BASELINE_MONTHS:]]
    recent.sort()
    n = len(recent)
    return recent[n // 2] if n % 2 else (recent[n // 2 - 1] + recent[n // 2]) / 2


def _same(rec: dict, det: dict) -> bool:
    a = _amount((rec or {}).get("amount"))
    return bool(a) and abs(a - det["amount"]) < 0.01 and str((rec or {}).get("date") or "") == det["date"]


def plan_updates(records: dict, detected: list) -> tuple[list, list, list]:
    """回傳 (updates, warnings, infos)。只回計畫，不寫檔。"""
    updates, warnings, infos = [], [], []
    by_month = {}
    for d in detected:
        by_month.setdefault(d["month"], []).append(d)
    for month in sorted(by_month):
        dets = by_month[month]
        rec = (records or {}).get(month) or {}
        if len(dets) > 1:
            warnings.append(
                f"{month} 偵測到 {len(dets)} 筆台電薪資入帳（{', '.join(str(int(x['amount'])) for x in dets)}）"
                f" → 不寫入，請人工確認是否為獎金/補發："
                + "；".join(f"{x['date']} {int(x['amount']):,}" for x in dets))
            continue
        det = dets[0]
        if rec:
            if _same(rec, det):
                infos.append(f"{month} 既有紀錄與 MB 相同（{det['date']} {int(det['amount']):,}）→ no-op")
                continue
            warnings.append(
                f"{month} 既有紀錄（{rec.get('date')} {_amount(rec.get('amount'))}）與 MB（{det['date']} {det['amount']}）"
                f" 不符 → 不覆蓋既有值，請人工確認")
            continue
        med = _baseline_median(records, month)
        note_extra = ""
        if med and abs(det["amount"] - med) / med * 100 > DEVIATION_PCT:
            pct = (det["amount"] / med - 1) * 100
            note_extra = f"（常態中位數 {med:,.0f}，偏離 {pct:+.1f}%）"
            warnings.append(f"{month} 金額偏離前 {BASELINE_MONTHS} 個月常態中位數 >{DEVIATION_PCT:.0f}%{note_extra}"
                            f" → 已寫入（實收事實）但請確認是否為一次性項目")
        amt = int(round(det["amount"]))
        updates.append({
            "month": month,
            "value": {
                "amount": amt, "date": det["date"],
                "note": f"台電薪資媒體轉入（自動帶入：MB 明細 {det['org']} {det['account']}{note_extra}）",
                "source": "mb_auto",
            },
        })
    return updates, warnings, infos


def run(apply: bool = False) -> int:
    try:
        meta = mb_source.load_or_raise("明細")
    except mb_source.MBSourceError as e:
        print(f"[FAIL] Moneybook 匯入契約失敗：{e}")
        return 2
    snap = json.loads(SNAP_PATH.read_text(encoding="utf-8"))
    records = snap.get("salary_records", {}) or {}
    detected, others = detect(meta["rows"])
    updates, warnings, infos = plan_updates(records, detected)

    print(f"來源：{mb_source.describe('明細', meta)}")
    print(f"掃描 {len(meta['rows'])} 列 → 台電薪資 {len(detected)} 筆"
          f"（{', '.join(d['month'] for d in detected) or '無'}）")
    for i in infos:
        print(f"  ℹ️ {i}")
    for o in others:
        print(f"  ℹ️ 分類＝薪資但非台電樣式（不寫入）：{o['date']} {o['amount']:,.0f} {o['memo']}")
    for w in warnings:
        print(f"  ⚠️ WARN: {w}")
    if not updates:
        print("✅ 無需變更（實收事實層已一致）")
        return 0
    for u in updates:
        print(f"  ＋ {u['month']}: {u['value']['amount']:,}（{u['value']['date']}）source=mb_auto")
    if not apply:
        print("（dry-run：未寫檔；加 --apply 才落地）")
        return 0

    backup = SNAP_PATH.with_suffix(f".json.bak-salary-{datetime.now():%Y%m%d%H%M%S}")
    shutil.copy(SNAP_PATH, backup)
    for u in updates:
        records[u["month"]] = u["value"]
    snap["salary_records"] = records
    snap.setdefault("salary_records_source", {})["mb_auto_last_run"] = {
        "at": date.today().isoformat(), "export_date": meta["export_date"],
        "origin": Path(meta["origin"]).name, "written": [u["month"] for u in updates]}
    text = json.dumps(snap, ensure_ascii=False, indent=1)     # 先 dumps 再開檔（避免截檔）
    with open(SNAP_PATH, "w", encoding="utf-8") as f:          # 預設換行轉譯＝維持 CRLF
        f.write(text)
    print(f"✅ 已寫入 {len(updates)} 個月；備份 {backup.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="台電薪資入帳自動追蹤（MB 明細 → salary_records）")
    ap.add_argument("--apply", action="store_true", help="實際寫入 snapshot.json（預設 dry-run）")
    a = ap.parse_args()
    try:
        return run(apply=a.apply)
    except Exception as e:                                      # 寫檔等未預期錯誤
        print(f"[FAIL] {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
