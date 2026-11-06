"""tools/stamp_content_date.py — 為 emergency_llm_analysis.json 標註內容日期

**為什麼需要**：`generated_at` 只證明「檔案何時產生」，不證明「內容所述哪一天」。
2026-11-06 13:00 的檔案 generated_at=11-06，但內文同時含 11/05 美股收盤敘述，
L3 因此假陽性 PASS（裁決③要修正的就是這件事）。

**用法**（日期一律由人／上游資料明確給定，本工具不推導）：
    python tools/stamp_content_date.py --file data/emergency_llm_analysis.json \
        --content-date 2026-11-06 \
        --section "台股:2026-11-06" --section "美股:2026-11-05"

寫入：
    content_date  = 明確給定的內容日期
    sections[]    = {heading, date, text}（text 自動加註〔歷史：DATE〕給非當日段落）

**拒絕**：未提供 --content-date、或提供與 generated_at 相同的「推定值」時不出手。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from date_integrity import parse_date, stamp_history  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--content-date", required=True)
    ap.add_argument("--section", action="append", default=[],
                    help="章節:日期，例如 美股:2026-11-05（可重複）")
    ap.add_argument("--report-date", default=None, help="報告基準日，預設今天")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    p = Path(a.file)
    if not p.is_absolute():
        p = BASE / p
    if not p.exists():
        print(f"❌ 檔案不存在：{p}")
        return 2

    cd = parse_date(a.content_date)
    if not cd:
        print("❌ --content-date 無法解析（必須 YYYY-MM-DD）")
        return 2

    rec = json.loads(p.read_text(encoding="utf-8"))
    report_date = parse_date(a.report_date) or date.today()

    # 拒絕「用 generated_at 冒充」：若 caller 直接複製 generated_at 的日期，明確警告
    gen = parse_date(rec.get("generated_at"))
    if gen and cd == gen and not a.section:
        print(f"⚠️ content_date 與 generated_at 同日（{cd}）；若內文含前一日資料，"
              f"請改用 --section 逐段標註，勿以產生時間代表內容日期。")

    sections = []
    for spec in a.section:
        head, _, d = spec.partition(":")
        sd = parse_date(d)
        if not head or not sd:
            print(f"❌ 章節格式錯誤：{spec}（應為 名稱:YYYY-MM-DD）")
            return 2
        sections.append({"heading": head, "date": sd.isoformat(), "text": ""})

    if sections:
        sections = stamp_history(sections, report_date)

    rec["content_date"] = cd.isoformat()
    if sections:
        rec["sections"] = sections

    if a.dry_run:
        print(json.dumps({k: rec[k] for k in ("content_date", "sections") if k in rec},
                         ensure_ascii=False, indent=1))
        return 0

    p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 已寫入 content_date={cd}｜sections={len(sections)}｜{p.name}")
    print("   （L3 將以 content_date 判定，不再使用 generated_at）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
