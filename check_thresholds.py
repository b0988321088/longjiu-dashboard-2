#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_thresholds.py — 門檻單一真值（SoT）一致性檢查（2026-09-15 INC-187）

背景：門檻曾散落 7 處（各腳本硬編碼），其中 4 處是 7-8 月舊口徑，
      造成「同一件事兩套值」與「假警報／漏警報」（實踩：債券目標 15 vs 25、
      LTV 安全值 35% vs 現行 53%、美股減碼 33% vs 40%）。
規則：所有門檻一律讀 snapshot.thresholds_2026_0915；本檢查負責
      ① 確認 SoT 存在且欄位齊全
      ② 確認各消費端程式真的有引用 SoT（不是口頭說要讀）
      ③ 掃描全庫殘留的舊門檻字面（擋 patch over patch）
用法：python check_thresholds.py                # 全檢（有違規 exit 1）
      python check_thresholds.py --sot-only    # 只驗 SoT／消費端／舊字面／口徑（產報「前」跑）
      python check_thresholds.py --report-only # 只驗已產出日報的基金部位行（產報「後」跑）
INC-238：日報渲染行比對讀的是磁碟上的日報檔，只能排在產報之後；排前面會拿上一輪日報
        對本輪 snapshot → 基金群組值一變動就必假失敗（且訊息誤導成「疑似又用反推」）。
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SOT_KEY = "thresholds_2026_0915"

REQUIRED_SECTIONS = ["桶目標_pct", "動作階梯_pp", "單桶硬上限_pct", "減碼可執行性",
                     "風險煞車", "ltv分級_pct", "美元曝險_pct", "現金_twd", "避險衛星_pct"]

# 消費端必須引用 SoT 的程式
CONSUMERS = ["allocation_alert.py", "debt_restructure_tracker.py", "institutional_flow.py",
             "build_rebalance_dashboard.py", "build_penetration_report.py"]

# 已退役的舊門檻字面（掃到即視為殘留）
LEGACY_PATTERNS = [
    (r'"債券"\s*:\s*15\b', "舊桶目標 債券15%（現行 25%）"),
    (r'"現金/安全網"\s*:\s*15\b', "舊桶目標 現金15%（現行 5% + 現金底線制）"),
    (r'"防守型配息"\s*:\s*20\b', "舊桶目標 防守20%（現行 30%）"),
    (r'安全值\s*≤\s*35%', "舊 LTV 安全值 35%（現行 綠≤45／黃≤53／追繳70）"),
    (r'完成後\s*20\.4%', "8 月預估 LTV 20.4%（已失效）"),
    (r'us_ratio\s*>\s*33\b', "舊美股門檻 33%（現行 單桶硬上限 40%）"),
    (r'DEVIATION_TOLERANCE_PP\s*=\s*10\b', "舊容忍帶 10pp（現行導流 6pp）"),
    (r'LTV[^\n]{0,20}≥\s*0\.3[58]\b', "舊 LTV 門檻 35%/38%（現行 45/53）"),
]
SKIP_DIRS = {".git", "data", "cache", "node_modules", "__pycache__"}
SKIP_NAME = re.compile(r"^(_|snapshot_|snapshot\.|.*_archive|.*\.bak|.*backup|.*stale)")


_MODE_LABEL = {"all": "全檢", "sot": "SoT／口徑", "report": "日報口徑"}


def _mode_name() -> str:
    """執行模式（2026-09-22 INC-238）：--sot-only／--report-only／預設全檢。"""
    _a = sys.argv[1:]
    if "--report-only" in _a:
        return "report"
    if "--sot-only" in _a:
        return "sot"
    return "all"


