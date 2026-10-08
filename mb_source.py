#!/usr/bin/env python3
"""mb_source.py — Moneybook 匯入契約（單一來源／單一實作，2026-10-08 SEC-P0／②-budget）

為什麼有這支（事故根因）：
    各消費端（budget_daily_check、mb_extract、sync_all …）各自維護「去哪找 Moneybook 檔案」的
    路徑清單，且部分只認 *.csv → 使用者上傳的 **ZIP 匯出**完全看不到，於是永遠讀到舊匯出
    （2026-10-08 實測：只找到 9/02 的 CSV，誤判「36 天未更新」）。

契約（消費端不得自建搜尋路徑，一律走本模組）：
    ① 唯一入口 load(kind)／load_or_raise(kind) → {rows, export_date, origin, container, member}
    ② 候選來源＝ZIP 匯出（canonical，使用者上傳的原始檔）＋ CSV（staging，受控短生命週期）
       staging 目錄：<repo>/tmp_mb、<repo>/moneybook；ZIP 慣例落點：hermes cache/documents
    ③ 選擇規則：檔名內 8 位日期最大者優先；同日 ZIP 優先於 CSV（原始優於解壓副本）
    ④ 一律 **記憶體解壓**（AES ZIP，密碼讀 .env）→ 不落地，避免原始資料再進 repo
    ⑤ 選中來源讀不到時 **raise**（fail-closed），**不得**靜默退回舊匯出 —— 舊的就是本次事故本身
    ⑥ metadata 語義分離：export_date＝檔案匯出日（新鮮度）；statement_due＝帳單期別（繳費截止日）
"""
from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from pathlib import Path

try:  # AES ZIP（Moneybook 匯出格式）
    import pyzipper
except Exception:  # pragma: no cover
    pyzipper = None

BASE = Path(__file__).resolve().parent
KINDS = ("帳戶", "明細", "帳單")
DATE_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})")


class MBSourceError(Exception):
    """匯入契約失敗：NO_SOURCE / NO_PASSWORD / READ_FAIL。呼叫端必須揭露（不得靜默退化）。"""

    def __init__(self, code: str, msg: str):
        super().__init__(f"[{code}] {msg}")
        self.code = code


def source_dirs(base: Path = BASE) -> list:
    """候選來源目錄（單一清單；新增位置只能改這裡）。"""
    return [
        Path(base) / "tmp_mb",                     # staging（受控、短生命週期）
        Path(base) / "moneybook",                  # 舊 staging（保留相容）
        Path(base),
        Path.home() / "AppData" / "Local" / "hermes" / "cache" / "documents",  # 使用者上傳的原始檔
    ]


def get_password() -> str:
    """讀 Moneybook ZIP 密碼：行程環境變數 → Hermes .env（repo 外）→ repo .env。未設定即 fail-closed。"""
    v = os.environ.get("MONEYBOOK_ZIP_PASSWORD", "").strip()
    if not v:
        home = os.environ.get("HERMES_HOME") or str(Path.home() / "AppData" / "Local" / "hermes")
        for p in (Path(home) / ".env", Path(BASE) / ".env"):
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.strip().startswith("MONEYBOOK_ZIP_PASSWORD="):
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
            if v:
                break
    if not v:
        raise MBSourceError("NO_PASSWORD",
                            "未設定 MONEYBOOK_ZIP_PASSWORD（憑證不得硬編碼；請寫入 Hermes .env）")
    return v


def _date_of(p: Path) -> str:
    m = DATE_RE.search(p.name)
    return "{}-{}-{}".format(*m.groups()) if m else "0000-00-00"


def _zip_members(p: Path):
    """列 ZIP 成員名（中央目錄免密碼）。回 None＝**容器本身讀不到**（損壞／非 ZIP）。

    None 與 [] 語義不同：[]＝可讀但沒有目標成員；None＝無法判定 → 呼叫端必須 fail-closed，
    不得略過後退回較舊的 CSV（2026-10-08 CIO RF-2：損壞的 canonical ZIP 曾被靜默略過）。
    """
    try:
        with zipfile.ZipFile(p) as zf:
            return [i.filename for i in zf.infolist()]
    except Exception:
        return None


