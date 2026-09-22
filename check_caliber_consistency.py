#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_caliber_consistency.py — 週報口徑 vs 再平衡基準的一致性檢查（read-only）

## 為什麼要有這支（2026-09-22）
週日「動態自我檢討週報」原本會自行重新推導配置權重與防守口徑，導致同一週的數字
在不同報告之間漂移（實測：9/20 週報 防守合併 67.8% vs 再平衡基準 67.9%，且週報
沒有任何來源標註）。現在週報 prompt 已改為「一律引用 rebalance_eval_<date>.html」，
這支腳本負責機械驗證「它真的引用了、而且數字對得上」——把一致性從口頭約定變成
可驗證的檢查（比對邏輯不依賴 LLM）。

## 用法
    python check_caliber_consistency.py                  # 自動：最新週報 vs 其同日基準
    python check_caliber_consistency.py <weekly.html> <rebalance_eval.html>

## 與其他檢查的職責分工（避免重複造輪子）
- `check_dashboard_sync.py`：儀表板 index.html ↔ snapshot（佔位符殘留、月份寫死、連結可達／已版控）
- `check_caliber_consistency.py`（本檔）：**週報 vs 再平衡基準** 的數字口徑一致性
兩者互補，不合併。

## 離開碼
    0 = 數字一致、來源標註存在，或走在 fallback（無新鮮基準，屬預期行為）
    1 = 數字不一致，或該有來源標註卻沒有（供 delivery 步驟擋下 push）
