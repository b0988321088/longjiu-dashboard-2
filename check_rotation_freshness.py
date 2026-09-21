# -*- coding: utf-8 -*-
"""check_rotation_freshness.py — 產業輪動建議一致性守衛（2026-09-21 新增）

背景（INC-234）：雷達 16:15 刷新 radar_state.sector_flow 後，全系統沒有任何步驟重算
snapshot.rotation_recommendation → 建議名單停在舊資金流。9/21 實例：金融的資金分數
仍是 9/20 的 -3 → 金融被誤列「避開」（依當日真值應為「維持現況」）；同一份錯誤名單
被日報／再平衡儀表板／LLM（CTO 段）複述。

守衛項目：
  ① 建議所依據的雷達資金流時間 == radar_state 現行 sector_flow.generated_at（不得落後）
  ② 建議日期（TODAY）== 今天
  ③ 產業現況不得全為 0（防「呼叫端誤傳整份 snapshot」導致全部算成 0% 最大缺口）
  ④ 避開名單必須能對應到全產業列（結構完整）

用法：python check_rotation_freshness.py   （exit 0 = 通過；1 = 有問題）
"""
import json
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent.resolve()


def load(p, default=None):
    try:
        return json.loads((BASE / p).read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def main() -> int:
    snap = load("snapshot.json")
    radar = load("radar_state.json")
    rec = (snap.get("rotation_recommendation") or {})
    sf = (radar.get("sector_flow") or {})
    problems = []

    if not rec:
        problems.append("snapshot.rotation_recommendation 不存在（輪動引擎從未產出）")

    # ① 資料來源時間
    _rec_ts = str(((rec.get("資料來源") or {}).get("雷達資金流 generated_at")) or "")
    _sf_ts = str(sf.get("generated_at") or "")
    if not _rec_ts or not _sf_ts:
        problems.append(f"缺少時間戳（建議 {_rec_ts or '—'}／雷達 {_sf_ts or '—'}）")
    elif _rec_ts != _sf_ts:
        problems.append(
            "產業輪動建議落後於雷達資金流：建議依據 "
            f"{_rec_ts[:19]}，現行雷達 {_sf_ts[:19]} → 名單是舊資金流算的（跑 python rotation_engine.py 重算）"
        )

    # ② 日期
    if rec.get("日期") and rec["日期"] != date.today().isoformat():
        problems.append(f"建議日期 {rec['日期']} ≠ 今天 {date.today().isoformat()}")

    # ③ 現況不得全 0（誤傳整份 snapshot 的特徵）
    rows = rec.get("全產業") or []
    _pos = [r.get("產業") for r in rows if (r.get("現況") or 0) > 0]
    if rows and not _pos:
        problems.append("全產業『現況』皆為 0% —— 疑似呼叫端誤傳整份 snapshot（應傳 industry_penetration）")

    # ④ 避開名單結構
    _names = {r.get("產業") for r in rows}
    for r in rec.get("避開") or []:
        if r.get("產業") not in _names:
            problems.append(f"避開名單的 {r.get('產業')} 不在全產業列中（結構不一致）")

    if problems:
        print("❌ 產業輪動建議一致性檢查未通過：")
        for p in problems:
            print(f"   • {p}")
        return 1

    print(f"✅ 產業輪動建議一致（依據雷達 {_rec_ts[:19]}｜{rec.get('總結', '')}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
