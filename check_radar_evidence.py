#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_radar_evidence.py — 雷達證據機（週報「法人驗證」扣分項的唯一事實來源）

背景（2026-11-08 週報誤報）：
  週報 11/08 場次在「輪動可信度」寫下「無連續 3 日法人驗證 −1 → 已扣（TWSE T86 抓取失敗、
  sector_flow 空）」。實際查核：radar_state.json 的 外資連日 有 3 筆（最新交易日 2026-11-06）、
  sector_flow.generated_at = 2026-11-07T16:12 且台股 19 桶／美股 11 桶皆非空，
  以 fetch_twse() 現場探測也回 OK → **沒有失敗、也沒有空值**，是憑印象下的判斷。

  修法：把「有沒有法人資料」變成機器判定，不再由 LLM 目測。週報／日報引用本檔輸出，
  沒有本檔的 ✅ 就不准寫「T86 抓取失敗／法人資料缺值」。

輸出（純唯讀，不改任何檔案；rc 一律 0，判定寫在內容裡）：
  ① T86 覆蓋：最新交易日、外資連日筆數、是否達「連續 3 日法人驗證」
  ② sector_flow：generated_at、落後天數、台股／美股桶數
  ③ --live：現場呼叫 fetch_twse() 探測（唯讀，不寫 radar_state）

用法：
  python check_radar_evidence.py            # 只看已落地資料
  python check_radar_evidence.py --live     # 加做 T86 現場探測
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
RADAR = BASE / "radar_state.json"
NEED_DAYS = 3          # 週報扣分規則：連續 3 日法人數據驗證
TOL_DAYS = 4           # sector_flow 容忍落後天數（週一/三/六 16:15 排程＋連假）


def _load(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _age_days(ts: str):
    try:
        return (datetime.now().date() - datetime.fromisoformat(str(ts)[:19]).date()).days
    except Exception:
        return None


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    radar = _load(RADAR)
    if not radar:
        print("📡 雷達證據：❌ 讀不到 radar_state.json（不是『抓取失敗』，是檔案不存在）")
        print("結論：法人資料無法判定 → 週報不得寫『已扣分』，須標『資料受限』")
        return 0

    # ① T86（三大法人）
    twse = radar.get("twse") or {}
    days = twse.get("外資連日") or []
    tw_date = twse.get("外資連日_日期")
    vals = [round(v / 1e8, 1) for v in days if isinstance(v, (int, float))]
    t86_ok = len(vals) >= NEED_DAYS and bool(tw_date)
    t86_line = (f"T86：最新交易日 {tw_date or '—'}｜外資連日 {len(vals)} 筆"
                f"（{'／'.join(f'{v:+.1f}億' for v in vals) or '—'}）"
                f"｜連續驗證 {len(vals)}/{NEED_DAYS} 日 → {'✅ 成立' if t86_ok else '❌ 未達'}")

    # ② sector_flow（產業資金流）
    sf = radar.get("sector_flow") or {}
    gen = sf.get("generated_at")
    age = _age_days(gen) if gen else None
    tw_buckets = len(sf.get("台股") or {})
    us_buckets = len(sf.get("美股") or {})
    sf_ok = bool(gen) and tw_buckets > 0 and (age is not None and age <= TOL_DAYS)
    sf_line = (f"sector_flow：{str(gen)[:16] if gen else '—'}"
               f"（落後 {age if age is not None else '—'} 天）"
               f"｜台股 {tw_buckets} 桶／美股 {us_buckets} 桶 → {'✅ 非空' if tw_buckets or us_buckets else '❌ 空值'}")

    # ③ 現場探測（唯讀）
    live_lines = []
    if "--live" in sys.argv:
        try:
            import institutional_flow as _if
            r = _if.fetch_twse()
            if r.get("error"):
                live_lines.append(f"live T86 探測：⚠️ {str(r['error'])[:120]}")
            else:
                _f = r.get("外資總買賣超")
                live_lines.append(
                    f"live T86 探測：✅ {r.get('date')}｜外資 "
                    f"{(_f / 1e8):+.1f}億" if isinstance(_f, (int, float)) else
                    f"live T86 探測：✅ {r.get('date')}")
        except Exception as e:
            live_lines.append(f"live T86 探測：⚠️ {type(e).__name__}: {str(e)[:100]}")

    print(f"📡 雷達證據（機器判定｜{date.today().isoformat()}｜last_run {str(radar.get('last_run'))[:16]}）")
    print("  " + t86_line)
    print("  " + sf_line)
    for ln in live_lines:
        print("  " + ln)

    if t86_ok and sf_ok:
        print("結論：法人資料可用 → 週報不得出現「T86 抓取失敗／法人資料缺值」；"
              f"『連續 3 日法人驗證』{'已成立（不得扣分）' if t86_ok else '未成立（可扣 −1）'}")
    else:
        print("結論：法人資料不足 → 週報須標『資料受限』並註明缺哪一項，仍不得寫成『抓取失敗』")
    return 0


if __name__ == "__main__":
    sys.exit(main())
