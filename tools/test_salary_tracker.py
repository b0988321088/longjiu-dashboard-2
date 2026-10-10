# -*- coding: utf-8 -*-
"""tools/test_salary_tracker.py — salary_tracker.py 驗收（相對式斷言，不寫死當期真值以外的期望）

驗收矩陣：
  A 單元：辨識（台電薪資／分類=薪資但非台電／一般列）
  B 單元：日期正規化、常態中位數
  C 單元：plan_updates 五分支（no-op／不符不覆蓋／同月兩筆不寫／新月份寫入／偏離>30% 寫入+WARN）
  D 回放：兩份歷史匯出（2026-09-02、2026-10-09）→ 偵測值必須與 snapshot.salary_records 現值一致且 no-op
  E 負向（端到端 fail-closed）：注入同月第二筆薪資 → run(--apply) 必須 0 寫入且 snapshot 位元不變
  F 正向（端到端寫入）：合成新月份 → 寫入正確、其他月份不動、CRLF 維持

跑法：python tools/test_salary_tracker.py    （FAIL 時 exit 1）
"""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import pyzipper                      # noqa: E402
import mb_source                     # noqa: E402
import salary_tracker as st          # noqa: E402

PASS, FAIL = [], []
MB_CACHE = Path.home() / "AppData" / "Local" / "hermes" / "cache" / "documents"


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'✅' if cond else '❌'} {name}" + (f"  ← {detail}" if detail and not cond else ""))


def _row(memo, cat="薪資", amount="39777.00", d="2026/10/06"):
    return {"機構名稱": "台新銀行", "帳戶名稱": "文心綜活儲存款-薪轉", "分類": cat,
            "明細描述": memo, "金額": amount, "消費日": d, "入帳日": d}


def _zip_from_rows(rows_csv_text: str, dest: Path, member="Moneybook_明細_20261009_1.csv"):
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member, rows_csv_text)


def read_zip_member(zip_path: Path, kind="明細") -> str:
    pw = mb_source.get_password()
    with pyzipper.AESZipFile(zip_path, "r") as zf:
        zf.pwd = pw.encode()
        name = next(m for m in zf.namelist() if kind in m)
        return zf.read(name).decode("utf-8-sig", "replace")


# ---------- A 辨識 ----------
check("A1 台電薪資列辨識", st.is_tpc_salary(_row("媒體轉入 - 薪資 台電 03795904")))
check("A2 分類=薪資但為顧問公司匯入 → 非台電薪資",
      not st.is_tpc_salary(_row("fxml入帳 - 上境工程設計顧問有限公司005/00012345678901266")) and
      st.salary_category_but_other(_row("fxml入帳 - 上境工程設計顧問有限公司005/00012345678901266")))
check("A3 一般消費列不誤判",
      not st.is_tpc_salary(_row("全支付—巧味牛雜湯 - 2106", cat="飲食", amount="-170")))

# ---------- B 日期／基準 ----------
check("B1 日期 YYYY/MM/DD", st._norm_date("2026/10/06") == "2026-10-06")
check("B2 日期 M/D/YYYY（帳戶 CSV 舊格式）", st._norm_date("10/6/2026") == "2026-10-06")
check("B3 日期無法解析回空字串", st._norm_date("--") == "" and st._norm_date("") == "")
check("B4 中位數樣本 <2 回 None", st._baseline_median({"2026-09": {"amount": 42560}}, "2026-10") is None)
_med = st._baseline_median({"2026-07": {"amount": 1}, "2026-08": {"amount": 39727},
                            "2026-09": {"amount": 42560}}, "2026-10")
check("B5 中位數取近 3 月（含目標月之前）", _med == 39727, f"got={_med}")

# ---------- C plan_updates 分支 ----------
_ok_recs = {"2026-10": {"amount": 39777, "date": "2026-10-06"}}
_u, _w, _i = st.plan_updates(_ok_recs, st.detect([_row("媒體轉入 - 薪資 台電 03795904")])[0])
check("C1 既有相同 → no-op（無 update）", not _u and not _w and len(_i) == 1, f"u={_u} w={_w}")

