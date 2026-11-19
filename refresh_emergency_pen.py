#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""refresh_emergency_pen.py — 緊急應變報告「穿透卡片」對齊 snapshot 真值

為什麼要有這支（2026-11-19 血淚）：
    緊急應變報告（emergency_report_{date}.html）是 13:00 由 emergency_1330.py 產出的
    「盤中快照」，內容寫死當下的穿透率與總資產。當天盤後只要任何真值變動
    （收盤覆蓋、基金淨值、保單 App、MoneyBook 匯入），check_penetration_consistency
    就會以「緊急應變 缺少真值 → 台股 x%、總資產 n」擋下 four_source_sync，
    導致 sync_all 在 10/30 步驟中止、後面 20 步全不執行。
    2026-11-19 一天內因此連擋三次，且每次都是手動改數字（patch over patch）。

做法（冪等、不碰敘述內文語意）：
    ① 用 update_all.calc_penetration 即時重算，不讀 penetration.actual_pct 快取
    ② 讀出頁面上「舊的」穿透數字 → 以「舊值→新值」對照全頁做字串替換
       （敘述段落的 12.1%／3,149,355 與卡片同步，不會前後矛盾）
    ③ 卡片段落重建為標準格式（總資產、台股、美股、防守、債券、現金）
    ④ 檔案不存在（非應變日）→ 直接 exit 0，不製造檔案、不擋流程

用法：
    python refresh_emergency_pen.py            # 今天
    python refresh_emergency_pen.py 2026-11-19
    python refresh_emergency_pen.py --check    # 只印差異，不寫檔
"""
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"

LABELS = [
    ("台股", "台股市值型成長"),
    ("美股", "美股市值型成長"),
    ("防守", "防守型配息"),
    ("債券", "債券"),
    ("現金", "現金/安全網"),
]


def _truth():
    from update_all import calc_penetration

    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    total = float(snap.get("total_assets", 0) or 0)
    pen = calc_penetration(
        snap.get("cash_total", 0) or 0,
        snap.get("insurance_total", 0) or 0,
        snap.get("securities_total_market_value", 0) or 0,
        snap.get("fund_market", 0) or 0,
        snap=snap,
    )
    num = {k: v for k, v in pen.items() if isinstance(v, (int, float))}
    pct = {k: (round(v / total * 100, 1) if total else 0) for k, v in num.items()}
    return snap, total, num, pct


def refresh(date_str: str, write: bool = True) -> int:
    path = BASE / f"emergency_report_{date_str}.html"
    if not path.exists():
        print(f"ℹ️ 無緊急應變報告（{path.name}）→ 非應變日，略過")
        return 0
    html = path.read_text(encoding="utf-8")
    snap, total, num, pct = _truth()

    # 舊卡片數字（若抓不到就整段重建，只做卡片層）
    m = re.search(r"總資產\s*<?b?>?\s*([\d,]+).*?台股\s*([\d.]+)%.*?美股\s*([\d.]+)%"
                  r".*?防守\s*([\d.]+)%.*?債券\s*([\d.]+)%.*?現金\s*([\d.]+)%", html, re.S)
    changes = []
    if m:
        old_total = m.group(1)
        old = {"台股": float(m.group(2)), "美股": float(m.group(3)),
               "防守": float(m.group(4)), "債券": float(m.group(5)), "現金": float(m.group(6))}
        new_total = f"{int(total):,}"
        if old_total != new_total:
            html = html.replace(old_total, new_total)
            changes.append(f"總資產 {old_total}→{new_total}")
        for label, key in LABELS:
            new = pct.get(key, 0)
            if old[label] != new:
                html = html.replace(f"{label} {old[label]}%", f"{label} {new}%")
                changes.append(f"{label} {old[label]}%→{new}%")
    # 逐桶金額（例：台股市值型成長 3,149,355 元）
    # 2026-11-19 血淚：這條曾把「現金底線 700,000」誤認成現金桶金額而覆寫成 1,195,855。
    # 限縮——只認「桶名 + 7~8 位數字 + 元」的寫法，且現金桶一律不參與（底線/可動用是別的口徑）。
    AMOUNT_LABELS = [
        (r"台股市值型成長", "台股市值型成長"),
        (r"美股市值型成長", "美股市值型成長"),
        (r"防守型配息", "防守型配息"),
        (r"債券", "債券"),
    ]
    for label_pat, key in AMOUNT_LABELS:
        amt = int(num.get(key, 0))
        pat = re.compile(rf"{label_pat}[^0-9]{{0,6}}([\d,]{{7,11}})\s*元")
        mm = pat.search(html)
        if mm:
            cur = mm.group(1)
            if cur.replace(",", "") != str(amt):
                html = html.replace(cur, f"{amt:,}")
                changes.append(f"{label_pat} {cur}→{amt:,}")

    # 卡片重建
    card = ("<div class=\"pen\"><h3>📊 資產穿透（%s）</h3><p>總資產 %s TWD｜台股 %.1f%%｜美股 %.1f%%"
            "｜防守 %.1f%%｜債券 %.1f%%｜現金 %.1f%%</p></div>") % (
        date_str, f"{int(total):,}",
        pct.get("台股市值型成長", 0), pct.get("美股市值型成長", 0),
        pct.get("防守型配息", 0), pct.get("債券", 0), pct.get("現金/安全網", 0))
    new_html, n = re.subn(r'<div class="pen"><h3>📊 資產穿透[^<]*</h3><p>.*?</p></div>',
                          card, html, count=1, flags=re.S)
    if n == 0:
        new_html = html.replace("</body>", card + "</body>")
        changes.append("卡片新增")
    html = new_html

    for label, key in LABELS:
        if f"{label} {pct.get(key, 0)}%" not in html:
            print(f"❌ 仍缺少 {label} {pct.get(key,0)}%")
            return 1
    if f"總資產 {int(total):,}" not in html:
        print(f"❌ 仍缺少 總資產 {int(total):,}")
        return 1

    if not changes:
        print(f"✅ 已是最新（{path.name}）")
        return 0
    print("🔁 " + "、".join(changes))
    if write:
        path.write_text(html, encoding="utf-8")
        print(f"✅ 已更新 {path.name}")
    else:
        print("--check：未寫檔")
    return 0


def main():
    args = [a for a in sys.argv[1:]]
    write = "--check" not in args
    args = [a for a in args if not a.startswith("--")]
    date_str = args[0] if args else __import__("datetime").date.today().isoformat()
    raise SystemExit(refresh(date_str, write=write))


if __name__ == "__main__":
    main()
