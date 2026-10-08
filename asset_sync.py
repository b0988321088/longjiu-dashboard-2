#!/usr/bin/env python3
"""asset_sync.py — 欄位同步函數（P0-1 防呆）
更新 snapshot 資產時，自動同步所有「同義欄位」，避免漏改導致穿透/日報不一致。

用法：
    from asset_sync import update_asset, sync_snapshot_keys
    update_asset(snapshot, insurance=9891257, securities=2887310, funds=772694, cash=2914656)
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
# DB 路徑（單一來源）：負債落地寫入器 land_liabilities_db 與 CLI 共用。測試可覆寫此常數。
DB_PATH = BASE / "dragon_assets.db"
# 2026-10-08（PEND-20261006-02／CIO 複審 required_fix）：落地必填真值鍵的**單一來源**。
# 缺任一鍵一律 fail-closed 不寫（含 total_liabilities/total_assets：缺了會把 NULL 寫成「成功」）。
_LIAB_REQUIRED_KEYS = ("mortgage_yy", "mortgage_yydu", "mortgage_xz", "policy_loan",
                       "pledge_loan", "fund_pledge_loan", "mortgage_cathay",
                       "cc_liability", "total_liabilities", "total_assets")
# 最近一次落地結果（供 CLI 依實際結果輸出訊息，取代無條件「已完成」）。
_LAST_LAND_RESULT = None

# 同義欄位對照（key 群組，全部要同步）
SYNONYM_GROUPS = {
    # 保險總值
    "insurance_total": ["insurance_total", "insurance_current_value", "insurance"],
    # 證券總值（含 8/24 新增 securities_current_value）
    "securities_total": ["securities_total_market_value", "securities_total", "securities_market", "securities_current_value"],
    # 基金總值（5 個 key + 國泰基金市值 8/24 新增）
    "funds_total": ["fund_market", "fund_market_value", "funds_total", "fund_total_market_value", "funds"],
    "funds_cathay": ["funds_cathay", "funds_cathay_market_value"],
    # 總負債／不動產（2026-10-04 P0 假真值退路清除）：
    # sot_targets 的讀取層 accessor 直接沿用本表，避免「第二份同義鍵清單」。
    # 兩組皆為單一語意欄；不動產 34,017,063 原有多處 .get(key, 34017063) 假真值退路。
    "total_liabilities": ["total_liabilities"],
    "real_estate": ["real_estate_value", "real_estate"],
    # 現金總值（4 個 key）
    "cash_total": ["cash_total", "cash", "real_liquid_assets", "bank_assets_moneybook"],
    # 安聯 A+B
    "allianz_combined": ["allianz_combined", "allianz_ab_current_value", "allianz_ab"],
    # 安聯保單 A／B 個別（2026-09-23 INC-242 新增）
    # 血淚：A/B 各有 5 個同義鍵，先前只有 3 個在群組內 → update_data --allianz 只改到
    # allianz_a/b、allianz_a/b_funds、allianz_a/b_current_value，而
    # allianz_policy_a/b_value 與 top-level policy_a/b_total 留在舊值，
    # 差異分析「安聯保單A現值」因此顯示 4,986,867（真值 4,986,448）。
    "allianz_policy_a": ["allianz_a", "allianz_a_funds", "allianz_a_current_value",
                         "allianz_policy_a_value", "policy_a_total"],
    "allianz_policy_b": ["allianz_b", "allianz_b_funds", "allianz_b_current_value",
                         "allianz_policy_b_value", "policy_b_total"],
    # 第一金
    "firstjin_total": ["firstjin_fl65_current_value", "firstjin_current_value", "firstjin"],
}

def sync_snapshot_keys(snap: dict) -> dict:
    """根據主 key 值，同步所有同義欄位"""
    for master, keys in SYNONYM_GROUPS.items():
        val = snap.get(master)
        if val is None:
            # 從其他 key 找回
            for k in keys:
                if snap.get(k) is not None:
                    val = snap[k]
                    break
        if val is not None:
            for k in keys:
                snap[k] = val
    return snap

def update_asset(snap: dict, insurance=None, securities=None, funds=None, cash=None,
                 allianz_combined=None, firstjin=None) -> dict:
    """更新資產並自動同步同義欄位 + 重算總資產"""
    if insurance is not None:
        snap["insurance_total"] = insurance
    if securities is not None:
        snap["securities_total_market_value"] = securities
    if funds is not None:
        snap["fund_market"] = funds
    if cash is not None:
        snap["cash_total"] = cash
    if allianz_combined is not None:
        snap["allianz_combined"] = allianz_combined
    if firstjin is not None:
        snap["firstjin_fl65_current_value"] = firstjin

    snap = sync_snapshot_keys(snap)
    # 2026-09-23 INC-242b v3（CIO S5）：caller 未顯式指定 allianz_combined 時，
    # combined 一律由 A+B 派生，避免只更新 A／B 而 combined 停在舊合計。
    if allianz_combined is None:
        sync_allianz_combined(snap, verbose=False)

    # 總資產重算 = 保險 + 證券 + 基金 + 現金
    ins = snap.get("insurance_total", 0) or 0
    sec = snap.get("securities_total_market_value", 0) or 0
    fund = snap.get("fund_market", 0) or 0
    cashv = snap.get("cash_total", 0) or 0
    snap["total_assets"] = ins + sec + fund + cashv
    return snap

# ─────────────────────────────────────────────────────────────
# legacy 鍵登錄（2026-09-23 INC-242b v2／CIO F4）
# 語意不明、全 repo 無任何程式讀取的歷史鍵。為什麼「登錄」而不刪：
# ① 刪掉會失去「這裡曾有值」的線索；② 登錄後 safe_update.apply_changes 直接拒寫
# （更新不會再被靜默吸收，正是 INC-242／INC-242b 的失效模式）；
# ③ 明確標示「勿引用、勿當真值」，避免下一個人誤把它併入 SYNONYM_GROUPS（會把現值覆寫成帳面值）。
# 真正的成本鍵另有 policy_a_book_value／policy_b_book_value／allianz_ab_book_value（有讀者）。
# ─────────────────────────────────────────────────────────────
LEGACY_KEYS = {
    "allianz_a_value": "安聯A 帳面/歷史值（4,925,927），無讀者；canonical＝allianz_policy_a_value",
    "allianz_b_value": "安聯B 帳面/歷史值（2,627,478），無讀者；canonical＝allianz_policy_b_value",
    "allianz_current_value": "安聯舊彙總值（7,553,405），無讀者；canonical＝allianz_combined",
    "allianz_total": "安聯舊彙總值（8,028,248），無讀者；canonical＝allianz_combined",
}


def verify_synonyms(snap: dict) -> list:
    """檢查同義欄位是否一致，回傳不一致清單"""
    issues = []
    for master, keys in SYNONYM_GROUPS.items():
        vals = {k: snap.get(k) for k in keys}
        non_none = [v for v in vals.values() if v is not None]
        if non_none and len(set(non_none)) > 1:
            issues.append(f"{master}: {vals}")
    return issues


# ─────────────────────────────────────────────────────────────
# 跨群組不變式（2026-09-23 INC-242b v3／CIO S5）
# 同義群組只保證「群組內一致」，不保證群組之間自洽：安聯 combined（A+B 合計）與
# A／B 個別現值分屬不同群組 → 只改 A 不會動到 combined（反之亦然），
# verify_synonyms 也不會報（實測：只改 A → A+B 7,675,892 但 combined 停 7,652,217，
# 而 verify_synonyms 回報「無不一致」）。
# 真值方向：A／B＝安聯 App 逐張現值（primary）；combined＝派生（A+B）。
# ─────────────────────────────────────────────────────────────
def allianz_ab_from_units(snap: dict):
    """由 A／B 個別現值算出安聯合計（取不到回 None）。"""
    a = snap.get("allianz_policy_a_value")
    b = snap.get("allianz_policy_b_value")
    if all(isinstance(v, (int, float)) and v for v in (a, b)):
        return int(a) + int(b)
    return None


def sync_allianz_combined(snap: dict, verbose: bool = True) -> list:
    """把 allianz_combined 群組同步為 A+B（派生方向唯一）。回傳修正訊息清單。"""
    msgs = []
    total = allianz_ab_from_units(snap)
    if total is None:
        return msgs
    before = snap.get("allianz_combined")
    if isinstance(before, (int, float)) and before != total:
        msgs.append(f"安聯 combined 由 A+B 派生：{int(before):,} → {total:,}"
                    f"（A={int(snap['allianz_policy_a_value']):,} + B={int(snap['allianz_policy_b_value']):,}）")
    for k in SYNONYM_GROUPS.get("allianz_combined", []):
        snap[k] = total
    if verbose:
        for m in msgs:
            print(f"  🔁 {m}")
    return msgs


def verify_cross_group_invariants(snap: dict) -> list:
    """跨群組不變式檢查（回傳不一致清單；由呼叫端決定警告或硬擋）。"""
    issues = []
    total = allianz_ab_from_units(snap)
    if total is not None:
        for k in SYNONYM_GROUPS.get("allianz_combined", []):
            v = snap.get(k)
            if isinstance(v, (int, float)) and v != total:
                issues.append(f"安聯 A+B={total:,} 但 {k}={int(v):,}（跨群組不變式）")
    return issues


# ─────────────────────────────────────────────────────────────
# 負債模型（2026-09-13 INC-159 P2）：負債由組成明細推導，禁手寫
# 背景：total_liabilities / net_worth / cc_liability 原本全系統沒有任何計算來源
# （grep 全 repo 無 assignment）→ 每次靠手寫，導致 78,099 無法解釋的殘差、
# cc_liability 停在 28,101、DB 與 snapshot 卡片金額不一致。
# 口徑（使用者 2026-09-13 明示）：無循環利息、每月全額自動扣繳 →
#   信用卡負債 = credit_card dict 負值合計（當期未繳，將被全額扣掉）
# ─────────────────────────────────────────────────────────────
INCLUDE_PERSONAL_LOANS = False   # 2026-09-13 修正：personal_loans 是「借出去的錢」＝應收款（資產），**不是負債**
RECEIVABLES_IN_ASSETS = False    # 使用者 2026-09-13 裁示「不併」：應收款只列備忘，**不併入 total_assets**（維持 False，勿擅自改）
PERSONAL_LOAN_PAYDAY_DEFAULT = 5  # 每月 5 號還款（info 沒寫時用）


def personal_loan_remaining(info: dict, today=None, records: dict | None = None) -> float:
    """女友借款「剩餘本金」=（原始金額 − 月還款 × 已過還款期數）。

    例：300,000（7/25 起、每月 5 號還 6,000、5% 年息）→ 9/13 已過 8/5、9/5 兩期
    → 本金 288,000 ＋ 未收利息 2,500（月息 1,250 × 2 期）= **290,500**；
    12/5 最後一期後歸零（之後自動從應收款消失）。寫死 300,000 會一路錯到清償。

    2026-09-13 補（使用者明示「出款 300,000 含 5% 年利率、已還兩期都沒有算到利息」）：
    6,000 還款**不含利息**（且使用者裁示 6,000 維持全列收入、不拆帳）→ 利息按月累計為
    「未收利息」，12/5 清償時一併回收。月息 = 原始金額 × 年息 ÷ 12（單利）× 已過期數
    （利率欄讀 `snapshot.personal_loans.*.利率`，無此欄或 0% → 不計息）。
    """
    import datetime as _dt
    import re as _re
    amt = float(info.get("金額") or 0)
    pay = float(info.get("月還款") or 0)
    start = str(info.get("日期") or "")
    payday = int(_re.sub(r"\D", "", str(info.get("還款日") or "")) or PERSONAL_LOAN_PAYDAY_DEFAULT)
    if not (amt and pay and start):
        return amt
    try:
        d0 = _dt.date.fromisoformat(start)
    except Exception:
        return amt
    today = today or _dt.date.today()
    # 最後清償日（例：2026-12-05）→ 當天最後一期清掉餘額，之後歸零
    _final = str(info.get("最後清償") or "").strip()
    if _final:
        try:
            if today >= _dt.date.fromisoformat(_final):
                return 0.0
        except Exception:
            pass
    n, y, m = 0, d0.year, d0.month
    while (y, m) <= (today.year, today.month):
        try:
            pd = _dt.date(y, m, payday)
        except ValueError:
            pd = None
        if pd and d0 < pd <= today:
            n += 1
        m += 1
        if m > 12:
            m, y = 1, y + 1
    # 2026-10-01：實收紀錄優先 —— 使用者常提早於還款日入帳（8/5、9/1、10/1 實例），只按排程日
    #   推算會出現「儀表板已收 6,000、應收餘額還沒掉」的同一事實兩套數字。
    #   期數取 max(排程推算, 實收紀錄月份數)；未來月份不計。有實收無排程（提早入帳）也算。
    if records:
        _now_m = today.strftime("%Y-%m")
        _nrec = len({str(k)[:7] for k in records
                     if str(k)[:4].isdigit() and str(k)[:7] <= _now_m})
        n = max(n, _nrec)
    _principal = max(0.0, amt - pay * n)
    if _principal <= 0:
        return 0.0
    # 未收利息：月息 = 原始金額 × 年息 ÷ 12（單利，以原始金額計）× 已過期數
    _m = _re.search(r"([\d.]+)\s*%", str(info.get("利率") or ""))
    _rate = float(_m.group(1)) if _m else 0.0
    if _rate <= 0:
        return _principal
    return _principal + (amt * _rate / 100.0 / 12.0) * n


def cc_unpaid(snap: dict) -> int:
    """信用卡當期未繳 = credit_card dict 負值合計。"""
    cc = snap.get("credit_card") or {}
    if not isinstance(cc, dict):
        return 0
    return int(abs(sum(v for v in cc.values() if isinstance(v, (int, float)) and v < 0)))


def personal_loan_clearance(info: dict) -> float:
    """最後清償日應結清金額 = 本金餘（扣到清償日當期為止）＋ 累計未收利息。

    例：300,000／6,000／5% 年息、12/5 清償 → 5 期（8/5…12/5）→ 本金 270,000
    ＋利息 6,250 = **276,250**。純供備忘明細，不影響資產/負債口徑。
    """
    import datetime as _dt
    import re as _re
    amt = float(info.get("金額") or 0)
    pay = float(info.get("月還款") or 0)
    d0s, dfs = str(info.get("日期") or ""), str(info.get("最後清償") or "").strip()
    if not (amt and pay and d0s and dfs):
        return 0.0
    try:
        d0, df = _dt.date.fromisoformat(d0s), _dt.date.fromisoformat(dfs)
    except Exception:
        return 0.0
    payday = int(_re.sub(r"\D", "", str(info.get("還款日") or "")) or PERSONAL_LOAN_PAYDAY_DEFAULT)
    n, y, m = 0, d0.year, d0.month
    while (y, m) <= (df.year, df.month):
        try:
            pd = _dt.date(y, m, payday)
        except ValueError:
            pd = None
        if pd and d0 < pd <= df:
            n += 1
        m += 1
        if m > 12:
            m, y = 1, y + 1
    _m = _re.search(r"([\d.]+)\s*%", str(info.get("利率") or ""))
    _rate = float(_m.group(1)) if _m else 0.0
    return max(0.0, amt - pay * n) + (amt * _rate / 100.0 / 12.0) * n


def rebuild_receivables(snap: dict) -> dict:
    """借出去的錢＝應收款（資產），用剩餘本金追蹤（≠ 負債）。

    2026-09-13 修正：`personal_loans.女友借款 300,000` 是「我借給女友」的錢（她每月 5 號
    還 6,000、12/5 清償），對我方是**應收款**，先前誤列為負債（方向反了）。
    預設只做備忘（RECEIVABLES_IN_ASSETS=False）→ 不改變 total_assets 口徑；
    要併入總資產時把旗標改 True 即可（屆時 net_worth 會 +應收餘額）。
    """
    pl = snap.get("personal_loans") or {}
    _gf_rec = snap.get("girlfriend_repayment_records") or {}   # 2026-10-01：實收紀錄（提早入帳也認）
    detail = {}
    if isinstance(pl, dict):
        for _k, _v in pl.items():
            if isinstance(_v, dict):
                _rec = _gf_rec if "女友" in str(_k) else None
                _r = personal_loan_remaining(_v, records=_rec)
                if _r > 0:
                    detail[_k] = int(_r)
    total = sum(detail.values())
    _clr, _brk = {}, {}
    if isinstance(pl, dict):
        for _k, _v in pl.items():
            if not isinstance(_v, dict):
                continue
            if detail.get(_k):
                _rec = _gf_rec if "女友" in str(_k) else None
                _prin = int(personal_loan_remaining({**_v, "利率": "0%"}, records=_rec))   # 同函式、利率歸零 → 只取本金
                _brk[_k] = {"本金": _prin, "未收利息": detail[_k] - _prin,
                            "結清日": str(_v.get("最後清償") or ""),
                            "結清金額": int(personal_loan_clearance(_v))}
            _c = int(personal_loan_clearance(_v))
            if _c > 0:
                _clr[_k] = _c
    snap["receivables"] = detail
    snap["receivables_total"] = total
    snap["receivables_clearance"] = _clr
    snap["receivables_breakdown"] = _brk
    snap["receivables_note"] = (
        f"借出款（應收款，非負債）：{detail}（明細見 receivables_breakdown：本金＋未收利息）；"
        f"每月 5 號回收 6,000，最後清償日結清 {_clr}；"
        f"{'已併入 total_assets（使用者裁示）' if RECEIVABLES_IN_ASSETS else '使用者 2026-09-13 裁示「不併」：僅列備忘，未計入 total_assets'}")
    if RECEIVABLES_IN_ASSETS:
        _base = int(snap.get("total_assets") or 0) - int(snap.get("_assets_incl_receivables") or 0)
        snap["_assets_incl_receivables"] = total
        snap["total_assets"] = _base + total
    return snap


def land_liabilities_db(snap: dict, date: str | None = None, db_path=None,
                        dry_run: bool = False) -> dict:
    """把 snapshot 的負債真值落地到 DB：assets.total_liabilities ＋ liabilities 當日列（UPSERT）。

    2026-10-08 斷點修復（PEND-20261006-02，使用者授權）：
      真值日只更新 snapshot（rebuild_liabilities 回傳 dict），夜間產線（regenerate_report／
      four_source_sync）只寫 assets → liabilities 表長期停在最近一次真值日，四源閘門與信用卡
      一致性檢查隔日必然各報一條 ❌。本函式補回「真值日 → DB liabilities 落列」這最後一哩。

    契約：
      · 缺任一負債真值鍵 → fail-closed：**不寫入**、不編造 0（回傳 ok=False）。
      · 冪等：同日可重複執行（有列 UPDATE／無列 INSERT）。
      · 只碰 assets.total_liabilities・total_assets 與 liabilities 當日列，不動其他表。
      · 日期語意沿用既有實作＝「執行日」（與 update_data.py／asset_sync CLI 同口徑）。
    """
    import datetime as _dt
    import sqlite3
    _t = date or _dt.date.today().isoformat()
    # 必填鍵走模組常數（單一來源，含 total_liabilities/total_assets）→ 缺鍵 fail-closed，不用 `or 0` 編造。
    _miss = [k for k in _LIAB_REQUIRED_KEYS if snap.get(k) in (None, "")]
    if _miss:
        print("⚠️ [asset_sync] 負債真值缺鍵（" + "、".join(_miss)
              + "）→ DB liabilities **不寫入**（保留原值、不編造 0）")
        _r = {"ok": False, "date": _t, "action": "skip",
              "reason": "missing_keys", "missing": _miss}
        globals()["_LAST_LAND_RESULT"] = _r
        return _r
    # liabilities.pledge_loan 欄＝質押「總額」（券商＋基金）：asset_diff_monitor 以欄位加總
    # 求 total_liab，若只寫券商那筆會少 590 萬（與 update_data.py 同口徑）。
    _pledge_agg = int(snap.get("pledge_loan", 0) or 0) + int(snap.get("fund_pledge_loan", 0) or 0)
    _lrow = (snap.get("mortgage_yy"), snap.get("mortgage_yydu"), snap.get("mortgage_xz"),
             snap.get("policy_loan"), _pledge_agg, snap.get("cc_liability"),
             snap.get("total_liabilities"), snap.get("mortgage_cathay"))
    if dry_run:
        _r = {"ok": True, "date": _t, "action": "dry-run", "row": _lrow}
        globals()["_LAST_LAND_RESULT"] = _r
        return _r
    _a_n = 0
    _db = sqlite3.connect(str(db_path or DB_PATH))
    try:
        _a_n = _db.execute("UPDATE assets SET total_liabilities=?, total_assets=? WHERE date=?",
                           (snap.get("total_liabilities"), snap.get("total_assets"), _t)).rowcount or 0
        if _a_n == 0:
            # 該日 assets 列尚未存在（assets 由夜間產線 INSERT；真值日 09:00 落列時常還沒有）：
            # 不猜測其他欄位硬 INSERT（會造出殘缺列）→ 顯式告警，指明這是暫態、夜鏈會補齊。
            print(f"⚠️ [asset_sync] DB assets 無 {_t} 列（UPDATE 0 列）→ 本次僅落 liabilities 列；"
                  f"assets 列由夜間產線建立後三源才會一致（暫態、已顯式告警）")
        if _db.execute("SELECT COUNT(*) FROM liabilities WHERE date=?", (_t,)).fetchone()[0]:
            _db.execute("""UPDATE liabilities SET mortgage_yy=?, mortgage_yydu=?, mortgage_xz=?,
                policy_loan=?, pledge_loan=?, credit_card=?, total_liabilities=?, mortgage_cathay=?
                WHERE date=?""", _lrow + (_t,))
            _act = "update"
        else:
            _db.execute("""INSERT INTO liabilities (mortgage_yy, mortgage_yydu, mortgage_xz,
                policy_loan, pledge_loan, credit_card, total_liabilities, mortgage_cathay, date)
                VALUES (?,?,?,?,?,?,?,?,?)""", _lrow + (_t,))
            _act = "insert"
        _db.commit()
    finally:
        _db.close()
    print(f"✅ DB liabilities 已落地（{_t}／{_act}）：信用卡 {int(snap.get('cc_liability') or 0):,}"
          f"／總負債 {int(snap.get('total_liabilities') or 0):,}"
          + ("" if _a_n else "（assets 列待夜鏈建立）"))
    _r = {"ok": True, "date": _t, "action": _act, "assets_updated": bool(_a_n)}
    globals()["_LAST_LAND_RESULT"] = _r
    return _r


def rebuild_liabilities(snap: dict, land_db: bool = False) -> dict:
    """由明細重建 cc_liability / total_liabilities / net_worth（冪等）。

    2026-10-08（PEND-20261006-02 修復）：
      · 本函式維持「計算函式」語意，**預設不碰 DB**（land_db=False）——避免任何新 caller
        默默產生持久化副作用。
      · 需要正式落 DB 的流程必須**顯式**傳 land_db=True（真值日／套用類腳本、CLI
        `--rebuild-liabilities`）；缺鍵時仍由 land_liabilities_db() fail-closed 不寫。
    """
    unpaid = cc_unpaid(snap)
    snap["credit_card_pending"] = unpaid
    snap["cc_liability"] = unpaid

    # 2026-10-04 P0（CIO 六審 8 項之一／使用者裁示 A）：真值層寫入器改「缺鍵 → 不寫入 ＋ 大聲告警」，不編造。
    # 原以 `or 0` 補值會把 基金質押=0、基金質押利率=2.65%（編造）、total_liabilities 少 590 萬、
    # net_worth 由 −417.6 萬翻正為 +172.4 萬寫進 snapshot（假真值入庫，且與 DB 對不上）。
    _liab_miss = [k for k in ("policy_loan", "pledge_loan", "fund_pledge_loan")
                  if snap.get(k) in (None, "")]
    if snap.get("mortgage_balance") in (None, "") and snap.get("mortgage") in (None, ""):
        _liab_miss.append("mortgage_balance/mortgage")
    mort = snap.get("mortgage_balance") or snap.get("mortgage") or 0
    pol = snap.get("policy_loan") or 0
    ple = snap.get("pledge_loan") or 0
    # 2026-09-29：國泰基金質押借款（590萬@2.65%，9/29 10:57 入帳）。獨立欄位 —
    # 勿併入 pledge_loan（券商 100萬@3.92%），否則利率/月息會被混算成單一利率。
    fpl = snap.get("fund_pledge_loan") or 0
    _per_detail = {}
    if INCLUDE_PERSONAL_LOANS:
        pl = snap.get("personal_loans") or {}
        if isinstance(pl, dict):
            for _k, _v in pl.items():
                if isinstance(_v, dict):
                    _r = personal_loan_remaining(_v, records=(snap.get("girlfriend_repayment_records") or {}) if "女友" in str(_k) else None)
                    if _r > 0:
                        _per_detail[_k] = int(_r)
    per = sum(_per_detail.values())

    if _liab_miss:
        # 2026-10-04 P0：缺鍵 → 保留原 total_liabilities（不覆蓋、不編造）
        total = int(snap.get("total_liabilities") or 0)
        print("⚠️ [asset_sync] 負債真值缺鍵（" + "、".join(_liab_miss)
              + "）→ **不重建** total_liabilities／liabilities_build_up（保留原值、不編造）")
        globals()["_LAST_LIAB_MISS"] = list(_liab_miss)
    else:
        total = int(mort) + int(pol) + int(ple) + int(fpl) + unpaid + int(per)
        snap["total_liabilities"] = total
    # 2026-09-13 INC-167：利率鍵曾在重建時遺失 → pledge_status 讀到 0% → 質押「月省息」被算成 868（應 4,135）；
    # 這裡一律保留舊值／回填預設（保單 4%、券商 3.92%），禁止讓利率隨重建消失。
    _lb_prev = snap.get("liabilities_build_up") or {}
    _r_policy = float(_lb_prev.get("保單借貸利率") or snap.get("policy_pledge_rate") or 0.04)
    _r_broker = float(_lb_prev.get("券商質押利率") or snap.get("pledge_loan_rate") or 0.0392)
    _lb_new = {
        "房貸_含國泰": int(mort),
        "保單借貸": int(pol),
        "保單借貸利率": _r_policy,
        "券商質押": int(ple),
        "券商質押利率": _r_broker,
        "基金質押": int(fpl),
        # 2026-10-04 P0：原 `or 0.0265` 會在缺鍵時**編造** 2.65% 寫進真值層
        # → 改保留原值；兩者皆缺則為 None（明示缺真值，不再編造）
        "基金質押利率": (float(snap["fund_pledge_rate"])
                         if snap.get("fund_pledge_rate") not in (None, "")
                         else _lb_prev.get("基金質押利率")),
        "信用卡_當期未繳_全額扣繳": unpaid,
        "個人借款_借出款_列應收款非負債": _per_detail,
        "total": total,
        "note": ("2026-09-13 建立：負債改由明細推導（原為手寫值，曾出現 78,099 不明殘差）；"
                 "借給女友的錢＝應收款（見 snapshot.receivables），不計入負債；"
                 "2026-09-29 起「基金質押」（fund_pledge_loan，國泰 590萬@2.65%）與「券商質押」"
                 "分列不同利率欄，勿合併計算月息"),
    }
    # 2026-10-04 P0（使用者裁示 A）：缺鍵 → 不寫入（保留原值），並已在上面大聲告警
    if not _liab_miss:
        snap["liabilities_build_up"] = _lb_new
    snap["net_worth"] = int(snap.get("total_assets") or 0) - total
    # 負債率雙軌（2026-08-10 使用者裁示格式）：含不動產主顯示 / 不含不動產流動監控
    _ta = float(snap.get("total_assets") or 0)
    _re = float(snap.get("real_estate_value") or 0)
    snap["debt_ratio"] = round(total / (_ta + _re) * 100, 1) if (_ta + _re) else 0
    snap["debt_ratio_flow"] = round(total / _ta * 100, 1) if _ta else 0
    # 2026-10-08（PEND-20261006-02）：真值日／套用類腳本 → DB liabilities 落列（補回最後一哩）。
    # 缺鍵時 land_liabilities_db 自身 fail-closed（不寫入、不編造）；DB 失敗不得阻斷 snapshot 重建。
    if land_db:
        try:
            _lres = land_liabilities_db(snap)
            # 2026-10-08（CIO 複審 required_fix R4）：rebuild 與 land 的必填鍵集**不同**（rebuild 管推導
            # 所需鍵、land 管落地所需鍵）。若 rebuild 端過關但 land 端 fail-closed → snapshot 已前進而 DB
            # 未落地，此狀態**不得視為完成**，故以 ❌ 顯式標示（不 raise，避免卡死真值日流程）。
            if not _lres.get("ok"):
                print("❌ [asset_sync] 真值已重建但 DB liabilities **未落地**（"
                      + "、".join(_lres.get("missing") or []) + "）→ 不得視為完成，請補齊後重跑落地")
        except Exception as _e:
            print(f"❌ [asset_sync] DB liabilities 落地失敗（snapshot 已重建，不得視為完成）：{_e}")
    return snap

if __name__ == "__main__":
    import sys as _sys
    if "--rebuild-liabilities" in _sys.argv:
        # 唯一入口：由明細重建 cc_liability / total_liabilities / net_worth / 負債率雙軌，
        # 並同步 DB assets.total_liabilities + liabilities 表（避免 snapshot/DB 再度分岔）
        snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        snap = rebuild_receivables(snap)
        # 2026-10-08：CLI 是「明確要落 DB」的流程 → 顯式 land_db=True（下方共用同一實作）。
        snap = rebuild_liabilities(snap, land_db=True)
        # 2026-10-04 P0（CIO 六審／使用者裁示 A）：缺鍵 → 真值層**不寫入**（保留原檔），不編造
        _m6 = globals().get("_LAST_LIAB_MISS") or []
        if _m6:
            print("⚠️ [asset_sync] 負債真值缺鍵（" + "、".join(_m6)
                  + "）→ **不寫回** snapshot.json（保留原檔、不編造）")
        else:
            (BASE / "snapshot.json").write_text(
                json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        _land_ok = True
        try:
            if _m6:
                raise RuntimeError("負債真值缺鍵 → 略過 DB 寫入（保留原值；見上方告警）")
            # 2026-10-08（CIO 複審 required_fix）：訊息依**實際落地結果**輸出，不再無條件宣稱完成。
            _lr = globals().get("_LAST_LAND_RESULT")
            if not _lr or not _lr.get("ok"):
                raise RuntimeError(f"DB 未落地（{(_lr or {}).get('reason') or '無落地結果'}）")
            print(f"（DB liabilities 落地：{_lr.get('action')}"
                  + ("；assets 列待夜鏈建立" if not _lr.get("assets_updated") else "，assets 已同步") + "）")
        except Exception as _e:
            _land_ok = False
            print(f"❌ DB 同步失敗：{_e}")
        bu = snap.get("liabilities_build_up") or {}
        if not bu:
            print("⚠️ [asset_sync] 無 liabilities_build_up 可印（缺真值，未重建）")
        else:
            print(f"✅ 負債重建：房貸 {bu['房貸_含國泰']:,} + 保單 {bu['保單借貸']:,}"
                  f" + 券商質押 {bu['券商質押']:,} + 基金質押 {bu.get('基金質押', 0):,}"
                  f" + 信用卡 {bu['信用卡_當期未繳_全額扣繳']:,}"
                  f" = {snap['total_liabilities']:,}")
        if snap.get("receivables_total"):
            print(f"ℹ️ 應收款（借出款，非負債）：{snap['receivables']}"
                  f" 合計 {snap['receivables_total']:,}"
                  f"｜{'已併入總資產' if RECEIVABLES_IN_ASSETS else '僅列備忘、未計入總資產'}")
        print(f"   淨值 {snap['net_worth']:,}｜負債率 {snap['debt_ratio']}%（含不動產）"
              f"／{snap['debt_ratio_flow']}%（流動）")
        # 2026-10-08（CIO 複審 required_fix）：DB 未落地 → rc≠0（fail-closed），
        # 讓真值日流程／cron／稽核能用 return code 偵測，不必靠文字比對。
        if not _land_ok:
            print("❌ DB liabilities 未落地 → 真值日流程不得視為完成（exit 1，fail-closed）")
            _sys.exit(1)
        _sys.exit(0)
    # 自檢
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    issues = verify_synonyms(snap)
    if issues:
        print("❌ 同義欄位不一致：")
        for i in issues:
            print(f"  {i}")
    else:
        print("✅ 所有同義欄位一致")
    print(f"  總資產: {snap.get('total_assets'):,}")
