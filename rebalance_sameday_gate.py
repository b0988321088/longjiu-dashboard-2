"""rebalance_sameday_gate.py — 週六再平衡同日去重 gate（P3.1 2026-09-06；判準修正 2026-09-22）

作為 cron prerun script（wake-gate）：今天若已有「真的跑過 agent」的輸出
→ 末行輸出 {"wakeAgent": false} → agent 完全跳過（零 LLM 零推播），
防止同日重複執行（9/5 曾 16:03 + 20:58 雙跑 = 重複燒 ~1.8 CNY）。
今天還沒真的跑過 → 空輸出 → 正常喚醒。

## 2026-09-22 判準修正（實測事故）
舊判準 = 「rebalance_summary_{today}.md 是否存在」。但該檔自 2026-09 起**每天 07:00 由管線產出**
（build_rebalance_dashboard.py / build_rebalance_eval_html.py / regenerate_report.py 都會寫），
於是判準恆為真 → agent 自 gate 上線（9/6）起**從未喚醒**：
9/12、9/19 兩次週六的輸出都只有 174 bytes 的「Script gate returned wakeAgent=false」，
使用者連續兩週沒收到週六再平衡簡報。

新判準 = 看本 job **自己的 cron 輸出**（HERMES_HOME/cron/output/<job_id>/）：
只有存在「今天、且不是 gate-skip / silent」的輸出，才算今天真的跑過。
讀不到輸出目錄 → fail-open（喚醒）並在 stderr 示警：靜音的自動化比多跑一次更貴。

強制重跑：刪掉今天本 job 的輸出檔後手動 run。
純 stdlib；輸出禁止時間戳。

2026-09-22 審查修正：加 `from __future__ import annotations` —— 原本的 `Path | None` 需 Python 3.10+，
若哪天 cron 改用較舊的直譯器會 SyntaxError，而這條正是靜音路徑（崩潰＝靜默失敗）。
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

JOB_ID = "f5e412363a17"  # 龍九每週六再平衡評估 16:00
_SILENT_MARKERS = ("wakeAgent=false", "**Status:** silent", "**Status:** no_change")


def default_output_dir() -> Path:
    home = os.environ.get("HERMES_HOME") or os.environ.get("LOCALAPPDATA") or str(Path.home())
    base = Path(home)
    if (base / "hermes").is_dir():
        base = base / "hermes"
    return base / "cron" / "output" / JOB_ID


def _is_silent(text: str) -> bool:
    """判斷這筆輸出是否為「gate/silent 跳過」而非真的跑過。

    只掃**檔頭區塊**（hermes 把 Status 寫在 `---` 之前；對齊上游 scheduler_prompt.py 的做法），
    避免正文剛好出現這些字樣時被誤判成沒跑過（那會導致同日重跑）。
    """
    header = text.split("\n---\n", 1)[0].split("\n## Prompt", 1)[0]
    return any(m in header for m in _SILENT_MARKERS)


def already_ran_today(today: str, out_dir: Path) -> bool:
    """今天是否已有一筆「真的跑過 agent」的輸出。讀不到 → False（fail-open）。"""
    try:
        files = sorted(out_dir.glob(f"{today}_*.md"))
    except OSError as e:
        sys.stderr.write(f"WARN: gate cannot read output dir {out_dir}: {e}\n")
        return False
    for f in files:
        try:
            head = f.read_text(encoding="utf-8", errors="replace")[:800]
        except OSError:
            continue
        if _is_silent(head):
            continue  # 這筆是 gate/silent 造成的跳過，不算真的跑過
        return True
    return False


def gate(today: str, out_dir: Path | None = None) -> str:
    """回傳 gate 輸出：今天真的跑過 → wakeAgent false；否則空字串。純函數供測試。"""
    if already_ran_today(today, out_dir or default_output_dir()):
        return '{"wakeAgent": false}'
    return ""


def main() -> None:
    out = gate(date.today().isoformat())
    if out:
        print(out)


if __name__ == "__main__":
    main()
