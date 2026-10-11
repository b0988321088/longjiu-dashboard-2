# -*- coding: utf-8 -*-
"""test_label_mask.py — tools/label_mask.py 驗收（2026-10-11 晨間產線事件修復）

對應使用者裁決的驗收項：
  Phase 3.2 合法遮罩差異能通過正規化檢查
  Phase 3.3 非遮罩欄位的任意變更仍會失敗
  Phase 3.5 正規化不得成為洩漏或寫檔向量（純函式、無寫檔 API）
  Phase 3.8 成功放行／失敗阻擋／不完整產物 三情境的判定證據（本檔 T10/T14/T15）

用法：python tools/test_label_mask.py    → 全綠 exit 0；任一 FAIL exit 1
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import label_mask as lm  # noqa: E402

PASS, FAIL = [], []


def chk(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + (f" — {detail}" if detail else ""))


NUM = "FJ" + "33"          # 數值型（原始代號）
NUM2 = "FJ" + "55"         # 另一組數值型（用於跨代號界線測試）
MSK = "FJXX"               # 遮罩型

print("== A. 正規化語意 ==")
chk("T1 數值型 → 遮罩型", lm.normalize(f"第一金 {NUM}") == f"第一金 {MSK}")
chk("T1b 遮罩型冪等", lm.normalize(f"第一金 {MSK}") == f"第一金 {MSK}")
_src = f"（安聯約2年 vs {NUM} 3-4個月）"
_out = lm.normalize(_src)
chk("T2 只動標籤 2 字元（長度不變）", len(_out) == len(_src), f"{len(_out)} vs {len(_src)}")
_diff = [i for i, (a, b) in enumerate(zip(_src, _out)) if a != b]
chk("T2b 差異僅落在代號 2 字元內", _diff == [len("（安聯約2年 vs FJ"), len("（安聯約2年 vs FJ") + 1], str(_diff))
chk("T3 兩種錨點都涵蓋", lm.normalize(f"第一金 {NUM}") == f"第一金 {MSK}"
    and lm.normalize(f"vs {NUM}") == f"vs {MSK}")

print("== B. 反向：不得忽略任何非標籤差異 ==")
h1 = f"<tr><td>第一金 {NUM}</td><td>1,868,043</td></tr>"
h2 = "<tr><td>第一金 " + MSK + "</td><td>1,868,044</td></tr>"      # 金額差 1
chk("T4 金額差 1 → 仍判不同", not lm.same_after_mask(h1, h2))
chk("T5 多一整行 → 仍判不同", not lm.same_after_mask(h1, h1 + "<tr><td>x</td></tr>"))
chk("T6 非核准型態（FJAB）不正規化 → 判不同",
    not lm.same_after_mask(f"第一金 FJAB", f"第一金 {MSK}"))
chk("T7 跨代號（33 vs 55）→ 視為相同（明文界線：代號不納入比對）",
    lm.same_after_mask(f"第一金 {NUM}", f"第一金 {NUM2}"))
chk("T8 無錨點的裸代號不正規化 → 判不同", not lm.same_after_mask(f"代號 {NUM}", f"代號 {MSK}"))
chk("T8b 標籤相同但其他文字不同 → 判不同",
    not lm.same_after_mask(f"第一金 {NUM} 累計", f"第一金 {NUM} 合計"))

print("== C. 邊界與介面 ==")
chk("T9 bytes 介面（UTF-8）", lm.same_after_mask(f"第一金 {NUM}".encode(), f"第一金 {MSK}".encode()))
chk("T9b 非 UTF-8 bytes → 退回位元比對（不炸、正確判不同）",
    not lm.same_after_mask(b"\xff\xfe\x01", b"\xff\xfe\x02"))
chk("T10 空值 vs 內容 → 判不同（不完整產物不得冒充相同）",
    not lm.same_after_mask("", h1) and not lm.same_after_mask(h1, ""))
_lm_src = (TOOLS / "label_mask.py").read_text(encoding="utf-8")
chk("T11 純函式：無寫檔 API（不得成為洩漏向量）",
    not re.search(r"\.write_text\(|\.write_bytes\(|open\([^)]*['\"][wa]", _lm_src))

print("== C2. 正向遮罩斷言（補回 A/B 放寬掉的偵測面；CIO required_fix #1）==")
chk("T17a 未遮罩數值型 → 抓到（re-leak 可攔）", lm.has_unmasked_label(f"<td>第一金 {NUM}</td>"))
chk("T17b 行內註記未遮罩 → 抓到", lm.has_unmasked_label(f"（vs {NUM} 3-4個月）"))
chk("T17c 已遮罩 → 不誤報", not lm.has_unmasked_label(f"<td>第一金 {MSK}</td>"))
chk("T17d 無標籤／空字串 → 不誤報（不得把正常頁面判紅）",
    not lm.has_unmasked_label("<td>無標籤</td>") and not lm.has_unmasked_label(""))

print("== D. 真實 A/B（沙盒；若無則略過）==")
import tempfile  # noqa: E402
SB = Path(tempfile.gettempdir()) / "verify_pc_task12"
_old = SB / "_old"
did = 0
if (SB / "investment_performance.html").exists() and (_old / "investment_performance.html").exists():
    a = (SB / "investment_performance.html").read_bytes()
    b = (_old / "investment_performance.html").read_bytes()
    chk("T12 真實 HTML（舊 vs 新）正規化後相同", lm.same_after_mask(a, b), f"{len(a)} vs {len(b)} bytes")
    # T13 把新版某個金額字元改掉（僅在記憶體）→ 必須判不同
    _t = a.decode("utf-8")
    _i = _t.find("1,868,043")
    if _i > 0:
        mutated = (_t[:_i] + "1,868,044" + _t[_i + 9:]).encode()
        chk("T13 真實 HTML 注入非標籤差異 → 判不同", not lm.same_after_mask(mutated, b))
    else:
        chk("T13 真實 HTML 注入非標籤差異 → 判不同", False, "找不到注入錨點")
    did += 1
if (SB / "_new_bip.log").exists() and (_old / "bip.log").exists():
    na = (SB / "_new_bip.log").read_text(encoding="utf-8", errors="replace")
    ob = (_old / "bip.log").read_text(encoding="utf-8", errors="replace")
    chk("T14 真實 console（舊 vs 新）正規化後相同", lm.same_after_mask(na, ob))
    chk("T14b console 注入非標籤差異 → 判不同",
        not lm.same_after_mask(na.replace("配息", "收益", 1), ob))
    did += 1
if (SB / "_new_mtd.log").exists() and (_old / "mtd.log").exists():
    nm_ = (SB / "_new_mtd.log").read_text(encoding="utf-8", errors="replace")
    om_ = (_old / "mtd.log").read_text(encoding="utf-8", errors="replace")
    # CIO required_fix #2：mtd console 舊/新逐位元相同 → 不得放寬，維持原始位元相等
    chk("T16 mtd console 維持逐位元相同（無須放寬）", nm_ == om_)
    did += 1

print("== E. 未經正規化的原始態（事故重現）==")
if (SB / "investment_performance.html").exists() and (_old / "investment_performance.html").exists():
    a = (SB / "investment_performance.html").read_bytes()
    b = (_old / "investment_performance.html").read_bytes()
    chk("T15 原始位元比對必然不同（＝10/11 事故根因）", a != b)
    chk("T15b 正規化後相同（＝修復後放行）", lm.same_after_mask(a, b))
else:
    print("  ⏭ 無沙盒可用（先跑 tools/verify_performance_core_task12.py 產生）")

print(f"\n{len(PASS)}/{len(PASS) + len(FAIL)} PASS")
if FAIL:
    print("FAIL:"); [print("  -", f) for f in FAIL]
sys.exit(1 if FAIL else 0)
