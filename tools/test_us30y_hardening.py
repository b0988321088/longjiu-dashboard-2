"""W2 驗收測試（RF-1＋RF-2 合併工單）— 2026-10-14 使用者核准。

F1–F5：us30y_monitor 全來源抓取失敗的連續計數與分級告警（RF-1）
G1–G5：sot_targets.us30y_gate 的 status 語意（RF-2）
M1–M8：v1.2（TD-20261015-02）US30Y 改宏觀風險警示＋複合解凍條件（現金／質押 LTV／還本安全閥）

全部隔離：不連網、不寫真值（STATE 指向 tmp、sync_snapshot_gate 以 no-op 取代）。
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import sot_targets as sot        # noqa: E402
import us30y_monitor as mon      # noqa: E402


class TestRF1ConsecutiveFailure(unittest.TestCase):
    """F1–F5：monitor 抓取失敗的分級告警與歸零。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._state, self._sync = mon.STATE, mon.sync_snapshot_gate
        self._f, self._y = mon.fetch_us30y_fred, mon.fetch_us30y_yahoo
        mon.STATE = Path(self.tmp.name) / "us30y_state.json"
        mon.sync_snapshot_gate = lambda: None          # 不碰真值層

    def tearDown(self):
        mon.STATE, mon.sync_snapshot_gate = self._state, self._sync
        mon.fetch_us30y_fred, mon.fetch_us30y_yahoo = self._f, self._y
        self.tmp.cleanup()

    def _run(self, fred, yahoo):
        mon.fetch_us30y_fred = lambda: fred
        mon.fetch_us30y_yahoo = lambda: yahoo
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mon.main()
        return buf.getvalue()

    def _st(self):
        p = Path(mon.STATE)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def _rows(self, days=2, rate=5.60):
        d0 = date.today()
        return [((d0 - timedelta(days=i)).isoformat(), rate) for i in range(days)]

    # ── F1 ──
    def test_F1_單次全失敗_第1級並計數1(self):
        out = self._run([], [])
        self.assertIn("第 1 次失敗", out)
        self.assertEqual(self._st().get("fetch_fail_streak"), 1)

    # ── F2 ──
    def test_F2_連續2次_升級告警(self):
        self._run([], [])
        out = self._run([], [])
        self.assertIn("連續 2 次", out)
        self.assertIn("⚠️⚠️", out)
        self.assertEqual(self._st().get("fetch_fail_streak"), 2)

    # ── F3 ──
    def test_F3_連續3次以上_最高級並揭露落後(self):
        self._run([], [])
        self._run([], [])
        out = self._run([], [])
        self.assertIn("連續 3 次", out)
        self.assertIn("🔴", out)
        self.assertIn("不得依賴", out)
        self.assertEqual(self._st().get("fetch_fail_streak"), 3)

    # ── F4 ──
    def test_F4_失敗後成功_歸零且不重複告警(self):
        self._run([], [])
        out1 = self._run(self._rows(), [])
        self.assertIn("已恢復", out1)
        self.assertNotIn("fetch_fail_streak", self._st())
        out2 = self._run(self._rows(), [])
        self.assertNotIn("已恢復", out2)          # 不重複告警

    def test_F4b_成功後再失敗_重新由1起算(self):
        self._run([], [])
        self._run(self._rows(), [])
        out = self._run([], [])
        self.assertIn("第 1 次失敗", out)
        self.assertEqual(self._st().get("fetch_fail_streak"), 1)

    # ── F5 ──
    def test_F5_僅FRED失敗Yahoo成功_不算全失敗(self):
        out = self._run([], self._rows())
        self.assertNotIn("無資料", out)
        self.assertNotIn("抓取失敗", out)
        self.assertNotIn("fetch_fail_streak", self._st())

    def test_F5b_僅Yahoo失敗FRED成功_不算全失敗(self):
        out = self._run(self._rows(), [])
        self.assertNotIn("無資料", out)
        self.assertNotIn("fetch_fail_streak", self._st())


