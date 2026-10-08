#!/usr/bin/env python3
"""mb_source_selftest.py — Moneybook 匯入契約的正／負向測試（2026-10-08 ②-budget）

覆蓋使用者指定的 5 個 case：
  T1 ZIP 存在                     → 能讀（且為 **記憶體解壓**，AES 加密真檔往返）
  T2 ZIP 不存在、合法 CSV 在暫存區 → 能讀
  T3 舊 9/2 CSV 與新 10/8 ZIP 並存 → 必須選 10/8（且是 ZIP 內的資料，不是舊 CSV）
  T4 解壓後不得落地／不得進 Git index
  T5 sync cleanup 不得破壞下一輪必要輸入契約（外部 ZIP 不受清理影響）

fixtures 全為假資料、假密碼；不讀真實憑證、不碰真實個資。
用法：python mb_source_selftest.py
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import mb_source  # noqa: E402

FIXTURE_PW = "fixture-pw-not-real"

BILL_HDR = "金融機構,帳單類型,帳單金額,最低應繳金額,繳費截止日\n"
ACCT_HDR = "機構名稱,帳戶名稱,幣別,帳戶金額\n"


def _bill_csv(yushan_amt: int, due: str = "2026/09/22") -> str:
    return BILL_HDR + (
        f"玉山銀行,信用卡,{yushan_amt},2591,{due}\n"
        f"永豐銀行,信用卡,18715,1873,2026/09/30\n"
        f"台北富邦,信用卡,3475,3475,2026/03/09\n")


def _acct_csv() -> str:
    return ACCT_HDR + (
        "玉山銀行,臺幣綜存,TWD,40044\n"
        "台北富邦,信用卡,TWD,-23464\n")


def _write_aes_zip(path: Path, members: dict, pw: str = FIXTURE_PW) -> None:
    """寫一個 AES 加密 ZIP（真加密，用於驗證記憶體解壓路徑）。"""
    import pyzipper
    with pyzipper.AESZipFile(path, "w", compression=zipfile.ZIP_DEFLATED,
                             encryption=pyzipper.WZ_AES) as zf:
        zf.setpassword(pw.encode())
        for name, text in members.items():
            zf.writestr(name, text.encode("utf-8-sig"))


def _write_plain_zip(path: Path, members: dict) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in members.items():
            zf.writestr(name, text.encode("utf-8-sig"))


def _snapshot(base: Path) -> set:
    return {str(p) for p in base.rglob("*") if p.is_file()}


def main() -> int:
    results = []
    os.environ["MONEYBOOK_ZIP_PASSWORD"] = FIXTURE_PW  # fixture 假密碼（不讀真實 .env 值）

    with tempfile.TemporaryDirectory() as t1:
        stage, ext = Path(t1) / "stage", Path(t1) / "external"
        stage.mkdir(); ext.mkdir()

        # ── T1：只有 ZIP（AES 加密）→ 能讀，且 container=zip
        (ext / "Moneybook_明細_20261008_1.zip").unlink(missing_ok=True)
        _write_aes_zip(ext / "Moneybook_明細_20261008_1.zip",
                       {"Moneybook_帳單_20261008_1.csv": _bill_csv(25906),
                        "Moneybook_帳戶_20261008_1.csv": _acct_csv()})
        d = mb_source.load("帳單", extra_dirs=[ext], include_default=False)
        ok = bool(d) and d["container"] == "zip" and d["export_date"] == "2026-10-08" and len(d["rows"]) == 3
        results.append(("T1 ZIP(AES) 存在→能讀（記憶體解壓）", ok))

        # ── T2：沒有 ZIP，只有合法 CSV 在標準暫存區 → 能讀
        stage2 = Path(t1) / "stage2"; stage2.mkdir()
        (stage2 / "Moneybook_帳單_20260902_1.csv").write_text(_bill_csv(11252), encoding="utf-8-sig")
        d2 = mb_source.load("帳單", extra_dirs=[stage2], include_default=False)
        ok = bool(d2) and d2["container"] == "csv" and d2["export_date"] == "2026-09-02"
        results.append(("T2 無 ZIP、暫存區有合法 CSV→能讀", ok))

        # ── T3：舊 9/2 CSV 與新 10/8 ZIP 並存 → 選 10/8（且取 ZIP 內的值 25906，非舊 CSV 的 11252）
        stage3 = Path(t1) / "stage3"; stage3.mkdir()
        (stage3 / "Moneybook_帳單_20260902_1.csv").write_text(_bill_csv(11252), encoding="utf-8-sig")
        ext3 = Path(t1) / "ext3"; ext3.mkdir()
        _write_plain_zip(ext3 / "Moneybook_明細_20261008_1.zip",
                         {"Moneybook_帳單_20261008_1.csv": _bill_csv(25906, "2026/10/19")})
        d3 = mb_source.load("帳單", extra_dirs=[stage3, ext3], include_default=False)
        amt = next((r["帳單金額"] for r in d3["rows"] if r["金融機構"] == "玉山銀行"), None)
        ok = d3["export_date"] == "2026-10-08" and d3["container"] == "zip" and amt == "25906"
        results.append(("T3 舊 CSV＋新 ZIP 並存→選新 ZIP（值來自 ZIP）", ok))

        # 同日 ZIP 與 CSV → ZIP 優先（原始優於解壓副本）
        stage4 = Path(t1) / "stage4"; stage4.mkdir()
        (stage4 / "Moneybook_帳單_20261008_1.csv").write_text(_bill_csv(11111), encoding="utf-8-sig")
        _write_plain_zip(stage4 / "Moneybook_明細_20261008_1.zip",
                         {"Moneybook_帳單_20261008_1.csv": _bill_csv(25906)})
        d4 = mb_source.load("帳單", extra_dirs=[stage4], include_default=False)
        results.append(("T3b 同日 ZIP 優先於 CSV", d4["container"] == "zip"))

        # ── T4：讀取不得落地（fixture 外部 ZIP 讀完後，stage 內不得多出解壓檔）
        before = _snapshot(stage4)
        mb_source.load("帳單", extra_dirs=[stage4], include_default=False)
        results.append(("T4a 記憶體解壓（stage 無新增檔案）", _snapshot(stage4) == before))
        try:
            import pii_guard  # noqa: E402
            results.append(("T4b Git index 無敏感檔（pii_guard --index）", pii_guard.check_index() == 0))
        except Exception as e:
            results.append((f"T4b pii_guard 不可用（{type(e).__name__}）", False))

        # ── T5：sync cleanup 不得破壞必要輸入契約（外部 ZIP 不受影響，清理後仍讀得到）
        stage5 = Path(t1) / "stage5"; stage5.mkdir()
        ext5 = Path(t1) / "ext5"; ext5.mkdir()
        _write_plain_zip(ext5 / "Moneybook_明細_20261008_1.zip",
                         {"Moneybook_帳單_20261008_1.csv": _bill_csv(25906),
                          "Moneybook_帳戶_20261008_1.csv": _acct_csv()})
        import sync_all  # noqa: E402
        for dname in sync_all.CLEANUP_DIRS:
            (stage5 / dname).mkdir(parents=True, exist_ok=True)
            (stage5 / dname / "Moneybook_帳單_20261008_1.csv").write_text(_bill_csv(999), encoding="utf-8-sig")
        removed = sync_all.cleanup_sensitive_dirs(stage5)
        left = [d for d in sync_all.CLEANUP_DIRS if (stage5 / d).exists()]
        still_reads = bool(mb_source.load("帳單", extra_dirs=[stage5, ext5], include_default=False))
        ok = len(removed) == len(sync_all.CLEANUP_DIRS) and not left and still_reads \
            and (ext5 / "Moneybook_明細_20261008_1.zip").exists()
        results.append(("T5 cleanup 後契約仍成立（外部 ZIP 為 canonical）", ok))

        # ── T6（CIO RF-2）：最新 ZIP 損壞（中央目錄讀不到）→ 必須 fail-closed，不得靜默退回舊 CSV
        stage6 = Path(t1) / "stage6"; stage6.mkdir()
        (stage6 / "Moneybook_帳單_20260902_1.csv").write_text(_bill_csv(11252), encoding="utf-8-sig")
        (stage6 / "Moneybook_明細_20261008_1.zip").write_bytes(b"NOT-A-ZIP-CORRUPT")
        try:
            _d6 = mb_source.load("帳單", extra_dirs=[stage6], include_default=False)
            t6_ok = False       # 不該回傳任何東西（尤其不得回舊 CSV）
        except mb_source.MBSourceError as e:
            t6_ok = (getattr(e, "code", None) == "ZIP_UNREADABLE") or ("ZIP_UNREADABLE" in str(e))
        results.append(("T6 最新 ZIP 損壞→fail-closed（不退回舊 CSV）", t6_ok))

    bad = [n for n, ok in results if not ok]
    print("=== mb_source_selftest（MB 匯入契約）===")
    for n, ok in results:
        print(f"  {'✅' if ok else '❌'} {n}")
    print(f"{'✅ PASS' if not bad else '❌ FAIL：' + ', '.join(bad)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
