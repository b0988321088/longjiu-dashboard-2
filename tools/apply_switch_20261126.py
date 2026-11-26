# -*- coding: utf-8 -*-
"""2026-11-26 保單轉換入帳：安聯A 收益成長50% → 摩根；安聯B 黃金/M&G/收益成長 三檔清空 → 摩根；
第一金 全額 → 摩根多重收益。只改「成分」，不動保單總值（轉換不改變保單總額）。"""
import json, shutil, os, datetime
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
SNAP = BASE / "snapshot.json"
BAK = Path(os.environ["LOCALAPPDATA"]) / "Temp" / "snapshot.bak_20261126_switch.json"
shutil.copy2(SNAP, BAK)

s = json.loads(SNAP.read_text(encoding="utf-8"))
b = s["insurance_breakdown"]
A = b["policy_a_funds"]
B = b["policy_b_funds"]

# --- 安聯A：安聯收益成長轉出 50% ---
kA = [k for k in A if k.startswith("USDEQ3490")][0]
kJ = [k for k in A if k.startswith("USDEQ5440")][0]
growth_A = A[kA]
out_A = int(round(growth_A * 0.5))
A[kA] = growth_A - out_A
A[kJ] = A[kJ] + out_A

# --- 安聯B：黃金 + M&G + 安聯收益成長 三檔清空 → 摩根 ---
src_keys = {}
for pre in ("USDEQ3490", "USDEQ5700", "USDEQ6730"):
    hit = [k for k in B if k.startswith(pre)]
    if hit:
        src_keys[pre] = hit[0]
b_out = sum(B[k] for k in src_keys.values())
for k in src_keys.values():
    B.pop(k)
name_b_jpm = "USDEQ5440 摩根投資基金-多重收益基金-JPM多重收益(美元對沖)-A股(穩定月配)"
B[name_b_jpm] = B.get(name_b_jpm, 0) + b_out

# --- 驗證總值未變 ---
assert sum(A.values()) == int(b["policy_a_total"]), (sum(A.values()), b["policy_a_total"])
assert sum(B.values()) == int(b["policy_b_total"]), (sum(B.values()), b["policy_b_total"])

# --- 第一金：全額轉回摩根 ---
s["firstjin_fund_name"] = ("FJXX-摩根投資基金-多重收益-JPM多重收益(美元對沖)-A股(每月派息) 100%"
                           "（2026/11/26 10:35 轉換；轉出單位數 0 待確認成交）")
fd = s["firstjin_detail"]
fd["current_fund"] = {
    "code": "FJXX",
    "name": "摩根投資基金-多重收益-JPM多重收益(美元對沖)-A股(每月派息)",
    "since": "2026-11-26",
    "note": "2026-11-26 10:35 App 轉換明細：IDXX M&G入息A(美元避險月配) 100% → FJXX 摩根多重收益(每月派息) 100%",
    "穿透比率": {"股票": 0.533, "債券": 0.467, "現金": 0,
              "note": "摩根多重收益（晨星：債 46.69／權益 46.07／現金 5.58；系統簡化 債+權益=100）"},
    "前五大持股": "見 snapshot.fund_components 摩根多重收益",
    "配息來源": "月配級別：配息來源可能為本金⚠️",
}
fd["conversion"] = ("✅ 2026-11-26 轉換：M&G入息A(美元避險月配)F 100% → 摩根多重收益(美元對沖)A股(每月派息) 100%"
                    "（10:35 線上送出；單位數顯示 0，待交易記錄確認）")
fd.setdefault("conversion_history", []).append({
    "date": "2026-11-26",
    "from": "IDXX M&G入息基金A(美元避險月配)F 100%",
    "to": "FJXX 摩根投資基金-多重收益-JPM多重收益(美元對沖)-A股(每月派息) 100%",
    "pct": "100%",
    "note": "10:35 App 轉換明細；轉出單位數 0 待確認",
})

ps = s.setdefault("policy_switch", {})
ps["asof"] = "2026-11-26"
ps["last_effective"] = "2026-11-26"
ps["last_detail"] = (
    "2026-11-26 三張同步轉入摩根多重收益：安聯A 由安聯收益成長轉出 50%（1,278,189）＋安聯B 由黃金129,034／"
    "M&G 617,734／安聯收益成長 470,713 三檔清空共 1,217,481＋第一金全額 1,840,657；"
    "轉換後摩根合計 5,018,703（保險部位 55.9%），台股元大兩檔 1,122,937 未動")
ps["status"] = "已完成（2026-11-26 執行）"

s["policy_conversion_executed_20261126"] = {
    "date": "2026-11-26",
    "source": "使用者口述 ＋ 安聯/第一金 App 截圖（10:35 轉換明細、10:38 帳戶價值）",
    "A": {"轉出": "USDEQ3490 安聯收益成長 50% = 1,278,189", "轉入": "USDEQ5440 摩根多重收益"},
    "B": {"轉出": {"USDEQ6730 黃金": 129034, "USDEQ5700 M&G入息": 617734,
                   "USDEQ3490 安聯收益成長": 470713},
          "轉出合計": 1217481, "轉入": "USDEQ5440 摩根多重收益"},
    "第一金": {"轉出": "IDXX M&G入息A 100%", "轉入": "FJXX 摩根多重收益(每月派息)", "金額": 1840657},
    "轉換後摩根合計": sum(A.values()) * 0 + int(A[kJ]) + int(B[name_b_jpm]) + int(s["firstjin_current_value"]),
    "口徑": "保單總值不變（A 4,796,376／B 2,340,418／第一金 1,840,657），僅成分改變",
    "App 顯示值（10:38，供下次真值日校正）": {"安聯A": 4796272, "安聯B": 2340418, "第一金": 1847017},
    "待確認": "第一金轉出單位數顯示 0；安聯B 是否已實際成交",
}

SNAP.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")

print("備份:", BAK)
print(f"安聯A 收益成長 {growth_A:,} → {A[kA]:,}（轉出 {out_A:,}）｜摩根 {A[kJ]:,}")
print(f"安聯B 三檔清空合計 {b_out:,} → 摩根 {B[name_b_jpm]:,}")
print("A 合計", f"{sum(A.values()):,}", "／ B 合計", f"{sum(B.values()):,}",
      "／ 第一金", f"{s['firstjin_current_value']:,}")
print("摩根三重合計", f"{A[kJ] + B[name_b_jpm] + s['firstjin_current_value']:,}")
print("JSON OK")
