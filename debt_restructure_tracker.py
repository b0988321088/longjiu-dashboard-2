#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debt_restructure_tracker.py v3 — 龍九動態監測模組（每週日 08:50 cron 輸出）
五大監測維度：市場利率(Rhythm-08) / 匯率 / PI狀態 / LTV槓桿 / 現金流與債務時程。
"""
import json, sys, urllib.request
from datetime import date, timedelta
from pathlib import Path

BASE = Path("C:/Users/bot/Desktop/longjiu_system")
today = date.today()

# -------- 輸入變數 --------
base_fx = 32.18          # 基準匯率
ideal_monthly_surplus = 40000
pessimistic_low = 0
pessimistic_high = 10000
PI_STATES = ["未申請", "審核中", "已正式核准"]

def load_engine_rules():
    """讀取 arbitrage_engine_rules.json 規則配置"""
    try:
        return json.load(open(BASE / "arbitrage_engine_rules.json", encoding="utf-8"))
    except Exception:
        return {}

def calc_net_yield(asset_yield, tax_rate, funding_cost, hedging_cost, friction_cost):
    """模組一：實質淨收益計算 Net Yield = Yield×(1-Tax) - Cost_funding - Cost_hedging - Cost_friction"""
    return asset_yield * (1 - tax_rate) - funding_cost - hedging_cost - friction_cost

def net_yield_light(net_yield, rules):
    """執行閥值判定 Rule 1.1/1.2/1.3"""
    th = rules.get("execution_thresholds", {})
    if net_yield >= th.get("green_light", 0.012):
        return "🟢 GREEN 允許建倉/掛單"
    elif net_yield >= th.get("yellow_light_min", 0.005):
        return "🟡 YELLOW 僅靜態保留，不擴張新資金"
    else:
        return "🔴 RED 自動拒絕交易"

def load(name):
    try:
        return json.load(open(BASE / name, encoding="utf-8"))
    except Exception as e:
        print(f"⚠️ {name} 讀取失敗: {e}")
        return {}

def fetch_fred(series_id):
    """抓取 FRED 最新值（公開 CSV endpoint）"""
    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = urllib.request.urlopen(req, timeout=15).read().decode()
        lines = [l for l in data.strip().split('\n') if l]
        if len(lines) >= 2:
            last = lines[-1].split(',')
            try:
                return float(last[1]), last[0]
            except:
                return None, None
    except Exception as e:
        return None, None
    return None, None

def fetch_fx():
    """抓取 USD/TWD 匯率"""
    try:
        req = urllib.request.Request("https://open.er-api.com/v6/latest/TWD",
                                     headers={'User-Agent': 'Mozilla/5.0'})
        d = json.loads(urllib.request.urlopen(req, timeout=15).read())
        usd = d.get('rates', {}).get('USD')
        if usd:
            return 1 / usd
    except Exception:
        pass
    return None

def main():
    snap = load("snapshot.json")
    pi = snap.get("professional_investor", {})
    plan = pi.get("deployment_plan", {})
    pending = load("pending_decisions.json")
    events = load("schedule_events.json")

    print("=" * 58)
    print(f"===== 龍九動態監測｜{today.isoformat()} =====")
    print("=" * 58)

    # -------- 1. 市場利率 Rhythm-08 --------
    us30y, us30y_date = fetch_fred("DGS30")
    if us30y is None:
        us30y = snap.get("rhythm08", {}).get("indicators", {}).get("us30y") or 5.21
        us30y_date = "snapshot 舊值"
    if us30y > 5.30:
        rhythm_light = "🔴全域凍結"
    elif us30y > 5.15:
        rhythm_light = "🟡滯脹警戒"
    else:
        rhythm_light = "🟢安全"
    print(f"\n【1.市場利率｜Rhythm-08】")
    print(f"  US30Y = {us30y:.2f}%（{us30y_date}）")
    print(f"  燈號：{rhythm_light}（🟢安全 / 🟡警戒>5.15 / 🔴全域凍結>5.30）")
    if rhythm_light == "🟢安全":
        print(f"  規則：可依 B先A後 時程執行")
    elif rhythm_light == "🟡滯脹警戒":
        print(f"  規則：LTV上限強制 ≤30%，停止擴張質押")
    else:
        print(f"  規則：禁止新增買債、禁止新增質押借貸；舊部位只監控LTV，不強制全數賣出")

    # -------- 2. 匯率監測 --------
    usd_twd = fetch_fx()
    if usd_twd is None:
        usd_twd = 32.18
        fx_note = "（抓取失敗，用基準值）"
    else:
        fx_note = ""
    fx_change = usd_twd - base_fx  # 台幣升 = 負值
    if fx_change <= -2.5:
        fx_light = "🔴風險"
    elif fx_change <= -2.0:
        fx_light = "🟡警示"
    else:
        fx_light = "🟢正常"
    print(f"\n【2.匯率監測 USD/TWD = {usd_twd:.2f}】{fx_note}")
    print(f"  階段升幅（相對基準 32.18）：{fx_change:+.2f}")
    print(f"  燈號：{fx_light}（🟢正常 / 🟡警示≥2.0% / 🔴風險≥2.5%）")
    if fx_light == "🟡警示":
        print(f"  動作：停止美元停泊部位繼續加碼")
    elif fx_light == "🔴風險":
        print(f"  動作：可部分結匯回台幣活存，不對賭匯率，停泊只求微薄利息")

    # -------- 3. PI 專業投資人狀態 --------
    pi_status = pi.get("pi_status", "未申請")
    if pi_status not in PI_STATES:
        pi_status = "未申請"
    can_do_lombard = (pi_status == "已正式核准")
    print(f"\n【3.PI專業投資人狀態】")
    print(f"  PI_approval_status：{pi_status}")
    print(f"  ⚠️ 硬性鎖定：PI非【已正式核准】→ 禁止執行任何 Lombard 質押借出作業")
    if not can_do_lombard:
        print(f"  → 10/1 國泰洲際W轉增貸前置檢查：PI未核准 → 建議延後轉增貸，避免負債變動干擾PI資產核算")
    else:
        print(f"  → 10/1 國泰洲際W轉增貸前置檢查：✅ 可執行")

    # -------- 4. LTV 質押槓桿監控 --------
    ltv = plan.get("current_ltv", 0)
    ltv_max = 0.30 if us30y > 5.15 else 0.40
    env = "滯脹警戒環境(US30Y>5.15)" if us30y > 5.15 else "正常環境"
    print(f"\n【4.LTV質押槓桿監控】")
    print(f"  current_LTV_ratio = {ltv*100:.1f}%" if ltv else "  current_LTV_ratio = 0%（尚未質押）")
    print(f"  環境判斷：{env}")
    print(f"  允許LTV上限：{ltv_max*100:.0f}%")
    if ltv <= ltv_max:
        print(f"  檢核結果：✅ 符合門檻（正常環境≤40% / 滯脹警戒≤30%）")
    else:
        print(f"  檢核結果：⚠️ 超出上限 → 需要主動還本降槓桿")

    # -------- 5. 現金流 & 債務重整時程 --------
    print(f"\n【5.現金流 & 債務重整時程】")
    print(f"  預估每月可償還結餘(理想)：{ideal_monthly_surplus:,} NTD")
    print(f"  悲觀場景可償還結餘：{pessimistic_low:,}~{pessimistic_high:,} NTD")
    print(f"  提醒：降槓桿週期非固定，環境惡化還本速度會顯著拉長")

    # -------- 5b. 階梯式債券配置（B方案 500萬）-------
    print(f"\n【5b.階梯式債券配置（B方案 500萬）】")
    print(f"  1-3年投資等級短債階梯（持有至到期，鎖定收益）")
    print(f"  ├ 1年內  200萬（40%）→ 流動性+再投資")
    print(f"  ├ 1-2年  150萬（30%）→ 核心收益")
    print(f"  └ 2-3年  150萬（30%）→ 收益鎖定")
    print(f"  預期收益：4.5-5.0% → 年收 ~23-25萬")
    print(f"  淨利差（扣 2.6% 融資）：1.9-2.4%")
    print(f"  ⚠️ 紀律：>5年凍結（US30Y 5.22% 警戒）；00983D 不新增；持有到期不炒價差")

    # -------- 6. 套利引擎（Arbitrage Engine）-------
    rules = load_engine_rules()
    fc = rules.get("funding_cost", {})
    print(f"\n【6.套利引擎｜實質淨收益計算】")
    print(f"  Net Yield = Yield×(1-Tax) - 融資 - 鎖匯 - 摩擦")
    # 三個路徑淨利差
    paths = [
        ("① 債務重置（清償高息債）", 0.04, 0.0, 0.026, "還債=確定性收益"),
        ("② 美元MMF/短債（BIL/00865B）", 0.04, 0.0, 0.026, "無Duration風險"),
        ("③ 階梯投資等級短債（1-3年）", 0.0475, 0.0, 0.026, "持有至到期"),
    ]
    for name, y, hedge, fund, note in paths:
        ny = calc_net_yield(y, 0.0, fund, hedge, fc.get("friction_cost", 0.0015))
        light = net_yield_light(ny, rules)
        print(f"  {name}: 淨利差 {ny*100:.2f}% → {light}（{note}）")

    # -------- 7. 熔斷閘門檢查（Safety Breaker）-------
    print(f"\n【7.熔斷閘門檢查（Safety Breaker）】")
    breakers = rules.get("risk_breakers", [])
    cash = snap.get("cash_total", 0)
    checks = []
    # US30Y（us30y 為百分比數值 5.22 → 轉 0.0522 比較）
    us30y_dec = us30y / 100.0
    if us30y_dec >= 0.053:
        checks.append(("US30Y", f"{us30y:.2f}% > 5.30%", "🔴 GLOBAL_FREEZE + 停泊退守MMF"))
    elif us30y_dec >= 0.052:
        checks.append(("US30Y", f"{us30y:.2f}% ≥ 5.20%", "🟡 美股停購/長債凍結/台股≤50萬"))
    # 現金
    if cash < 850000:
        checks.append(("現金", f"{cash:,.0f} < 85萬", "🔴 HALT_ALL_BUY"))
    # 美股占比
    us_ratio = snap.get("penetration", {}).get("actual_pct", {}).get("美股市值型成長", 0)
    if us_ratio > 33:
        checks.append(("美股占比", f"{us_ratio:.1f}% > 33%", "🟡 FREEZE_US_BUY + 逢彈減碼"))
    # LTV（未質押=0）
    ltv_val = plan.get("current_ltv", 0)
    if ltv_val >= 0.38:
        checks.append(("LTV", f"{ltv_val:.0%} ≥ 38%", "🔴 INJECT_CASH + HALT_EXPANSION"))
    elif ltv_val >= 0.35:
        checks.append(("LTV", f"{ltv_val:.0%} ≥ 35%", "🟡 停止新增質押"))
    if not checks:
        print("  ✅ 全部閘門通過（無熔斷觸發）")
    else:
        for metric, val, action in checks:
            print(f"  {action}｜{metric}: {val}")

    # 重大時程檢查
    print(f"\n  重大時程檢查：")
    if today >= date(2026, 8, 15):
        print(f"  ☑ 8-15 國泰撥款：執行清高息壞債 + 400萬停泊配置（已到期）")
    else:
        print(f"  ☐ 8-15 國泰撥款：執行清高息壞債 + 400萬停泊配置（還有 {(date(2026,8,15)-today).days} 天）")
    oct_gate = "✅ 可執行" if can_do_lombard else "🔒 受PI狀態鎖定（未核准→延後）"
    print(f"  ☐ 10-01 國泰洲際W轉增貸（{oct_gate}）")

    # 下週關鍵節點
    print(f"\n  下週關鍵節點（{today.isoformat()} ~ {(today+timedelta(days=7)).isoformat()}）：")
    found = False
    if isinstance(events, list):
        for e in events:
            d = str(e.get("date", e.get("start", "")))[:10]
            try:
                ed = date.fromisoformat(d)
            except:
                continue
            if today <= ed <= today + timedelta(days=7):
                print(f"    📅 {d}: {e.get('item', e.get('title', '?'))}")
                found = True
    if not found:
        print("    （無）")

    # -------- 綜合建議 --------
    print(f"\n【本週綜合建議動作】")
    n = 1
    if rhythm_light != "🟢安全":
        print(f"  {n}. 🎵 Rhythm-08 {rhythm_light}：{'停止擴張質押' if rhythm_light=='🟡滯脹警戒' else '禁止新增買債/質押，只監控LTV'}")
        n += 1
    if fx_light != "🟢正常":
        print(f"  {n}. 💱 匯率{fx_light}：{'停止美元停泊加碼' if fx_light=='🟡警示' else '部分結匯回台幣，不對賭匯率'}")
        n += 1
    if not can_do_lombard:
        print(f"  {n}. 🎫 PI 未核准：禁 Lombard 質押；10/1 轉增貸建議延後")
        n += 1
    if today < date(2026, 8, 15):
        print(f"  {n}. 🔵 8/15 撥款前：台股≤50萬/週・美股停購・長債不疊・現金底線85萬")
        n += 1
    print(f"  {n}. 🛡️ 400萬停泊永遠禁止質押（防火牆）；全域凍結≠賣光舊部位")
    print("=" * 58)

if __name__ == "__main__":
    main()
