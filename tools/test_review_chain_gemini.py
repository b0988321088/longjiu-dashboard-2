"""RC-GEMINI-01 驗收測試 — Gemini 候選層（受控接入）。

涵蓋：
1. 開關語意：預設關閉 / =1 備援層 / =only 獨佔層 / 憑證不可用時的行為。
2. Gemini 原生回覆的結構與安全處理（無候選、SAFETY、空 parts、非 JSON）。
3. 防線：有效 REJECT 不得被降層覆蓋；無效回覆不得被記成 APPROVE；全層失敗 fail-closed。
4. 憑證不外洩（錯誤訊息與審查紀錄皆不得含 key）。

全部以 stub 隔離，不連網、不消耗真實憑證。
"""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import review_chain as rc  # noqa: E402

FAKE_BASE = "https://example.invalid/v1beta"
FAKE_KEY = "FAKE-KEY-FOR-TEST-ONLY"


class _Resp:
    def __init__(self, payload):
        self._p = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._p

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _gemini_payload(text, finish="STOP", parts=None):
    if parts is None:
        parts = [{"text": text}]
    return {"candidates": [{"content": {"parts": parts}, "finishReason": finish}]}


class TestSwitchSemantics(unittest.TestCase):
    """開關語意：預設關閉；開啟才納入。"""

    def _labels(self, mode=None, creds=(FAKE_BASE, FAKE_KEY)):
        env = {}
        if mode is not None:
            env[rc.GEMINI_ENV] = mode
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(rc, "_gemini_credentials", return_value=creds):
            os.environ.pop(rc.GEMINI_ENV, None) if mode is None else None
            with mock.patch.object(rc, "_read_hermes_env", return_value=""):
                return [lbl for lbl, _ in rc._layers()]

    def test_01_預設關閉_不含Gemini(self):
        labels = self._labels(None)
        self.assertFalse(any("Gemini" in x for x in labels))
        self.assertTrue(any("Pollinations" in x for x in labels))

    def test_02_設1_追加為最後一層(self):
        labels = self._labels("1")
        self.assertTrue(labels[-1].startswith("CIO-Gemini("))
        self.assertTrue(any("Pollinations" in x for x in labels))

    def test_03_設1但憑證不可用_不列入且既有層不變(self):
        labels = self._labels("1", creds=None)
        self.assertFalse(any("Gemini" in x for x in labels))
        self.assertTrue(any("Pollinations" in x for x in labels))

    def test_04_設only_只走Gemini(self):
        labels = self._labels("only")
        self.assertEqual(len(labels), 1)
        self.assertTrue(labels[0].startswith("CIO-Gemini("))

    def test_05_設only但憑證不可用_空鏈(self):
        self.assertEqual(self._labels("only", creds=None), [])

    def test_06_設only且憑證不可用_review必須fail_closed(self):
        with mock.patch.object(rc, "_layers", return_value=[]):
            with self.assertRaises(RuntimeError):
                rc.review("p")


