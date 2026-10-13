#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_health_alert_check.py — A 案單元測試（2026-10-10）

對應使用者裁決 A 案的驗收條件表：

  情境                          預期結果
  ────────────────────────────  ──────────────────────────────────────
  美元曝險 59.9%                不觸發曝險提示
  60%–64.9%                     不因超過目標而報警
  65%–69.9%                     黃色觀察提示
  70% 以上                      觀察提示，不升級為危機紅燈
  健康分數低於 60               不再因分數本身推播紅燈
  門檻來源缺失或無效            明確報資料異常，不可靜默套用舊門檻

執行：python tools/test_health_alert_check.py
"""
import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

import health_alert_check as H  # noqa: E402

# 乾淨基底：所有維度都在安全區，只有 usd 依情境變動（避免紅線干擾判讀）
SAFE = dict(ltv=24.3, cash=900000, floor=700000, cov=113.0, defense=48.5, usd=59.9,
            th=(60.0, 65.0, 70.0))


def run(**over):
    kw = dict(SAFE)
    kw.update(over)
    return H.classify(**kw)


class TestUsdBands(unittest.TestCase):
    """曝險分級：60 不是紅線；65 起才是黃色觀察；70 仍不紅。"""

    def test_59_9_no_alert(self):
        red, obs, err = run(usd=59.9)
        self.assertEqual(obs, [], "59.9% 不應觸發曝險提示")
        self.assertEqual(err, [])

    def test_60_0_no_alert(self):
        """目標值本身不是紅線 → 剛好 60% 也不報。"""
        red, obs, err = run(usd=60.0)
        self.assertEqual(obs, [], "60%（目標值）不應觸發提示")

    def test_64_9_no_alert(self):
        red, obs, err = run(usd=64.9)
        self.assertEqual(obs, [], "64.9% 不應因超過目標而報警")

    def test_65_0_yellow(self):
        red, obs, err = run(usd=65.0)
        self.assertEqual(len(obs), 1)
        self.assertIn("黃色觀察區", obs[0])
        self.assertEqual(red, [], "曝險不得進紅線")

    def test_69_9_yellow(self):
        red, obs, err = run(usd=69.9)
        self.assertEqual(len(obs), 1)
        self.assertIn("黃色觀察區", obs[0])
        self.assertEqual(red, [])

    def test_70_0_observe_not_red(self):
        red, obs, err = run(usd=70.0)
        self.assertEqual(len(obs), 1)
        self.assertIn("高曝險觀察線", obs[0])
        self.assertEqual(red, [], "70% 以上仍不得升級為紅色危機")

    def test_71_4_observe_not_red(self):
        """現值情境（2026-10-10 實況）。"""
        red, obs, err = run(usd=71.4)
        self.assertEqual(len(obs), 1)
        self.assertIn("高曝險觀察線", obs[0])
        self.assertEqual(red, [], "71.4% 不得進紅線")
        self.assertNotIn("紅線", obs[0], "文案不得再出現「紅線」字樣")

    def test_no_hardcoded_60_redline(self):
        """原版 `if usd > 60: ...（紅線50）` 的行為必須消失。"""
        for v in (60.0, 61.0, 62.5, 64.9):
            _red, obs, _err = run(usd=v)
            self.assertEqual(obs, [], f"{v}% 不該有任何提示（60 僅是目標值）")


class TestScoreAlertRemoved(unittest.TestCase):
    """「健康分數 < 60」不得再作為推播觸發條件。"""

    def test_classify_has_no_score_input(self):
        import inspect
        params = set(inspect.signature(H.classify).parameters)
        self.assertNotIn("score", params,
                         "classify 不應接受 score —— 分數不得參與觸發判定")

    def test_source_has_no_score_threshold_alert(self):
        src = (H.__file__ and Path(H.__file__).read_text(encoding="utf-8")) or ""
        body = src.split('"""', 2)[-1]  # 去掉 docstring，避免沿革註記誤判
        self.assertNotIn("健康分數", body,
                         "程式本體不得再有『健康分數 < 60』的警報字串")


