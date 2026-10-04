#!/usr/bin/env python3
"""PI 雙軌｜E2E 閉環驗收（使用者 2026-10-04 指定 5 測）

T1 approval=已核准        → Lombard / 執行鏈 解鎖
T2 approval=未核准        → 鎖定
T3 財力 proxy < 30M       → 不得影響 PI 核准狀態（雙軌分離）
T4 質押事實 12M/5.9M      → 與負債 SoT 一致
T5 sandbox 改未核准       → 所有 PI execution chain 立即重新鎖定（真實腳本跑一次）
T6 缺值／非法值           → fail-closed raise（禁 fail-open）
"""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent   # tests/ 的上一層 = repo 根
sys.path.insert(0, str(BASE))

import sot_targets as sot
import pi_card

SNAP = BASE / "snapshot.json"
OK, FAIL = "✅ PASS", "❌ FAIL"
results = []


def chk(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(f"  {OK if cond else FAIL}  {name}" + (f"　{detail}" if detail else ""))


def load():
    return json.loads(SNAP.read_text(encoding="utf-8"))


print("=" * 62)
print("PI 雙軌 E2E 閉環驗收")
print("=" * 62)

real = load()

# ---------- T1 已核准 → 解鎖 ----------
print("\n[T1] approval_status = 已核准 → capability 解鎖")
chk("pi_is_approved() == True", sot.pi_is_approved(real) is True)
p = pi_card.pi_payload(real)
chk("pi_card 無 error", p.get("error") is None, str(p.get("error"))[:80])
chk("pi_card.approved == True", p.get("approved") is True)
chk("卡片文案含『已解除』", "已解除" in pi_card.pi_html(p))
chk("卡片文案含『已核准』", "已核准" in pi_card.pi_html(p))

# ---------- T2 未核准 → 鎖定 ----------
print("\n[T2] approval_status = 未核准 → 鎖定")
s2 = json.loads(json.dumps(real))
s2["professional_investor"]["approval_status"] = "未核准"
chk("pi_is_approved() == False", sot.pi_is_approved(s2) is False)
chk("卡片文案含『鎖定』", "鎖定" in pi_card.pi_html(pi_card.pi_payload(s2)))

# ---------- T3 財力軌不影響資格軌 ----------
print("\n[T3] 財力 proxy = 26.79M < 30M 不得影響 PI 核准狀態")
proxy = sot.pi_financial_asset_proxy(real)
thr = sot.pi_regulatory_threshold()
chk(f"proxy {proxy:,.0f} < 門檻 {thr:,}", proxy < thr)
chk("同時 pi_is_approved() 仍為 True（雙軌分離）", sot.pi_is_approved(real) is True)
_html = pi_card.pi_html(pi_card.pi_payload(real))
chk("同一張卡同時顯示『已核准』與『未達』",
    ("已核准" in _html) and ("未達" in _html))
chk("pi_meets_financial_threshold() 不得回傳 True", sot.pi_meets_financial_threshold(real) is False)

# ---------- T4 質押事實與負債 SoT 一致 ----------
print("\n[T4] 質押事實（質押品 / 動用額 / 利率）三源一致")
cp = real.get("cathay_pledge_0911", {})
drawn = real.get("fund_pledge_loan")
rate = real.get("fund_pledge_rate")
pool_mv = float(cp.get("擔保池", {}).get("合計") or real.get("funds_cathay_market_value"))
con = sqlite3.connect(BASE / "dragon_assets.db")
db_pledge = con.execute(
    "SELECT pledge_loan FROM liabilities ORDER BY date DESC LIMIT 1").fetchone()[0]
con.close()
chk("snapshot.fund_pledge_loan 有值", drawn == 5900000, f"{drawn}")
chk("DB liabilities.pledge_loan 相等", db_pledge == drawn, f"DB={db_pledge}")
chk("cathay_pledge_0911.可貸金額 相等", cp.get("可貸金額") == drawn, f"{cp.get('可貸金額')}")
chk("利率 2.65% 單一值（snapshot vs 質押記錄）",
    float(real.get("fund_pledge_rate")) == 0.0265 and "2.65%" in str(cp.get("利率")),
    f"{rate}")
chk("LTV = 動用 ÷ 質押品市值（重算）",
    abs(drawn / pool_mv * 100 - 50.09) < 0.05, f"{drawn/pool_mv*100:.2f}%")
chk("『銀行核定授信額度』不得由質押品價值反推（12M 非授信額度）",
    cp.get("授信額度") in (None, "", "未取得銀行核定文件"), f"現況={cp.get('授信額度', '（未設此欄）')}")

# ---------- T5 sandbox relock：真實腳本雙態對照 ----------
# 2026-10-04 CIO 審查：原版此段有恆真式斷言（尾端接了短路恆真運算子）與無鑑別力的字串（被測腳本無論解鎖
# 與否都會印「硬性鎖定…禁止」）。改為「同一支腳本跑兩態、逐條斷言必須在另一態為偽」的
# 2×2 對照，並附突變自測證明判別式真的有鑑別力。
print("\n[T5] 雙態對照：approval=已核准 vs 未核准，跑真實 entry_monitor / debt_restructure_tracker")
orig_bytes = SNAP.read_bytes()
orig_md5 = hashlib.md5(orig_bytes).hexdigest()
ENV = dict(os.environ, LJ_NO_TELEGRAM="1", TG_TOKEN="", TG_CHAT_ID="")
_M3 = "【3.PI專業投資人狀態】"


def _run(script):
    r = subprocess.run([sys.executable, str(BASE / script)], cwd=BASE,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=600, env=ENV)
    return r.stdout or ""


def _body(out):
    return out[out.find(_M3):out.find(_M3) + 600] if _M3 in out else ""


em_ok, dt_ok = _run("entry_monitor.py"), _body(_run("debt_restructure_tracker.py"))

_lk = json.loads(orig_bytes.decode("utf-8"))
_lk["professional_investor"]["approval_status"] = "未核准"
try:
    SNAP.write_text(json.dumps(_lk, ensure_ascii=False, indent=1), encoding="utf-8")
    em_lk, dt_lk = _run("entry_monitor.py"), _body(_run("debt_restructure_tracker.py"))
finally:
    SNAP.write_bytes(orig_bytes)

_APPROVED_MARK = "PI 已核准（唯一容器"
chk("entry_monitor 已核准態：印出執行鏈啟動", _APPROVED_MARK in em_ok)
chk("entry_monitor 未核准態：不印執行鏈啟動", _APPROVED_MARK not in em_lk,
    (em_lk.strip().splitlines() or [""])[-1][:60])
chk("debt_tracker 已核准態：出現『✅ 可執行』", "✅ 可執行" in dt_ok)
chk("debt_tracker 未核准態：出現『建議延後』且無『✅ 可執行』",
    ("建議延後" in dt_lk) and ("✅ 可執行" not in dt_lk))

# 突變自測：把未核准態的判別字串換成已核准態字串 → 同一判別式必須轉偽
_mut = dt_lk.replace("建議延後", "✅ 可執行")
chk("突變自測：debt_tracker 判別式有鑑別力（換字後判偽）",
    not (("建議延後" in _mut) and ("✅ 可執行" not in _mut)))
_mut2 = em_lk + "\n" + _APPROVED_MARK
chk("突變自測：entry_monitor 判別式有鑑別力（注入字串後判偽）",
    not (_APPROVED_MARK not in _mut2))

restored = hashlib.md5(SNAP.read_bytes()).hexdigest()
chk("sandbox 後 snapshot 已還原（md5 一致，未污染真值）", restored == orig_md5)

# ---------- T6 fail-closed 守門 ----------
print("\n[T6] 缺值／非法值 → fail-closed（禁 fail-open）")
for label, mut in [
    ("無容器", lambda d: d.pop("professional_investor")),
    ("缺 approval_status", lambda d: d["professional_investor"].pop("approval_status")),
    ("非法值『已認列』", lambda d: d["professional_investor"].__setitem__("approval_status", "已認列")),
]:
    d = json.loads(json.dumps(real))
    mut(d)
    try:
        sot.pi_is_approved(d)
        chk(f"{label} → raise", False, "未 raise（fail-open 風險）")
    except Exception as e:
        chk(f"{label} → raise", True, type(e).__name__)

# ---------- 總結 ----------
print("\n" + "=" * 62)
bad = [r for r in results if not r[1]]
print(f"總計 {len(results)} 項｜PASS {len(results)-len(bad)}｜FAIL {len(bad)}")
for n, _, d in bad:
    print(f"  ❌ {n}  {d}")
print("=" * 62)
sys.exit(1 if bad else 0)
