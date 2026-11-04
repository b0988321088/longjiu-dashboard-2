#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/test_history_schema_completeness.py — B1／R2 asset_diff_history 鍵集完整性（2026-10-15）

驗證行為：
  H1 `append_today()` 產出的當日條目**必含 `bonds`**（原本缺鍵 → 當日 18 鍵、前一日 19 鍵）。
  H2 `bonds` 取自有明確規則的來源：DB 同日列 → DB 最新列 → snapshot.bonds。
  H3 兩者皆無有效值 → **raise**（不得以 0 掩蓋資料缺失）。
  H4 今日鍵集必須涵蓋前一日鍵集（缺鍵會顯式 WARN，不靜默）。

負向自測：H4 的檢查器對「舊行為樣本（去掉 bonds 的 dict）」必須報出缺鍵，證明斷言有鑑別力。

全程離線：SQLite 與 history 檔皆建在臨時目錄（每階段各自獨立目錄），不動真 repo／真 DB。
執行：python -X utf8 tools/test_history_schema_completeness.py
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PASS = FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _mkdb(path: Path, rows: list[tuple[str, object]]) -> None:
    con = sqlite3.connect(str(path))
    try:
        con.execute("CREATE TABLE IF NOT EXISTS assets (date TEXT PRIMARY KEY, cash_total REAL,"
                    " bonds REAL, securities REAL, insurance REAL, funds REAL, real_estate REAL,"
                    " total_assets REAL, total_liabilities REAL, created_at TEXT)")
        for d, b in rows:
            con.execute("INSERT OR REPLACE INTO assets (date, cash_total, bonds, securities,"
                        " insurance, funds, real_estate, total_assets, total_liabilities,"
                        " created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (d, 1000.0, b, 2000.0, 3000.0, 4000.0, 5000.0, 15000.0, 100.0, "t"))
        con.commit()
    finally:
        con.close()


EX_KEYS = dict(date="2026-10-15", total_assets=15000.0, total_liabilities=100.0, net_worth=14900.0,
               securities_market=2000.0, insurance_current=3000.0, insurance_total=3000.0,
               fund_market=4000.0, real_estate=5000.0, cash=1000.0, other=0.0,
               insurance_detail={"【安聯保單A】現值": 3000.0}, fund_dividend_monthly=0.0,
               monthly_income=1.0, monthly_expense=2.0, rent_monthly=3.0, cathay_refinance=0.0)


def main() -> int:
    m = _load("adm_probe", ROOT / "asset_diff_monitor.py")

    def wire(rows: list[tuple[str, object]] | None) -> tuple[Path, Path]:
        """每個階段用獨立臨時目錄（避免共用／刪除已開啟的 DB 造成 Windows 檔案鎖）。"""
        base = Path(tempfile.mkdtemp(prefix="admt_"))
        pref = base / "asset_diff_history.json"
        if rows is not None:
            _mkdb(base / "dragon_assets.db", rows)
        m.REPO_BASE = base
        m.HISTORY_FILE = pref
        m._restricted_cash_of = lambda snap: 0.0
        m.real_estate_value = lambda *a, **k: 0.0
        m._truth = lambda *a, **k: 0.0        # 原函式為 (snap, key, ...) 多參數 → 吃 *args
        m.extract_snapshot = lambda snap: dict(EX_KEYS)
        return base, pref

    # ---- H1／H2：bonds 由 DB 同日列取得 ---------------------------------
    print("H1/H2 bonds 由 DB 同日列取得，且當日條目必含 bonds")
    base, pref = wire([("2026-10-14", 0.0), ("2026-10-15", 123.0)])
    hist = m.append_today({})
    ins = hist["2026-10-15"]
    check("當日條目含 bonds", "bonds" in ins, str(sorted(ins.keys())))
    check("bonds=DB 同日值（123.0）", float(ins["bonds"]) == 123.0, str(ins.get("bonds")))
    check("今日鍵集 ⊇ 前一日鍵集",
          not (set(hist["2026-10-14"].keys()) - set(ins.keys())),
          str(sorted(set(hist["2026-10-14"].keys()) - set(ins.keys()))))
    check("當日鍵數＝19（與前一日一致）", len(ins.keys()) == 19, str(len(ins.keys())))
    check("落檔內容亦含 bonds",
          "bonds" in json.loads(pref.read_text(encoding="utf-8"))["2026-10-15"])
    prev_keys = set(hist["2026-10-14"].keys())

    # ---- H2b：DB 無同日列 → 取 DB 最新列；DB 全無 → snapshot -------------
    print("H2b fallback 規則：DB 同日 → DB 最新 → snapshot")
    base, pref = wire([("2026-10-13", 777.0)])
    hist = m.append_today({})
    check("無同日列 → 取 DB 最新列（777.0）", float(hist["2026-10-15"]["bonds"]) == 777.0,
          str(hist["2026-10-15"].get("bonds")))
    base, pref = wire(None)                      # 無 DB
    hist = m.append_today({"bonds": 55.0})
    check("DB 不存在 → 用 snapshot.bonds（55.0）", float(hist["2026-10-15"]["bonds"]) == 55.0,
          str(hist["2026-10-15"].get("bonds")))

    # ---- H3：兩者皆無 → raise（不得以 0 掩蓋）----------------------------
    print("H3 兩者皆無有效值 → raise（不得靜默以 0 補值）")
    base, pref = wire(None)
    try:
        m.append_today({})
        check("應 raise", False, "未拋出例外（可能以 0 掩蓋）")
    except ValueError as e:
        check("raise ValueError", True)
        check("訊息說明不以 0 掩蓋", "不以 0 掩蓋" in str(e), str(e)[:120])
    except Exception as e:  # noqa: BLE001
        check("應為 ValueError", False, f"{type(e).__name__}: {e}")

    # ---- H4：缺鍵偵測有牙（負向自測）------------------------------------
    print("H4 缺鍵偵測：舊行為樣本（去掉 bonds）必須被判缺鍵")
    base, pref = wire([("2026-10-14", 0.0), ("2026-10-15", 1.0)])
    fixed = m.append_today({})["2026-10-15"]
    # 舊行為樣本＝修好後的條目再抽掉 bonds（重現原缺陷，證明檢查器有鑑別力）
    legacy_today = {k: v for k, v in fixed.items() if k != "bonds"}
    missing = sorted(prev_keys - set(legacy_today.keys()))
    check("負向：舊行為樣本被判缺 bonds", missing == ["bonds"], str(missing))
    check("正向：修好後的條目無缺鍵", not (prev_keys - set(fixed.keys())),
          str(sorted(prev_keys - set(fixed.keys()))))

    print("\n" + "=" * 54)
    print(f"測試結果：{PASS} PASS / {FAIL} FAIL")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