class TestRF2GateStatus(unittest.TestCase):
    """G1–G5：us30y_gate 的 status 語意。"""

    def _g(self, last_rate, last_date=None, lag_days=0):
        ref = date.today()
        ld = last_date if last_date is not None else (ref - timedelta(days=lag_days)).isoformat()
        snap = {"date": ref.isoformat(), "thresholds_2026_0915": {"US30Y紅線": 5.30}}
        return sot.us30y_gate(snap=snap, state={"last_date": ld, "last_rate": last_rate},
                              max_lag_days=3)

    # ── G1 ──
    def test_G1_缺last_rate_UNKNOWN(self):
        g = self._g(None)
        self.assertEqual(g["status"], "UNKNOWN")
        self.assertFalse(g["unfreeze_allowed"])

    # ── G2 ──
    def test_G2_不可解析_UNKNOWN(self):
        g = self._g("abc")
        self.assertEqual(g["status"], "UNKNOWN")
        self.assertFalse(g["unfreeze_allowed"])

    # ── G3 ──
    def test_G3_NaN_UNKNOWN(self):
        for bad in (float("nan"), float("inf"), "-"):
            with self.subTest(bad=bad):
                g = self._g(bad)
                self.assertEqual(g["status"], "UNKNOWN")
                self.assertFalse(g["unfreeze_allowed"])

    # ── G4 ──
    def test_G4_落後9天_STALE(self):
        g = self._g(5.10, lag_days=9)
        self.assertEqual(g["status"], "STALE")
        self.assertFalse(g["unfreeze_allowed"])

    # ── G5 ──
    def test_G5_正常有效_OK(self):
        g = self._g(5.60)
        self.assertEqual(g["status"], "OK")

    def test_G5b_正常但高於紅線_不得解凍(self):
        g = self._g(5.60)                     # 5.60 > 紅線 5.30
        self.assertEqual(g["status"], "OK")
        self.assertFalse(g["unfreeze_allowed"])

    def test_G6_低於紅線且新鮮_但無複合條件真值_仍不得解凍(self):
        """v1.2：advisory 模式下解凍改由 unfreeze_conditions 決定；
        本測試 snap 無現金／LTV／還本真值 → fail-closed，不得回可解凍。"""
        g = self._g(5.10)                     # 5.10 < 5.30 且新鮮
        self.assertEqual(g["status"], "OK")
        self.assertTrue(g["below_red_line"])
        self.assertFalse(g["risk_warning"])
        self.assertFalse(g["unfreeze_allowed"])


