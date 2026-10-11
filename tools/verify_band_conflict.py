# -*- coding: utf-8 -*-
"""verify_band_conflict.py — 債券目標/範圍衝突揭露與 fail-closed 回歸測試（工單D，唯讀）

使用者裁決（2026-10-11）：不自選值修訂。目標 25%（thresholds.桶目標_pct）與範圍 27–33%
（2026-10-02 裁示② snapshot.可接受範圍_pct）並存 → **只揭露、不改值**，且不得把 25% 稱「上限」。
衝突存在期間，該桶自動交易 fail-closed（動作降待裁示、金額 0）。

測項：
  1 可接受範圍改讀 SoT（不得再是 目標±5pp）
  2 衝突偵測欄位齊備（目標／下限／上限／來源／處置／禁止）
  3 fail-closed：債券 是否交易=False、精算金額=0、動作含「待裁示」
  4 未衝突桶回歸（美股／台股 動作與金額不受影響）
  5 不得敘述為「上限」；不得出現「戰略上限」字樣
  6 邊界：目標 27/33（貼界）不算衝突；26/34 算衝突
  7 缺值：無 可接受範圍_pct → 不自行推導 ±5pp
  8 fail-closed 在 US30Y 凍結情境亦成立
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sot_targets as st          # noqa: E402
import tactical_table as tt       # noqa: E402

SNAP = json.loads((ROOT / "snapshot.json").read_text(encoding="utf-8"))
P, F = [], []


def rec(tag, desc, ok, detail=""):
    (P if ok else F).append(tag)
    print(f"  {'✅' if ok else '❌'} {tag} {desc}" + (f" — {detail}" if detail else ""))


def rows_of(t):
    return t["rows"] if isinstance(t, dict) and "rows" in t else t


TBL = tt.build_table(SNAP, None)
ROWS = {r["資產分類"]: r for r in rows_of(TBL)}

print("== 1. 可接受範圍改讀 SoT ==")
_bond = ROWS["債券"]
rec("A-1", "債券 目標區間＝SoT 27~33%（非 22~28／20~30）", _bond["目標區間"] == "27~33%", _bond["目標區間"])
rec("A-2", "美股 目標區間＝SoT 27~33%（非 目標±5pp 的 25~35%）", ROWS["美股市值型成長"]["目標區間"] == "27~33%",
    ROWS["美股市值型成長"]["目標區間"])
rec("A-3", "台股 目標區間＝SoT 7~13%（非 5~15%）", ROWS["台股市值型成長"]["目標區間"] == "7~13%",
    ROWS["台股市值型成長"]["目標區間"])
rec("A-4", "現金不設百分比範圍（不推導帶狀）", "不設百分比" in ROWS["現金/安全網"]["目標區間"],
    ROWS["現金/安全網"]["目標區間"])
_src = (ROOT / "tactical_table.py").read_text(encoding="utf-8")
rec("A-5", "靜態：tactical_table.py 已無 ±5pp 推導（tgt-5／tgt+5）", "tgt-5" not in _src and "tgt+5" not in _src)

print("\n== 2. 衝突偵測（只揭露、不改值）==")
_cf = st.band_conflicts(SNAP)
rec("B-1", "偵測到且僅偵測到 債券 1 筆", len(_cf) == 1 and _cf[0]["桶"] == "債券",
    str([c["桶"] for c in _cf]))
_c = _cf[0] if _cf else {}
rec("B-2", "欄位齊備（目標/下限/上限/衝突/來源/處置/禁止）",
    all(k in _c for k in ("目標", "下限", "上限", "衝突", "來源", "處置", "禁止")))
rec("B-3", "衝突敘述正確（目標 25% < 下限 27%）", _c.get("衝突") == "目標 25% < 下限 27%", str(_c.get("衝突")))
rec("B-4", "來源雙軌可追溯（裁示② vs 桶目標_pct）",
    "2026-10-02" in _c.get("來源", "") and "桶目標_pct" in _c.get("來源", ""))
rec("B-5", "處置＝待裁決（不得自行改值）", "待" in _c.get("處置", "") and "fail-closed" in _c.get("處置", ""))
rec("B-6", "SoT 值未被修改（目標仍 25、範圍仍 27–33）",
    _c.get("目標") == 25 and _c.get("下限") == 27 and _c.get("上限") == 33)
rec("B-7", "thresholds SoT 值未動（snapshot.thresholds_2026_0915.桶目標_pct.債券＝25）",
    ((SNAP.get("thresholds_2026_0915") or {}).get("桶目標_pct") or {}).get("債券") == 25)

print("\n== 3. fail-closed（債券自動交易）==")
rec("C-1", "建議動作＝⛔ 設定衝突・待裁示", "待裁示" in str(_bond.get("建議動作")), str(_bond.get("建議動作")))
rec("C-2", "是否交易=False", _bond.get("是否交易") is False)
rec("C-3", "精算金額=0", float(_bond.get("精算金額") or 0) == 0)
rec("C-4", "停止條件/註記含 fail-closed 敘述",
    "fail-closed" in json.dumps(_bond, ensure_ascii=False))

print("\n== 4. 未衝突桶回歸 ==")
rec("D-1", "美股 動作＝減碼、金額 200000（不受 D 影響）",
    ROWS["美股市值型成長"]["建議動作"] == "減碼" and float(ROWS["美股市值型成長"]["精算金額"]) == 200000,
    f"{ROWS['美股市值型成長']['建議動作']}／{ROWS['美股市值型成長']['精算金額']}")
rec("D-2", "台股 動作＝增持、金額 20000（不受 D 影響）",
    ROWS["台股市值型成長"]["建議動作"] == "增持" and float(ROWS["台股市值型成長"]["精算金額"]) == 20000,
    f"{ROWS['台股市值型成長']['建議動作']}／{ROWS['台股市值型成長']['精算金額']}")
rec("D-3", "無衝突桶之 設定衝突 欄為空",
    all(not ROWS[k].get("設定衝突") for k in ("美股市值型成長", "台股市值型成長")))

print("\n== 5. 不得敘述為「上限」==")
_blob = json.dumps(ROWS, ensure_ascii=False)
rec("E-1", "輸出不得出現「戰略上限」字樣", "戰略上限" not in _blob)
rec("E-2", "輸出不得出現「戰略上限」字樣（靜態 .py）", "戰略上限" not in _src.replace("不得把目標值敘述為「上限」", ""))
rec("E-3", "衝突列明確標示『目標為中樞值，非上限』", "非上限" in str(_bond.get("目標註記")))

print("\n== 6. 邊界（貼界不算衝突、越界才算）==")
for tgt, want in ((27, False), (33, False), (26, True), (34, True)):
    _s = json.loads(json.dumps(SNAP))
    _s["可接受範圍_pct"]["債券"]["目標"] = tgt
    _got = bool([c for c in st.band_conflicts(_s) if c["桶"] == "債券"])
    rec(f"F-{tgt}", f"目標 {tgt}% → {'衝突' if want else '不衝突'}", _got == want, f"got={_got}")

print("\n== 7. 缺值：不自行推導 ==")
_s = json.loads(json.dumps(SNAP))
_s.pop("可接受範圍_pct", None)
_t = rows_of(tt.build_table(_s, None))
_rb = [r for r in _t if r["資產分類"] == "債券"]
rec("G-1", "缺 可接受範圍_pct → 區間＝「無真值（不推導）」（不吐 ±5pp 假範圍）",
    bool(_rb) and _rb[0]["目標區間"] == "無真值（不推導）", _rb[0]["目標區間"] if _rb else "no row")
rec("G-2", "缺真值時不得誤判為無衝突而放行交易（動作不得為 減碼／加碼）",
    bool(_rb) and "減碼" not in str(_rb[0].get("建議動作")) and "加碼" not in str(_rb[0].get("建議動作")),
    str(_rb[0].get("建議動作")) if _rb else "no row")
rec("G-3", "缺真值時 band_conflicts 回傳空（不 raise、不猜）", st.band_conflicts(_s) == [])

print("\n== 8. US30Y 凍結情境下 fail-closed 仍成立 ==")
_r8 = {r["資產分類"]: r for r in rows_of(tt.build_table(SNAP, 5.60))}   # >5.30 → 凍結
rec("H-1", "凍結時 債券 仍為待裁示（不被凍結字樣覆蓋）", "待裁示" in str(_r8["債券"].get("建議動作")),
    str(_r8["債券"].get("建議動作")))
rec("H-2", "凍結時 債券 金額仍 0、是否交易 False",
    float(_r8["債券"].get("精算金額") or 0) == 0 and _r8["債券"].get("是否交易") is False)

print("\n== 9. 報告層揭露（Markdown／文字過濾器）==")
_md = tt.to_markdown(TBL)
rec("I-1", "Markdown 表頭含『可接受範圍』欄", "可接受範圍" in _md)
rec("I-2", "債券列同時出現 目標 25%、範圍 27~33%、設定衝突標示",
    ("25%" in _md) and ("27~33%" in _md) and ("設定衝突" in _md))
rec("I-3", "衝突揭露為逐列（非整表外掛一句）", _md.count("⚠️ 設定衝突") >= 1 and "非上限" in _md)
import report_components as rc      # noqa: E402
_txt = rc.band_filter("債券 26.9%（可接受範圍 27~33%，低於下限 1.1pp）")
rec("I-4", "band_filter 於衝突桶後補標示（揭露、不改值）",
    "設定衝突" in _txt and "fail-closed" in _txt, _txt[:80])
rec("I-5", "揭露文字不得稱 25% 為上限", "上限" not in _txt.replace("非上限", ""), _txt[:120])
_ok_txt = rc.band_filter("台股（7.8%，缺口 2.2pp）")
rec("I-6", "範圍內桶維持靜默（裁示②：範圍內不得出現行動字樣）",
    "設定衝突" not in _ok_txt and "缺口" not in _ok_txt, _ok_txt[:60])

print(f"\n=== 結果：{'PASS' if not F else 'FAIL'}（PASS {len(P)}／FAIL {len(F)}） ===")
if F:
    print("FAIL:", ", ".join(F))
sys.exit(0 if not F else 1)
