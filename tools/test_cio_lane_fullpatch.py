"""W1 驗收測試（CIO 審查完整性）— 2026-10-14 使用者核准 A+C 方案；
2026-10-15 使用者裁決「修復審查基建、不採例外放行」後，對齊新車道介面（review_segmented）。

驗證：
1. 送審內文**含實際 patch**（不再以 --stat 統計代替程式碼）。
2. 超量自動分段，各段獨立送審，且**不得二次截斷**（2026-10-15 修復項）。
3. 任何一段 REJECT／blocking／綁定不符／鏈失敗／逾時／涵蓋率不足 → 整體 fail-closed，不落 RECORD。
4. RECORD 具完整性記錄（總字元數／送審字元數／has_patch／coverage／各段結果）。
5. 既有 prompt 契約相容（不傳 patch 時不含「變更內容」段落）。

全部以 stub 隔離：不連網、不碰真 git、不寫真 .git/cio_reviews（BASE 指向 tmp）。
"""
import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import cio_lane as lane          # noqa: E402
import review_chain as rc        # noqa: E402

C40 = "a" * 40
T40 = "b" * 40
C12, T12 = C40[:12], T40[:12]


class _R:
    def __init__(self, s=""):
        self.stdout = s
        self.stderr = ""
        self.returncode = 0


def _mk_git(patch_body):
    """模擬 cio_lane._git：依參數分派固定的假資料。"""
    def _git(*args, timeout=60):
        a = list(args)
        if a[:1] == ["rev-list"]:
            return _R(C40 + "\n")
        if a[:1] == ["rev-parse"]:
            return _R(T40 + "\n")
        if a[:2] == ["log", "-1"]:
            return _R("test subject\n")
        if a[:2] == ["show", "--name-only"]:
            return _R("sot_targets.py\nus30y_monitor.py\n")
        if a[:2] == ["show", "--stat"]:
            return _R(" 2 files changed, 10 insertions(+), 2 deletions(-)\n")
        if a[:2] == ["show", "--format="]:
            return _R(patch_body)
        if a[:1] == ["show"] and len(a) == 2 and ":" in a[1]:
            return _R("{}")      # governance_invariant 讀前後版本
        return _R("")
    return _git


def _approve_json(c12=C12, t12=T12):
    return json.dumps({"verdict": "APPROVE",
                       "reviewed_commits": [{"commit": c12, "tree": t12}],
                       "blocking": [], "required_fixes": [], "note": "ok"})


