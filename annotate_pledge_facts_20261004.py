#!/usr/bin/env python3
"""annotate_pledge_facts_20261004.py — 質押事實四概念分離（使用者 2026-10-04 裁決）

只做「加法」：在既有唯一質押容器 snapshot.cathay_pledge_0911 補上四個概念的明確區分，
不改動任何既有鍵、不改任何腳本讀取路徑。

四概念（不得互相推導）：
  ① PI 資格        → snapshot.professional_investor.approval_status
  ② 質押品價值      → funds_cathay（即時）＋ 擔保池明細
  ③ 銀行核定授信額度 → 未取得文件 → null（禁由質押品價值反推）
  ④ 實際動用額      → 5,900,000（已存在：fund_pledge_loan／可貸金額／實際撥款金額）

用法：python annotate_pledge_facts_20261004.py [--dry-run]
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
KEY = "cathay_pledge_0911"

NEW = {
    "PI關聯": "依 PI 專業投資人資格辦理（professional_investor.approval_status=已核准）",
    "質押標的類別": "基金（國泰世華基金帳戶）",
    "質押標的類別備註": "2026-10-04 依 funds_cathay／blackrock_b11_0911 證據認定為基金質押；使用者口述為保單質押，待銀行文件覆核",
    "質押標的": [
        "富達全球動能多元B股C月配息美元",
        "聯博全球多元收益AD美元月配",
        "貝萊德智慧數據收益成長B11-美元-強化穩定月配息",
    ],
    "四概念分離_20261004": {
        "①PI資格": "professional_investor.approval_status（唯一容器）",
        "②質押品價值": "即時計算：funds_cathay／fund_breakdown_cathay（不落地為單一常數）",
        "③銀行核定授信額度": None,
        "④實際動用額": "fund_pledge_loan（＝DB liabilities.pledge_loan）",
        "紅線": "四者不得互相推導：不可由借款反推 PI 門檻、不可將質押品價值當成銀行授信額度、不可由 額度本金−動用額 計算『剩餘可借』",
    },
    "銀行核定授信額度": None,
    "銀行核定授信額度狀態": "未取得銀行核定文件 → 不得計算剩餘可借（使用者 2026-10-04 裁決；原『1,200 萬 − 590 萬 = 610 萬』推論已撤回）",
    "額度_本金語意": "質押品本金口徑（成本），非銀行核定授信額度（鍵名為歷史遺留，2026-10-04 更正語意）",
    "pi_basis": True,
    "updated_at_質押事實": None,  # 執行時填入
}


def main() -> int:
    dry = "--dry-run" in sys.argv
    raw = SNAP.read_text(encoding="utf-8")
    data = json.loads(raw)
    if json.dumps(data, ensure_ascii=False, indent=1) != raw:
        print("❌ snapshot.json 無法以 indent=1 無損 round-trip → 中止")
        return 3

    cp = data.get(KEY)
    if not isinstance(cp, dict):
        print(f"❌ 找不到 {KEY}")
        return 2

    rec = dict(cp)
    added, changed = [], []
    for k, v in NEW.items():
        if v is None and k != "銀行核定授信額度":
            continue
        if k in rec:
            if rec[k] != v:
                changed.append(k)
        else:
            added.append(k)
        rec[k] = v
    rec["updated_at_質押事實"] = datetime.now().astimezone().isoformat(timespec="seconds")
    data[KEY] = rec

    print(f"=== 質押事實四概念分離{'（DRY-RUN）' if dry else ''} ===")
    print(f"  新增鍵：{added}")
    print(f"  已存在（覆寫）：{changed}")
    print(f"  質押品本金（額度_本金）：{rec.get('額度_本金'):,} ← 成本口徑，非授信額度")
    print(f"  質押品市值（即時）：{data.get('funds_cathay_market_value'):,}")
    print(f"  實際動用額：{data.get('fund_pledge_loan'):,}｜利率 {data.get('fund_pledge_rate')}")
    print(f"  銀行核定授信額度：{rec.get('銀行核定授信額度')}（未取得文件）")
    print(f"  PI 資格：{data.get('professional_investor', {}).get('approval_status')}")

    if dry:
        print("  [dry-run] 未寫入")
        return 0

    bak = SNAP.with_name(SNAP.name + ".bak-pledge-" + datetime.now().strftime("%Y%m%d%H%M%S"))
    shutil.copy2(SNAP, bak)
    SNAP.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    chk = json.loads(SNAP.read_text(encoding="utf-8"))
    assert chk[KEY]["銀行核定授信額度"] is None
    diff = [k for k in set(chk) | set(json.loads(raw)) if chk.get(k) != json.loads(raw).get(k)]
    if diff != [KEY]:
        shutil.copy2(bak, SNAP)
        print(f"❌ 非目標鍵被改動 {diff} → 已還原（{bak.name}）")
        return 4
    print(f"  ✅ 已寫入（三重驗證通過）；備份 {bak.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
