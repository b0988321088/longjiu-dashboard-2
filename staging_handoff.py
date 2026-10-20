# -*- coding: utf-8 -*-
"""staging_handoff.py — 緊急應變隔夜交接（F1 第一階段：契約／驗證／狀態機）

角色分工（2026-10-20 使用者裁決 B）：
  21:30 應變班只把產出寫到 repo 外的 staging（本模組只管資料契約與驗證）；
  07:00 主產線是唯一發布出口。本模組**不** commit、**不** push、**不**寫入正式 repo。

旗標：LJ_EMERGENCY_HANDOFF = off（預設）| on | dry-run
路徑：LJ_HANDOFF_ROOT 可覆寫；預設 %LOCALAPPDATA%/hermes/staging/emergency
狀態：ABSENT / VALID / VALID_DRYRUN / INVALID / INVALID_DRYRUN / DISABLED_WITH_DATA
退出碼：0＝正常；12＝已發布但應變段無效（需人工）；13＝功能關閉卻存在當日資料（需人工）
兩者皆**不得**自動重試。

失敗碼（對外只透過 PUBLIC_TEXT 揭露，內部 reason 才含檔名／sha）：
  H01 未封存或交接單缺失　H02 格式／欄位不符　H03 日期不一致　H04 時間異常
  H05 檔案不齊　H06 內容驗證失敗　H07 內容為空或大小不符　H08 來源未經認可
  H09 批次衝突　H10 封存紀錄不一致（交接單事後被改）　H90 功能關閉但有當日資料
  H99 未分類
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = 1
LANE_DEFAULT = "emergency_us_2130"
LANE_WHITELIST = (LANE_DEFAULT,)
REQUIRED = ("analysis.json", "emergency_report_{date}.html", "emergency_taiex_report_{date}.html")
MANIFEST_NAME = "handoff.json"
STATUS_NAME = "status.jsonl"
ARCHIVE_DIRNAME = "_archive"
ARCHIVE_KEEP_DAYS = 30
WINDOW = (_dt.time(21, 20), _dt.time(23, 59))

PUBLIC_TEXT = {
    "H01": "應變資料不完整（H01）",
    "H02": "應變資料格式不符（H02）",
    "H03": "應變資料日期不一致（H03）",
    "H04": "應變資料時間異常（H04）",
    "H05": "應變資料不齊（H05）",
    "H06": "應變資料驗證失敗（H06）",
    "H07": "應變資料為空（H07）",
    "H08": "應變資料來源未經認可（H08）",
    "H09": "應變資料批次衝突（H09）",
    "H10": "應變資料封存紀錄不一致（H10）",
    "H90": "當日應變分析未注入（H90）",
    "H99": "應變資料驗證失敗（未分類）（H99）",
}

ABSENT = "ABSENT"
VALID = "VALID"
VALID_DRYRUN = "VALID_DRYRUN"
INVALID = "INVALID"
INVALID_DRYRUN = "INVALID_DRYRUN"
DISABLED_WITH_DATA = "DISABLED_WITH_DATA"

RC = {ABSENT: 0, VALID: 0, VALID_DRYRUN: 0, INVALID: 12, INVALID_DRYRUN: 0, DISABLED_WITH_DATA: 13}


@dataclass
class Result:
    """驗證／消費結果。public_text 可上公開頁；reasons 只留內部紀錄。"""

    state: str
    codes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    manifest: dict | None = None
    analysis: dict | None = None
    path: Path | None = None

    @property
    def rc(self) -> int:
        return RC.get(self.state, 99)

    def verdict(self) -> str:
        """給上層判斷的唯一語意（**不得**用 rc 或 ok 代替）。

        PASS／ABSENT／DRYRUN 可繼續正常發布流程；FAIL 必須硬擋應變段；
        DRYRUN_FAIL 表示 dry-run 期間驗證失敗（rc=0 但**不是**通過，不得據此啟用）；
        DISABLED_WITH_DATA 表示功能關閉卻有資料（不得回退讀 repo 舊 JSON）。
        """
        return {
            ABSENT: "ABSENT",
            VALID: "PASS",
            VALID_DRYRUN: "DRYRUN",
            INVALID: "FAIL",
            INVALID_DRYRUN: "DRYRUN_FAIL",
            DISABLED_WITH_DATA: "DISABLED_WITH_DATA",
        }.get(self.state, "UNKNOWN")

    def can_inject(self) -> bool:
        """只有 VALID 可注入分析（dry-run 一律不可）。"""
        return self.state == VALID and self.analysis is not None

    def verified(self) -> bool:
        """真正通過驗證（dry-run 通過也算，但那不是發布授權）。"""
        return self.state in (VALID, VALID_DRYRUN)

    def blocks_publish(self) -> bool:
        """是否必須硬擋應變段（僅 INVALID）。"""
        return self.state == INVALID

    @property
    def rc_ok(self) -> bool:
        return RC.get(self.state, 99) == 0

    def public(self, limit: int = 3) -> str:
        return public_text(self.codes, limit=limit)


# ── 環境 ────────────────────────────────────────────────────────────
def flag() -> str:
    """回傳 off|on|dry-run。未知值一律視為 off（fail-safe），由 reason 明示。"""
    v = (os.environ.get("LJ_EMERGENCY_HANDOFF") or "off").strip().lower()
    return v if v in ("off", "on", "dry-run") else "off"


def flag_raw() -> str:
    return (os.environ.get("LJ_EMERGENCY_HANDOFF") or "").strip().lower()


def root() -> Path:
    env = os.environ.get("LJ_HANDOFF_ROOT")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "hermes" / "staging" / "emergency"
    return Path.home() / "AppData" / "Local" / "hermes" / "staging" / "emergency"


def day_dir(date: str, root_dir: Path | None = None) -> Path:
    return (root_dir or root()) / str(date)


# ── 對外文字（公開面唯一來源）────────────────────────────────────────
def public_text(codes, limit: int = 3) -> str:
    """把失敗碼轉成公開文字：只查 PUBLIC_TEXT，永不拼接例外原文／檔名／路徑／sha。"""
    seen, out = set(), []
    for c in codes or []:
        key = c if c in PUBLIC_TEXT else "H99"
        if key in seen:
            continue
        seen.add(key)
        out.append(PUBLIC_TEXT[key])
    if not out:
        return ""
    if len(out) > limit:
        extra = len(out) - limit
        return "；".join(out[:limit]) + f"；及其他 {extra} 項"
    return "；".join(out)


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _naive(ts: _dt.datetime) -> _dt.datetime:
    """統一成 naive 本地時間（避免 offset-aware 與 naive 相減）。"""
    return ts.astimezone().replace(tzinfo=None) if ts.tzinfo is not None else ts


def _sha256_file(p: Path) -> str:
    return _sha256_bytes(p.read_bytes())


# ── 產生端 ──────────────────────────────────────────────────────────
def stage(date: str, files: dict, lane: str = LANE_DEFAULT, root_dir: Path | None = None) -> list[str]:
    """把產物寫進當日 staging 目錄（尚未封存）。只接受契約內的三個檔名。

    files: {檔名: str|bytes}
    安全邊界：檔名必須是單一檔名（不得含路徑分隔、磁碟代號、`.`／`..`），
    且解析後必須仍落在當日 staging 目錄內 —— 任何越界一律 ValueError，不寫任何檔。
    """
    d = day_dir(date, root_dir)
    allowed = {p.format(date=date) for p in REQUIRED}
    names = []
    for name in files:
        s = str(name)
        bad = (s != Path(s).name or "/" in s or "\\" in s or ":" in s
               or s in (".", "..") or Path(s).is_absolute() or s not in allowed)
        if bad:
            raise ValueError(f"契約外檔名（含路徑／穿越／未知名稱）：{s!r}")
        target = (d / s).resolve()
        try:
            target.relative_to(d.resolve())
        except ValueError as e:
            raise ValueError(f"越界寫入（解析後不在 staging 內）：{s!r}") from e
        names.append(s)
    d.mkdir(parents=True, exist_ok=True)
    written = []
    for name in names:
        payload = files[name]
        raw = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
        (d / name).write_bytes(raw)
        written.append(name)
    return written


def seal(date: str, lane: str = LANE_DEFAULT, generated_at: str | None = None,
         root_dir: Path | None = None) -> Result:
    """產生 handoff.json（不可變）＋ status.jsonl 第一筆 seal 紀錄。

    缺檔／空檔／時窗外 → 不寫交接單，回 INVALID（fail-closed，不留半成品交接單）。
    """
    d = day_dir(date, root_dir)
    if not d.is_dir():
        return Result(ABSENT, path=d, reasons=[f"staging 目錄不存在：{d}"])

    names = [p.format(date=date) for p in REQUIRED]
    codes, reasons, entries = [], [], []
    for name in names:
        f = d / name
        if not f.is_file():
            codes.append("H05")
            reasons.append(f"缺檔 {name}")
            continue
        size = f.stat().st_size
        if size <= 0:
            codes.append("H07")
            reasons.append(f"空檔 {name}")
            continue
        entries.append({"name": name, "sha256": _sha256_file(f), "bytes": size})

    if generated_at is None:
        try:
            aj = json.loads((d / names[0]).read_text(encoding="utf-8"))
            generated_at = str(aj.get("generated_at") or "")
        except Exception:  # noqa: BLE001
            generated_at = ""
    if not generated_at:
        codes.append("H04")
        reasons.append("analysis.json 缺 generated_at 且未提供")
    else:
        ok_win, why_win = _in_window(generated_at)
        if not ok_win:
            codes.append("H04")
            reasons.append(why_win)

    if lane not in LANE_WHITELIST:
        codes.append("H08")
        reasons.append(f"lane 不在白名單：{lane!r}")

    if codes:
        mark_status(date, "seal_rejected", codes=codes, reasons=reasons, root_dir=root_dir)
        return Result(INVALID, codes=codes, reasons=reasons, path=d)

    manifest = {
        "schema": SCHEMA,
        "date": str(date),
        "lane": lane,
        "generated_at": generated_at,
        "batch_complete": True,
        "files": sorted(entries, key=lambda e: e["name"]),
        "producer_host": os.environ.get("COMPUTERNAME") or "unknown",
        "sealed_at": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    raw = _manifest_bytes(manifest)
    (d / MANIFEST_NAME).write_bytes(raw)
    mark_status(date, "seal", manifest_sha256=_sha256_bytes(raw), codes=[], reasons=[], root_dir=root_dir)
    return Result(VALID, manifest=manifest, path=d)


def _manifest_bytes(manifest: dict) -> bytes:
    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _in_window(generated_at: str) -> tuple[bool, str]:
    try:
        ts = _dt.datetime.fromisoformat(str(generated_at))
    except Exception:  # noqa: BLE001
        return False, f"generated_at 無法解析：{generated_at!r}"
    t = ts.time()
    if not (WINDOW[0] <= t <= WINDOW[1]):
        return False, f"generated_at 落在時窗外（{ts.isoformat()}；允許 {WINDOW[0]}–{WINDOW[1]}）"
    return True, ""


# ── 狀態紀錄（append-only）───────────────────────────────────────────
def _status_path(date: str, root_dir: Path | None = None) -> Path:
    return day_dir(date, root_dir) / STATUS_NAME


def status_log(date: str, root_dir: Path | None = None) -> list[dict]:
    p = _status_path(date, root_dir)
    if not p.is_file():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:  # noqa: BLE001
            continue
    return out


def mark_status(date: str, action: str, codes=None, reasons=None, manifest_sha256: str | None = None,
                commit: str | None = None, note: str | None = None, published_at: str | None = None,
                root_dir: Path | None = None) -> dict:
    """追加一筆狀態（永不改寫既有行）。"""
    d = day_dir(date, root_dir)
    d.mkdir(parents=True, exist_ok=True)
    rec = {"ts": _dt.datetime.now().isoformat(timespec="seconds"), "date": str(date), "action": action,
           "codes": list(codes or []), "reasons": list(reasons or [])}
    if manifest_sha256:
        rec["manifest_sha256"] = manifest_sha256
    if commit:
        rec["commit"] = commit
    if note:
        rec["note"] = note
    if published_at:
        rec["published_at"] = published_at
    with _status_path(date, root_dir).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


# ── 驗證 ────────────────────────────────────────────────────────────
def verify(date: str, root_dir: Path | None = None) -> Result:
    """完整驗證交接單與三件套。不讀正式 repo、不看旗標。"""
    d = day_dir(date, root_dir)
    if not d.is_dir():
        return Result(ABSENT, path=d, reasons=["staging 目錄不存在（正常：無當日應變任務）"])

    mp = d / MANIFEST_NAME
    if not mp.is_file():
        return Result(INVALID, codes=["H01"], reasons=[f"目錄存在但缺交接單 {MANIFEST_NAME}"], path=d)
    raw = mp.read_bytes()
    try:
        m = json.loads(raw.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return Result(INVALID, codes=["H02"], reasons=[f"交接單非合法 JSON：{e}"], path=d)

    codes, reasons = [], []

    # 封存紀錄（manifest 不可變的依據）
    log = status_log(date, root_dir)
    seal_rec = next((r for r in reversed(log) if r.get("action") == "seal"), None)
    m_sha = _sha256_bytes(raw)
    if seal_rec is None:
        codes.append("H01")
        reasons.append("交接單無封存紀錄（未 seal 或 status.jsonl 遺失）")
    elif seal_rec.get("manifest_sha256") != m_sha:
        codes.append("H10")
        reasons.append(f"交接單與封存紀錄不一致（sealed={str(seal_rec.get('manifest_sha256'))[:12]} "
                       f"now={m_sha[:12]}）")

    if int(m.get("schema") or 0) != SCHEMA:
        codes.append("H02")
        reasons.append(f"schema 不符（{m.get('schema')!r}）")
    for k in ("date", "lane", "generated_at", "files"):
        if not m.get(k):
            codes.append("H02")
            reasons.append(f"缺欄位 {k}")
    if str(m.get("date")) != str(date):
        codes.append("H03")
        reasons.append(f"交接單日期 {m.get('date')!r} ≠ 目錄／要求日期 {date!r}")
    if str(m.get("lane")) not in LANE_WHITELIST:
        codes.append("H08")
        reasons.append(f"lane 不在白名單：{m.get('lane')!r}")
    ok_win, why_win = _in_window(str(m.get("generated_at") or ""))
    if not ok_win:
        codes.append("H04")
        reasons.append(why_win)
    if m.get("batch_complete") is not True:
        codes.append("H02")
        reasons.append("batch_complete 不為 true（不完整批次）")

    # 檔案清單：必須恰好三件套
    want = {p.format(date=date) for p in REQUIRED}
    got = {}
    for e in m.get("files") or []:
        if isinstance(e, dict) and e.get("name"):
            got[str(e["name"])] = e
    missing = sorted(want - set(got))
    extra = sorted(set(got) - want)
    if missing:
        codes.append("H05")
        reasons.append(f"交接單缺檔項：{missing}")
    if extra:
        codes.append("H02")
        reasons.append(f"交接單含契約外檔名：{extra}")

    analysis = None
    for name in sorted(want & set(got)):
        e = got[name]
        f = d / name
        if not f.is_file():
            codes.append("H05")
            reasons.append(f"檔案不存在：{name}")
            continue
        size = f.stat().st_size
        if size <= 0:
            codes.append("H07")
            reasons.append(f"檔案為空：{name}")
            continue
        try:
            exp_bytes = int(e.get("bytes"))
        except Exception:  # noqa: BLE001
            exp_bytes = -1
        if exp_bytes != size:
            codes.append("H07")
            reasons.append(f"大小不符：{name}（單 {exp_bytes}／實 {size}）")
        try:
            real = _sha256_file(f)
        except Exception as ex:  # noqa: BLE001
            codes.append("H06")
            reasons.append(f"無法讀取 {name}：{ex}")
            continue
        if str(e.get("sha256")) != real:
            codes.append("H06")
            reasons.append(f"SHA-256 不符：{name}（單 {str(e.get('sha256'))[:12]}／實 {real[:12]}）")

    # 批次衝突：同日已 published，卻出現不同 manifest
    for r in log:
        if r.get("action") == "published" and r.get("manifest_sha256") and r.get("manifest_sha256") != m_sha:
            codes.append("H09")
            reasons.append("同日已有發布紀錄但交接單不同（批次衝突，需人工）")
            break

    if not codes:
        try:
            analysis = json.loads((d / "analysis.json").read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            codes.append("H02")
            reasons.append(f"analysis.json 解析失敗：{e}")

    state = VALID if not codes else INVALID
    return Result(state, codes=_uniq(codes), reasons=reasons, manifest=m, analysis=analysis, path=d)


def _uniq(seq):
    out = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out


# ── 旗標／狀態機 ────────────────────────────────────────────────────
def consume(date: str, root_dir: Path | None = None) -> Result:
    """07:00 的唯一入口：旗標 × 驗證 → 六態之一。

    off            + 無目錄 → ABSENT（正常）
    off            + 有目錄 → DISABLED_WITH_DATA（rc=13；不得回退讀 repo 舊 JSON）
    dry-run        + 驗證過 → VALID_DRYRUN（rc=0；不注入）
    dry-run        + 驗證失敗 → INVALID_DRYRUN（rc=0；大聲 WARN，不阻擋發布）
    on             + 驗證過 → VALID（rc=0；可注入）
    on             + 驗證失敗 → INVALID（rc=12；應變段硬擋，日報其餘照發）
    """
    raw = flag_raw()
    mode = flag()
    d = day_dir(date, root_dir)
    had_dir = d.is_dir()          # 必須在寫任何狀態紀錄之前判定（mark_status 會建立目錄）
    if mode == "off" and raw not in ("", "off") and had_dir:
        # 未知值：維持 off（fail-safe），但要在狀態紀錄留下痕跡。
        # 僅在當日目錄已存在時記錄：否則 mark_status 會憑空建立目錄，
        # 反把「無資料」變成 DISABLED_WITH_DATA（rc=13 假警報）。
        mark_status(date, "flag_unknown", note=f"LJ_EMERGENCY_HANDOFF={raw!r} → 視為 off", root_dir=root_dir)

    if mode == "off":
        if not had_dir:
            return Result(ABSENT, path=d, reasons=["staging 目錄不存在（正常）"])
        return Result(DISABLED_WITH_DATA, codes=["H90"],
                      reasons=[f"功能關閉（off）但存在當日交接目錄 {d}；未注入，且不得改用 repo 舊 JSON"],
                      path=d)

    res = verify(date, root_dir)
    if mode == "dry-run":
        if res.state == VALID:
            mark_status(date, "validated_dry_run", codes=[], reasons=["dry-run 驗證通過（未注入）"],
                        root_dir=root_dir)
            return Result(VALID_DRYRUN, manifest=res.manifest, analysis=None, path=d,
                          reasons=["dry-run：驗證通過，未注入"])
        if res.state == ABSENT:
            return res
        mark_status(date, "invalid_dry_run", codes=res.codes, reasons=res.reasons, root_dir=root_dir)
        return Result(INVALID_DRYRUN, codes=res.codes, reasons=res.reasons, manifest=res.manifest, path=d)
    return res


# ── 07:00 發布閘門（F1 第三階段；呼叫端唯一決策入口）─────────────────
MODE_LEGACY = "legacy"   # 旗標關閉且無當日資料 → 完全沿用舊行為（回滾語意）
MODE_INJECT = "inject"   # 驗證通過 → 可複製／注入／發布
MODE_BLANK = "blank"     # 不注入（無資料／dry-run／功能關閉但有資料）
MODE_BLOCK = "block"     # 應變段硬擋（驗證失敗）


@dataclass
class Gate:
    """呼叫端只需要看這四個欄位；不要自行用 rc 或 state 重新推論動作。"""

    mode: str
    state: str
    public: str
    rc: int
    result: Result

    def may_copy(self) -> bool:
        """是否可把交接檔案複製進正式 repo（只有 inject 且 analysis 為真）。"""
        return self.mode == MODE_INJECT and self.result.can_inject()


def gate(date: str, root_dir: Path | None = None) -> Gate:
    """把 consume() 的六態收斂成呼叫端唯一需要的四種動作，並帶出退出碼。

    off    + 無當日資料 → legacy（**舊行為完全不變**；回滾＝旗標 off）
    off    + 有當日資料 → blank + rc13（不得回退讀 repo 舊 JSON）
    PASS                → inject（唯一可複製／注入／發布）
    ABSENT（on/dry-run）→ blank（第八章留空，不用舊檔冒充）
    FAIL                → block + rc12（應變段硬擋，日報其餘照發）
    dry-run（通過／失敗）→ blank + rc0（rc=0 不代表通過，失敗已記 invalid_dry_run）
    """
    res = consume(date, root_dir)
    v = res.verdict()
    if v == "PASS":
        return Gate(MODE_INJECT, res.state, "", 0, res)
    if v == "ABSENT":
        return Gate(MODE_LEGACY if flag() == "off" else MODE_BLANK, res.state, "", 0, res)
    if v in ("DRYRUN", "DRYRUN_FAIL"):
        return Gate(MODE_BLANK, res.state, res.public(), 0, res)
    if v == "FAIL":
        return Gate(MODE_BLOCK, res.state, res.public(), 12, res)
    if v == "DISABLED_WITH_DATA":
        return Gate(MODE_BLANK, res.state, res.public(), 13, res)
    return Gate(MODE_BLOCK, res.state, public_text(["H99"]), 12, res)


# ── 歸檔（滿 30 天且已發布）──────────────────────────────────────────
def archive(now: _dt.datetime | None = None, keep_days: int = ARCHIVE_KEEP_DAYS,
            root_dir: Path | None = None) -> tuple[list[str], list[tuple[str, str]]]:
    """把「已發布且超過保留期」的當日目錄移入 _archive/YYYY-MM/。

    pending／狀態不明／未發布者**不搬**（回傳 skipped 供人眼確認）。永不直接刪除。
    """
    base = root_dir or root()
    now = now or _dt.datetime.now()
    moved, skipped = [], []
    if not base.is_dir():
        return moved, skipped
    for d in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith("_")):
        log = status_log(d.name, base)
        pub = next((r for r in reversed(log) if r.get("action") == "published"), None)
        if pub is None:
            skipped.append((d.name, "無 published 紀錄（pending／狀態不明，不搬）"))
            continue
        try:
            ts = _dt.datetime.fromisoformat(str(pub.get("published_at") or pub.get("ts")))
        except Exception:  # noqa: BLE001
            skipped.append((d.name, "published 時間無法解析（不搬）"))
            continue
        ts = _naive(ts)
        age = (_naive(now) - ts).days
        if age < keep_days:
            skipped.append((d.name, f"已發布 {age} 天（未滿 {keep_days} 天）"))
            continue
        dest = base / ARCHIVE_DIRNAME / ts.strftime("%Y-%m")
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / d.name
        if target.exists():
            skipped.append((d.name, f"歸檔目的地已存在：{target}"))
            continue
        shutil.move(str(d), str(target))
        moved.append(d.name)
    return moved, skipped


def mark_published(date: str, commit: str | None = None, root_dir: Path | None = None) -> dict:
    """07:00 發布成功後呼叫：寫 published 紀錄（供歸檔與批次衝突判定）。"""
    mp = day_dir(date, root_dir) / MANIFEST_NAME
    sha = _sha256_bytes(mp.read_bytes()) if mp.is_file() else None
    return mark_status(date, "published", manifest_sha256=sha, commit=commit,
                       published_at=_dt.datetime.now().isoformat(timespec="seconds"), root_dir=root_dir)


def mark_pending(date: str, codes=None, reasons=None, root_dir: Path | None = None) -> dict:
    return mark_status(date, "pending", codes=codes, reasons=reasons, root_dir=root_dir)