_u, _w, _i = st.plan_updates({"2026-10": {"amount": 10000, "date": "2026-10-01"}},
                             st.detect([_row("媒體轉入 - 薪資 台電 03795904")])[0])
check("C2 既有不符 → 不覆蓋 + WARN", not _u and len(_w) == 1)

_dupe = st.detect([_row("媒體轉入 - 薪資 台電 03795904"),
                   _row("媒體轉入 - 薪資 台電 年終獎金", amount="120000.00", d="2026/10/20")])[0]
_u, _w, _i = st.plan_updates({}, _dupe)
check("C3 同月兩筆 → 不寫入 + WARN", not _u and len(_w) == 1 and "2 筆" in _w[0])

_u, _w, _i = st.plan_updates({}, st.detect([_row("媒體轉入 - 薪資 台電 03795904")])[0])
check("C4 新月份 → 寫入（amount/date/source）",
      len(_u) == 1 and _u[0]["month"] == "2026-10" and _u[0]["value"]["amount"] == 39777
      and _u[0]["value"]["date"] == "2026-10-06" and _u[0]["value"]["source"] == "mb_auto")

_base = {"2026-07": {"amount": 39727}, "2026-08": {"amount": 39727}, "2026-09": {"amount": 42560}}
_u, _w, _i = st.plan_updates(_base, st.detect([_row("媒體轉入 - 薪資 台電 03795904", amount="60000.00")])[0])
check("C5 偏離常態 >30% → 仍寫入但 WARN", len(_u) == 1 and any("偏離" in x for x in _w))

_u, _w, _i = st.plan_updates({}, st.detect([
    _row("fxml入帳 - 上境工程設計顧問有限公司005/00012345678901266", amount="332342.00", d="2026/10/07")])[0])
check("C6 分類=薪資但非台電 → 不寫入、不 WARN（僅 ℹ️）", not _u and not _w and len(_i) == 0)

# ---------- D 回放歷史匯出 ----------
snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
live = snap.get("salary_records", {}) or {}

for label, extra in (("2026-09-02 匯出", MB_CACHE / "mb_0902"), ("2026-10-09 匯出", MB_CACHE)):
    try:
        meta = mb_source.load_or_raise("明細", extra_dirs=[extra], include_default=False)
    except mb_source.MBSourceError as e:
        check(f"D[{label}] 可載入", False, str(e))
        continue
    det, oth = st.detect(meta["rows"])
    u, w, i = st.plan_updates(live, det)
    months = sorted(d["month"] for d in det)
    check(f"D[{label}] 偵測台電薪資 {len(det)} 筆 ({','.join(months) or '無'})", len(det) >= 1)
    ok = all(not _u for _u in [u]) and not w
    check(f"D[{label}] 與 snapshot 現值一致 → 全 no-op、無 WARN", ok,
          f"updates={u} warn={w}")
    if label.startswith("2026-09-02"):
        check("D2 顧問公司匯入（上境 332,342）被列為 ℹ️ 而非寫入",
              any("上境" in o["memo"] for o in oth))

