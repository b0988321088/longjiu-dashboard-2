# -*- coding: utf-8 -*-
"""test_perf_caliber_20261020.py — 口徑驗收（使用者 2026-10-20 指定三項）

T1 資金流入不得算成獲利（買進/申購）
T2 賣出不得算成虧損（出清回流）
T3 配息不得重複分類（每筆只落一類，總額＝明細合計）
T4 估值更新不得算成市場報酬（校正排除）
T5 TWR：無 flow 時不可標 reliable；有 flow 時資金流不貢獻報酬

用法：python tools/test_perf_caliber_20261020.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import performance_core as pc  # noqa: E402

fails: list[str] = []


def chk(cond, label, detail=""):
    print(("  ✅ " if cond else "  ❌ ") + label + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(label)


def mkdaily(prev_sec, sec, prev_fund=0, fund=0, prev_ins=0, ins=0, days=2):
    """建立 in-memory db（assets 表）→ 月初/月末兩點。"""
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE assets (date TEXT PRIMARY KEY, cash_total REAL, bonds REAL, "
               "securities REAL, insurance REAL, funds REAL, real_estate REAL, "
               "total_assets REAL, created_at TEXT, total_liabilities REAL)")
    rows = [("2026-09-30", 0, 0, prev_sec, prev_ins, prev_fund, 0, 0, "", 0),
            ("2026-10-20", 0, 0, sec, ins, fund, 0, 0, "", 0)]
    db.executemany("INSERT INTO assets VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    # TWR 需要連續日；只補一個中間點，避免 gaps 讓結論模糊
    db.execute("INSERT INTO assets VALUES ('2026-10-10',0,0,?,?,?,0,0,'',0)",
               (prev_sec, prev_ins, prev_fund))
    db.commit()
    return db


def case(label, *, prev, now, flows, expect_mkt, updates=None, invest=None):
    db = mkdaily(prev, now)
    adj = {"2026-10": {"市值可靠": True,
                       "配息": {}, "手續費": {}, "利息": {"房貸": 0},
                       "新增投入": invest or {},
                       "資金流": {"股票": flows} if flows else {},
                       "估值更新": updates or []}}
    res = pc.monthly_performance("2026-10", snap={}, adjust_all=adj, db=db,
                                 asof="2026-10-20")
    got = round(res["rows"][0]["mkt"])
    chk(got == expect_mkt, label, f"mkt={got:,} 期望 {expect_mkt:,}")
    db.close()
    return res


print("== T1/T2 資金流不得當損益 ==")
case("T1 買進 50,000：市值 100,000→150,000 應為 0 損益", prev=100000, now=150000,
     flows=[{"date": "2026-10-10", "金額": 50000}], expect_mkt=0)
case("T2 賣出 40,000：市值 100,000→60,000 應為 0 損益", prev=100000, now=60000,
     flows=[{"date": "2026-10-10", "金額": -40000}], expect_mkt=0)
case("T1b 買進 50,000 且市價漲 10,000 → 損益 +10,000", prev=100000, now=160000,
     flows=[{"date": "2026-10-10", "金額": 50000}], expect_mkt=10000)
case("T1c 新增投入（外部新資金）不當獲利", prev=100000, now=150000, flows=None,
     invest={"股票": 50000}, expect_mkt=0)

print("== T4 估值更新不得算成市場報酬 ==")
case("T4 市值 −100,000、其中校正 −20,000 → 市場損益 −80,000", prev=100000, now=0,
     flows=None, expect_mkt=-80000,
     updates=[{"date": "2026-10-10", "類": "股票", "金額": -20000}])

print("== T3 配息不得重複 ==")
snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
tot = pc.dividend_totals(snap, "2026-10")
detail = (snap.get("dividend_records") or {}).get("2026-10") or {}
raw = sum(v for v in detail.values() if isinstance(v, (int, float)))
chk(abs(sum(tot.values()) - raw) < 0.01, "配息三桶合計 == 明細合計（無重複/無遺漏）",
    f"{sum(tot.values()):,.0f} vs {raw:,.0f}")
for k, v in tot.items():
    print(f"     {k} {v:,.0f}")

print("== T5 TWR 可靠度標記 ==")
db = mkdaily(100000, 160000)
adj = {"2026-10": {"市值可靠": True, "配息": {}, "手續費": {}, "利息": {"房貸": 0}}}
r = pc.monthly_performance("2026-10", snap={}, adjust_all=adj, db=db, asof="2026-10-20")
chk(r["twr"]["overall"]["twr"] is not None, "TWR 可算（有日估值）",
    f"{r['twr']['overall']['twr']:.4%}")
chk(r["rate_price"] is not None and r["rate_total"] is not None, "rate_price / rate_total 皆提供分母")
db.close()
db2 = sqlite3.connect(":memory:")
db2.execute("CREATE TABLE assets (date TEXT, cash_total REAL, bonds REAL, securities REAL, "
            "insurance REAL, funds REAL, real_estate REAL, total_assets REAL, created_at TEXT, "
            "total_liabilities REAL)")
r2 = pc.monthly_performance("2026-10", snap={}, adjust_all=adj, db=db2, asof="2026-10-20")
chk(r2["twr"]["overall"]["twr"] is None and not r2["twr"]["overall"]["reliable"],
    "無日估值 → TWR 回 None 並標不可靠（不回退簡化百分比）")
db2.close()


print("== T6–T9 9 月分母備援／勾稽／不可比（2026-10-20 追加）==")
import sqlite3 as _s3
_db = _s3.connect(str(BASE / "dragon_assets.db"))
_adj = json.loads((BASE / "investment_performance_adjust.json").read_text(encoding="utf-8"))
_snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
_h = pc.monthly_history(["2026-09", "2026-10"], snap=_snap, adjust_all=_adj, db=_db, asof="2026-10-20")
_db.close()
_m9 = next(m for m in _h["months"] if m["month"] == "2026-09")
_m10 = next(m for m in _h["months"] if m["month"] == "2026-10")
_mv0 = _adj["2026-09"]["月初市值"]
chk(_m9["mv_total0"] == 25373048, "T6a 9 月分母＝8/31 三類合計 25,373,048", f'{_m9["mv_total0"]:,.0f}')
chk("2026-08-31_snapshot" in (_m9.get("mv0_source") or ""), "T6b 9 月分母來源可追溯（8/31 snapshot）",
    (_m9.get("mv0_source") or "")[:36])
chk(_mv0["股票"] + 119040 == 2993630 and _mv0["基金"] - 125976 == 12654144
    and _mv0["保單"] - 115335 - 178547 == 9424456, "T6c 三類勾稽到 db 9/30（零誤差）")
chk(_m9["rate_price"] is not None and abs(_m9["rate_price"] + 0.004819) < 5e-5,
    "T7a 9 月純價格報酬 −0.4819%", f'{_m9["rate_price"]:.4%}')
chk(_m9["rate_total"] is not None and abs(_m9["rate_total"] - 0.001904) < 5e-5,
    "T7b 9 月含配息報酬 +0.1904%", f'{_m9["rate_total"]:.4%}')
chk(_m9["twr_reliable"] is False and "2026-09-19" in (_m9["twr_reason"] or ""),
    "T8 9 月 TWR 標不可靠且載明僅涵蓋 9/19 起", (_m9["twr_reason"] or "")[:44])
chk(abs(_m10["net"] - 202146) < 1 and abs(_m10["rate_total"] - 0.008063) < 5e-5
    and abs(_m10["twr"]["twr"] - 0.009401) < 5e-5,
    "T9 10 月回歸不變（202,146／+0.8063%／TWR +0.9401%）",
    f'{_m10["net"]:,.0f} / {_m10["rate_total"]:.4%}')

print(f"\n=== 口徑驗收：{'PASS' if not fails else 'FAIL（' + str(len(fails)) + '）'} ===")
for f in fails:
    print("  - " + f)
raise SystemExit(0 if not fails else 1)