def candidates(kind: str, base: Path = BASE, extra_dirs=None, include_default: bool = True) -> list:
    """回傳候選清單（已排序，最優在前）。ZIP 內含該 kind 成員才算候選。

    include_default=False 時只掃 extra_dirs（測試用：避免真實來源污染 fixture 判定）。
    """
    if kind not in KINDS:
        raise ValueError(f"kind 必須是 {KINDS}")
    dirs = (source_dirs(base) if include_default else []) + [Path(d) for d in (extra_dirs or [])]
    out = []
    for d in dirs:
        if not d.exists():
            continue
        for pat in ("*.zip", "*.csv", "*/*.zip", "*/*.csv"):
            for p in d.glob(pat):
                if not p.is_file():
                    continue
                if p.suffix.lower() == ".zip":
                    members = _zip_members(p)
                    if members is None:
                        # 讀不到中央目錄＝契約不可判定 → 保留為候選（依日期排序），load() 必須 fail-closed
                        out.append({"path": p, "date": _date_of(p), "container": "zip",
                                    "members": [], "unreadable": True})
                        continue
                    if not any(kind in m for m in members):
                        continue
                    out.append({"path": p, "date": _date_of(p), "container": "zip", "members": members})
                elif p.suffix.lower() == ".csv":
                    if kind not in p.name:
                        continue
                    out.append({"path": p, "date": _date_of(p), "container": "csv", "members": []})
    out.sort(key=lambda c: (c["date"], 1 if c["container"] == "zip" else 0,
                            c["path"].stat().st_mtime), reverse=True)
    return out


def load(kind: str, base: Path = BASE, extra_dirs=None, include_default: bool = True) -> dict | None:
    """依契約載入最新資料；找不到任何來源回 None（呼叫端自行揭露）。"""
    cands = candidates(kind, base=base, extra_dirs=extra_dirs, include_default=include_default)
    if not cands:
        return None
    best = cands[0]
    if best.get("unreadable"):
        raise MBSourceError(
            "ZIP_UNREADABLE",
            f"最新來源 {best['path'].name} 無法讀取（損壞或非 ZIP）→ 契約失敗，不退回舊檔")
    p, container = best["path"], best["container"]
    text, member = None, None
    try:
        if container == "zip":
            if pyzipper is None:
                raise MBSourceError("READ_FAIL", "pyzipper 不可用，無法讀 AES ZIP")
            pw = get_password()
            member = next(m for m in best["members"] if kind in m)
            with pyzipper.AESZipFile(p, "r") as zf:
                zf.pwd = pw.encode()
                raw = zf.read(member)          # 記憶體解壓，不落地
            text = raw.decode("utf-8-sig", errors="replace")
        else:
            text = p.read_text(encoding="utf-8-sig", errors="replace")
    except MBSourceError:
        raise
    except Exception as e:
        raise MBSourceError("READ_FAIL", f"{p.name} 讀取失敗（{type(e).__name__}）") from e

    rows = list(csv.DictReader(io.StringIO(text)))
    return {"rows": rows, "export_date": best["date"], "origin": str(p),
            "container": container, "member": member, "kind": kind,
            "candidates": [(str(c["path"]), c["date"], c["container"]) for c in cands[:5]]}


def load_or_raise(kind: str, base: Path = BASE, extra_dirs=None, include_default: bool = True) -> dict:
    d = load(kind, base=base, extra_dirs=extra_dirs, include_default=include_default)
    if d is None:
        raise MBSourceError("NO_SOURCE", f"找不到含「{kind}」的 Moneybook 匯出（ZIP 或 CSV）")
    return d


def freshness_days(export_date: str, today=None) -> int:
    """檔案匯出日距今天數；無法解析回 -1。"""
    import datetime as _dt
    try:
        y, m, d = [int(x) for x in export_date.split("-")]
        t = today or _dt.date.today()
        return (t - _dt.date(y, m, d)).days
    except Exception:
        return -1


def latest_statement_due(rows: list) -> str:
    """帳單期別＝該批資料內最新繳費截止日（事件語義，與 export_date 分離）。"""
    dues = [str(r.get("繳費截止日", "")).strip() for r in rows or []]
    dues = [d for d in dues if d]
    return max(dues) if dues else ""


def describe(kind: str, meta: dict | None) -> str:
    """"資料來源" 段落用的一行字串（匯出日／期別語義分離）。"""
    if not meta:
        return f"{kind}：無資料來源（契約失敗）"
    where = "ZIP 記憶體解壓" if meta.get("container") == "zip" else "CSV"
    return (f"{kind}：檔案匯出日 {meta.get('export_date')}"
            f"（{freshness_days(meta.get('export_date'))} 天前）｜來源 {where} {Path(meta.get('origin', '')).name}")


if __name__ == "__main__":  # 手動檢視用
    for k in KINDS:
        cs = candidates(k)
        print(f"=== {k}：{len(cs)} 個候選")
        for c in cs[:5]:
            print(f"   {c['date']}  {c['container']:<3} {c['path']}")
