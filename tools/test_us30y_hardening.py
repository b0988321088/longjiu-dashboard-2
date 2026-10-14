"""W2 驗收測試（RF-1＋RF-2 合併工單）— 2026-10-14 使用者核准。

F1–F5：us30y_monitor 全來源抓取失敗的連續計數與分級告警（RF-1）
G1–G5：sot_targets.us30y_gate 的 status 語意（RF-2）

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

    def test_G6_低於紅線且新鮮_允許解凍判定(self):
        g = self._g(5.10)                     # 5.10 < 5.30 且新鮮
        self.assertEqual(g["status"], "OK")
        self.assertTrue(g["unfreeze_allowed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
