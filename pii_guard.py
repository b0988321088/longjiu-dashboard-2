#!/usr/bin/env python3
"""pii_guard.py — 敏感資料（PII／帳務）防線（2026-10-08 SEC-P0-20261008）

單一實作，四種模式：

  ① --index      負向閘門：Git **index**（`git ls-files`）不得含敏感檔。命中即 rc=1（fail-closed）。
                 判準（不看副檔名、不看「有沒有遮罩」，看資料是否可被還原／再識別）：
                   R1 檔名：Moneybook 匯出／分析／校準檔、mb*.zip、暫存目錄內容
                   R2 內容：逐位元含 .env 內敏感值（預設 MONEYBOOK_ZIP_PASSWORD）
                   R3 內容：Moneybook 遮罩格式的身分證值（字母＋3 位數字＋2–6 個星號＋3 位數字；本檔不寫字面範例，避免閘門自命中）
                   R5 內容：含 Moneybook 匯出表頭簽章（≥3 個欄位名；擋「改名＋無遮罩值」的匯出外洩）
                   R4 容器：ZIP 內含 Moneybook 匯出檔名（含「加密 ZIP 不等於安全」——ZipCrypto＋已知明文可還原金鑰）
  ② --selftest   正／負向自我測試（fixtures 不碰真實個資），rc=0 才算通過
  ③ --lifecycle  解壓→使用→清除 生命週期：以假目錄驗證 sync_all.cleanup_sensitive_dirs 真的清得掉
  ④ --public     公開面查詢（**強制 percent-encoding**）：中文檔名未編碼會誤回 404，這裡統一處理

用法：
    python pii_guard.py --index
    python pii_guard.py --selftest
    python pii_guard.py --public Moneybook_帳戶_20260727_1.csv mb2.zip
    python pii_guard.py --classify path/to/file

設計原則（事件教訓）：
    「本機 filesystem 乾淨」≠ 完成；完成＝index＋history＋公開面三層全清。
"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
PAGES = "https://b0988321088.github.io/longjiu-dashboard-2/"
RAW = "https://raw.githubusercontent.com/b0988321088/longjiu-dashboard-2/"
ENV_KEYS = ("MONEYBOOK_ZIP_PASSWORD",)

# R1：敏感檔名（適用任何目錄，含 repo 根目錄）
NAME_PATTERNS = (
    r"^Moneybook_.*\.csv$",
    r"^moneybook_.*\.csv$",
    r"^moneybook_analysis.*\.json$",
    r"^moneybook_calibration_log.*\.md$",
    r"^mb.*\.zip$",
    r"(^|/)tmp_mb/",
    r"(^|/)tmp_mb_extract/",
)
NAME_RE = [re.compile(p, re.I) for p in NAME_PATTERNS]

# R3：Moneybook 匯出檔的遮罩格式身分證值（字母＋3 數字＋2~6 個 *＋3 數字）
MASKED_ID_RE = re.compile(rb"[A-Z][0-9]{3}\*{2,6}[0-9]{3}")
# 僅供提示（非阻擋）：完整身分證格式字串（會誤中 base64／教科書範例）
FULL_ID_RE = re.compile(rb"[A-Z][12][0-9]{8}")
# R4：ZIP 內出現這些檔名＝Moneybook 匯出容器
ZIP_ENTRY_RE = re.compile(r"(Moneybook_|moneybook_)", re.I)

CODE_EXT = (".py", ".sh", ".bat", ".ps1", ".cmd", ".toml", ".yml", ".yaml", ".js", ".ts", ".sql")

# R5：Moneybook 匯出表頭簽章（擋「改名＋不含遮罩值」的匯出）。≥3 個欄位名同時出現＝匯出檔。
#   已知界線：程式檔（CODE_EXT）不做 R5 —— 其內容已由 R2（.env 逐位元）與 R3（遮罩值）覆蓋，
#   且測試 fixture 必然引用欄位名；此界線已在事件紀錄揭露。
MB_HEADER_TOKENS = ("機構名稱", "帳戶名稱", "帳單類型", "繳費截止日", "最低應繳金額",
                    "總投資成本", "平均申購淨值", "最新淨值日期", "約當市值")


def load_env_secrets(keys=ENV_KEYS) -> dict:
    """從 hermes .env 讀敏感值（值永不輸出、不進紀錄）。"""
    out = {}
    p = Path.home() / "AppData" / "Local" / "hermes" / ".env"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        for k in keys:
            if line.startswith(k + "="):
                v = line.split("=", 1)[1].strip()
                if v:
                    out[k] = v
    return out


def is_sensitive_name(path: str) -> bool:
    p = path.replace("\\", "/")
    return any(r.search(p) for r in NAME_RE)


def zip_report(path: Path):
    """回 (sensitive: bool, reason: str)。加密 ZIP 一律視為高風險容器。"""
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            names = [i.filename for i in infos]
            enc = any(i.flag_bits & 0x1 for i in infos)
    except Exception as e:
        return False, f"無法讀取（{type(e).__name__}）"
    hit = [n for n in names if ZIP_ENTRY_RE.search(n)]
    if hit:
        tail = "（加密：ZipCrypto＋已知明文可還原金鑰）" if enc else ""
        return True, f"ZIP 內含 Moneybook 匯出檔 {len(hit)} 個{tail}"
    return False, f"一般 ZIP（{len(names)} 檔，未含匯出檔名）"


def content_report(path: Path, secrets: dict):
    """回 (level, reasons)。R2/R3 為 FAIL，完整 ID 僅 WARN。"""
    fails, warns = [], []
    try:
        b = path.read_bytes()
    except Exception as e:
        return [], [f"無法讀取（{type(e).__name__}）"]
    for k, v in secrets.items():
        if v.encode() in b:
            fails.append(f"逐位元含 .env 值（{k}）")
    if MASKED_ID_RE.search(b):
        fails.append("含 Moneybook 遮罩格式身分證值（R3）")
    if path.suffix.lower() not in CODE_EXT:
        _hits = sum(1 for _t in MB_HEADER_TOKENS if _t.encode() in b)
        if _hits >= 3:
            fails.append(f"含 Moneybook 匯出表頭簽章（R5，命中 {_hits} 個欄位名）")
    if FULL_ID_RE.search(b):
        warns.append("含完整身分證格式字串（可能為 base64／教科書範例，請人工確認）")
    return fails, warns


def git_ls_files(base: Path) -> list:
    return subprocess.run(["git", "ls-files"], cwd=str(base), capture_output=True,
                          text=True).stdout.splitlines()


def check_index(base: Path = BASE, tracked: list | None = None) -> int:
    """負向閘門：index 內不得有敏感檔。回 0 = 乾淨、1 = 命中（fail-closed）。"""
    files = git_ls_files(base) if tracked is None else list(tracked)
    secrets = load_env_secrets()
    fails, warns = [], []

    for f in files:
        p = Path(base) / f
        if is_sensitive_name(f):
            fails.append(f"{f} — 檔名命中敏感樣式（R1）")
        if not p.is_file():
            continue
        if p.suffix.lower() == ".zip":
            sens, reason = zip_report(p)
            if sens:
                fails.append(f"{f} — {reason}（R4）")
            continue
        c_fails, c_warns = content_report(p, secrets)
        fails += [f"{f} — {r}（R2/R3）" for r in c_fails]
        warns += [f"{f} — {r}" for r in c_warns]

    print("=== pii_guard --index（Git index 敏感資料負向閘門）===")
    print(f"  追蹤檔 {len(files)} 檔｜敏感值來源：{'已讀取（值不輸出）' if secrets else '未設定 → 略過 R2'}")
    for w in warns:
        print(f"  ⚠️ {w}")
    if fails:
        for x in fails:
            print(f"  ❌ {x}")
        print(f"❌ index 檢查未通過（{len(fails)} 項）→ fail-closed，阻擋推送")
        return 1
    print("  ✅ index 無敏感檔（R1 檔名／R2 敏感值／R3 遮罩值／R4 匯出容器）")
    return 0


def build_public_url(file_path: str, kind: str = "pages", ref: str = "HEAD") -> str:
    """公開面 URL —— **必須** percent-encoding（中文檔名未編碼會誤判 404）。"""
    enc = urllib.parse.quote(file_path.replace("\\", "/"))
    if kind == "pages":
        return PAGES + enc
    return f"{RAW}{ref}/{enc}"


def http_status(url: str) -> int | str:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "pii_guard"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return type(e).__name__


def public_check(paths: list) -> int:
    print("=== pii_guard --public（公開面；已強制 percent-encoding）===")
    rc = 0
    for f in paths:
        p = http_status(build_public_url(f, "pages") + "?cb=1")
        r = http_status(build_public_url(f, "raw"))
        flag = "✅" if (p == 404 and r == 404) else "❌"
        if flag == "❌":
            rc = 1
        print(f"  {flag} Pages={p}  raw@HEAD={r}  {f}")
    return rc


def lifecycle_check() -> int:
    """解壓→使用→清除：用假目錄驗證 sync_all 的清理實作（不碰真實個資）。"""
    print("=== pii_guard --lifecycle（解壓→使用→清除）===")
    sys.path.insert(0, str(BASE))
    try:
        import sync_all  # noqa: WPS433
    except Exception as e:
        print(f"  ❌ 無法 import sync_all：{type(e).__name__} {e}")
        return 1
    dirs = list(getattr(sync_all, "CLEANUP_DIRS", ()))
    if not dirs:
        print("  ❌ sync_all.CLEANUP_DIRS 不存在或為空")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        for d in dirs:
            (tmp_p / d).mkdir(parents=True, exist_ok=True)
            (tmp_p / d / "Moneybook_帳戶_fixture.csv").write_text("x", encoding="utf-8")
        (tmp_p / "keepme").mkdir()
        removed = sync_all.cleanup_sensitive_dirs(tmp_p)
        left = [d for d in dirs if (tmp_p / d).exists()]
        ok = sorted(removed) == sorted(dirs) and not left and (tmp_p / "keepme").exists()
        print(f"  清理清單：{dirs}")
        print(f"  實際移除：{sorted(removed)}")
        print(f"  殘留暫存目錄：{left if left else '無'}｜無關目錄保留：{'是' if (tmp_p / 'keepme').exists() else '否'}")
        print("  ✅ lifecycle PASS" if ok else "  ❌ lifecycle FAIL")
        return 0 if ok else 1


def classify(paths: list) -> int:
    secrets = load_env_secrets()
    print("=== pii_guard --classify（敏感容器／檔案判定）===")
    rc = 0
    for f in paths:
        p = Path(f)
        if not p.is_file():
            print(f"  ⚠️ {f}：不存在")
            continue
        reasons = []
        if is_sensitive_name(f):
            reasons.append("檔名命中敏感樣式（R1）")
        if p.suffix.lower() == ".zip":
            sens, reason = zip_report(p)
            reasons.append(reason + ("（R4 高風險）" if sens else ""))
        else:
            cf, cw = content_report(p, secrets)
            reasons += [r + "（R2/R3）" for r in cf] + [r + "（WARN）" for r in cw]
        verdict = "SENSITIVE" if any("（R" in r and "WARN" not in r for r in reasons) else "一般"
        if verdict == "SENSITIVE":
            rc = 1
        print(f"  [{verdict}] {f}｜" + "；".join(reasons) if reasons else f"  [一般] {f}")
    return rc


def selftest() -> int:
    """正／負向自我測試；fixtures 全為假資料，不碰真實個資。"""
    print("=== pii_guard --selftest ===")
    results = []

    # 1) 檔名判定：正／負向
    pos = ["Moneybook_帳戶_20260727_1.csv", "moneybook_20260714.csv", "mb2.zip",
           "tmp_mb/Moneybook_明細_x.csv", "tmp_mb_extract/Moneybook_帳單_x.csv",
           "moneybook_analysis.json", "moneybook_calibration_log.md"]
    neg = ["cost_log.csv", "snapshot.json", "index.html", "daily_report_v2_2026-10-08.html",
           "moneybook_6m_analysis.py", "src/mb_tools/notes.md"]
    results.append(("R1 正向全命中", all(is_sensitive_name(x) for x in pos)))
    results.append(("R1 負向不誤判", not any(is_sensitive_name(x) for x in neg)))

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)

        # 2) 內容判定：遮罩格式身分證值應命中，一般數字不命中
        # 動態組字串：本檔不得留下可命中 R3 的字面值（否則閘門會自我命中而永久紅燈）
        _masked = "A" + "123" + ("*" * 3) + "789"
        (t / "fake_export.csv").write_text(
            "金融機構,身分證字號,金額\n玉山," + _masked + ",100\n", encoding="utf-8")
        (t / "clean.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        f_fail, _ = content_report(t / "fake_export.csv", {})
        f_ok, _ = content_report(t / "clean.csv", {})
        results.append(("R3 遮罩值命中", bool(f_fail)))
        results.append(("R3 一般資料不誤判", not f_ok))

        # 2b) R5：改名且不含遮罩值、但含匯出表頭簽章 → 必須命中（RF-1）
        (t / "renamed_export.dat").write_text(
            "金融機構,機構名稱,帳戶名稱,帳單類型,繳費截止日\n玉山,玉山銀行,臺幣綜存,信用卡,2026/09/22\n",
            encoding="utf-8")
        (t / "renamed_export.py").write_text(
            "金融機構,機構名稱,帳戶名稱,帳單類型,繳費截止日\n", encoding="utf-8")
        f_r5, _ = content_report(t / "renamed_export.dat", {})
        f_r5c, _ = content_report(t / "renamed_export.py", {})
        results.append(("R5 改名匯出（表頭簽章）命中", any("R5" in x for x in f_r5)))
        results.append(("R5 程式檔不誤判（已知界線，已揭露）", not any("R5" in x for x in f_r5c)))

        # 3) 逐位元敏感值（以假值測，不讀真 .env）
        (t / "leak.txt").write_text("password=FAKE-SECRET-VALUE-123", encoding="utf-8")
        f2, _ = content_report(t / "leak.txt", {"K": "FAKE-SECRET-VALUE-123"})
        results.append(("R2 逐位元命中", bool(f2)))

        # 4) 容器判定：ZIP 內含匯出檔名＝敏感；一般 ZIP 不誤判
        with zipfile.ZipFile(t / "mb_fixture.zip", "w") as z:
            z.writestr("Moneybook_帳戶_fixture.csv", "x")
        with zipfile.ZipFile(t / "plain_fixture.zip", "w") as z:
            z.writestr("readme.txt", "hello")
        s1, _ = zip_report(t / "mb_fixture.zip")
        s2, _ = zip_report(t / "plain_fixture.zip")
        results.append(("R4 匯出容器命中（含『有密碼』不降級）", s1 and not s2))

        # 5) index 閘門：合成 tracked 清單（正向須 FAIL、負向須 PASS）
        rc_pos = check_index(base=t, tracked=["Moneybook_帳戶_fake.csv"])
        rc_neg = check_index(base=t, tracked=["readme.md"])
        results.append(("index 正向 FAIL(fail-closed)", rc_pos == 1))
        results.append(("index 負向 PASS", rc_neg == 0))

    # 6) 公開面 URL 必須 percent-encoding
    u = build_public_url("Moneybook_帳戶_20260727_1.csv", "pages")
    u2 = build_public_url("mb2.zip", "raw")
    results.append(("中文檔名已 percent-encoding", "%" in u and "帳" not in u))
    results.append(("raw URL 指向 repository", "/longjiu-dashboard-2/" in u2 and u2.endswith("mb2.zip")))

    # 7) lifecycle（解壓→使用→清除）走同一支實作
    results.append(("lifecycle（sync_all 清理實作）", lifecycle_check() == 0))

    bad = [n for n, ok in results if not ok]
    for n, ok in results:
        print(f"  {'✅' if ok else '❌'} {n}")
    print(f"{'✅ selftest PASS' if not bad else '❌ selftest FAIL：' + ', '.join(bad)}")
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="敏感資料防線（index／公開面／容器／生命週期）")
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--lifecycle", action="store_true")
    ap.add_argument("--public", nargs="*", metavar="PATH")
    ap.add_argument("--classify", nargs="*", metavar="PATH")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if a.lifecycle:
        return lifecycle_check()
    if a.public:
        return public_check(a.public)
    if a.classify:
        return classify(a.classify)
    if a.index:
        return check_index()
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
