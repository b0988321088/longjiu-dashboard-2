#!/usr/bin/env python3
"""check_dashboard_structure.py — 儀表板 HTML 巢狀結構嚴格檢查（2026-08-29 血淚）

背景：8/29 儀表板「手機看不到後 3 分頁」的真正根因 =
4 處 `<div class="..." style="width: 79%"</div>` 開標籤缺 `>`，
手機瀏覽器（嚴格解析）在 panel-2 就崩潰 → 吞掉 panel-3/4/5；
Chrome headless 會自動修復錯誤標籤 → 測試正常但真實手機失敗。

正則「標籤平衡」抓不到巢狀錯誤（開閉數量平衡但巢狀錯位），
必須用 HTMLParser 嚴格追蹤開閉順序。

用法：python check_dashboard_structure.py [檔名，預設 index.html]
退出碼：0 = 結構乾淨；1 = 有巢狀錯誤/未閉合
"""
import sys
from html.parser import HTMLParser
from pathlib import Path

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
        'link', 'meta', 'param', 'source', 'track', 'wbr'}


class StrictParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []   # [(tag, line)]
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.errors.append(f"多餘閉合 </{tag}> line {self.getpos()[0]}")
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for j in range(len(self.stack) - 1, i, -1):
                    t, ln = self.stack[j]
                    self.errors.append(
                        f"巢狀錯誤: <{t}> line {ln} 被 </{tag}> line {self.getpos()[0]} 提前關閉")
                del self.stack[i:]
                break
        else:
            self.errors.append(f"找不到開標籤 </{tag}> line {self.getpos()[0]}")


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    path = Path(__file__).resolve().parent / target
    if not path.exists():
        print(f"❌ 找不到 {path}")
        return 1
    h = path.read_text(encoding="utf-8")
    p = StrictParser()
    p.feed(h)
    p.close()

    ok = True
    if p.stack:
        ok = False
        print(f"❌ {len(p.stack)} 個標籤未閉合:")
        for tag, line in p.stack[:10]:
            print(f"   <{tag}> line {line}")
    if p.errors:
        ok = False
        print(f"❌ {len(p.errors)} 個巢狀錯誤:")
        for e in p.errors[:10]:
            print(f"   {e}")
    if ok:
        print(f"✅ {target} HTML 巢狀結構乾淨（{len(h)} 字元）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