class TestThresholdSource(unittest.TestCase):
    """門檻來源缺失／無效 → 明確報資料異常，且不靜默套用舊門檻。"""

    def _bad_cases(self):
        return [
            ("空 snapshot", {}),
            ("thresholds 段為空", {"thresholds_2026_0915": {}}),
            ("美元曝險_pct 為空 dict",
             {"thresholds_2026_0915": {"美元曝險_pct": {}}}),
            ("只給目標、缺黃與紅",
             {"thresholds_2026_0915": {"美元曝險_pct": {"目標": 60}}}),
            ("順序無效（目標 > 黃）",
             {"thresholds_2026_0915": {"美元曝險_pct": {"目標": 70, "黃": 65, "紅": 60}}}),
            ("非數值",
             {"thresholds_2026_0915": {"美元曝險_pct": {"目標": "abc", "黃": 65, "紅": 70}}}),
            ("超出 0-100",
             {"thresholds_2026_0915": {"美元曝險_pct": {"目標": 0, "黃": 65, "紅": 170}}}),
        ]

    def test_invalid_sources_return_none(self):
        for name, snap in self._bad_cases():
            with self.subTest(name=name):
                self.assertIsNone(H.usd_thresholds(snap),
                                  f"{name} 應回 None（不得回預設門檻）")

    def test_valid_source_returns_triple(self):
        snap = {"thresholds_2026_0915": {"美元曝險_pct": {"目標": 60, "黃": 65, "紅": 70}}}
        self.assertEqual(H.usd_thresholds(snap), (60.0, 65.0, 70.0))

    def test_missing_source_reports_data_error_not_silent(self):
        """門檻取不到時：報資料異常，且**不**產生曝險提示（不套用 60 當預設）。"""
        for name, snap in self._bad_cases():
            with self.subTest(name=name):
                th = H.usd_thresholds(snap)
                red, obs, err = run(usd=71.4, th=th)
                self.assertEqual(len(err), 1, f"{name}：應明確報資料異常")
                self.assertIn("門檻來源缺失或無效", err[0])
                self.assertEqual(obs, [], f"{name}：不得用預設門檻產生提示")

    def test_real_snapshot_thresholds(self):
        """真實 snapshot 應讀得到 60/65/70。"""
        snap = json.loads((_HERE.parent / "snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual(H.usd_thresholds(snap), (60.0, 65.0, 70.0))


class TestRedLinesUnchanged(unittest.TestCase):
    """🔴 立即行動紅線維持原判準（A 案不動）。"""

    def test_ltv(self):
        red, _obs, _err = run(ltv=50.1)
        self.assertTrue(any("LTV" in x for x in red))

    def test_ltv_at_50_ok(self):
        red, _obs, _err = run(ltv=50.0)
        self.assertFalse(any("LTV" in x for x in red))

    def test_cash_below_floor(self):
        red, _obs, _err = run(cash=639661, floor=700000)
        self.assertTrue(any("現金" in x for x in red))

    def test_cash_at_floor_ok(self):
        red, _obs, _err = run(cash=700000, floor=700000)
        self.assertFalse(any("現金" in x for x in red))

    def test_coverage(self):
        red, _obs, _err = run(cov=99.9)
        self.assertTrue(any("覆蓋率" in x for x in red))

    def test_defense(self):
        red, _obs, _err = run(defense=39.9)
        self.assertTrue(any("防禦維度" in x for x in red))

    def test_live_scenario_2026_10_10(self):
        """實況：LTV 24.3、現金 639,661、覆蓋 113、防禦 48.5、曝險 71.4。
        預期＝1 條現金紅線 + 1 條曝險黃色觀察（**不再有分數紅燈**）。"""
        red, obs, err = run(ltv=24.3, cash=639661, floor=700000,
                            cov=113.0, defense=48.5, usd=71.4, th=(60.0, 65.0, 70.0))
        self.assertEqual(len(red), 1)
        self.assertIn("現金", red[0])
        self.assertEqual(len(obs), 1)
        self.assertIn("高曝險觀察線", obs[0])
        self.assertEqual(err, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