def check_daily_report_row(snap: dict, errs: list[str]) -> str:
    """驗證「已產出」日報的基金部位行＝明細口徑且閉合（2026-09-15 INC-188）。

    回傳 "ok"／"no-report"（日報檔不存在）／"no-row"（找不到該行，格式可能已變）。
    ⚠️ INC-238：本檢查讀的是磁碟上既有的 daily_report_v2_<today>.html，**只能在日報產出後執行**；
       排在產報之前 = 拿上一輪日報比對本輪 snapshot → 基金群組值一動就必假失敗。
    """
    _fb = snap.get("funds_breakdown") or {}

    def _grp(_name):
        return sum(float(v) for k, v in (_fb.get(_name) or {}).items() if k != "note")

    _ju, _ca = _grp("一般申購") + _grp("自由Pay"), _grp("國泰直購")
    import datetime as _dt
    _rep = BASE / f"daily_report_v2_{_dt.date.today().isoformat()}.html"
    if not _rep.exists():
        return "no-report"
    _h = _rep.read_text(encoding="utf-8", errors="replace")
    _m = re.search(r"基金總市值\s*<strong>([\d,]+)\s*TWD</strong>[^\n]{0,200}?鉅亨網\s*<strong>([\d,]+)</strong>[^\n]{0,80}?國泰基金\s*<strong>([\d,]+)</strong>", _h)
    if not _m:
        return "no-row"
    _z, _x, _y = (int(g.replace(",", "")) for g in _m.groups())
    if abs(_x - _ju) > 1 or abs(_y - _ca) > 1:
        errs.append(f"日報基金部位口徑不符明細：鉅亨 {_x:,}（應 {_ju:,.0f}）／國泰 {_y:,}（應 {_ca:,.0f}）"
                    f" — 疑似又用反推（總值−國泰）")
    elif _x + _y != _z:
        errs.append(f"日報基金部位行不閉合：鉅亨 {_x:,} + 國泰 {_y:,} ＝ {_x+_y:,} ≠ 表頭總值 {_z:,}")
    else:
        print(f"✅ 日報基金部位行：明細口徑且閉合 {_x:,} + {_y:,} = {_z:,}")
    # 已不在 snapshot 的停泊/標的不得出現在該行（實例：MMF 500萬已轉 B11）
    _seg = _h[_m.start():_m.start() + 400]
    for _tok in ("MMF", "貨幣基金"):
        if _tok in _seg and not any(_tok in str(k) for k in _fb.get("國泰直購", {})):
            errs.append(f"日報基金部位行仍描述「{_tok}」停泊，但 snapshot 國泰直購已無該標的（字樣需同步）")

    # 2026-09-29 CIO major：日報「可動用流動資金」不得等於現金真值（指定用途款不得當可動用）。
    # 這條斷言抓的是「顯示端拿不到 restricted_cash 就當 0」的靜默失敗（regenerate_report.py 路徑曾中招）。
    try:
        from sot_targets import restricted_cash as _rst_fn
        _rst = _rst_fn(snap)
    except Exception:
        _rst = float(((snap.get("restricted_cash") or {}) or {}).get("金額") or 0)
    if _rst > 0:
        _cash_all = float(snap.get("cash_total") or 0)
        _avail = max(0.0, _cash_all - _rst)
        if f"可動用流動資金 {_cash_all:,.0f}" in _h:
            errs.append(f"日報「可動用流動資金」＝現金真值 {_cash_all:,.0f}（未扣指定用途款 {_rst:,.0f}，應為 {_avail:,.0f}）")
        elif f"可動用流動資金 {_avail:,.0f}" not in _h:
            errs.append(f"日報缺「可動用流動資金 {_avail:,.0f}」字樣（口徑缺漏或格式已變）")
        else:
            print(f"✅ 日報可動用流動資金口徑：{_avail:,.0f}（真值 {_cash_all:,.0f} − 指定用途款 {_rst:,.0f}）")
    return "ok"


def _summarize(mode: str, errs: list[str], rep_status: str = "") -> int:
    print("=" * 50)
    print(f"  門檻 SoT 一致性檢查（check_thresholds.py｜{_MODE_LABEL.get(mode, mode)}）")
    print("=" * 50)
    if errs:
        for e in errs:
            print(f"❌ {e}")
        print(f"\n❌ 檢查未通過（{len(errs)} 項）")
        return 1
    if mode != "report":
        print(f"✅ SoT 完整（{len(REQUIRED_SECTIONS)} 區塊）")
        print(f"✅ 消費端 {len(CONSUMERS)} 支皆引用 {SOT_KEY}")
        print("✅ 無舊門檻字面殘留")
    if mode != "sot":
        _msg = {"ok": "✅ 日報基金部位行：明細口徑且閉合",
                "no-report": "⏭️  日報檔不存在 → 未驗渲染行",
                "no-row": "⚠️ 日報找不到基金部位行（格式變了？未驗）"}
        print(_msg.get(rep_status, "⏭️  日報渲染行未驗"))
    return 0


