#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""taipower_tender_watch 分類器回歸測試（改關鍵字後必跑）
執行：python test_taipower_tender_watch.py   （全過 RC=0）
2026-11-02 定調：只做督導類（全台電）＋中部勞務類；不做環境調查/環評/監測/檢測
"""
import importlib.util
import sys
from pathlib import Path

P = Path(__file__).resolve().parent / "taipower_tender_watch.py"
spec = importlib.util.spec_from_file_location("w", P)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

T = "台灣電力股份有限公司"
CASES = [
    # 督導類（全台電）
    ("116年度工地安衛督導查證工作", "🎯 督導"),
    ("116年度工地安衛巡查工作(通霄工區)", "🎯 督導"),
    ("115年度工地環保督導查證工作(通霄工區)", "🎯 督導"),
    ("115年度工地安衛督導查證工作", "🎯 督導"),
    # 勞務類（地區在 main 過濾）
    ("116年度通霄業務勞務性工作", "👷 勞務"),
    ("116年度業務類勞務性工作", "👷 勞務"),
    ("115年度勤務類勞務性工作", "👷 勞務"),
    ("116年度材料裝卸、搬運、捆紮、整理等勞務性工作", "👷 勞務"),
    # 不做：環境調查／監測／檢測／清潔／保全／財物
    ("通霄發電廠環境調查評析", None),
    ("116年度作業環境監測工作", None),
    ("116-117年大林電廠煙氣排放監測儀器之相對準確度測試查核", None),
    ("115年度工地環保督導查證工作(通霄工區)".replace("督導查證", "監測"), None),
    ("7號機NOx取樣控制器等五項(含施工安裝)", None),
    ("115年度辦公場所清潔維護類勞務性工作", None),
    ("116年度警衛勤務(保全)勞務性工作", None),
    ("116年遠途員工住宿工房(通霄)", None),
    ("115~116年度橋梁安全檢測評估工作", None),
]


def main() -> int:
    bad = 0
    for name, exp in CASES:
        got = w.classify(T + "台中發電廠", name)
        if got != exp:
            bad += 1
            print(f"❌ {name} → {got}（預期 {exp}）")
    if bad:
        print(f"{bad}/{len(CASES)} 失敗")
        return 1
    print(f"✅ 分類器 {len(CASES)}/{len(CASES)} 全過")
    # 地區判讀
    assert w.region_of(T + "台中發電廠", "") == "中部"
    assert w.region_of(T + "高雄區營業處", "") == "其他"
    assert w.region_of(T, "某案") == "未註明"
    print("✅ 地區判讀 3/3 全過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
