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
            # 安全網模式：CIO agent 已寫 structured 的 date 不覆蓋（只補缺 date）
            _ex = merged.get(entry["date"])
            if _ex is None:
                merged[entry["date"]] = entry
            elif not _ex.get("structured") and not _ex.get("text"):
                _ex["text"] = entry["text"]
            # 更新時間戳
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

    # 2026-09-09：自動 push（僅內容有變更時），確保 18:45 收錄後線上儀表板立即讀到新審查，
    # 不等到 22:00 夜間批次（否則 18:45→22:00 之間線上顯示舊審查）。
    # 成功靜默；失敗才印 ERR（cron 空 stdout = 不推送）。
    try:
        import subprocess
        _chk = subprocess.run(["git", "diff", "--quiet", "--", "cio_review.json"],
                              capture_output=True, cwd=str(BASE), timeout=60)
        if _chk.returncode != 0:
            _cmds = [
                ["git", "add", "cio_review.json"],
                ["git", "commit", "-m", "data: cio_review.json 收錄更新（CIO 審查） [cioreviewed]"],
                ["git", "push", "origin", "clean-main"],
                ["git", "push", "origin", "clean-main:main"],
            ]
            for _c in _cmds:
                _r = subprocess.run(_c, capture_output=True, cwd=str(BASE), timeout=120)
                if _r.returncode != 0:
                    print(f"ERR: ingest push 失敗 {' '.join(_c[:2])}: {(_r.stderr or _r.stdout).decode('utf-8','ignore')[-300:]}")
                    return 1
    except Exception as _e:
        print(f"ERR: ingest push 例外: {_e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
