"""date_integrity.py — 日期仲裁唯一入口（INC-20261106-01）

**為什麼存在**：2026-11-06 一份 snapshot 內同時存在 11 個日期（11-02 ~ 11-06、09-14），
報告只印 `snapshot.date` 並稱它為「估值日」，導致「11-06 收盤估值」實際上是
11-05（證券）與 11-02/UNKNOWN（基金）的數字。詳見
`~/longjiu_drafts/incidents/INC-20261106-01/日期完整性治理_整合修正方案.md`。

**鐵則（不可違反）**：
  R1 一資產一權威來源，見 AUTHORITY；不得由其他日期推定。
  R2 `report_date` / `snapshot.date` / `report_base_date` 只表示「報告基準日」，
      **永不得**作為任何資產的估值日或市場資料日（列入 FORBIDDEN_SOURCES）。
  R3 UNKNOWN 不得被任何其他日期洗成 PASS；即使金額正確、四源加總一致。
  R4 缺日期 → UNKNOWN → BLOCKED；不得以預設值、抓取日、匯入日填充。
  R5 UNKNOWN 不得導致數值被刪除或歸零；數值照顯示，只取消「日期推定能力」。

狀態三態：PASS / DEGRADED / BLOCKED，合成取最差不平均。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

PASS, DEGRADED, BLOCKED, UNKNOWN = "PASS", "DEGRADED", "BLOCKED", "UNKNOWN"
_RANK = {PASS: 0, DEGRADED: 1, BLOCKED: 2}

# ── 權威來源表（使用者 2026-11-06 裁決）────────────────────────────────
# tier：core＝核心資產（被冒充會擋整份）；noncore＝落後只標示、不停發
AUTHORITY = {
    "tw_securities":   {"label": "台股", "path": "securities.price_date", "tolerance": 1, "tier": "core"},
    "funds":           {"label": "基金", "path": "fund_nav_dates", "tolerance": 1, "tier": "core"},
    "policy_firstjin": {"label": "第一金保單", "path": "firstjin_detail.last_update", "tolerance": 1, "tier": "noncore"},
    "policy_allianz":  {"label": "安聯保單", "path": "policy_valuation_dates", "tolerance": 1, "tier": "noncore"},
    "cash":            {"label": "現金", "path": "cash_source.date", "tolerance": 1, "tier": "core"},
    "market":          {"label": "市場行情", "path": "daily_analysis.date", "tolerance": 0, "tier": "core"},
    "us30y":           {"label": "US30Y", "path": "us30y_gate.as_of", "tolerance": 1, "tier": "noncore"},
}

# ── 禁用來源：這些欄位永遠不是估值日（R2）────────────────────────────
FORBIDDEN_SOURCES = {
    "snapshot.date": "報告基準日，非估值日",
    "report_base_date": "報告基準日，非估值日",
    "snapshot.generated_at": "產出時間，非資料日期",
    "snapshot.market_snapshot": "2026-09-14 遺留欄位，已退役、不得作為 fallback",
    "source_import_dates": "匯入日，非估值日",
}

TW_CLOSE_READY = (13, 45)  # 台股收盤資料可驗證時間（使用者傾向 13:45）


# ── 基礎工具 ────────────────────────────────────────────────────────
def parse_date(value):
    """從任意格式取出 YYYY-MM-DD；取不到回 None（不猜）。"""
    if value is None:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:len(datetime.now().strftime(fmt))], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _dig(data, dotted):
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def trading_days_between(older, newer):
    """兩個日期之間的交易日數（僅排除週末；國定/臨時停市日待交易日曆模組）。

    註：停市日尚未納入 → 本函式在長假期間會「高估」延遲，屬保守方向（寧可 BLOCKED）。
    """
    if older is None or newer is None or older >= newer:
        return 0
    n, cur = 0, older
    while cur < newer:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


# ── L2 財務層 ──────────────────────────────────────────────────────
def financial_layer(snapshot, asof=None):
    """逐資產判定估值日。回傳 {status, items[], reasons[]}。"""
    asof = asof or date.today()
    items, reasons = [], []
    worst = PASS

    for key, spec in AUTHORITY.items():
        if key in ("market", "us30y"):
            continue
        raw = _dig(snapshot, spec["path"])
        status, resolved = UNKNOWN, None

        if isinstance(raw, dict):
            # 多平台（如 fund_nav_dates 三平台）：逐一判定，取最差
            sub_status, sub_dates = PASS, {}
            for platform, val in raw.items():
                d = parse_date(val)
                sub_dates[platform] = d.isoformat() if d else None
                if d is None:
                    sub_status = BLOCKED
                else:
                    lag = trading_days_between(d, asof)
                    if lag > spec["tolerance"]:
                        # 裁決（2026-11-06）：落後＝標示，不是停發
                        sub_status = max([sub_status, DEGRADED], key=lambda s: _RANK[s])
            status, resolved = sub_status, sub_dates
            if any(v is None for v in sub_dates.values()):
                sub_status = max([sub_status, DEGRADED], key=lambda s: _RANK[s])
            status = sub_status
        else:
            d = parse_date(raw)
            if d is None:
                status, resolved = UNKNOWN, None
            else:
                lag = trading_days_between(d, asof)
                resolved = d.isoformat()
                status = PASS if lag == 0 else DEGRADED

        # R3 修正（裁決 2026-11-06）：UNKNOWN 不得被洗成 PASS，但也**不停發** →
        #   降級為 DEGRADED 並標示 UNKNOWN；只有「冒充成當日」才阻擋（見 publish_decision）。
        if status == UNKNOWN:
            status = DEGRADED
            reasons.append(f"{spec['label']}：估值日 UNKNOWN（{spec['path']} 無有效日期）→ 標示、不得推定")
        elif status == DEGRADED:
            reasons.append(f"{spec['label']}：估值日落後（{resolved}）→ 標示最後有效日期")

        items.append({
            "key": key, "label": spec["label"], "source": spec["path"],
            "value": resolved, "status": status, "tier": spec.get("tier", "core"),
            # 落後／UNKNOWN 本身不阻擋發布（裁決：改為標示），只有「冒充」才阻擋
            "publish_blocking": False,
            "display": _fmt_item(spec["label"], resolved, status),
        })
        worst = max([worst, status], key=lambda s: _RANK[s])

    return {"layer": "L2_financial", "status": worst, "items": items, "reasons": reasons}


def _fmt_item(label, resolved, status):
    if resolved is None:
        return f"{label}：資料日不明（UNKNOWN）"
    if isinstance(resolved, dict):
        parts = [f"{k.split('（')[0]} {v or 'UNKNOWN'}" for k, v in resolved.items()]
        return f"{label}：{'／'.join(parts)}"
    return f"{label}：{resolved}" + ("（落後）" if status == DEGRADED else "")


# ── L1 市場層 ──────────────────────────────────────────────────────
def market_layer(market_meta, report_date=None, now=None):
    """market_meta: {date, phase: 'close'|'intraday', source, source_updated_at}"""
    report_date = report_date or date.today()
    now = now or datetime.now()
    reasons = []
    status = PASS

    if not market_meta:
        return {"layer": "L1_market", "status": BLOCKED,
                "reasons": ["市場資料完全缺失 → 不得產生任何結論"], "items": []}

    d = parse_date(market_meta.get("date"))
    phase = (market_meta.get("phase") or "").lower()
    if d is None:
        return {"layer": "L1_market", "status": BLOCKED,
                "reasons": ["market_data_date 缺失 → BLOCKED"], "items": []}
    if phase not in ("close", "intraday"):
        return {"layer": "L1_market", "status": BLOCKED,
                "reasons": [f"market_data_phase 非法／缺失（{phase or '—'}）→ BLOCKED"], "items": []}

    lag = trading_days_between(d, report_date)

    # 台股：13:45 前不得自稱 close
    if phase == "close" and d == now.date() and (now.hour, now.minute) < TW_CLOSE_READY:
        status = BLOCKED
        reasons.append(f"宣稱 close 但現在 {now.strftime('%H:%M')} 早於收盤可驗證時間 "
                       f"{TW_CLOSE_READY[0]:02d}:{TW_CLOSE_READY[1]:02d} → 盤中冒充收盤")
    elif phase == "intraday":
        status = DEGRADED
        reasons.append("盤中值：僅得標示「盤中」，禁止出現在「收盤」語境")

    if lag > 0:
        if lag >= 2:
            status = BLOCKED
            reasons.append(f"市場資料落後 {lag} 個交易日（≥2）→ BLOCKED")
        elif status == PASS:
            status = DEGRADED
            reasons.append(f"市場資料落後 {lag} 個交易日 → DEGRADED（僅可使用，不得宣稱當日）")

    return {"layer": "L1_market", "status": status,
            "items": [{"date": d.isoformat(), "phase": phase,
                       "label": "盤中" if phase == "intraday" else "收盤"}],
            "reasons": reasons}


# ── L3 文字層 ──────────────────────────────────────────────────────
def narrative_layer(texts, report_date, value_pairs=None, unsourced=None,
                    require_content_date=True):
    """L3 內容日期層。

    texts: [{
        'content_date': 'YYYY-MM-DD',      # 必要：內容所述日期（producer 提供）
        'sections': [{'heading': str, 'date': 'YYYY-MM-DD', 'text': str}],  # 選用：混合日期
        'text': str, 'contains_today_word': bool,
        'narrative_date': 舊欄位（僅相容，不得由 generated_at 產生）
    }]

    規則（使用者 2026-11-06 裁決③）：
    · 缺 content_date → BLOCKED（generated_at 只能證明產生時間，不得替代內容日期）
    · content_date ≠ report_date 且未標記〔歷史：DATE〕→ BLOCKED
    · 章節混合不同日期 → 逐段檢查；該段日期缺漏 → BLOCKED
    · 指向前一交易日卻用「今日」字樣 → BLOCKED
    """
    reasons, status, segments = [], PASS, []
    for i, t in enumerate(texts or []):
        body = t.get("text") or ""
        cd = parse_date(t.get("content_date"))
        legacy = parse_date(t.get("narrative_date"))
        seg_ok, seg_reason = True, ""

        if require_content_date and not cd:
            if t.get("date_from_generated_at"):
                # 冒充：把生成時間當內容日期 → 這一段不可信，且屬「錯誤冒充」→ BLOCKED
                status = BLOCKED
                seg_ok, seg_reason = False, "以 generated_at 冒充內容日期"
                reasons.append(f"第 {i+1} 段：以 generated_at 冒充內容日期（禁止）")
            else:
                # 缺日期 ≠ 冒充：該段標示資料不足、不作為當日結論；其餘段落照發
                status = max([status, DEGRADED], key=lambda x: _RANK[x])
                seg_ok, seg_reason = False, "內容日期未提供（資料不足，不作為當日結論）"
                reasons.append(f"第 {i+1} 段：內容日期未提供 → 該段標示資料不足，不拖垮整份")

        eff = cd or legacy
        if eff and eff != report_date and "〔歷史：" not in body and "(歷史" not in body:
            status = BLOCKED
            reasons.append(f"第 {i+1} 段：敘述日 {eff} ≠ 報告日 {report_date}，且未標記〔歷史：{eff}〕")
        if t.get("contains_today_word") and eff and eff != report_date:
            status = BLOCKED
            reasons.append(f"第 {i+1} 段：指向前一交易日卻使用「今日」字樣")

        # 同章節混合多日期 → 逐段標記
        for s in t.get("sections") or []:
            sd = parse_date(s.get("date"))
            head = s.get("heading") or "未命名章節"
            stext = s.get("text") or ""
            if not sd:
                status = max([status, DEGRADED], key=lambda x: _RANK[x])
                seg_ok = False
                seg_reason = f"章節「{head}」未提供日期（該段不採用）"
                reasons.append(f"章節「{head}」未提供日期 → 該段標示資料不足")
            elif sd != report_date and "〔歷史：" not in stext and "(歷史" not in stext:
                status = BLOCKED
                reasons.append(f"章節「{head}」為 {sd} 資料，未標記〔歷史：{sd}〕")
        segments.append({"index": i + 1, "publishable": seg_ok, "reason": seg_reason})

    # T8：同一標籤出現兩個不同數值
    for p in value_pairs or []:
        vals = [str(v).strip() for v in (p.get("values") or []) if str(v).strip()]
        if len(set(vals)) > 1:
            status = BLOCKED
            reasons.append(f"同區塊雙值：{p.get('label')} 同時出現 {'／'.join(sorted(set(vals)))}")

    # T9：無來源數字（不得補造）
    for u in unsourced or []:
        if not u.get("source"):
            status = BLOCKED
            reasons.append(f"無來源數字：{u.get('label')} {u.get('value')}（不得補造）")

    return {"layer": "L3_narrative", "status": status, "reasons": reasons,
            "segments": segments, "suppressed": sum(1 for x in segments if not x["publishable"])}


HIST_MARK = "〔歷史：{d}〕"


def stamp_history(sections, report_date):
    """producer 用：把非當日章節自動加註〔歷史：YYYY-MM-DD〕（不改數字、不改文意）。"""
    out = []
    for s in sections or []:
        sd = parse_date(s.get("date"))
        text = s.get("text") or ""
        if sd and sd != report_date and "〔歷史：" not in text:
            text = HIST_MARK.format(d=sd) + text
        out.append({**s, "text": text})
    return out


def report_base(snap):
    """報告基準日（僅供標題／報告期間）。R2：不得用於任何資產估值日。"""
    s = snap if isinstance(snap, dict) else {}
    return str(s.get("report_base_date") or s.get("date") or "")[:10] or "UNKNOWN"


def authority_date(snap, key):
    """單一資產的權威日期；缺 → 'UNKNOWN'（R4：不推定、不補造）。"""
    spec = AUTHORITY.get(key)
    if not spec:
        return "UNKNOWN"
    raw = _dig(snap if isinstance(snap, dict) else {}, spec["path"])
    if isinstance(raw, dict):
        ds = [d for d in (parse_date(v) for v in raw.values()) if d]
        return max(ds).isoformat() if ds else "UNKNOWN"
    d = parse_date(raw)
    return d.isoformat() if d else "UNKNOWN"


# ── 合成 ───────────────────────────────────────────────────────────
def overall(*layers):
    """取最差不平均（使用者：不得平均）。"""
    layers = [l for l in layers if l]
    status = PASS
    for l in layers:
        status = max([status, l["status"]], key=lambda s: _RANK[s])
    return {
        "status": status,
        "layers": {l["layer"]: l["status"] for l in layers},
        "reasons": [r for l in layers for r in l.get("reasons", [])],
        "market_conclusion_allowed": status == PASS,
        "financial_usable": all(l["status"] != BLOCKED for l in layers if l["layer"] == "L2_financial"),
    }


def fund_dual_write_check(prev_funds, cur_funds, prev_nav_dates, cur_nav_dates):
    """基金金額與 NAV 估值日必須在同一筆真值更新中雙寫（使用者 2026-11-06 裁決①）。

    2026-11-06 實證：11-04 → 11-05 金額 12,568,172 → 12,684,574（已前進），
    但 fund_nav_dates 三平台仍停在 11-02（未同步）→ 金額與日期脫鉤，是本次事故成因。
    金額變動而日期未變 → BLOCKED（日期不可信，不得靠金額正確放行）。
    """
    amount_changed = float(cur_funds or 0) != float(prev_funds or 0)
    dates_changed = (cur_nav_dates or {}) != (prev_nav_dates or {})
    if amount_changed and not dates_changed:
        return {"status": BLOCKED,
                "reasons": ["基金金額已更新但 fund_nav_dates 未同步 → 日期脫鉤，估值日不可信"]}
    return {"status": PASS, "reasons": []}


def assert_no_forbidden_sources(used_sources):
    """R2 執行點：任何程式以禁用來源充當日期 → 直接拋錯（fail-closed）。"""
    bad = [s for s in used_sources if s in FORBIDDEN_SOURCES]
    if bad:
        raise RuntimeError("禁用日期來源被當成資料日期：" +
                           "；".join(f"{b}（{FORBIDDEN_SOURCES[b]}）" for b in bad))


def check(snapshot, market_meta=None, narratives=None, report_date=None, now=None):
    """單一入口：回傳完整判定（供日報、asset_diff、驗證器共用）。"""
    report_date = parse_date(report_date) or date.today()
    l1 = market_layer(market_meta, report_date, now)
    l2 = financial_layer(snapshot, report_date)
    l3 = narrative_layer(narratives, report_date)
    return {**overall(l1, l2, l3), "detail": {"L1": l1, "L2": l2, "L3": l3}}


def publish_decision(verdict, claims=None, snapshot=None):
    """發布決策：最新資料優先、落後標示、問題局部隔離、核心冒充才整份阻擋。

    claims: [{"asset": "funds", "claimed": "2026-11-06"}] —— 報告「宣稱」的估值日。
            宣稱 ≠ 權威日期 = 冒充，核心資產直接阻擋。

    回傳 publish：True 可發布（可能 DEGRADED，但必須標示）；False 阻擋整份。
    """
    det = (verdict or {}).get("detail", {})
    l1, l2, l3 = det.get("L1") or {}, det.get("L2") or {}, det.get("L3") or {}
    blocking, labels, isolated = [], [], []

    # L1：盤中冒充收盤／過期當今日 → 關鍵市場資訊錯誤陳述 → 整份阻擋
    if l1.get("status") == BLOCKED:
        blocking.append("L1 市場：盤中冒充收盤或落後行情被當成當日（關鍵市場資訊錯誤陳述）")

    # L3：以 generated_at／前一日資料冒充當日 → 整份阻擋
    if l3.get("status") == BLOCKED:
        blocking.append("L3 敘述：內容以生成時間或前一日資料冒充當日")

    # L3 段落：缺日期 → 只隔離該段，不拖垮整份
    for seg in l3.get("segments") or []:
        if not seg.get("publishable"):
            isolated.append(f"第 {seg.get('index')} 段不採用：{seg.get('reason')}")

    # L2：落後／UNKNOWN 一律不阻擋，但必須逐項標示（含核心與非核心）
    for it in l2.get("items") or []:
        labels.append(f"{it.get('label')}：{it.get('value') or 'UNKNOWN'}"
                      f"（{'核心' if it.get('tier') == 'core' else '非核心'}／{it.get('status')}）")

    # 冒充檢查：報告宣稱的估值日必須等於權威日期
    for c in claims or []:
        key, claimed = c.get("asset"), parse_date(c.get("claimed"))
        spec = AUTHORITY.get(key)
        if not spec or not claimed:
            continue
        auth = authority_date(snapshot or {}, key)
        if auth == "UNKNOWN":
            blocking.append(f"{spec['label']}：宣稱估值日 {claimed} 但權威日期 UNKNOWN（不得聲稱已知）")
        elif claimed.isoformat() != auth:
            blocking.append(f"{spec['label']}：宣稱估值日 {claimed} ≠ 權威日期 {auth}")

    return {
        "publish": not blocking,
        "status": (verdict or {}).get("status"),
        "blocking": blocking,
        "labels": labels,
        "isolated": isolated,
        "requires_labels": bool(labels) or bool(isolated),
    }


# ── 產線接線（第二階段；使用者 2026-11-06 批准）────────────────────────
BASE_DIR = Path(__file__).resolve().parent


def _infer_phase(da_path: Path, report_date: date, now: datetime):
    """由 daily_analysis.json 的 mtime 推斷 phase（不猜數值，只判類型）。"""
    try:
        mtime = datetime.fromtimestamp(da_path.stat().st_mtime)
    except OSError:
        return None
    if mtime.date() != report_date:
        return "close"          # 舊檔：視為前一交易日收盤（由 market_layer 判落後）
    return "intraday" if (now.hour, now.minute) < TW_CLOSE_READY else "close"


def load_gate_inputs(base=None, now=None):
    """從既有檔案組出 check() 的輸入。缺檔一律回 None（→ BLOCKED，不補造）。"""
    base = Path(base or BASE_DIR)
    now = now or datetime.now()
    report_date = date.today()

    snap = {}
    try:
        snap = json.loads((base / "snapshot.json").read_text(encoding="utf-8"))
    except Exception:
        snap = {}

    da_path = base / "daily_analysis.json"
    market_meta = None
    if da_path.exists():
        try:
            da = json.loads(da_path.read_text(encoding="utf-8"))
            market_meta = {
                "date": da.get("date"),
                "phase": _infer_phase(da_path, report_date, now),
                "source": "daily_analysis.json",
                "source_updated_at": datetime.fromtimestamp(da_path.stat().st_mtime).isoformat(),
            }
        except Exception:
            market_meta = None

    narratives = []
    em_path = base / "data" / "emergency_llm_analysis.json"
    if em_path.exists():
        try:
            em = json.loads(em_path.read_text(encoding="utf-8"))
            body = str(em.get("full_report") or "")
            narratives.append({
                "text": body,
                # 只認 producer 明確提供的 content_date；generated_at 僅記錄、不得當日期
                "content_date": em.get("content_date"),
                "sections": em.get("sections") or [],
                "contains_today_word": "今日" in body,
                "generated_at": em.get("generated_at"),  # 僅供追溯，不參與判定
            })
        except Exception:
            pass

    return snap, market_meta, narratives, report_date, now


def pipeline_gate(base=None, now=None):
    """產線用：回傳 check() 結果，並把 DIS 狀態落檔供首頁／日報共用。

    **不 commit、不 push、不刪任何原始資料**。BLOCKED 時呼叫端必須擋下發布。
    """
    snap, market_meta, narratives, report_date, now = load_gate_inputs(base, now)
    verdict = check(snap, market_meta, narratives, report_date, now)
    verdict["report_base_date"] = report_date.isoformat()
    try:
        write_dis_status(verdict, base=base, report_date=report_date)
    except Exception as exc:  # 落檔失敗不得靜默，但也不得阻斷產物生成
        print(f"[DATE-GATE][WARN] DIS 落檔失敗：{exc}")
    return verdict


def write_dis_status(verdict, base=None, report_date=None):
    """寫 data/dis_status_{date}.json（首頁與日報共用同一份，禁止各自計算）。"""
    base = Path(base or BASE_DIR)
    rd = report_date or date.today()
    out = base / "data" / f"dis_status_{rd.isoformat()}.json"
    payload = {
        "report_base_date": rd.isoformat(),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": verdict.get("status"),
        "layers": verdict.get("layers"),
        "reasons": verdict.get("reasons", []),
        "market_conclusion_allowed": verdict.get("market_conclusion_allowed"),
        "items": (verdict.get("detail", {}).get("L2") or {}).get("items", []),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def format_gate_lines(verdict, max_reasons=6):
    """產線輸出用：一行狀態 + 逐層原因。"""
    lines = [f"[DATE-GATE] {verdict.get('status')} "
             f"（L1={verdict['layers'].get('L1_market')} / "
             f"L2={verdict['layers'].get('L2_financial')} / "
             f"L3={verdict['layers'].get('L3_narrative')}）"]
    for it in (verdict.get("detail", {}).get("L2") or {}).get("items", []):
        lines.append(f"    · {it['display']}")
    for r in (verdict.get("reasons") or [])[:max_reasons]:
        lines.append(f"    ⛔ {r}")
    if verdict.get("status") == BLOCKED:
        lines.append("    ⛔ BLOCKED：禁止發布、禁止市場因果結論（財務數字照出，估值日各自標示）")
    return lines