def main() -> int:
    _mode = _mode_name()
    # --report-only：只驗日報渲染行（產報後跑），其餘區塊不適用（它們與日報無關）
    if _mode == "report":
        try:
            snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        except Exception as e:
            print(f"❌ snapshot.json 無法解析：{e}")
            return 1
        errs: list[str] = []
        return _summarize(_mode, errs, check_daily_report_row(snap, errs))
    errs: list[str] = []
    warns: list[str] = []
    _rep_status = ""

    # ① SoT 存在且欄位齊全
    try:
        snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ snapshot.json 無法解析：{e}")
        return 1
    sot = snap.get(SOT_KEY)
    if not isinstance(sot, dict):
        errs.append(f"snapshot 缺 {SOT_KEY}（門檻 SoT 未建立）")
        sot = {}
    for sec in REQUIRED_SECTIONS:
        if sec not in sot:
            errs.append(f"{SOT_KEY}.{sec} 缺漏")
    # 桶目標 = penetration.targets 需一致（同一件事不得兩套值）
    _bt = sot.get("桶目標_pct") or {}
    _tg = (snap.get("penetration") or {}).get("targets") or {}
    for _k, _pk in [("台股市值型", "台股市值型目標"), ("美股市值型", "美股市值型目標"),
                    ("防守型配息", "配息型目標"), ("債券", "債券型目標"), ("現金", "現金目標")]:
        if _k in _bt and _pk in _tg and float(_bt[_k]) != float(_tg[_pk]):
            errs.append(f"桶目標不一致：SoT {_k}={_bt[_k]} vs penetration.targets.{_pk}={_tg[_pk]}")

    # ②b 雙維度派生欄自洽（2026-09-29 INC-255：組成改了、合計沒同步 → 反推 % 與全系統不一致）
    try:
        _dd = (snap.get("dual_dimension_metric") or {}).get("防禦維度") or {}
        _comp = _dd.get("組成") or {}
        if _comp:
            _s = sum(float(v) for v in _comp.values())
            _t = float(_dd.get("合計") or 0)
            if abs(_s - _t) > 1:
                errs.append(f"雙維度防禦維度：Σ組成 {_s:,.0f} ≠ 合計 {_t:,.0f}（派生欄未同步）")
            else:
                print(f"✅ 雙維度防禦維度自洽：Σ組成 = 合計 {_s:,.0f}")
    except (TypeError, ValueError) as e:
        errs.append(f"雙維度防禦維度欄位無法解析：{e}")

    # ②c 負債月息口徑自洽（2026-09-30 使用者核准動態化：利息項禁寫死，三項相加必等動態值與合計）
    try:
        from sot_targets import liability_interest as _li_fn   # noqa: E402
        _li = _li_fn(snap)
        _mfe = snap.get("monthly_fixed_expense") or {}
        _lk = ("保單借貸利息", "券商質押利息", "基金質押利息")
        _mfe_int = sum(float(_mfe.get(k) or 0) for k in _lk)
        # 同源斷言（2026-09-30 CIO minor）：保單借貸餘額兩欄不得漂移（報表標籤與利息各讀一處）
        _lb_pol = float((snap.get("liabilities_build_up") or {}).get("保單借貸") or 0)
        _top_pol = float(snap.get("policy_pledge_loan") or 0)
        # 2026-10-04 P0（CIO 七審 bip 延期條件①）：mortgage_cathay_rate 必須存在 →
        # 使 build_investment_performance.py `or dl["rate"]`（寫死 0.026）的 fallback 永遠不可達。
        # 凍結期保護（PEND-20261004-07）：此鍵一缺，績效引擎就會以 0.026 編造月息且不會大聲失敗。
        if snap.get("mortgage_cathay_rate") in (None, ""):
            errs.append("snapshot 缺 mortgage_cathay_rate：績效引擎 build_investment_performance 的 "
                        "0.026 fallback 將變為可達（PEND-20261004-07 凍結期保護條件，禁止缺鍵）")
        if abs(_lb_pol - _top_pol) > 1:
            errs.append(f"保單借貸餘額不同源：liabilities_build_up.保單借貸 {_lb_pol:,.0f} ≠ policy_pledge_loan {_top_pol:,.0f}")
        if _li.get("合計") is None:
            # 2026-10-04 P0（PEND-20261004-02）：缺利率 → 無法驗證，不得以預設利率算出的值混充
            errs.append(f"負債月息無法計算：liabilities_build_up 缺利率鍵 {_li.get('_缺真值')}"
                        "（禁以預設利率 4.0/3.92/2.65% 頂替；請補真值後重跑）")
        elif abs(_mfe_int - float(_li["合計"])) > 1:
            errs.append(f"月支出利息口徑不一致：monthly_fixed_expense 三項 {_mfe_int:,.0f} ≠ sot_targets 動態值 {_li['合計']:,.0f}")
        else:
            print(f"✅ 負債月息自洽：保單 {_li['保單借貸利息']:,} + 券商 {_li['券商質押利息']:,} + 基金質押 {_li['基金質押利息']:,} = {_li['合計']:,}")
        _lines = sum(float(_mfe.get(k) or 0) for k in ("生活支出", "醫療_常態回診", "房貸_永豐", "房貸_國泰", *_lk))
        if abs(_lines - float(_mfe.get("合計") or 0)) > 1:
            errs.append(f"monthly_fixed_expense 分項相加 {_lines:,.0f} ≠ 合計 {_mfe.get('合計')}")
        if abs(float(snap.get("monthly_expense") or 0) - float(_mfe.get("合計") or 0)) > 1:
            errs.append(f"monthly_expense {snap.get('monthly_expense')} ≠ monthly_fixed_expense.合計 {_mfe.get('合計')}")
        _sc = (snap.get("sabbatical_checklist") or {}).get("記錄") or {}
        _last = _sc.get(sorted(_sc.keys())[-1]) if _sc else None
        if isinstance(_last, dict) and _last.get("每月負債成本") is not None:
            if abs(float(_last["每月負債成本"]) - float(_li["合計"])) > 1:
                errs.append(f"留停記錄.每月負債成本 {_last['每月負債成本']} ≠ 動態值 {_li['合計']}（請重跑 sabbatical_checklist_update.py）")
    except (TypeError, ValueError) as e:
        errs.append(f"負債月息口徑檢查失敗：{e}")

    # ②a 決策/評分/跑道端不得裸用 cash_total（2026-09-29 INC-254~256：同一病在 9 支腳本輪流復發）
    #     這些檔案的現金一律須經 sot_targets（available_cash／restricted_cash）才可進入判斷。
    _DECISION_ENDPOINTS = [
        "rotation_engine.py", "coast_fi_engine.py", "macro_regime.py", "report_components.py",
        "sabbatical_checklist_update.py", "debt_restructure_tracker.py", "institutional_flow.py",
        "build_retirement_plan.py", "asset_moat_monitor.py", "run_daily.py",
    ]
    _de_ok = 0
    for _f in _DECISION_ENDPOINTS:
        _p = BASE / _f
        if not _p.exists():
            continue
        _src = _p.read_text(encoding="utf-8", errors="replace")
        if "sot_targets" not in _src:
            errs.append(f"{_f} 決策/評分端未經 sot_targets 取得現金口徑（禁裸用 cash_total）")
        elif "cash_total" in _src and "restricted_cash" not in _src and "available_cash" not in _src:
            errs.append(f"{_f} 仍裸用 cash_total 且未扣指定用途款")
        else:
            _de_ok += 1
    # 2026-09-29 CIO minor：原用 for/else，✅ 訊息恆印（有 err 也印）→ 改計數，且未達全數列出
    print(f"✅ 決策端現金口徑檢查完成（{_de_ok}/{len(_DECISION_ENDPOINTS)} 支）")

    # ② 消費端有引用 SoT
    for f in CONSUMERS:
        p = BASE / f
        if not p.exists():
            errs.append(f"消費端檔案不存在：{f}")
            continue
        if SOT_KEY not in p.read_text(encoding="utf-8", errors="replace"):
            errs.append(f"{f} 未引用 {SOT_KEY}（可能仍在用硬編碼門檻）")

    # ③ 五桶＋衛星 = 總資產（穿透完整性；衛星＝黃金/健康為獨立避險桶，
    #    不在 penetration.actual_twd 內 → 必須另外加回。2026-09-15 有審查方只看 actual_twd
    #    五桶就判「資產對不上」→ 此檢查把不變量固定下來，避免同類誤判重演。）
    try:
        _a = (snap.get("penetration") or {}).get("actual_twd") or {}
        _five = sum(float(v) for k, v in _a.items() if not k.startswith("美股市值型成長_"))
        _sat = 0.0
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("_ua_chk", BASE / "update_all.py")
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
        _pv = _mod.calc_penetration(snap.get("cash_total"), snap.get("insurance_current_value"),
                                    snap.get("securities_total_market_value"),
                                    snap.get("fund_market_value"), snap=snap)
        _sat = float(_pv.get("黃金", 0)) + float(_pv.get("健康", 0))
        # 2026-09-29 使用者核准（restricted 隔離）：指定用途現金（質押撥款待清償）已從現金桶
        # 扣除，但它仍是總資產的一部分 → 不變量必須加回，否則會誤判「穿透不完整」。
        from sot_targets import restricted_cash as _rst_fn   # 單一實作（CIO minor3）
        _rst = _rst_fn(snap)
        # 2026-10-02（統一現金口徑）：現金桶改讀可動用真值後，餘數法的在途／未對帳差額
        # 已從桶內移出 → 不變量必須把它加回，否則會誤判「穿透不完整」（差 589）。
        # 讀「快取 penetration」的欄位（不是現算 _pv）：快取桶位與在途欄位必須同源，
        # 否則重算前後會出現「舊桶已含在途、又再加一次」的雙重計算假失敗。
        _cit = float(((snap.get("penetration") or {}).get("cash_in_transit")) or 0)
        _tot = float(snap.get("total_assets", 0))
        _diff = _five + _sat + _rst + _cit - _tot
        if abs(_diff) > 1:
            _hint = ""
            if abs(_five + _sat - _tot) <= 1 and _rst:
                _hint = "｜診斷：快取 penetration 尚未重算（舊口徑仍含指定用途款）→ 先跑 build_penetration_report.py 再同步"
            errs.append(f"穿透完整性失敗：五桶 {_five:,.0f} + 衛星 {_sat:,.0f} + 指定用途款 {_rst:,.0f} + 在途 {_cit:,.0f} = {_five+_sat+_rst+_cit:,.0f} ≠ 總資產 {_tot:,.0f}（差 {_diff:,.0f}）{_hint}")
        else:
            print(f"✅ 穿透完整性：五桶 {_five:,.0f} + 衛星 {_sat:,.0f} + 指定用途款 {_rst:,.0f} + 在途 {_cit:,.0f} = 總資產 {_tot:,.0f}")
    except Exception as _e:
        errs.append(f"穿透完整性檢查執行失敗：{_e}")

    # ④ 基金口徑閉合（2026-09-15 INC-188）
    #    實踩：日報「基金部位」那行原用 `基金總市值 − funds_cathay` 反推鉅亨網，
    #    而 funds_cathay 漏了 9/11 申購的 B11 4,981,060 → 印出「鉅亨網 5,803,222 ＋ 國泰基金 6,824,922」，
    #    兩者相加 7,647,084 ≠ 總值 12,628,144（使用者一眼抓到）。
    #    反推本身是「隱式假設被減項完整」，被減項漏同步就靜默出錯，且既有檢查全數通過 → 固化成不變量。
    try:
        _fb = snap.get("funds_breakdown") or {}
        def _grp(name):
            return sum(float(v) for k, v in (_fb.get(name) or {}).items() if k != "note")
        _ju, _ca = _grp("一般申購") + _grp("自由Pay"), _grp("國泰直購")
        _fc = snap.get("funds_cathay")
        _fcm = snap.get("funds_cathay_market_value")
        _fcb = sum(float(v) for v in (snap.get("funds_cathay_breakdown") or {}).values())
        _funds = float(snap.get("funds") or snap.get("fund_market_value") or 0)
        for _label, _val in [("funds_cathay", _fc), ("funds_cathay_market_value", _fcm),
                             ("sum(funds_cathay_breakdown)", _fcb)]:
            if _val is None:
                errs.append(f"基金口徑：snapshot 缺 {_label}")
            elif abs(float(_val) - _ca) > 1:
                errs.append(f"基金口徑：{_label}={float(_val):,.0f} ≠ 國泰直購明細 {_ca:,.0f}（同義欄位漏同步）")
        if _funds and abs(_ju + _ca - _funds) > 1:
            errs.append(f"基金口徑：鉅亨 {_ju:,.0f} + 國泰 {_ca:,.0f} ＝ {_ju+_ca:,.0f} ≠ funds {_funds:,.0f}（差 {_ju+_ca-_funds:,.0f}）")
        else:
            print(f"✅ 基金口徑閉合：鉅亨 {_ju:,.0f} + 國泰 {_ca:,.0f} = funds {_funds:,.0f}")
        # 反推寫法黑名單（run_daily 等渲染端不得再用 總值−國泰 推鉅亨）
        # 註：`funds'[^)]*\)` 是為了吃掉 `tv.get('funds',0)` 的 `,0)`；寫成 `funds'\)`
        #     會漏抓（2026-09-15 負向測試實測 False，差點交出假防線）。
        _rev = re.compile(r"funds'[^)]*\)\s*[-−]\s*tv\.get\(\s*['\"]funds_cathay"
                          r"|fund_market[^\n]{0,60}[-−]\s*(?:snap|tv)\.get\(\s*['\"]funds_cathay")
        for _p in [BASE / "run_daily.py", BASE / "regenerate_report.py", BASE / "build_dashboard.py"]:
            if _p.exists() and _rev.search(_p.read_text(encoding="utf-8", errors="replace")):
                errs.append(f"{_p.name} 仍用「基金總值 − funds_cathay」反推鉅亨網（應改讀 funds_breakdown 群組加總）")
        # 日報渲染行比對（INC-188／INC-238）：讀的是磁碟上的日報檔 → 只能在產報「之後」驗。
        # sync_all 步驟 2 以 --sot-only 跳過此段，日報產出後再以 --report-only 補驗。
        if _mode != "sot":
            _rep_status = check_daily_report_row(snap, errs)
    except Exception as _e:
        errs.append(f"基金口徑閉合檢查執行失敗：{_e}")

    # ⑤ 舊門檻字面殘留掃描
    hits: list[str] = []
    for p in BASE.rglob("*"):
        if not p.is_file() or p.suffix not in (".py", ".json", ".sh"):
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if SKIP_NAME.match(p.name):
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for ln, line in enumerate(txt.splitlines(), 1):
            # 說明/檢討用的引述行不掃（標記慣例：行內含 sot-exempt）；
            # 全域字串比對若連「解釋舊值錯在哪」的行都擋，就會讓人不想寫檢討 → 綁形式不綁字面。
            if "sot-exempt" in line:
                continue
            for pat, desc in LEGACY_PATTERNS:
                if re.search(pat, line):
                    hits.append(f"  {p.relative_to(BASE)}:{ln} → {desc}")
    if hits:
        errs.append(f"殘留舊門檻 {len(hits)} 處：\n" + "\n".join(sorted(set(hits))[:15]))

    # ── 真值層四塊（2026-09-30 Q4 核心原則，使用者裁示）：存在性／同源／算術／狀態字樣 ──
    try:
        for _k in ("cash_layers", "metrics_registry", "us30y_gate", "redline_policy"):
            if not snap.get(_k):
                errs.append(f"真值層缺 {_k}（須由 update_data 的單一 writer 派生寫回）")
        _cl = snap.get("cash_layers") or {}
        if _cl:
            _tot = float(_cl.get("cash_total") or 0)
            _res = float((_cl.get("restricted_cash") or {}).get("total") or 0)
            _unr = float(_cl.get("unrestricted_cash") or 0)
            if abs(_tot - _res - _unr) > 1:
                errs.append(f"現金分層不閉合：cash_total {_tot:,.0f} − restricted {_res:,.0f} ≠ unrestricted {_unr:,.0f}")
            _emg = float((_cl.get("emergency_cash") or {}).get("金額") or 0)
            _dry = float(_cl.get("dry_powder") or 0)
            if abs(_emg + _dry - _unr) > 1:
                errs.append(f"現金分層不閉合：底線 {_emg:,.0f} + 乾粉 {_dry:,.0f} ≠ 可動用 {_unr:,.0f}")
        _ug = snap.get("us30y_gate") or {}
        try:
            _st = json.loads((BASE / "us30y_state.json").read_text(encoding="utf-8"))
        except Exception:
            _st = {}
        if _ug and _st:
            if _ug.get("as_of") != _st.get("last_date"):
                errs.append(f"us30y_gate.as_of {_ug.get('as_of')} ≠ us30y_state.last_date {_st.get('last_date')}（未同源 → 解凍判定會踩舊讀值）")
            if _ug.get("value") != _st.get("last_rate"):
                errs.append(f"us30y_gate.value {_ug.get('value')} ≠ us30y_state.last_rate {_st.get('last_rate')}")
        if _ug and _ug.get("status") != "OK" and _ug.get("unfreeze_allowed"):
            errs.append(f"US30Y 閘門 {_ug.get('status')} 卻許可解凍（應為 False）")
        if _ug and _ug.get("below_red_line") is False and _ug.get("unfreeze_allowed"):
            errs.append("US30Y 未脫離紅線卻許可解凍")
        # 未閉環 pending 卡狀態不得含「已結案」字樣（build_dashboard 以子字串過濾 → 整卡會靜默消失）
        _closed_kw = ("✅", "☑", "已完成", "已結案", "已定案", "閉環", "已送出", "已核定")
        for _it in json.loads((BASE / "pending_decisions.json").read_text(encoding="utf-8")):
            _s = str(_it.get("status") or "")
            for _t in _closed_kw:
                if _t in _s:
                    errs.append(f"pending 未閉環卡狀態含「{_t}」→ build_dashboard 會誤判已結案、整卡隱藏：{str(_it.get('title',''))[:34]}")
                    break
        # ── 國泰房貸利率一致性（2026-10-01）：權威鍵 vs 實繳月付 vs 舊副本 ──
        _mcr = float(snap.get("mortgage_cathay_rate") or 0)
        _mcp = float(snap.get("mortgage_cathay") or 0)
        if _mcr and _mcp:
            _exp_pay = _mcp * _mcr / 12
            _act_pay = float((snap.get("monthly_fixed_expense") or {}).get("房貸_國泰") or 0)
            if _act_pay and abs(_act_pay - _exp_pay) > 1:
                errs.append(f"國泰房貸月付與 利率×本金/12 不一致：實繳 {_act_pay:,.0f} vs 派生 {_exp_pay:,.0f}"
                            f"（rate={_mcr:.4f}、本金 {_mcp:,.0f}）→ 寬限期付息下兩者應相等；若已進入本利攤還請更新 mortgage_cathay_rate")
            _cd = snap.get("cathay_disbursement")
            _old_r = float((_cd or {}).get("rate") or 0) if isinstance(_cd, dict) else 0
            if _old_r and abs(_old_r - _mcr) > 1e-9:
                errs.append(f"國泰利率副本不一致：cathay_disbursement.rate {_old_r} ≠ mortgage_cathay_rate {_mcr}（應收斂為單一權威鍵）")
    except Exception as _e:
        errs.append(f"真值層檢查失敗：{_e}")

    return _summarize(_mode, errs, _rep_status)


if __name__ == "__main__":
    sys.exit(main())
