#!/usr/bin/env python3
"""佔位符偵測的鑑別力測試（2026-10-15 建立）

背景：`check_dashboard_sync.py` 第 1 條（佔位符殘留）把 build_dashboard 合法注入的
JS 變數 `window.__LJ_LIVE_ROWS__` 誤判為「未注入的版型佔位符」→ 每天假 FAIL，
且真正的殘留會被假警報蓋掉。修法＝排除緊接在 `window.` 之後的樣式。

本測試以「複製最小檔案集到暫存目錄、跑真腳本」的方式驗證（不動 repo 產物）：

  A 基準：現行 index.html → 不得出現「佔位符殘留」（假警報已消除）
  A2 鑑別力前提：基準 html 確實含 `window.__LJ_LIVE_ROWS__`（否則 A 無意義）
  B 負向：注入位置型 `__FAKE_UNPLUGGED__` → 必須被抓到（真偵測未被削弱）
  C 負向：注入 `window.__FAKE_LIVE__`（JS 命名空間形式）→ 不視為殘留（語意一致）

跑法：python tools/test_dashboard_sync_placeholder.py（全過 exit 0）
"""
from __future__ import annotations

import datetime
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")


# 被測腳本在暫存目錄執行時需要的最小檔案集（缺檔會讓它中途失敗、看不到結論行）
_COPY = ["check_dashboard_sync.py", "links_config.py", "index_template.html", "snapshot.json"]


def run_case(html_text: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        for f in _COPY:
            src = BASE / f
            if src.exists():
                shutil.copy2(src, t / f)
        _dr = BASE / f"daily_report_v2_{datetime.date.today().isoformat()}.html"
        if _dr.exists():
            shutil.copy2(_dr, t / _dr.name)
        (t / "index.html").write_text(html_text, encoding="utf-8")
        p = subprocess.run([sys.executable, "-X", "utf8", str(t / "check_dashboard_sync.py")],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=str(t), timeout=300)
        return (p.stdout or "") + (p.stderr or "")


def main() -> int:
    print("=== 佔位符偵測鑑別力（check_dashboard_sync.py 第 1 條） ===")
    html = (BASE / "index.html").read_text(encoding="utf-8")

    check("A2 鑑別力前提：index.html 含 window.__LJ_LIVE_ROWS__（合法 JS 變數）",
          "window.__LJ_LIVE_ROWS__" in html)

    out_a = run_case(html)
    check("A 基準：現行 index.html 不再被判「佔位符殘留」",
          "佔位符殘留" not in out_a,
          next((ln.strip() for ln in out_a.splitlines() if "佔位符殘留" in ln), "")[:120])

    out_b = run_case(html.replace("</body>", "<div>__FAKE_UNPLUGGED__</div></body>", 1))
    check("B 負向：注入位置型佔位符 __FAKE_UNPLUGGED__ → 必須仍被抓到（真偵測未削弱）",
          "佔位符殘留" in out_b and "__FAKE_UNPLUGGED__" in out_b,
          f"len(out)={len(out_b)}")

    out_c = run_case(html.replace("</body>", "<script>window.__FAKE_LIVE__ = [];</script></body>", 1))
    check("C 語意一致：window.__FAKE_LIVE__（JS 命名空間形式）不列入殘留",
          "佔位符殘留" not in out_c,
          next((ln.strip() for ln in out_c.splitlines() if "佔位符殘留" in ln), "")[:120])

    print(f"\n測試結果：{PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