# ---------- E 負向：注入同月第二筆薪資 → fail-closed ----------
tmp = Path(tempfile.mkdtemp(prefix="salary_tracker_test_"))
try:
    raw = read_zip_member(MB_CACHE / "doc_5a33ee791456_Moneybook_明細_20261009.zip")
    lines = raw.rstrip().splitlines()                     # 通用換行，不受 CRLF/LF 影響
    dupe = next(l for l in lines if "薪資 台電" in l).replace("2026/10/06", "2026/10/20")  # 模擬同月獎金/補發
    injected = "\n".join(lines + [dupe]) + "\n"
    zpath = tmp / "Moneybook_明細_20261009_1.zip"
    _zip_from_rows(injected, zpath)

    snap_copy = tmp / "snapshot.json"
    shutil.copy(BASE / "snapshot.json", snap_copy)
    before = snap_copy.read_bytes()

    class FakeMB:
        """只換來源目錄，其餘行為沿用真 mb_source（含 describe 與例外型別）。"""

        load_or_raise = staticmethod(
            lambda kind, **kw: mb_source.load_or_raise(kind, extra_dirs=[tmp], include_default=False))
        describe = staticmethod(mb_source.describe)
        MBSourceError = mb_source.MBSourceError

    real_mb, real_snap = st.mb_source, st.SNAP_PATH
    st.mb_source, st.SNAP_PATH = FakeMB, snap_copy
    try:
        rc = st.run(apply=True)
    finally:
        st.mb_source, st.SNAP_PATH = real_mb, real_snap
    after = snap_copy.read_bytes()
    check("E1 注入同月第二筆 → run(apply) 仍 exit 0（契約成功）", rc == 0, f"rc={rc}")
    check("E2 fail-closed：snapshot 位元未變（0 寫入）", before == after)
    d2 = json.loads(after.decode("utf-8"))
    check("E3 既有 2026-10 未被覆蓋", (d2.get("salary_records", {}).get("2026-10") or {}).get("amount") == 39777)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---------- F 正向：合成新月份 → 寫入且不擾其他月份 ----------
tmp = Path(tempfile.mkdtemp(prefix="salary_tracker_test_"))
try:
    hdr = ("金融機構/手動新增,身分證字號,機構名稱,帳戶名稱,分類,明細描述,幣別,金額,消費日,入帳日,標籤,備註,帳戶停用時間")
    body = ("Moneybook,,台新銀行,文心綜活儲存款-薪轉,薪資,媒體轉入 - 薪資 台電 03795904,TWD,"
            "41000.00,2026/11/06,2026/11/06,,")
    _zip_from_rows(hdr + "\r\n" + body + "\r\n", tmp / "Moneybook_明細_20261106_1.zip",
                   member="Moneybook_明細_20261106_1.csv")
    snap_copy = tmp / "snapshot.json"
    shutil.copy(BASE / "snapshot.json", snap_copy)

    class FakeMB:
        """只換來源目錄，其餘行為沿用真 mb_source（含 describe 與例外型別）。"""

        load_or_raise = staticmethod(
            lambda kind, **kw: mb_source.load_or_raise(kind, extra_dirs=[tmp], include_default=False))
        describe = staticmethod(mb_source.describe)
        MBSourceError = mb_source.MBSourceError

    real_mb, real_snap = st.mb_source, st.SNAP_PATH
    st.mb_source, st.SNAP_PATH = FakeMB, snap_copy
    try:
        rc = st.run(apply=True)
    finally:
        st.mb_source, st.SNAP_PATH = real_mb, real_snap
    b = snap_copy.read_bytes()
    d3 = json.loads(b.decode("utf-8"))
    sr = d3.get("salary_records", {})
    check("F1 新月份寫入成功", rc == 0 and (sr.get("2026-11") or {}).get("amount") == 41000, f"rc={rc}")
    check("F2 既有月份未動（2026-10 仍 39,777）", (sr.get("2026-10") or {}).get("amount") == 39777)
    check("F3 未觸碰模型層欄位", d3.get("monthly_salary") == snap.get("monthly_salary")
          and d3.get("monthly_income") == snap.get("monthly_income")
          and d3.get("working_surplus") == snap.get("working_surplus"))
    check("F4 檔案維持 CRLF 且 JSON 可解析", b.count(b"\r\n") > 0 and b.count(b"\r\n") == b.count(b"\n"))
    check("F5 來源戳記落地", (d3.get("salary_records_source", {}).get("mb_auto_last_run", {}) or {}).get("written") == ["2026-11"])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
print(f"{len(PASS)}/{len(PASS) + len(FAIL)} PASS" + (f"，FAIL：{FAIL}" if FAIL else ""))
sys.exit(1 if FAIL else 0)
