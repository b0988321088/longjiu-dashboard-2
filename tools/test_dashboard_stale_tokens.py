#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/test_dashboard_stale_tokens.py — 儀表板「舊值殘留」守門的正／負向驗收（2026-10-15）

對應使用者 2026-10-15 裁決（P1-2 Dashboard stale token 過時）：
  「現金 −0.7pp 不應被當成陳舊資料；真正過時的值仍必須觸發警示。」
驗收條件：
  ① 活的衍生值（穿透卡「實際 X% / 目標 Y% (±Zpp)」）不得被判為真殘留 → rc=0、列「清單過時」
  ② 真正的過時字面（已下線的舊句）仍必須 rc=1 並點名
  ③ active 清單不得存在「與今日活衍生值同形」的 token（誤判結構性根因）
  ④ 被退休的 token 必須留日期與理由，且偵測用途由更精確的條件承接（不得整份清空）

離線、唯讀真產物以外不動任何東西（注入測試用 $TEMP 副本）。
執行：python -X utf8 tools/test_dashboard_stale_tokens.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "check_dashboard_stale.py"
TOKENS = ROOT / "data" / "dashboard_stale_tokens.json"
PRECISE = "科技 14.3%（3,735,174 TWD）｜非科技 29.6%（7,764,551 TWD）"
PASS = FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")


def run_checker(html: str) -> tuple[int, str]:
    """把注入用的 HTML 寫進 $TEMP，再跑真守門（不碰產物）。"""
    d = Path(tempfile.mkdtemp(prefix="lj_stale_"))
    p = d / "index.html"
    p.write_text(html, encoding="utf-8", newline="\n")
    r = subprocess.run([sys.executable, "-X", "utf8", str(CHECKER), str(p)],
                       cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    import check_dashboard_stale as cds  # noqa: E402

    print("=== 儀表板舊值守門：正／負向驗收 ===")
    truth = cds.truth_tokens()

    # ③ 結構性根因：active 不得與今日活衍生值同形
    live = {t for t in truth if t.endswith("pp")}
    active = json.loads(TOKENS.read_text(encoding="utf-8"))["active"]
    clash = sorted(set(active) & live)
    check(f"③ active 與今日活衍生值（{sorted(live)}）無同形 token（否則會誤判活值為殘留）",
          not clash, f"衝突 token={clash}")

    # ① 活衍生值：即使 active 內有同形 token，也必須列「清單過時」而非真殘留
    real, obsolete = cds.scan("<b>4.3%</b> / 目標 5% (-0.7pp)", ["-0.7pp"])
    check("①a 活衍生值 token → 列『清單過時』（obsolete），非真殘留",
          obsolete and not real, f"real={real} obsolete={obsolete}")
    check("①b live 值確實由 snapshot 派生（現金 4.3% − 目標 5%）", "-0.7pp" in truth,
          f"truth 樣本={sorted(x for x in truth if x.endswith('pp'))}")
    rc, out = run_checker("<span>4.3% / 目標 5% (-0.7pp)</span>")
    check("①c 真守門跑活衍生值 HTML → rc=0（現金列不再被誤報）", rc == 0, f"rc={rc} out={out[:160]!r}")

    # ② 真正的過時字面仍必須被抓到（負向鑑別力）
    rc2, out2 = run_checker(f"<div>{PRECISE}｜科技目標 ≤20%（缺口 -0.7pp）</div>")
    check("②a 已下線的完整舊句仍觸發 rc=1（偵測力保留）", rc2 != 0, f"rc={rc2}")
    check("②b 命中時明確點名該字面", "科技 14.3%" in out2, out2[:160])
    real3, ob3 = cds.scan(PRECISE, [PRECISE])
    check("②c 舊句不是活值 → 判真殘留（非 obsolete）", real3 and not ob3, f"real={real3}")

    # ① 的真產物：交付的 index.html 必須乾淨
    rc3, out3 = subprocess.run([sys.executable, "-X", "utf8", str(CHECKER)], cwd=str(ROOT),
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=180).returncode, ""
    check("①d 交付 index.html 掃描 rc=0（無真殘留）", rc3 == 0, f"rc={rc3}")

    # ④ 退休紀錄完整性（逐項證明後退休，不得整份清空）
    d = json.loads(TOKENS.read_text(encoding="utf-8"))
    ret = {r["token"]: r for r in d.get("retired", [])}
    need = ["-0.7pp", "14.3%", "3,735,174", "7,764,551"]
    check("④a 四個過寬 token 已逐項退休且附日期", all(t in ret and ret[t].get("retired_at") for t in need),
          f"retired={sorted(ret)}")
    check("④b 每筆退休都有理由（可追溯，不是靜默移除）",
          all(str(ret[t].get("reason") or "").strip() for t in need if t in ret))
    check("④c 偵測用途由更精確的完整舊句 token 承接（active 內）", PRECISE in active)
    check("④d 未清空守門：active 仍保留 ≥30 項（其餘 31 項逐項查核後保留）",
          len(active) >= 30, f"active={len(active)}")

    print(f"\n測試結果：{PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
