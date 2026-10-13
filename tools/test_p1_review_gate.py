#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_p1_review_gate.py — P1 審查閘門核心回歸（2026-10-13）

刻意只留 5 條：守住實質問題所需的證據，不為讓工單看起來完整而增加維護負擔
（使用者 2026-10-13 裁決：少管理、少變更、重結果）。

  1. ★ 核准放行邊界：verdict=APPROVE 但 blocking 非空 → **不得**寫入正式核准紀錄
  2. 非阻塞項（required_fixes／required_changes）不得單獨改變 APPROVE 判定
  3. 缺 blocking 欄位或 JSON 格式錯誤 → fail-closed（不得當成空清單放行）
  4. 既有發布路徑不被意外阻擋（auto_record 的 AUTO-checker 通道、人工自宣告通道）
  5. 兩條車道共用同一 builder：12 碼綁定、契約在 prompt 內、不洩漏完整 sha

全部在臨時 git repo 內實跑，不污染真紀錄檔。
執行：python tools/test_p1_review_gate.py
"""
import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(r"C:/Users/bot/Desktop/longjiu_system")
CIO_APPROVE = REPO / "cio_approve.py"
sys.path.insert(0, str(REPO))
import review_chain as RC          # noqa: E402

C_FULL = "3089735c0e687d34741b234545f2753223bc4f22"
T_FULL = "f42641e8452f301238cd09d8c117edd361399"
LANES = ("cio_lane.py", "regenerate_report.py")


class TmpRepo:
    """臨時 git repo：cio_approve.py 在其中實跑，紀錄檔完全隔離。"""

    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="p1_gate_"))
        self._git("init", "-q")
        self._git("-c", "user.email=t@t", "-c", "user.name=t",
                  "commit", "-q", "--allow-empty", "-m", "init")

    def _git(self, *a):
        return subprocess.run(["git", *a], cwd=str(self.dir), capture_output=True,
                              text=True, encoding="utf-8", errors="replace")

    @property
    def approve_file(self) -> Path:
        return self.dir / ".git" / "CIO_APPROVED"

    def rows(self) -> list[str]:
        if not self.approve_file.exists():
            return []
        return [x for x in self.approve_file.read_text(encoding="utf-8").splitlines() if x.strip()]

    def approve(self, *args, payload=None):
        if payload is not None:
            p = self.dir / "r.json"
            p.write_text(payload if isinstance(payload, str)
                         else json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            args = ("--result", str(p)) + tuple(args)
        return subprocess.run([sys.executable, str(CIO_APPROVE), *args],
                              cwd=str(self.dir), capture_output=True,
                              text=True, encoding="utf-8", errors="replace")


class TestApproveReleaseBoundary(unittest.TestCase):
    """核准放行邊界：release boundary ＝ verdict == APPROVE 且 blocking == []。"""

    def test_1_approve_with_blocking_is_refused(self):
        """★ 核心：APPROVE 但 blocking 非空 → 絕不可寫入正式核准紀錄。"""
        r = TmpRepo()
        p = r.approve("--reviewer", "CIO-Test", "--commit", "HEAD",
                      payload={"verdict": "APPROVE", "blocking": ["現金口徑計算錯誤"]})
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertEqual(r.rows(), [], "blocking 非空時不得落任何紀錄")
        self.assertIn("release boundary", p.stderr)

    def test_2_non_blocking_items_do_not_change_verdict(self):
        """required_fixes／required_changes 非空 → 仍可落紀錄（屬後續 hardening）。"""
        for key in ("required_fixes", "required_changes"):
            with self.subTest(field=key):
                r = TmpRepo()
                p = r.approve("--reviewer", "CIO-Test", "--commit", "HEAD",
                              payload={"verdict": "APPROVE", "blocking": [], key: ["後續硬化項"]})
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(len(r.rows()), 1, f"{key} 不應阻擋落紀錄")

    def test_3_missing_or_malformed_blocking_fails_closed(self):
        """缺 blocking 欄位、或 result 檔格式錯誤 → 一律 fail-closed。"""
        r = TmpRepo()
        p = r.approve("--reviewer", "CIO-Test", "--commit", "HEAD",
                      payload={"verdict": "APPROVE", "required_fixes": []})
        self.assertEqual(p.returncode, 1, "缺 blocking 欄位＝無法確認 → fail-closed")
        self.assertEqual(r.rows(), [])

        r2 = TmpRepo()
        p2 = r2.approve("--reviewer", "CIO-Test", "--commit", "HEAD", payload="{ not json ")
        self.assertEqual(p2.returncode, 2)
        self.assertEqual(r2.rows(), [])

    def test_4_legacy_channels_not_blocked(self):
        """既有通道不得被本次收緊阻擋：AUTO-checker（無審查 JSON）、人工自宣告。"""
        r = TmpRepo()
        p = r.approve("--verdict", "APPROVE", "--reviewer", "AUTO-checker:test.py",
                      "--commit", "HEAD")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("SELF-DECLARED", r.approve_file.read_text(encoding="utf-8"))

        r2 = TmpRepo()
        p2 = r2.approve("--verdict", "APPROVE", "--reviewer", "CIO-Manual", "--commit", "HEAD")
        self.assertEqual(p2.returncode, 0, p2.stdout + p2.stderr)
        self.assertIn("SELF-DECLARED:CIO-Manual",
                      r2.approve_file.read_text(encoding="utf-8"))


class TestLaneContractAndBinding(unittest.TestCase):
    """prompt 與綁定修改的驗收（不得只測 cio_approve.py）。"""

    def test_5_lanes_share_contract_builder(self):
        # (a) 兩條車道都必須呼叫共用的 builder
        for lane in LANES:
            with self.subTest(lane=lane):
                tree = ast.parse((REPO / lane).read_text(encoding="utf-8"))
                called = any(
                    isinstance(n, ast.Call)
                    and getattr(n.func, "attr", getattr(n.func, "id", "")) == "build_review_prompt"
                    for n in ast.walk(tree)
                )
                self.assertTrue(called, f"{lane} 未使用 review_chain.build_review_prompt")
                self.assertNotIn("你是龍九控股的獨立 CIO 審查者",
                                 (REPO / lane).read_text(encoding="utf-8"),
                                 f"{lane} 仍有內嵌 prompt 複本")

        # (b) builder 只允許一處定義
        defs = []
        for p in REPO.glob("*.py"):
            try:
                t = ast.parse(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if any(isinstance(n, ast.FunctionDef) and n.name == "build_review_prompt"
                   for n in ast.walk(t)):
                defs.append(p.name)
        self.assertEqual(defs, ["review_chain.py"], f"builder 定義不唯一：{defs}")

        # (c) 綁定 12 碼、不洩漏完整 sha、契約在 prompt 內
        prompt = RC.build_review_prompt(C_FULL, T_FULL, "主旨", "a.py", " a.py | 1 +")
        self.assertIn(C_FULL[:12], prompt)
        self.assertIn(T_FULL[:12], prompt)
        self.assertNotIn(C_FULL, prompt, "不得把完整 commit sha 交給免費層模型抄")
        self.assertNotIn(T_FULL, prompt, "不得把完整 tree sha 交給免費層模型抄")
        for clause in ("`blocking=[]` ⇒ verdict 必須是 `APPROVE`", "不得改變 verdict",
                       "不得自行補齊", "具體、可指名"):
            with self.subTest(clause=clause):
                self.assertIn(clause, prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