class TestV12Unfreeze(unittest.TestCase):
    """M1–M8：v1.2 解凍條件（現金／質押 LTV／還本安全閥）與 hard_veto 回復路徑。"""

    POOL = 11_798_203.0            # 測試用合成池值（非真值）
    LOAN = 5_900_000.0
    RATE = 0.0265

    def _snap(self, avail=1_055_740.0, pool=None, loan=None, rate=None,
              income=225_968.0, expense=159_210.0, mode=None, pool_scale=1.0,
              terms=None, ltv_line=53.0):
        pool = (pool if pool is not None else self.POOL) * pool_scale
        snap = {
            "date": date.today().isoformat(),
            "thresholds_2026_0915": {
                "US30Y紅線": 5.30,
                "ltv分級_pct": {"綠上限": 45, "黃上限": ltv_line, "追繳": 70, "單池上限": 50,
                                "判定單位": "各池分別判定"},
            },
            "sabbatical_gate_twd": {"自由現金_twd": 1_000_000.0, "壓力覆蓋_pct": 100.0,
                                    "跑道天數": 540.0},
            "cash_layers": {"restricted_cash": {"total": 900_000.0},
                            "unrestricted_cash": avail, "cash_total": avail + 900_000.0},
            "fund_pledge_loan": (loan if loan is not None else self.LOAN),
            "fund_pledge_rate": (rate if rate is not None else self.RATE),
            "fund_breakdown_cathay": {"A": pool * 0.50, "B": pool * 0.42, "C": pool * 0.08},
            "monthly_income": income,
            "monthly_expense": expense,
        }
        if mode:
            snap["thresholds_2026_0915"]["US30Y閘門模式"] = mode
        if terms:
            snap["cathay_pledge_0911"] = terms
        return snap

    def _gate(self, snap, last_rate=5.60, lag_days=0):
        ref = date.today()
        state = {"last_date": (ref - timedelta(days=lag_days)).isoformat(), "last_rate": last_rate}
        return sot.us30y_gate(snap=snap, state=state, max_lag_days=3)

    # ── M1：US30Y 高於紅線 → 警示、不再單獨否決；未達原因必須是實體條件 ──
    def test_M1_US30Y高於紅線僅警示_不得作為單一否決來源(self):
        g = self._gate(self._snap())
        self.assertEqual(g["mode"], "advisory")
        self.assertTrue(g["risk_warning"])
        self.assertFalse(g["unfreeze_allowed"])
        self.assertIn("不單獨否決台股分批", g["reason"])
        unmet = g["unfreeze_conditions"]["未達"]
        self.assertTrue(any("還本安全閥" in u for u in unmet), unmet)
        self.assertFalse(any("US30Y" in u for u in unmet), unmet)

    # ── M2：核心行為 — US30Y 5.60 但 U1 已證實為只繳息 → 條件全過，許可解凍判定 ──
    def test_M2_US30Y高於紅線_但U1證實只繳息_條件全過可解凍(self):
        snap = self._snap(terms={"還本方式": "按月繳息，到期續約（只繳息）", "月付": 13_029})
        g = self._gate(snap)
        self.assertTrue(g["risk_warning"])
        self.assertTrue(g["unfreeze_conditions"]["all_passed"], g["unfreeze_conditions"]["未達"])
        self.assertTrue(g["unfreeze_allowed"])

    # ── M3：LTV 市值口徑負向測試（擔保品 −20%／−30%）──
    def test_M3_LTV市值口徑_跌20與30(self):
        g0 = self._gate(self._snap())
        l0 = g0["unfreeze_conditions"]["pledge_ltv"]
        self.assertAlmostEqual(l0["LTV_pct"], 50.01, delta=0.05)
        l20 = self._gate(self._snap(pool_scale=0.8))["unfreeze_conditions"]["pledge_ltv"]
        self.assertAlmostEqual(l20["LTV_pct"], 62.51, delta=0.05)
        self.assertFalse(l20["通過"])
        l30 = self._gate(self._snap(pool_scale=0.7))["unfreeze_conditions"]["pledge_ltv"]
        self.assertAlmostEqual(l30["LTV_pct"], 71.44, delta=0.05)
        self.assertTrue(l30["觸追繳"])

    # ── M4：hard_veto 回復路徑（零殘留）──
    def test_M4_hard_veto回復_行為與v1_1相同(self):
        lo = self._gate(self._snap(mode="hard_veto"), last_rate=5.10)
        self.assertEqual(lo["mode"], "hard_veto")
        self.assertTrue(lo["unfreeze_allowed"])       # 低於紅線 → 許可（v1.1 語意）
        self.assertIsNone(lo["unfreeze_conditions"])
        hi = self._gate(self._snap(mode="hard_veto"), last_rate=5.60)
        self.assertFalse(hi["unfreeze_allowed"])      # 高於紅線 → 不許可（v1.1 語意）

    # ── M5：現金低於門檻 → 未達條件必含現金 ──
    def test_M5_現金低於門檻_不得解凍(self):
        snap = self._snap(avail=900_000.0, terms={"還本方式": "按月繳息，到期續約"})
        g = self._gate(snap)
        self.assertFalse(g["unfreeze_allowed"])
        self.assertTrue(any("現金" in u for u in g["unfreeze_conditions"]["未達"]))

    # ── M6：還本安全閥 — U1 證實為 5 年攤還 → 月盈餘轉負 → 暫停新增分批 ──
    def test_M6_U1證實五年攤還_月盈餘轉負_暫停新增分批(self):
        snap = self._snap(terms={"還本方式": "本金平均攤還 5 年"})
        g = self._gate(snap)
        v = g["unfreeze_conditions"]["repayment_valve"]
        self.assertTrue(v["暫停新增分批"])
        self.assertFalse(g["unfreeze_allowed"])

    # ── M7：缺真值 fail-closed（不得因缺資料而放行）──
    def test_M7_缺質押真值_不得解凍(self):
        for key in ("fund_pledge_loan", "fund_breakdown_cathay"):
            with self.subTest(key=key):
                snap = self._snap(terms={"還本方式": "按月繳息"})
                snap.pop(key)
                g = self._gate(snap)
                self.assertFalse(g["unfreeze_allowed"])
                self.assertFalse(g["unfreeze_conditions"]["all_passed"])

    # ── M8：指定用途款不得計入可動用；只認 cash_layers.unrestricted_cash ──
    def test_M8_指定用途款不得計入可動用(self):
        snap = self._snap(avail=1_055_740.0)
        snap["cash_layers"]["restricted_cash"]["total"] = 5_000_000.0   # 指定款膨脹
        c = [x for x in self._gate(snap)["unfreeze_conditions"]["conditions"] if "現金" in x["名稱"]][0]
        self.assertEqual(float(c["現值"]), 1_055_740.0)
        self.assertIn("指定用途款", c["註記"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
