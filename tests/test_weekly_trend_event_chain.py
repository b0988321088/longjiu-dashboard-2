#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回歸測試：資產趨勢週報「事件鏈」判定（2026-10-09 唯讀稽核後修正）

驗收基準（使用者 2026-10-09 裁決）：
1. 2026-09-26→10-09 真實序列：剔除事件鏈 9/29-10/1 後，同口徑 = -53,548
   （舊版 -2,012,811 為跨日入帳造成的假性損失，非投資虧損）。
2. 真正的市場損失（資產腿連續下跌、無反向負債腿）不得被排除，須留在異常判定內。
3. 對沖不足（<80%）、或兩腿同為資產腿的市場 V 型反轉，不得被排除。
4. 舊口徑「單日資產/負債跳變 ≥10% 基準變動日」規則不得因新增事件鏈而失效。

執行：pytest tests/test_weekly_trend_event_chain.py -q
"""
import importlib.util
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "notion_weekly_trend_wrapper", REPO / "notion_weekly_trend_wrapper.py")
w = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w)

# === 真實序列（dragon_assets.db assets 表 2026-10-09 稽核當日之 14 筆原值）===
REAL_ROWS = [
    ("2026-09-26", 26_180_597, 30_129_538),
    ("2026-09-27", 26_180_597, 30_129_538),
    ("2026-09-28", 26_180_597, 30_129_538),
    ("2026-09-29", 31_808_561, 36_003_720),
    ("2026-09-30", 28_825_191, 34_979_613),
    ("2026-10-01", 26_791_534, 30_967_893),
    ("2026-10-02", 26_791_534, 30_967_893),
    ("2026-10-03", 26_791_534, 30_967_893),
    ("2026-10-04", 26_791_534, 30_967_893),
    ("2026-10-05", 26_807_075, 30_980_255),
    ("2026-10-06", 26_823_015, 30_980_708),
    ("2026-10-07", 26_823_015, 30_980_708),
    ("2026-10-08", 26_717_875, 30_980_898),
    ("2026-10-09", 26_751_051, 30_980_958),
]


def _rows(pairs):
    return [{"date": d, "total_assets": ta, "total_liabilities": li, "cash_total": 0}
            for d, ta, li in pairs]


def _analyse(rows):
    m = w.compute_daily_metrics(rows)
    sd = [d for d, v in sorted(m.items()) if v["structural"]]
    chains = w.detect_event_chains(m, sd)
    excl = sorted(set(sd) | {dt for c in chains for dt in c["dates"]})
    rs = sorted(rows, key=lambda r: r["date"])

    def nw(r):
        return float(r["total_assets"] or 0) - float(r["total_liabilities"] or 0)

    net = nw(rs[-1]) - nw(rs[0])
    comp = sum(nw(rs[i + 1]) - nw(rs[i]) for i in range(len(rs) - 1)
               if rs[i + 1]["date"][:10] not in excl)
    return m, chains, excl, net, comp


# ---------- 1. 稽核基準：真實序列同口徑必須是 -53,548 ----------
def test_real_series_comparable_is_53548():
    m, chains, excl, net, comp = _analyse(_rows(REAL_ROWS))
    assert net == -280_966
    assert comp == -53_548, "剔除事件鏈後同口徑必須為 -53,548（2026-10-09 稽核基準）"
    assert excl == ["2026-09-29", "2026-09-30", "2026-10-01"]
    assert chains, "真實序列必須偵測到事件鏈"
    assert chains[0]["dates"] == ["2026-09-29", "2026-09-30", "2026-10-01"]
    assert chains[0]["first"] == "2026-09-30" and chains[0]["reverse"] == "2026-10-01"
    assert chains[0]["first_leg"] == "資產" and chains[0]["reverse_leg"] == "負債"
    assert chains[0]["ratio"] == pytest.approx(1.0096, abs=0.001)


# ---------- 2. 真實市場損失不得被排除 ----------
def test_real_market_loss_not_excluded():
    pairs = [("2026-10-01", 100_000_000, 50_000_000),
             ("2026-10-02", 97_000_000, 50_000_000),   # 資產腿 -3,000,000（-3%）
             ("2026-10-03", 95_000_000, 50_000_000)]   # 續跌 -2,000,000
    m, chains, excl, net, comp = _analyse(_rows(pairs))
    assert chains == [] and excl == [], "市場連續下跌不得被判為事件鏈"
    assert comp == net == -5_000_000


def test_v_shaped_market_move_not_excluded():
    pairs = [("2026-10-01", 100_000_000, 50_000_000),
             ("2026-10-02", 98_000_000, 50_000_000),   # 資產腿 -2,000,000
             ("2026-10-03", 99_900_000, 50_000_000)]   # 資產腿 +1,900,000（對沖 95%）
    m, chains, excl, net, comp = _analyse(_rows(pairs))
    assert chains == [] and excl == [], "兩腿皆資產腿（市場 V 型）不得排除"
    assert comp == net == -100_000


# ---------- 3. 對沖不足的負債變動不得被排除 ----------
def test_unhedged_liability_change_not_excluded():
    pairs = [("2026-10-01", 26_000_000, 30_000_000),
             ("2026-10-02", 26_000_000, 31_000_000),   # 負債腿 -1,000,000（淨值 -1,000,000，3.3%）
             ("2026-10-03", 26_500_000, 31_000_000)]   # 資產腿 +500,000（對沖僅 50% < 80%）
    m, chains, excl, net, comp = _analyse(_rows(pairs))
    assert chains == [] and excl == [], "對沖不足 80% 不得視為事件鏈"
    assert comp == net == -500_000


def test_small_amount_days_not_chained():
    pairs = [("2026-10-01", 26_000_000, 30_000_000),
             ("2026-10-02", 25_950_000, 30_000_000),   # 資產腿 -50,000（低於金額門檻）
             ("2026-10-03", 25_950_000, 29_960_000)]   # 負債腿 +40,000
    m, chains, excl, net, comp = _analyse(_rows(pairs))
    assert chains == [] and excl == []


# ---------- 4. 正向控制：資產腿→負債腿且對沖 ≥80% = 事件鏈，整鏈排除 ----------
def test_asset_then_liability_hedge_is_chain():
    pairs = [("2026-10-01", 26_000_000, 30_000_000),
             ("2026-10-02", 24_000_000, 30_000_000),   # 資產腿 -2,000,000
             ("2026-10-03", 24_000_000, 28_300_000)]   # 負債腿 +1,700,000（對沖 85%）
    m, chains, excl, net, comp = _analyse(_rows(pairs))
    assert excl == ["2026-10-02", "2026-10-03"]
    assert comp == 0 and net == -300_000
    assert chains[0]["first_leg"] == "資產" and chains[0]["reverse_leg"] == "負債"


# ---------- 5. 舊口徑基準變動日（≥10%）規則不得失效 ----------
def test_single_day_structural_rule_kept():
    pairs = [("2026-10-01", 26_000_000, 30_000_000),
             ("2026-10-02", 31_000_000, 35_000_000)]   # 借款入帳：資產/負債同增 +5,000,000
    m, chains, excl, net, comp = _analyse(_rows(pairs))
    assert m["2026-10-02"]["structural"] is True
    assert excl == ["2026-10-02"]


# ---------- 6. 文案：各類別資料截至時間解析 ----------
def test_asof_parser():
    snap = {
        "cash_source": {"date": "2026-10-09", "note": "Moneybook 帳戶 CSV 匯入"},
        "securities_note_20261008": "2026-10-08 09:19 盤中即時報價：持有股票市值 3,045,250",
        "heng_note_20261008": "2026-10-08 09:18 鉅亨帳戶總覽：台幣市值 898,416",
        "funds_cathay_note_1008": "2026-10-08 國泰基金頁截圖（09:18）",
        "allianz_note_20261008": "2026-10-08 安聯保單 App 資料查詢時間 115/10/08 08:55:12",
    }
    got = {lbl: (d, t) for lbl, d, t, _k in w.extract_asof(snap)}
    assert got["現金"][0] == "2026-10-09"
    assert got["證券"] == ("2026-10-08", "09:19")
    assert got["基金"][0] == "2026-10-08"
    assert got["保單"] == ("2026-10-08", "08:55")


# ---------- 7. 真實 DB 不變量（不寫入；DB 不存在則略過）----------
def test_live_db_invariant():
    if not (REPO / "dragon_assets.db").exists():
        pytest.skip("dragon_assets.db 不存在")
    rows = w.load_from_db(14)
    if not rows:
        pytest.skip("DB 無資料")
    m = w.compute_daily_metrics(rows)
    sd = [d for d, v in sorted(m.items()) if v["structural"]]
    chains = w.detect_event_chains(m, sd)
    excl = set(sd) | {dt for c in chains for dt in c["dates"]}
    rs = sorted(rows, key=lambda r: r["date"])

    def nw(r):
        return float(r["total_assets"] or 0) - float(r.get("total_liabilities") or 0)

    net = nw(rs[-1]) - nw(rs[0])
    skipped = sum(nw(rs[i + 1]) - nw(rs[i]) for i in range(len(rs) - 1)
                  if rs[i + 1]["date"][:10] in excl)
    comp = sum(nw(rs[i + 1]) - nw(rs[i]) for i in range(len(rs) - 1)
               if rs[i + 1]["date"][:10] not in excl)
    assert comp == pytest.approx(net - skipped), "同口徑必等於期間變動扣除被排除各日"
    assert all(c["first_leg"] != c["reverse_leg"] for c in chains), "事件鏈兩腿必須不同"