class TestGeminiReplyHandling(unittest.TestCase):
    """原生回覆的結構／安全處理：一律 raise → 該層失敗。"""

    def _call(self, payload, json_mode=True):
        with mock.patch.object(rc.urllib.request, "urlopen",
                               lambda req, timeout=None: _Resp(payload)):
            return rc._call_gemini(FAKE_BASE, FAKE_KEY, rc.GEMINI_MODEL, "p", 64, 5, json_mode)

    def test_07_正常回覆(self):
        self.assertEqual(self._call(_gemini_payload('{"verdict":"APPROVE"}')),
                         '{"verdict":"APPROVE"}')

    def test_08_無candidates_raise(self):
        with self.assertRaises(rc._LayerBlocked):
            self._call({"promptFeedback": {"blockReason": "SAFETY"}})

    def test_09_SAFETY_finishReason_raise(self):
        with self.assertRaises(rc._LayerBlocked):
            self._call(_gemini_payload("x", finish="SAFETY"))

    def test_10_空parts_重試後仍空_raise(self):
        # 空 parts 屬「空輸出」→ 放大上限重試 → 仍空才 raise（與 OpenAI 相容層語意一致）
        with mock.patch.object(rc.urllib.request, "urlopen",
                               lambda req, timeout=None: _Resp(_gemini_payload("", parts=[]))):
            with self.assertRaises(RuntimeError):
                rc._call_gemini(FAKE_BASE, FAKE_KEY, rc.GEMINI_MODEL, "p", 64, 5)

    def test_11_純空白內容_重試後仍空_raise(self):
        with mock.patch.object(rc.urllib.request, "urlopen",
                               lambda req, timeout=None: _Resp(_gemini_payload("   "))):
            with self.assertRaises(RuntimeError):
                rc._call_gemini(FAKE_BASE, FAKE_KEY, rc.GEMINI_MODEL, "p", 64, 5)

    def test_11b_MAX_TOKENS截斷_放大上限重試成功(self):
        # 首次截斷（實測：maxOutputTokens 被 reasoning 吃掉）→ 放大上限重試 → 第二次完整
        seq = [_Resp(_gemini_payload('{"verdict":"APP', finish="MAX_TOKENS")),
               _Resp(_gemini_payload('{"verdict":"APPROVE"}'))]
        with mock.patch.object(rc.urllib.request, "urlopen", side_effect=seq):
            out = rc._call_gemini(FAKE_BASE, FAKE_KEY, rc.GEMINI_MODEL, "p", 64, 5)
        self.assertIn("APPROVE", out)

    def test_11c_兩次皆截斷_raise不得進審查(self):
        seq = [_Resp(_gemini_payload('{"verdict":"APP', finish="MAX_TOKENS")),
               _Resp(_gemini_payload('{"verdict":"APP', finish="MAX_TOKENS"))]
        with mock.patch.object(rc.urllib.request, "urlopen", side_effect=seq):
            with self.assertRaises(RuntimeError):
                rc._call_gemini(FAKE_BASE, FAKE_KEY, rc.GEMINI_MODEL, "p", 64, 5)

    def test_11d_截斷不得被當成有效審查(self):
        """截斷的 JSON 即使含 "APPROVE" 字樣也不得通過 `_valid_review`。"""
        self.assertFalse(rc._valid_review('```json\n{\n  "verdict": "APPROVE",\n  "reviewed_commits": [\n  '))

    def test_12_非JSON物件_raise(self):
        with mock.patch.object(rc.urllib.request, "urlopen",
                               lambda req, timeout=None: _Resp([1, 2, 3])):
            with self.assertRaises(RuntimeError):
                rc._call_gemini(FAKE_BASE, FAKE_KEY, rc.GEMINI_MODEL, "p", 64, 5)

    def test_13_憑證不外洩於錯誤訊息(self):
        with mock.patch.object(rc.urllib.request, "urlopen",
                               lambda req, timeout=None: _Resp({"candidates": []})):
            try:
                rc._call_gemini(FAKE_BASE, FAKE_KEY, rc.GEMINI_MODEL, "p", 64, 5)
                self.fail("應 raise")
            except rc._LayerBlocked as e:
                self.assertNotIn(FAKE_KEY, str(e))


class TestChainIntegration(unittest.TestCase):
    """鏈整合（假層）：Gemini 作為 only／備援層時的行為。"""

    def _run(self, responses, labels=None):
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
        if labels:
            layers = [(labels[i], _mk()) for i in range(len(responses))]
        with mock.patch.object(rc, "_layers", return_value=layers):
            return rc.review("p", max_tokens=16, timeout=5)

    def test_14_有效APPROVE_被採用(self):
        txt, lbl = self._run(['{"verdict":"APPROVE","blocking":[]}'], labels=["CIO-Gemini(x)"])
        self.assertEqual(lbl, "CIO-Gemini(x)")
        self.assertIn("APPROVE", txt)

    def test_15_有效REJECT_原樣採用不降層(self):
        txt, lbl = self._run(['{"verdict":"REJECT","blocking":[{"file":"a"}]}',
                              '{"verdict":"APPROVE"}'],
                             labels=["CIO-Gemini(x)", "L1"])
        self.assertEqual(lbl, "CIO-Gemini(x)")
        self.assertIn("REJECT", txt)

    def test_16_回覆為空物件_視為失敗(self):
        with self.assertRaises(RuntimeError):
            self._run(['{}'], labels=["CIO-Gemini(x)"])

    def test_17_無候選_blocked_續下一層(self):
        _txt, lbl = self._run([rc._LayerBlocked("無候選（blockReason=SAFETY）"),
                               '{"verdict":"APPROVE"}'],
                              labels=["CIO-Gemini(x)", "L1"])
        self.assertEqual(lbl, "L1")

    def test_18_逾時_續下一層(self):
        _txt, lbl = self._run([TimeoutError("timed out"), '{"verdict":"APPROVE"}'],
                              labels=["CIO-Gemini(x)", "L1"])
        self.assertEqual(lbl, "L1")

    def test_19_備援層情境_第一層無效才用Gemini(self):
        _txt, lbl = self._run(['{}', '{"verdict":"APPROVE","blocking":[]}'],
                              labels=["CIO-Pollinations(openai)", "CIO-Gemini(x)"])
        self.assertEqual(lbl, "CIO-Gemini(x)")

    def test_20_全層無效_fail_closed(self):
        with self.assertRaises(RuntimeError):
            self._run(['{}', rc._LayerBlocked("無候選")],
                      labels=["CIO-Pollinations(openai)", "CIO-Gemini(x)"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
