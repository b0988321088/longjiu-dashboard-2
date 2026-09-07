#!/usr/bin/env python3
"""cio_review_ingest.py — CIO 每日戰略審查 → 儀表板資料收錄（2026-09-07 建立）

來源：Hermes cron 輸出檔 ~/AppData/Local/hermes/cron/output/fb014d759ac5/2026-*.md
      每檔含「## Response」後的審查報告正文。
產出：longjiu_system/cio_review.json（供儀表板「🧑💻 CIO 審查」分頁 JS 即時讀取）
排程：每週一/三 18:45（CIO 18:30 審查後 15 分鐘，no_agent cron）
行為：成功靜默（stdout 空 = 不推送）；錯誤才印出。
注意：LLM 報告格式會漂移 → 只擷取報告標題行(日期/星期) + 正文全文，不做欄位級解析。
"""
import json
import re
from datetime import datetime
from pathlib import Path

BASE = Path(r"C:\Users\bot\Desktop\longjiu_system")
SRC = Path(r"C:\Users\bot\AppData\Local\hermes\cron\output\fb014d759ac5")
OUT = BASE / "cio_review.json"

TITLE_RE = re.compile(r"【龍九控股：18:30 戰略審計與決策復盤】\s*(\d{4}-\d{2}-\d{2})（(?:週)?([一二三四五六日天])）")


def parse_md(path: Path):
    """回傳 {date, weekday, text} 或 None。"""
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        return None
    idx = raw.find("## Response")
    body = raw[idx + len("## Response"):] if idx >= 0 else raw
    m = TITLE_RE.search(body)
    if not m:
        return None
    # 正文 = 標題行起到尾（去除結尾分隔線/空白）
    start = body.find(m.group(0))
    text = body[start:].strip()
    text = re.sub(r"\n\s*-{3,}\s*$", "", text).strip()
    if len(text) < 60 or text.startswith("[SILENT]"):
        return None
    return {"date": m.group(1), "weekday": m.group(2), "text": text}


def main():
    if not SRC.is_dir():
        print(f"ERR: 找不到 CIO cron 輸出目錄 {SRC}")
        return 1
    files = sorted(SRC.glob("*.md"))
    if not files:
        print("ERR: CIO cron 輸出目錄無 md 檔")
        return 1

    merged = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
            for r in old.get("reviews", []):
                if r.get("date"):
                    merged[r["date"]] = r
        except Exception:
            pass

    newest_ts = ""
    for p in files:
        entry = parse_md(p)
        if entry:
            merged[entry["date"]] = entry
            # 用檔案修改時間當更新時間戳
            try:
                ts = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            except Exception:
                ts = entry["date"]
            if entry["date"] >= (newest_ts[:10] or ""):
                newest_ts = ts

    reviews = sorted(merged.values(), key=lambda r: r["date"], reverse=True)[:40]
    out = {"updated": newest_ts or datetime.now().strftime("%Y-%m-%d %H:%M"),
           "source": "CIO 每日戰略審查 cron 輸出（fb014d759ac5）",
           "reviews": reviews}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"cio_review.json 已更新：{len(reviews)} 筆（最新 {reviews[0]['date']}）") if __import__("os").environ.get("CIO_INGEST_VERBOSE") else None
    # 成功預設靜默（cron no_agent 空 stdout = 不推送）
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