class TestW1(unittest.TestCase):
    """注意：**不得覆寫 lane.BASE** —— review_and_record() 會 os.chdir(BASE) 後再呼叫
    cio_approve（其 git 呼叫相對於 cwd），BASE 一離開真 repo 就會 sys.exit(2)。
    因此改用唯一 tag 前綴 + tearDown 清理，把 RECORD 副作用限制在測試自己的檔案上。
    """

    TAG = "w1test"

    def setUp(self):
        import cio_approve as ca
        self.rdir = lane.BASE / ".git" / "cio_reviews"
        self.before = ({p.name for p in self.rdir.glob("*" + self.TAG + "*")}
                       if self.rdir.exists() else set())
        self._git, self._review = lane._git, rc.review
        # 外部工具隔離：cio_lane 以子行程呼叫 cio_approve 落地 **append-only 治理紀錄檔**，
        # 測試絕不可污染它 → subprocess.run 與 is_approved 皆以 stub 取代。
        # （RECORD 本體仍真寫入 rdir，路徑以唯一 tag 隔離並於 tearDown 清除。）
        self._ca, self._isap, self._sp = ca, ca.is_approved, lane.subprocess.run
        # is_approved 需有狀態：第 1 次呼叫（前置檢查「此 tree 是否已有 APPROVE」）必須為 False，
        # 否則車道會判定「已審查 → 跳過」而不送審；之後（落紀錄後複驗）才回 True。
        _calls = {"n": 0}

        def _isap(t):
            _calls["n"] += 1
            return _calls["n"] > 1
        ca.is_approved = _isap
        lane.subprocess.run = lambda *a, **k: type("_P", (), {
            "returncode": 0, "stdout": "", "stderr": ""})()
        self.sent = []

    def tearDown(self):
        lane._git, rc.review = self._git, self._review
        self._ca.is_approved, lane.subprocess.run = self._isap, self._sp
        if self.rdir.exists():
            for p in self.rdir.glob("*" + self.TAG + "*"):
                if p.name not in self.before:
                    p.unlink()

    # ── 工具 ──
    def _stub(self, responder):
        """stub review_chain.review（review_segmented 的底層呼叫；需接受 json_mode）。"""
        def _rev(prompt, max_tokens=8192, timeout=300, json_mode=False):
            self.sent.append(prompt)
            return responder(len(self.sent))
        rc.review = _rev

    def _run(self, patch_body):
        lane._git = _mk_git(patch_body)
        return lane.review_and_record(self.TAG)

    def _records(self):
        return sorted(self.rdir.glob("*" + self.TAG + "*")) if self.rdir.exists() else []

    # ── 1. 小 patch → 單段且內文含 patch ──
    def test_01_送審內文含實際patch(self):
        body = "diff --git a/x.py b/x.py\n@@ -1 +1 @@\n-MARKER_OLD\n+MARKER_NEW\n" * 20
        self._stub(lambda n: (_approve_json(), "stub"))
        ok, msg = self._run(body)
        self.assertTrue(ok, msg)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("MARKER_NEW", self.sent[0])          # 真的有程式碼內容
        self.assertIn("變更內容", self.sent[0])
        self.assertGreater(len(self.sent[0]), len(body) * 0.9)

    def test_02_超量patch自動分段且無遺漏重複(self):
        body = "".join(f"LINE{i:05d}\n" for i in range(16000))   # > DIFF_CAP
        self._stub(lambda n: (_approve_json(), "stub"))
        ok, msg = self._run(body)
        self.assertTrue(ok, msg)
        want = -(-len(body) // lane.DIFF_CAP)
        self.assertEqual(len(self.sent), want)
        self.assertGreater(want, 1)
        for i, p in enumerate(self.sent, 1):
            self.assertIn(f"第 {i}/{want} 段", p)

    def test_02b_分段不得二次截斷且涵蓋率100(self):
        """2026-10-15 修復項：每段 diff 完整落在 prompt 內（無「diff 未完整」警告）。

        舊版把「本段所屬檔案」脈絡串進 patch → 段長 = DIFF_CAP + 脈絡 → 二次截斷 →
        涵蓋率 99.6% → 當日 B1／R1 守門必然 REJECT（0da98b37 實測）。
        """
        body = "".join("D" * 999 + "\n" for _ in range(40))       # > DIFF_CAP
        self._stub(lambda n: (_approve_json(), "stub"))
        ok, msg = self._run(body)
        self.assertTrue(ok, msg)
        for p in self.sent:
            self.assertNotIn("diff 未完整", p)
            self.assertNotIn("涵蓋率", p)

    def test_03_RECORD含完整性記錄(self):
        body = "x" * (lane.DIFF_CAP + 50)
        self._stub(lambda n: (_approve_json(), "stub"))
        ok, _ = self._run(body)
        self.assertTrue(ok)
        recs = self._records()
        self.assertEqual(len(recs), 1)
        meta = json.loads(recs[0].read_text(encoding="utf-8"))["_lane_meta"]
        self.assertTrue(meta["has_patch"])
        self.assertEqual(meta["patch_total_chars"], len(body))
        self.assertEqual(meta["patch_sent_chars"], len(body))
        self.assertEqual(meta["coverage_pct"], 100.0)
        self.assertEqual(meta["segments"], 2)

    # ── 2. fail-closed 各情境 ──
    def test_04_某段REJECT_fail_closed(self):
        body = "y" * (lane.DIFF_CAP * 2 + 10)
        self._stub(lambda n: (json.dumps({"verdict": "REJECT",
                                          "blocking": ["sot_targets.py: 口徑錯誤"],
                                          "reviewed_commits": [{"commit": C12, "tree": T12}],
                                          "note": "no"}), "stub") if n == 2 else (_approve_json(), "stub"))
        ok, msg = self._run(body)
        self.assertFalse(ok)
        self.assertIn("blocking", msg)
        self.assertEqual(self._records(), [])          # 不落 RECORD

    def test_05_某段blocking_fail_closed(self):
        body = "z" * (lane.DIFF_CAP + 10)
        self._stub(lambda n: (json.dumps({"verdict": "APPROVE",
                                          "blocking": ["us30y_monitor.py: 靜默失敗"],
                                          "reviewed_commits": [{"commit": C12, "tree": T12}],
                                          "note": "blk"}), "stub") if n == 2 else (_approve_json(), "stub"))
        ok, msg = self._run(body)
        self.assertFalse(ok)
        self.assertIn("blocking", msg)
        self.assertIn("us30y_monitor.py", msg)
        self.assertEqual(self._records(), [])

    def test_06_綁定不符_fail_closed(self):
        self._stub(lambda n: (_approve_json(c12="deadbeef0000"), "stub"))
        ok, msg = self._run("small")
        self.assertFalse(ok)
        self.assertIn("綁定", msg)
        self.assertEqual(self._records(), [])

    def test_07_鏈失敗不降級且不落RECORD(self):
        def _boom(prompt, max_tokens=8192, timeout=300, json_mode=False):
            self.sent.append(prompt)
            raise RuntimeError("三層皆掛")
        rc.review = _boom
        ok, msg = self._run("w" * 100)
        self.assertFalse(ok)
        self.assertIn("審查鏈不可用", msg)
        self.assertIn("fail-closed", msg)
        # 關鍵：失敗前送出的內文仍必須含完整 patch（證明沒有「降級為統計摘要」）
        self.assertIn("變更內容", self.sent[0])
        self.assertEqual(self._records(), [])

    def test_08_非JSON回覆不得核准(self):
        """模型回非 JSON → 無法回報綁定 → 整體 REJECT（fail-closed，不得核准）。"""
        self._stub(lambda n: ("完全不是 JSON", "stub"))
        ok, msg = self._run("v" * 100)
        self.assertFalse(ok)
        self.assertIn("fail-closed", msg)
        self.assertEqual(self._records(), [])

    def test_09_涵蓋率不足_fail_closed(self):
        """車道自檢：build_review_prompts 回報涵蓋率 <100% → 不得送審、不得落 RECORD。"""
        _orig = rc.build_review_prompts
        try:
            rc.build_review_prompts = lambda *a, **k: (
                ["P"], {"total_chars": 12043, "provided_chars": 12000, "pct": 99.6, "segments": 1})
            self._stub(lambda n: (_approve_json(), "stub"))
            ok, msg = self._run("u" * 100)
            self.assertFalse(ok)
            self.assertIn("涵蓋率", msg)
            self.assertEqual(self.sent, [])            # 未送審
            self.assertEqual(self._records(), [])
        finally:
            rc.build_review_prompts = _orig

    def test_10_某段REJECT無blocking_視為無效審查_fail_closed(self):
        """B1／R1 契約：REJECT ⇔ blocking 非空。回 REJECT 但未指名缺陷＝無效審查，不得當核准。"""
        body = "y" * (lane.DIFF_CAP + 10)
        self._stub(lambda n: (json.dumps({"verdict": "REJECT", "blocking": [],
                                          "reviewed_commits": [{"commit": C12, "tree": T12}],
                                          "note": "no"}), "stub") if n == 2 else (_approve_json(), "stub"))
        ok, msg = self._run(body)
        self.assertFalse(ok)
        self.assertIn("無效審查", msg)
        self.assertEqual(self._records(), [])


class TestPromptContract(unittest.TestCase):
    """既有 prompt 契約的相容性（不傳 patch → 行為不變）。"""

    def test_01_不傳patch不含變更內容段(self):
        p = rc.build_review_prompt(C40, T40, "s", "files", "stat")
        self.assertNotIn("變更內容（實際 patch", p)
        self.assertIn(C12, p)
        self.assertIn(T12, p)

    def test_02_傳patch含內容與分段標示(self):
        p = rc.build_review_prompt(C40, T40, "s", "files", "stat",
                                   patch="PATCH_BODY", segment=(1, 2))
        self.assertIn("PATCH_BODY", p)
        self.assertIn("第 1/2 段", p)

    def test_03_單段不顯示分段標示(self):
        p = rc.build_review_prompt(C40, T40, "s", "files", "stat",
                                   patch="P", segment=(1, 1))
        self.assertNotIn("第 1/1 段", p)

    def test_04_審查重點含內容缺陷項(self):
        p = rc.build_review_prompt(C40, T40, "s", "files", "stat")
        self.assertIn("變更內容本身是否有具體缺陷", p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
