#!/usr/bin/env python3
"""龍九資產統一更新入口。"""
import json, sqlite3, sys, subprocess
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent
# Cron no_agent 模式：CWD 可能不是 workdir，手動後備路徑
if not (BASE / "snapshot.json").exists():
    _alt = Path(r"C:\Users\bot\Desktop\longjiu_system")
    if _alt.exists():
        BASE = _alt
SNAP = BASE / "snapshot.json"
DB = BASE / "dragon_assets.db"
HIST = BASE / "asset_diff_history.json"
# 確保 BASE 在 Python 路徑中（給 cron no_agent 用）
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
TODAY = date.today().isoformat()

def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))
def save_json(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

def _fv(v):
    """Extract numeric value from snapshot fund entry (may be int or dict)."""
    return v["value"] if isinstance(v, dict) else (v if isinstance(v, (int,float)) else 0)


def calc_penetration(cash, ins, sec, funds, bond_portion=None, fund_ratios=None, snap=None):
    _fj = int((snap or {}).get(\"firstjin_detail\", {}).get(\"base_value_before_dividend\")
              or (snap or {}).get(\"firstjin_current_value\")
              or (snap or {}).get(\"firstjin_fl65_current_value\") or 1_958_980)
    _fjd = (snap or {}).get(\"firstjin_detail\", {})
    _cf_ratios = (_fjd.get(\"current_fund\") or {}).get(\"穿透比率\", {}) or {}
    _fj_eq_r = float(_cf_ratios.get(\"股票\", 0.55))
    _fj_br_r = float(_cf_ratios.get(\"債券\", 0.40))
    _fj_bond = round(_fj * _fj_br_r)
    _fj_eqv = round(_fj * _fj_eq_r)

    _TECH = {"貝萊德世界科技": 1.0, "貝萊德科技": 1.0, "009824": 1.0, "00924": 1.0, "台新美日台半導體": 0.90,
             "富達全球動能多元": 0.35, "安聯AI收益成長": 0.35, "聯博美國成長": 0.40, "安聯收益成長": 0.20,
             "摩根JPM": 0.15, "摩根多重收益": 0.15, "PIMCO收益增長": 0.20, "M&G入息": 0.15, "聯博全球多元收益": 0.15,
             "貝萊德世界黃金基金A10美元(總報酬穩定配息)": 0, "貝萊德世界健康科學基金A10美元(總報酬穩定配息)": 0.30, "00646": 0.32, "009823": 0.32}

    def _match_fund_key(_full_name, _lookup_dict):
        \"\"\"模糊匹配基金名稱\"\"\"
        for _k in _lookup_dict:
            if _k in _full_name:
                return _k
        return None

    def _match_fund_key(_full_name, _lookup_dict):
        """模糊匹配基金名稱"""
        for _k in _lookup_dict:
            if _k in _full_name:
                return _k
        return None

    def _tr(_fn):
        _matched_key = _match_fund_key(_fn, _TECH)
        return _TECH.get(_matched_key, 0.15) if _matched_key else 0.15

    if bond_portion is not None:
        ins_bonds = int(bond_portion)
        ins_eq = int(ins) - int(bond_portion) - _fj
    elif fund_ratios:
        # 從 snapshot 動態讀取保險基金市值
        if snap:
            _a = snap.get(\"insurance_breakdown\", {}).get(\"policy_a_funds\", {})
            _b = snap.get(\"insurance_breakdown\", {}).get(\"policy_b_funds\", {})
            fv = {}
            for k in list(dict.fromkeys(list(_a.keys()) + list(_b.keys()))):
                fv[k] = _fv(_a.get(k, 0)) + _fv(_b.get(k, 0))
        else:
            fv = {\"安聯收益成長\": 1_220_722, \"M&G入息\": 1_069_377, \"安聯AI收益成長\": 885_569, \"貝萊德科技A10\": 1_833_036, \"PIMCO收益增長\": 2_636_319}
        ins_bonds = sum(round(fv[n] * fund_ratios.get(_match_fund_key(n, fund_ratios), 0)) for n in fv)
        ins_tech = sum(round(fv[n] * _tr(n)) for n in fv)
        ins_eq = int(ins) - ins_bonds - _fj
    else:
        # 從 snapshot 動態讀取 + 預設債券比率（安聯收益35%, M&G 55%, AI收益50%）
        if snap:
            _a = snap.get(\"insurance_breakdown\", {}).get(\"policy_a_funds\", {})
            _b = snap.get(\"insurance_breakdown\", {}).get(\"policy_b_funds\", {})
            fv = {}
            for k in list(dict.fromkeys(list(_a.keys()) + list(_b.keys()))):
                fv[k] = _fv(_a.get(k, 0)) + _fv(_b.get(k, 0))
            _br = {"安聯收益成長": 0.35, "M&G入息": 0.55, "安聯AI收益成長": 0.50, "PIMCO收益增長": 0.48, "摩根JPM多重收益": 0.50, "貝萊德世界黃金基金A10美元(總報酬穩定配息)": 0, "貝萊德世界健康科學基金A10美元(總報酬穩定配息)": 0, "第一金FA81（聯博-全球多元收益基金 AD月配級別美元…）": 0.61}
            ins_bonds = sum(round(fv[n] * _br.get(_match_fund_key(n, _br), 0)) for n in fv)
            ins_tech = sum(round(fv[n] * _tr(n)) for n in fv)
        else:
            ins_bonds = round(2_780_466*0.35 + 3_136_436*0.55 + 902_679*0.50)
            ins_tech = round(2_780_466*0.16 + 3_136_436*0.07 + 902_679*0.35)
        ins_eq = int(ins) - ins_bonds - _fj
    # 分類基金（鉅亨基金帳戶）— 支援扁平 {name: val} 或嵌套 {群組: {name: val}}
    _fund_tw = _fund_us = _fund_def = _fund_us_tech = _fund_cash = _fund_bonds = 0
    _fb = (snap or {}).get(\"funds_breakdown\", {})
    _fb_flat = {}
    for _fn, _fval in _fb.items():
        if isinstance(_fval, dict):
            for _sn, _sv in _fval.items():
                if _sn in (\"小計\", \"匯率調整\", \"note\") or not isinstance(_sv, (int, float)):
                    continue
                _fb_flat[_sn] = _sv
        elif isinstance(_fval, (int, float)):
            _fb_flat[_fn] = _fval
    for _fn, _fval in _fb_flat.items():
        # 2026-08-21 成分穿透：富達（股80.75/債14.03/現5.21，月報 2026/6/30）與
        # 聯博全球多元收益（股55/債40/現5，估計待月報）拆股債現，不再整筆丟單一桶
        if \"富達全球動能多元\" in _fn:
            # 成分穿透（月報 2026/6/30）：股 80.75 / 債 14.03 / 現 5.21
            # ⚠️ 2026-08-21：基金內部現金 5.21% 併入美股（85.96%），不進現金桶 — 避免污染「現金/安全網」
            _fund_us += round(_fval * 0.8075) + round(_fval * 0.0521)
            _fund_bonds += round(_fval * 0.1403)
            _fund_cash += 0
            _fund_us_tech += round(_fval * 0.8075 * _tr(_fn))
        elif \"聯博全球多元收益\" in _fn:
            # 8/24 月報真值（使用者提供 PDF）：股票 34.63% + 其他 4.00%（選擇權策略）= 38.63% 權益；債券 61.37%
            # 前5大持股全科技 8.03%（NVDA2.28+AAPL2.00+GOOGL1.60+AVGO1.15+MSFT1.00）→ 科技保守估 10%
            # ⚠️ AD 月配級別配息來源可能為本金；信評 BB+B = 46.7% 高收益債
            _fund_us += round(_fval * 0.3863)
            _fund_bonds += round(_fval * 0.6137)
            _fund_cash += 0
            _fund_us_tech += round(_fval * 0.10)
        elif \"台中銀台灣優息\" in _fn or \"國泰台灣高股息\" in _fn:
            _fund_def += _fval
        elif any(_k in _fn for _k in [\"台新美日台\", \"貝萊德\", \"安聯AI\", \"聯博\", \"摩根\", \"M&G\", \"安聯收益成長\", \"投資型保單\"]): # 增加投資型保單匹配
            _fund_us += _fval
            _fund_us_tech += _fval * _tr(_fn)
        elif any(_k in _fn for _k in [\"0050連結\", \"統一奔騰\", \"安聯台灣科技\", \"路博邁台灣5G\", \"路博邁5G\"]): # 增加投資型保單匹配
            _fund_tw += _fval
        elif \"貨幣\" in _fn:
            _fund_cash += _fval
        else:
            _fund_tw += _fval
    _SEC_TW = {\"0050\", \"006208\", \"009816\"}
    _SEC_US = {\"00646\", \"009823\", \"009824\", \"00924\"}
    _SEC_DEF = {\"00713\", \"00878\", \"0056\", \"00919\", \"00918\", \"00888\"}
    _SEC_BOND = {\"00983D\"}
    sec_tw = sec_us = sec_def = sec_bond = sec_us_tech = 0
    _sec_holdings = (snap or {}).get(\"securities\", {}).get(\"holdings\", [])
    if _sec_holdings:
        for h in _sec_holdings:
            _t = h.get(\"ticker\", \"\")
            _v = h.get(\"shares\", 0) * h.get(\"price\", 30)
            if _t in _SEC_DEF:
                sec_def += _v
            elif _t in _SEC_BOND:
                sec_bond += _v
            elif _t in _SEC_US:
                sec_us += _v
                _SEC_TECH = {\"00646\": 0.32, \"009823\": 0.32, \"009824\": 1.0, \"00924\": 1.0}
                sec_us_tech = sec_us_tech + _v * _SEC_TECH.get(_t, 0.30)
            else:
                sec_tw += _v
        _sec_sum = sec_tw + sec_us + sec_def + sec_bond
        if _sec_sum > 0 and sec > 0 and abs(_sec_sum - sec) / sec > 0.02:
            _k = sec / _sec_sum
            sec_tw, sec_us, sec_def, sec_bond = (round(sec_tw * _k), round(sec_us * _k),
                                                 round(sec_def * _k), round(sec_bond * _k))
    else:
        sec_tw = sec
    ins_eq += _fj_eqv
    ins_bonds += _fj_bond
    tw = sec_tw + _fund_tw
    us = sec_us + ins_eq + _fund_us
    total = cash + ins + sec + funds
    def_v = sec_def + _fund_def
    bond_v = sec_bond + ins_bonds + _fund_bonds
    _fund_sum = _fund_tw + _fund_us + _fund_def + _fund_cash + _fund_bonds
    if _fund_sum > 0 and funds > 0 and abs(_fund_sum - funds) / funds > 0.001:
        _fk = funds / _fund_sum
        _fund_tw, _fund_us, _fund_def, _fund_bonds = (round(_fund_tw * _fk), round(_fund_us * _fk),
                                         round(_fund_def * _fk), round(_fund_bonds * _fk))
        tw = sec_tw + _fund_tw
        us = sec_us + ins_eq + _fund_us
        def_v = sec_def + _fund_def
        bond_v = sec_bond + ins_bonds + _fund_bonds
    c = total - (tw + us + def_v + bond_v)
    us_tech = _fund_us_tech + ins_tech + sec_us_tech
    us_non_tech = us - us_tech
    return {\"台股市值型成長\": tw, \"美股市值型成長\": us, \"防守型配息\": def_v, \"債券\": bond_v, \"現金/安全網\": c,
            \"美股市值型成長_科技\": round(us_tech), \"美股市值型成長_非科技\": round(us_non_tech),
            \"_meta\": {\"ins_eq\": ins_eq, \"fund_us\": _fund_us, \"fund_def\": _fund_def,
                      \"sec_tw\": sec_tw, \"sec_us\": sec_us, \"sec_def\": sec_def, \"sec_bond\": sec_bond,
                      \"us_tech\": round(us_tech), \"us_non_tech\": round(us_non_tech)}}
