"""safe_read.py — 財務檔案安全讀取層（PII 遮蔽）

為什麼存在：DeepSeek 的內容過濾（HTTP 400 "Content Exists Risk"）會擋掉含
識別碼格式字串的 payload。2026-09-16 單日 151 筆 CER、跨 6 個 session，
主因是財務原始檔（Moneybook CSV、snapshot.json、保單轉出文字）原樣進 context。
把敏感格式在「進 context 前」遮掉，是唯一能治本又不花錢的作法。

用法：
    from safe_read import sanitize, read_sanitized, read_csv_rows
    text = read_sanitized('moneybook/Moneybook_明細_20260916_1.csv')
    rows = read_csv_rows('moneybook/Moneybook_明細_20260916_1.csv', limit=50)

CLI：
    python safe_read.py <file> [--csv] [--limit N]     # 印出遮罩後內容
    python safe_read.py --audit <file>                 # 只印命中統計（不輸出內容）
    python safe_read.py --selftest                     # 規則自我驗證

鐵則：金額、日期、股數、代號、百分比一律不動；只遮「識別碼型」字串。
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys

__all__ = ["sanitize", "read_sanitized", "read_csv_rows", "audit_file", "RULES"]

MASK_CHAR = "*"


def _mask(token: str) -> str:
    """保留前 3 後 2，其餘遮罩；太短則全遮。"""
    if len(token) <= 6:
        return MASK_CHAR * len(token)
    return token[:3] + MASK_CHAR * (len(token) - 5) + token[-2:]


# 順序即優先序：憑證類最前（避免被數字規則先切走），識別碼型在後。
RULES: list[tuple[str, re.Pattern[str]]] = [
    # —— 憑證 / 金鑰 ——
    ("credential", re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_\-]{12,}\b")),
    ("credential", re.compile(r"\bAIza[0-9A-Za-z_\-]{25,}\b")),
    ("credential", re.compile(r"\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{20,}\b")),
    ("credential", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("credential", re.compile(r"\bxox[bpoars]-[A-Za-z0-9\-]{10,}\b")),
    ("credential", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("credential", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{6,}\b")),
    ("credential", re.compile(r"(?i)\b(?:bearer|token|api[_-]?key|password|passwd|secret)\s*[:=]?\s*[A-Za-z0-9_\-\.]{16,}")),
    # —— 身分識別 ——
    ("tw_id", re.compile(r"\b[A-Z][12]\d{8}\b")),
    ("email", re.compile(r"\b([A-Za-z0-9._%+\-]{2,})@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")),
    ("mobile", re.compile(r"\b09\d{2}[- ]?\d{3}[- ]?\d{3}\b")),
    # —— 帳號 / 卡號（只抓 >=12 位數，且不碰小數；避免動到金額/百分比）——
    ("account_no", re.compile(r"(?<![\d.])(?:\d{4}[-\s]){3}\d{4}(?![\d.])")),
    ("account_no", re.compile(r"(?<![\d.])\d{12,19}(?![\d.])")),
]


def sanitize(text: str) -> str:
    """遮罩敏感格式，回傳乾淨文字（金額/日期/代號不變）。"""
    return sanitize_with_stats(text)[0]


def sanitize_with_stats(text: str) -> tuple[str, dict[str, int]]:
    stats: dict[str, int] = {}
    out = text
    for label, pat in RULES:
        if label == "email":
            def _em(m: re.Match[str]) -> str:
                stats[label] = stats.get(label, 0) + 1
                # 整個 local part 一律換掉：保留前後字元會殘留 5 碼，也會被自己的規則再命中
                return "***@" + m.group(2)
            out = pat.sub(_em, out)
            continue

        def _sub(m: re.Match[str]) -> str:
            stats[label] = stats.get(label, 0) + 1
            return _mask(m.group(0))

        out = pat.sub(_sub, out)
    return out, stats


def _read_text(path: str) -> tuple[str, str]:
    """嘗試常見編碼（Moneybook 匯出多為 utf-8-sig 或 cp950）。"""
    for enc in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            with open(path, encoding=enc) as fh:
                return fh.read(), enc
        except (UnicodeDecodeError, LookupError):
            continue
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read(), "utf-8/replace"


def read_sanitized(path: str) -> str:
    """讀檔後遮罩，回傳可直接進 context 的文字。"""
    text, _enc = _read_text(path)
    return sanitize(text)


def read_csv_rows(path: str, limit: int | None = None, columns: list[str] | None = None) -> list[dict[str, str]]:
    """以結構化方式讀 CSV（比全文更安全），每個欄位值都遮罩。"""
    text, _enc = _read_text(path)
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, str]] = []
    for i, row in enumerate(reader):
        if limit is not None and i >= limit:
            break
        cells = row if columns is None else {k: row.get(k, "") for k in columns}
        rows.append({(k or ""): sanitize(v or "") for k, v in cells.items()})
    return rows


def audit_file(path: str) -> dict[str, int]:
    """只算命中數，不輸出任何內容（可安全貼回對話）。"""
    text, enc = _read_text(path)
    _clean, stats = sanitize_with_stats(text)
    stats = dict(stats)
    stats["_bytes"] = os.path.getsize(path)
    stats["_encoding"] = enc  # type: ignore[assignment]
    return stats


def _selftest() -> int:
    cases = [
        ("A123456789", False),          # 身分證
        ("F298765432", False),
        ("0412345678901234", False),    # 16 位帳號
        ("5194-1234-5678-9012", False),  # 卡號
        ("sk-abcdefghijklmnop1234", False),
        ("AIzaSyA1234567890abcdefghijklmnopqrs", False),
        ("ghp_abcdefghijklmnopqrstuvwxyz0123456789", False),
        ("user@example.com", False),
        ("0912-345-678", False),
        # 這些必須原封不動
        ("25,972,350", True),
        ("-23706.00", True),
        ("2026/06/29", True),
        ("56.84402960750934", True),
        ("0050", True),
        ("2330", True),
        ("20260916_154945", True),
        ("TWD", True),
    ]
    ok = True
    for raw, must_survive in cases:
        out = sanitize(raw)
        intact = raw in out
        good = intact if must_survive else (raw not in out)
        if not good:
            ok = False
        print(f"{'PASS' if good else 'FAIL'}  {'保留' if must_survive else '遮罩'}  {raw!r} -> {out!r}")
    # 冪等性
    s1 = sanitize("帳號 0412345678901234 金額 -23706.00")
    s2 = sanitize(s1)
    print(f"{'PASS' if s1 == s2 else 'FAIL'}  冪等性  {s1!r}")
    ok = ok and s1 == s2
    s3 = sanitize("聯絡 ***@cathaybk.com.tw")
    print(f"{'PASS' if s3 == '聯絡 ***@cathaybk.com.tw' else 'FAIL'}  已遮罩 email 不再被規則命中  {s3!r}")
    ok = ok and s3 == "聯絡 ***@cathaybk.com.tw"
    print("SELFTEST", "ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--selftest":
        return _selftest()
    as_csv = "--csv" in argv
    as_audit = "--audit" in argv
    limit = None
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    path = next((a for a in argv if not a.startswith("--") and not a.isdigit()), None)
    if not path or not os.path.exists(path):
        print(f"file not found: {path}")
        return 2
    if as_audit:
        print(f"{path}: {audit_file(path)}")
        return 0
    if as_csv:
        rows = read_csv_rows(path, limit=limit)
        for r in rows:
            print(r)
        return 0
    out = read_sanitized(path)
    print(out if limit is None else "\n".join(out.splitlines()[:limit]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
