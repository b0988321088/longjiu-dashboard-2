"""review_chain 失敗判定強化驗收 — 2026-10-14（W1 首次實戰暴露的鏈缺陷）。

驗證：
1. `_valid_review`：有內容但缺可判定 verdict（如 `{}`）→ 判為無效。
2. 無效回覆 → 視為該層失敗、續下一層（與逾時／空輸出同類）。
3. **REJECT 是有效判定、原樣採用**（「拒審不換層」契約不變）。
4. 全層無效 → RuntimeError（呼叫端 fail-closed）。
"""
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import review_chain as rc  # noqa: E402


class TestValidReview(unittest.TestCase):
    def test_01_APPROVE為有效(self):
        self.assertTrue(rc._valid_review('{"verdict":"APPROVE","blocking":[]}'))

    def test_02_REJECT為有效(self):
        self.assertTrue(rc._valid_review('前言 {"verdict":"REJECT","blocking":[{"file":"a"}]} 後語'))

    def test_03_空物件為無效(self):
        self.assertFalse(rc._valid_review('{}'))

    def test_04_缺verdict為無效(self):
        self.assertFalse(rc._valid_review('{"blocking":[],"note":"x"}'))

    def test_05_非JSON為無效(self):
        self.assertFalse(rc._valid_review('我覺得很好'))

    def test_06_verdict空字串為無效(self):
        self.assertFalse(rc._valid_review('{"verdict":"","blocking":[]}'))

    def test_07_小寫verdict仍有效(self):
        self.assertTrue(rc._valid_review('{"verdict":"approve"}'))


class TestChainFallback(unittest.TestCase):
    """以假層驗證鏈的行為（不動真憑證、不連網）。"""

    def _run(self, responses):
        calls = {"i": 0}

        def _mk():
            def _fn(prompt, max_tokens, timeout, json_mode):
                r = responses[calls["i"]]
                calls["i"] += 1
                if isinstance(r, Exception):
                    raise r
                return r
            return _fn

        layers = [(f"L{i}", _mk()) for i in range(len(responses))]
        orig = rc._layers
        rc._layers = lambda: layers
        try:
            return rc.review("p", max_tokens=16, timeout=5)
        finally:
            rc._layers = orig

    def test_08_第一層空物件_降層(self):
        _txt, label = self._run(['{}', '{"verdict":"APPROVE","blocking":[]}'])
        self.assertEqual(label, "L1")

    def test_09_第一層拋錯_降層(self):
        _txt, label = self._run([RuntimeError("402"), '{"verdict":"APPROVE"}'])
        self.assertEqual(label, "L1")

    def test_10_第一層缺verdict_降層(self):
        _txt, label = self._run(['{"blocking":[],"note":"x"}', '{"verdict":"APPROVE"}'])
        self.assertEqual(label, "L1")

    def test_11_第一層REJECT_不降層(self):
        txt, label = self._run(['{"verdict":"REJECT","blocking":[{"file":"a"}]}',
                                '{"verdict":"APPROVE"}'])
        self.assertEqual(label, "L0", "拒審不得改試下一層求 APPROVE")
        self.assertIn("REJECT", txt)

    def test_12_全層無效_拋錯(self):
        with self.assertRaises(RuntimeError):
            self._run(['{}', '{}'])

    def test_13_全層無效_錯誤訊息可診斷(self):
        try:
            self._run(['{}', 'nope'])
            self.fail("應拋 RuntimeError")
        except RuntimeError as e:
            self.assertIn("無可判定 verdict", str(e))


if __name__ == "__main__":
    unittest.main(verbosity=2)
