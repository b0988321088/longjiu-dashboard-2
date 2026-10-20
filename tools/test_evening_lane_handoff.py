# -*- coding: utf-8 -*-
"""test_evening_lane_handoff.py — evening_sync 步 4／步 5 的車道交接驗收（2026-10-20 A 案）

驗的是行為契約，不是實作細節：
T1 auto_push rc=0 → 視為已推
T2 rc=3（強制真 CIO）＋車道 APPROVE → 必須再送 --record skip 推一次
T3 車道失敗且本步驟有 commit → 必須 reset --soft HEAD~1（撤回毒藥 commit）並回 False
T4 車道失敗但本次沒有 commit（收尾提交）→ 不得 reset，回 False
T5 rc≠0/3（一般推送失敗）→ 回 False，不得回報成功
T6 車道 APPROVE 但第二段推送失敗 → 仍回 False（不得只看審查就宣告成功）
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import evening_sync as es  # noqa: E402

fails = []


def chk(name, cond, detail=""):
    print(("  ✅ " if cond else "  ❌ ") + name + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(name)


class R:
    def __init__(self, rc, out=""):
        self.returncode, self.stdout, self.stderr = rc, out, ""


def run_case(heads, rc_seq, lane_ok=True, own=True):
    """heads: _git_head 依序回傳的值（模擬 commit 前後）"""
    calls, resets = [], []
    state = {"h": 0, "seq": list(rc_seq)}

    def runner(cmd, **kw):
        calls.append(cmd)
        if cmd[:3] == ["git", "reset", "--soft"]:
            resets.append(cmd)
            return R(0, "reset ok")
        out = state["seq"].pop(0) if state["seq"] else 0
        return R(out, f"stub rc={out}")

    def head():
        v = heads[min(state["h"], len(heads) - 1)]
        state["h"] += 1
        return v

    orig = es._git_head
    es._git_head = head
    try:
        lines = []
        ok = es._publish("auto: t", lines, own_commit=own, runner=runner,
                         lane=(lambda: (lane_ok, "APPROVE" if lane_ok else "REJECT")))
    finally:
        es._git_head = orig
    return ok, calls, resets, lines


print("== T1 rc=0 ==")
ok, calls, resets, _ = run_case(["A", "A"], [0])
chk("直接推成功", ok is True and len(calls) == 1, f"calls={len(calls)}")

print("== T2 rc=3 + 車道 APPROVE ==")
ok, calls, resets, _ = run_case(["A", "B"], [3, 0])
second_skip = len(calls) == 2 and "--record" in calls[1] and "skip" in calls[1]
chk("審查後以 --record skip 重推", ok is True and second_skip, f"calls={calls}")

print("== T3 車道 REJECT（有 commit）==")
ok, calls, resets, _ = run_case(["A", "B"], [3], lane_ok=False)
chk("撤回本步驟 commit", ok is False and len(resets) == 1, f"resets={resets}")

print("== T4 車道 REJECT（無 commit，收尾提交未產生）==")
ok, calls, resets, _ = run_case(["A", "A"], [3], lane_ok=False, own=False)
chk("不得 reset", ok is False and len(resets) == 0, f"resets={resets}")

print("== T5 一般推送失敗 rc=1 ==")
ok, calls, resets, _ = run_case(["A", "A"], [1])
chk("回 False 且不宣稱成功", ok is False and len(calls) == 1)

print("== T6 車道 APPROVE 但第二段推送失敗 ==")
ok, calls, resets, _ = run_case(["A", "B"], [3, 1])
chk("仍回 False", ok is False, f"calls={len(calls)}")

print("\n=== 車道交接驗收：" + ("PASS" if not fails else f"FAIL（{len(fails)}）") + " ===")
sys.exit(0 if not fails else 1)