"""
import html as H
import json
import re
import sys
import datetime as dt
from pathlib import Path

REPO = Path(__file__).resolve().parent
KEYS = ['台股', '美股', '防守', '債券', '現金']
TOL_PP = 0.05          # 同一日基準下應完全相同；留 0.05pp 只吸收四捨五入
MAX_AGE_DAYS = 3       # 與週報 prompt 的「日曆日差 ≤3 天」一致

WEEKLY_GLOB = 'dynamic_weekly_review_*.html'
BASE_GLOB = 'rebalance_eval_*.html'


def text_of(p: Path) -> str:
    s = p.read_text(encoding='utf-8', errors='ignore')
    s = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', s, flags=re.S | re.I)
    s = re.sub(r'<[^>]+>', ' ', s)
    return H.unescape(re.sub(r'\s+', ' ', s))


def grab(txt: str) -> dict:
    """抽出各桶佔比與防守合併口徑。

    ⚠️ 這些正則與「週報／rebalance_eval」的模板措辭耦合：報告模板改版時必須同步這裡，
    否則 main() 的 missing 檢查會讓閘門直接 rc=1（刻意設計成 fail-loud，不要改成略過）。
    """
    out = {}
    for k in KEYS:
        if k == '防守':
            # 排除「防守合併」：單桶口徑（防守 <n>%）
            m = re.search(r'防守(?!合併)[^0-9%]{0,40}?([0-9]+\.[0-9])%', txt)
        else:
            m = re.search(rf'{k}[^0-9%]{{0,40}}?([0-9]+\.[0-9])%', txt)
        if m:
            out[k] = float(m.group(1))
    m = re.search(r'防守合併[^0-9]{0,20}?([0-9]+\.[0-9])%', txt) or \
        re.search(r'合併口徑[^0-9]{0,20}?([0-9]+\.[0-9])%', txt)
    if m:
        out['防守合併'] = float(m.group(1))
    return out


def date_of(p: Path):
    m = re.search(r'(\d{4}-\d{2}-\d{2})', p.name)
    if not m:
        return None
    return dt.date.fromisoformat(m.group(1))


def newest(pat: str):
    fs = sorted(REPO.glob(pat), key=lambda f: f.name)
    return fs[-1] if fs else None


def pick_baseline(weekly_date):
    """同日的 rebalance_eval；沒有就取日期 ≤ 週報日的最新一份。"""
    cands = sorted((p for p in REPO.glob(BASE_GLOB)), key=lambda f: f.name)
    if not cands:
        return None
    same = [p for p in cands if date_of(p) == weekly_date]
    if same:
        return same[-1]
    earlier = [p for p in cands if date_of(p) and weekly_date and date_of(p) <= weekly_date]
    return earlier[-1] if earlier else cands[-1]


def snapshot_expected() -> dict:
    """從單一真值派生預期口徑：snapshot.json（穿透實際佔比）＋ sot_targets.defensive_caliber（防守合併）。

    2026-09-22 新增。用途：週六再平衡 agent 會**自己寫** rebalance_eval_{date}.html（LLM 產出的百分比），
    這是唯一能獨立驗證「它寫的數字是否等於真值」的方式（同檔自我比對沒有意義）。
    """
    sys.path.insert(0, str(REPO))
    from sot_targets import defensive_caliber  # INC-201 單一入口
    s = json.loads((REPO / 'snapshot.json').read_text(encoding='utf-8'))
    pen = (s.get('penetration') or {}).get('actual_pct') or {}
    dc = defensive_caliber(s)
    return {
        '台股': pen.get('台股市值型成長'),
        '美股': pen.get('美股市值型成長'),
        '防守': pen.get('防守型配息'),
        '債券': pen.get('債券'),
        '現金': pen.get('現金/安全網'),
        '防守合併': dc.get('佔比'),
    }


def check_vs_snapshot(path: Path) -> int:
    """比對指定報告的數字 vs snapshot 真值（獨立於其他報告）。"""
    if not path.exists():
        print(f"❌ 檔案不存在：{path}（路徑錯誤不得靜默通過）")
        return 2
    exp = snapshot_expected()
    got = grab(text_of(path))
    missing = [k for k in KEYS + ['防守合併'] if k not in got]
    if missing:
        print(f"❌ 抽取失敗：{'、'.join(missing)} 未能在 {path.name} 取得"
              "（可能是報告模板措辭改版）→ 無法判定，視為失敗")
        return 1
    print(f"報告: {path.name}")
    print("真值: snapshot.json（穿透實際佔比）＋ sot_targets.defensive_caliber（防守合併）")
    print(f"\n{'項目':<10}{'報告':>9}{'真值':>9}{'差異':>9}  判定")
    bad = 0
    for k in KEYS + ['防守合併']:
        a = got[k]
        b = exp.get(k)
        if not isinstance(b, (int, float)):
            print(f"{k:<10}{a:>9.2f}{'—':>9}{'—':>9}  ↷ 真值缺，略過")
            continue
        d = a - b
        ok = abs(d) <= TOL_PP
        bad += 0 if ok else 1
        print(f"{k:<10}{a:>9.2f}{b:>9.2f}{d:>9.2f}  {'✅ 一致' if ok else f'⚠️ 與真值差 {d:+.2f}pp'}")
    if bad:
        print(f"\n❌ 有 {bad} 項與 snapshot 真值不符 → 不要 push，把上述輸出貼進回覆。")
        return 1
    print("\n✅ 全部與 snapshot 真值一致")
    return 0


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == '--vs-snapshot':
        return check_vs_snapshot(Path(sys.argv[2]))
    if len(sys.argv) >= 3:
        weekly, base = Path(sys.argv[1]), Path(sys.argv[2])
    else:
        weekly = newest(WEEKLY_GLOB)
        if weekly is None:
            print("ℹ️ 找不到任何動態週報，無需比對"); return 0
        base = pick_baseline(date_of(weekly))
    if base is None:
        print("ℹ️ 找不到 rebalance_eval 基準檔；無法比對（fallback 路徑，不視為失敗）"); return 0
    for _label, _p in (('週報', weekly), ('基準', base)):
        if not _p.exists():
            print(f"❌ {_label}檔不存在：{_p}（路徑錯誤不得靜默通過）")
            return 2

    wd, bd = date_of(weekly), date_of(base)
    age = (wd - bd).days if (wd and bd) else None
    print(f"週報      : {weekly.name}")
    print(f"再平衡基準: {base.name}（落差 {age} 天）")

    if age is None or age > MAX_AGE_DAYS:
        print(f"ℹ️ 基準超過 {MAX_AGE_DAYS} 天（或無法判定日期）→ 週報走 fallback 自行推導屬預期行為，不比對數字")
        print("   提醒：週報應在模組 0 標示「⚠️ 本週無再平衡基準，已自行推導」")
        return 0
    if age < 0:
        print("ℹ️ 基準日期晚於週報（時序異常或人為指定）→ 不比對數字，僅提示")
        return 0

    tw, tb = text_of(weekly), text_of(base)
    aw, ab = grab(tw), grab(tb)
    # 2026-09-22 審查修正：抽取不到就大聲失敗，不要靜默略過 ——
    # 否則模板改版（措辭變了）會讓閘門悄悄失效卻回 rc=0，比沒有閘門更危險。
    missing = [k for k in KEYS + ['防守合併'] if k not in aw or k not in ab]
    if missing:
        print(f"❌ 抽取失敗：{'、'.join(missing)} 未能在兩份報告中同時取得"
              "（可能是報告模板措辭改版）→ 閘門無法判定，視為失敗。")
        print("   請檢查 grab() 的正則或報告模板，不要放行。")
        return 1
    print(f"\n{'項目':<10}{'週報':>9}{'基準':>9}{'差異':>9}  判定")
    bad = 0
    for k in KEYS + ['防守合併']:
        if k in aw and k in ab:
            d = round(aw[k] - ab[k], 2)
            ok = abs(d) < TOL_PP
            if not ok:
                bad += 1
            print(f"{k:<10}{aw[k]:>9.2f}{ab[k]:>9.2f}{d:>9.2f}  {'✅ 一致' if ok else '❌ 不一致'}")
        else:
            print(f"{k:<10}{'—':>9}{'—':>9}{'—':>9}  ↷ 未同時出現，略過")

    # 來源標註：容忍檔名被反引號/引號包住（agent 寫法可能有 `rebalance_eval_...`）
    has_src = bool(re.search(r'口徑來源[:：][^0-9A-Za-z]{0,6}rebalance_eval', tw))
    has_flag = '與再平衡口徑分歧' in tw
    print(f"\n來源標註: {'✅ 有' if has_src else '❌ 缺（有新鮮基準就必須標示）'}"
          f"｜分歧標記: {'有' if has_flag else '無'}")
    print(f"不一致項目 = {bad}")

    if bad or not has_src:
        print("\n❌ 口徑檢查未過 → 不要 push，把上述輸出貼進回覆。")
        return 1
    print("\n✅ 口徑一致。")
    return 0


if __name__ == '__main__':
    sys.exit(main())
