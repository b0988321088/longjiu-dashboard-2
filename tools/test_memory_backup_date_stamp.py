#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/test_memory_backup_date_stamp.py — 06:50 記憶備份「日期戳記」行為測試（零網路）

背景（2026-10-21 使用者裁決 A＋C 的 C 案）：
    notion_cleanup 規則 2＝「類型 ∈ 備份類 且 日期 < today−N 天 → 可封存」。
    記憶備份頁的「日期」屬性原本停在首次建立日 2026-08-04，於是 2026-10-16 06:53
    被自動清理封存 → 06:50 連續 5 天失敗。修法＝每次內容寫入並通過 md5 往返後，
    同步把「日期」屬性更新為當日；清理規則本身不動（避免掩蓋真正過期的備份）。

本測試以假 notion() 驗四件事（不連網、不寫備份日誌）：
    ① 成功寫入後確實送出 PATCH pages/{id}，properties.日期.date.start == today
    ② 日期戳記發生在「內容寫入」之後（不是先改日期再寫內容）
    ③ 日期屬性更新失敗 → phase2_notion 必須拋錯（fail-closed，不得靜默）
    ④ md5 往返不符 → 不應送出日期戳記（先驗內容，再談防誤封存）

用法：python tools/test_memory_backup_date_stamp.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import memory_backup as mb  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}{(' — ' + detail) if detail else ''}")


class FakeNotion:
    """最小 Notion 假物件：只模擬 phase2_notion 用到的四種呼叫，並記錄順序。"""

    def __init__(self, page_text: str, *, fail_prop: bool = False, corrupt_roundtrip: bool = False):
        self.page_text = page_text
        self.fail_prop = fail_prop
        self.corrupt_roundtrip = corrupt_roundtrip
        self.written = ""          # 實際寫進 children 的文字
        self.calls: list[str] = []  # 呼叫順序（write / date / delete）
        self.date_sent = None

    def __call__(self, method, path, body=None):
        body = body or {}
        if method == "GET" and path.endswith("/children"):
            if not self.calls or "write" not in self.calls:
                return 200, {"results": []}
            back = self.written
            if self.corrupt_roundtrip:
                back = back + "（污染）"
            return 200, {"results": [{"type": "code",
                                      "code": {"rich_text": [{"plain_text": back}]}}]}
        if method == "DELETE":
            return 200, {}
        if method == "PATCH" and path.endswith("/children"):
            blocks = body.get("children") or []
            for b in blocks:
                if b.get("type") == "code":
                    self.written = "".join(t["text"]["content"]
                                           for t in b["code"]["rich_text"])
            self.calls.append("write")
            return 200, {}
        if method == "PATCH" and path.startswith("pages/"):
            self.date_sent = ((body.get("properties") or {}).get("日期") or {}).get("date", {}).get("start")
            self.calls.append("date")
            if self.fail_prop:
                raise RuntimeError("Notion PATCH pages/x -> HTTP 400: simulated")
            return 200, {}
        raise AssertionError(f"未預期的呼叫：{method} {path}")


def run_case(name: str, fake: FakeNotion, *, expect_error: bool):
    src = mb.MEM_DIR / "MEMORY.md"
    text = src.read_text(encoding="utf-8")
    orig_notion, orig_log = mb.notion, mb.log
    mb.notion = fake
    mb.log = lambda *_a, **_k: None          # 不寫 backups/backup_log.txt
    try:
        err = None
        try:
            mb.phase2_notion()
        except Exception as e:                # noqa: BLE001 — 測試要看錯誤字串
            err = e
        return text, err
    finally:
        mb.notion, mb.log = orig_notion, orig_log


def main() -> int:
    print("=== memory_backup 日期戳記測試 ===")
    today = date.today().isoformat()

    # ①＋② 正常路徑：先寫內容、後蓋日期，且日期＝今天
    fake = FakeNotion("")
    run_case("happy", fake, expect_error=False)
    check("寫入後有送出日期戳記", fake.calls.count("date") == 1, f"calls={fake.calls}")
    check("日期戳記內容＝今天", fake.date_sent == today, f"送出={fake.date_sent!r} 期望={today!r}")
    check("順序為 先內容 後日期", fake.calls[:2] == ["write", "date"], f"calls={fake.calls}")

    # ③ 日期屬性更新失敗 → 必須拋錯（fail-closed）
    fake2 = FakeNotion("", fail_prop=True)
    _, err2 = run_case("prop-fail", fake2, expect_error=True)
    check("日期屬性失敗時拋錯", err2 is not None, "未拋錯 → 防誤封存會靜默失效")
    check("錯誤訊息標明防誤封存", bool(err2) and "防誤封存" in str(err2), f"訊息={err2}")

    # ④ md5 往返不符 → 不得送出日期戳記
    fake3 = FakeNotion("", corrupt_roundtrip=True)
    _, err3 = run_case("md5-fail", fake3, expect_error=True)
    check("md5 不符時拋錯", err3 is not None)
    check("md5 不符時不蓋日期", "date" not in fake3.calls, f"calls={fake3.calls}")

    print(f"\n=== 日期戳記測試：PASS {PASS} / FAIL {FAIL} ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
