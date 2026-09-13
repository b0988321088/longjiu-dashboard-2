# -*- coding: utf-8 -*-
"""institutional_flow.py 剩餘硬編碼：⑨ 質押敘述、⑦ 美元曝險門檻"""
import ast
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
P = BASE / "institutional_flow.py"
src = P.read_text(encoding="utf-8")

s = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
usd = s.get("usd_exposure_monitor", {}) or {}
print("usd_exposure_monitor keys:", list(usd.keys()), "| current:", json.dumps(usd.get("current"), ensure_ascii=False)[:120],
      "| target:", json.dumps(usd.get("target"), ensure_ascii=False)[:160])

EDITS = [
    # ⑨ 質押（原本貼死 9/11 版：申購中/待過戶/還安聯300）
    ('        lines.append("🔍 質押：9/11 未質押 — 先以 MMF 500萬贖回款申購貝萊德B11 500萬（申購中）；整池(富達600+聯博100+B11 500)1,200萬×4.5成 = 540萬@2.77% 質押，待 B11 過戶後送件、撥款約2週（≈9/25）到位後才啟動後續部署；到位前全面觀望")',
     '        lines.append("🔍 " + _ps.pledge_status_line(_snap) + "；到位前全面觀望")'),
    # ⑦ 美元曝險（門檻寫死 55%，9/12 裁示目標已放寬至 60% → 改讀 snapshot）
    ('        if _usd > 55:\n            lines.append(f"🔴 美元曝險 {_usd}% 超標（>55%）→ 美股減碼/美元定存到期轉台幣")\n        else:\n            lines.append(f"🟡 美元曝險 {_usd}% （目標≤60%）→ 未達減碼閾值，續觀察")',
     '        _usd_t = (usd or {}).get("target", 60)\n        if isinstance(_usd_t, dict):\n            _usd_t = _usd_t.get("合計", _usd_t.get("total", 60))\n        if _usd > float(_usd_t):\n            lines.append(f"🔴 美元曝險 {_usd}% 超標（目標 ≤{_usd_t}%）→ 美股減碼/美元定存到期轉台幣")\n        else:\n            lines.append(f"🟡 美元曝險 {_usd}%（目標 ≤{_usd_t}%）→ 未達減碼閾值，續觀察")'),
]

for old, new in EDITS:
    n = src.count(old)
    assert n == 1, f"出現 {n} 次（需 1）：{old[:50]}"
    src = src.replace(old, new)

ast.parse(src)
P.write_text(src, encoding="utf-8")
print("syntax OK；殘留掃描：", re.findall(r"待 B11 過戶後送件|9/11 未質押|>55%", src))
