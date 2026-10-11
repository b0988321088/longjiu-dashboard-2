#!/usr/bin/env python3
"""決策自動閉環引擎 — 每日掃描，條件滿足自動 ✅

2026-10-11 修復（pending 只增不減根治）：
  ① 狀態口徑：2026-10-06 INC-284 已把 status 正規化為四態（pending_engine.STATUS_ENUM
     ＝ 待處理／已確認／已完成／關案）。本檔逾時條件原寫 `"待執行" in status` → 該字串
     全庫 0 筆 → 逾時歸檔與逾期警報**兩條路徑同時失效**（實測 87 筆會閉環 0 筆）。
     現改以四態判定，並以 due_date 為優先檢視點。
  ② 安全界線：**只自動歸檔「工程／治理類」逾期卡**；任何命中資產關鍵字（債券／保單／
     質押／標案／轉貸…）者即使逾期也只列警報，交由 CEO 裁示 —— 避免自動砍掉「等條件
     成立的資產決策」（例：美債 ladder 等標案定案）。
  ③ 歸檔而非刪除：閉環一律先寫入 pending_decisions_archive.json（含 cleanup_reason）
     才從正本移除，維持可追溯性。
"""
import hashlib, json, re, sys
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
DECISIONS = BASE / "pending_decisions.json"
ARCHIVE = BASE / "pending_decisions_archive.json"
SNAP = BASE / "snapshot.json"
NOTION_LOG = BASE / "notion_decision_logger.py"

STATUS_OPEN = ("待處理", "已確認")          # pending_engine.STATUS_ENUM 的「未結案」兩態
OVERDUE_LIMIT = {"待處理": 30, "已確認": 90}  # 無 due_date 者：逾 N 天視為逾期
ASSET_KW = ("債券", "美債", "標案", "資金", "質押", "保單", "房貸", "轉貸", "配息", "股",
            "配置", "再平衡", "美元曝險", "資產", "現金", "退休", "洲際W", "台股", "美股",
            "衛星", "第一金", "安聯", "薪資", "收入", "房產", "押標金")
# 2026-10-11（CIO RF4）：工程/治理類必須有**正向標記**才可自動歸檔。
#   舊版把「備份／歸檔／註解」等一般詞也算工程類 → 實測偽陰性：
#   『安排家族信託文件清單備份』『四家銀行授權書備份歸檔』會被誤判為工程類而自動歸檔。
#   現改為只認工程/治理專有詞，且**不得由「缺乏資產關鍵字」反推資產性**。
ENG_MARK = ("技術債", "守門", "閘門", "發布", "驗證器", "治理", "寫死", "硬編碼",
            "回歸", "測試", "死碼", "docstring", "AST", "producer", "隔離",
            "事件鏈", "審計", "顯示層", "CLI", "schema", "鏡像", "追溯",
            "dirty", "cron", "遮罩", "fallback", "重產")
# 2026-10-11（CIO RF8）：資安／高優先卡不得靜默自動歸檔 → 一律走警報，交 CEO
# 2026-10-12（CIO 二輪 RF-4）：P0/P1 改**詞邊界**比對。舊版純子字串會誤保護
#   『P10 驗證器』『MP0 測試』『P1X 回歸』（任何含 P1 字樣者永不清帳）。
PROTECT_TEXT = ("資安", "安全", "SECURITY")
_PROTECT_RE = re.compile(r"(?<![0-9A-Za-z])P[01](?![0-9A-Za-z])")


def _is_protected(body: str) -> bool:
    return any(k in body for k in PROTECT_TEXT) or bool(_PROTECT_RE.search(body))
# 2026-10-11（CIO RF6）：無 due_date 的卡過去既不歸檔也不提醒 → 永遠不老化
NO_DUE_ALERT_DAYS = 45

def load_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except:
        return []


def load_json_strict(p: Path, what: str):
    """2026-10-12（CIO 第二輪 blocking）：存在但不可解析 → raise（fail-closed）。

    原 load_json() 對不可解析輸入一律回 []，使 archive 的讀-改-寫在檔案損壞
    （部分寫入／尾端殘字）時被當成「空清單」，接著以「只剩本次新卡」覆寫整檔
    → 實測 108 筆 → 1 筆、靜默遺失 107 筆且無例外。凡本檔寫入路徑皆改用本函式。
    缺檔仍視為空清單（合法的首次建立情境）。
    """
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(
            f"{what} 存在但無法解析（疑似部分寫入／損壞）→ fail-closed，不覆寫任何檔案：{e}") from e
    if not isinstance(data, list):
        raise RuntimeError(f"{what} 型別非清單（{type(data).__name__}）→ fail-closed，不覆寫任何檔案")
    return data

def _atomic_write(p: Path, text: str) -> None:
    """原子寫入（tmp → JSON 驗證 → os.replace）。2026-10-11（CIO RF1/RF3）：
    正本 pending_decisions.json 原以 write_text 直接覆寫，中斷即永久遺失（21 筆保留卡
    僅存在此檔）。凡本檔寫入一律走此路徑。"""
    import os as _os
    _tmp = p.with_name(p.name + ".tmp")
    try:
        _tmp.write_text(text, encoding="utf-8")
        json.loads(_tmp.read_text(encoding="utf-8"))  # 讀回驗證（不合法即 raise，不動正本）
        _os.replace(str(_tmp), str(p))
    except Exception:
        # 2026-10-12（CIO 二輪 RF-2）：失敗時清掉暫存檔，否則 .tmp 殘檔會污染
        #   repo 根目錄與發布閘門（正本仍逐位元不變）。
        try:
            if _tmp.exists():
                _tmp.unlink()
        except Exception:
            pass
        raise


def save_json(p, data):
    _atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

def check_conditions(d, _all_decisions=()):
    """回傳 (auto_close: bool, reason: str)"""
    title = d.get("title", "")
    status = d.get("status", "")
    today = date.today()

    # ── 00983D方案B ──
    if "00983D" in title and "方案B" in title:
        snap = load_json(SNAP)
        for h in snap.get("securities", {}).get("holdings", []):
            if h["ticker"] == "00983D":
                current_shares = h["shares"]
                target_shares = 100000  # ~100萬/10元
                if current_shares >= target_shares * 0.9:
                    return True, f"00983D已達 {current_shares} 股（目標 {target_shares}）"
                break
        # 也檢查006208和00713是否增加了
        tw_added = False
        for h in snap.get("securities", {}).get("holdings", []):
            if h["ticker"] == "006208" and h["shares"] > 2000:
                tw_added = True
        if tw_added:
            return True, "006208已加碼"
        return False, ""

    # ── 國泰轉貸 ──
    if "國泰轉貸" in title:
        if today >= date(2026, 9, 25):
            snap = load_json(SNAP)
            old_liab = snap.get("mortgage_balance", 0)
            # 如果負債結構改變了，視為已完成
            if old_liab != 13159422:  # 原始值變了
                return True, "房貸結構已變更"
            return False, "9/25到期檢查"
        return False, ""

    # ── 築巢優利貸 ──
    if "築巢" in title or "台銀" in title:
        if today >= date(2026, 10, 1):
            return True, "10/1築巢優利貸生效日已到"
        return False, ""

    # ── 信貸套利：依賴二轉貸完成 ──
    if "信貸套利" in title:
        # 檢查國泰轉貸和築巢是否已完成（不在 pending 列表）
        other_titles = [x.get("title", "") for x in (_all_decisions or []) if x is not d]
        refinance_done = all(
            "轉貸" not in t and "築巢" not in t and "台銀" not in t
            for t in other_titles
        )
        if refinance_done and today >= date(2026, 10, 1):
            return True, "前序轉貸已完成，可啟動信貸套利"
        return False, ""

    # ── 其他：逾期自動歸檔（僅限工程／治理類，2026-10-11 修復；同日二修＝CIO RF4/RF8）──
    d_date = d.get("date", "")
    # 判定只用「標題＋標籤」（原含 detail 前 200 字 → 內文出現任一工程詞即誤判）
    body = str(title) + " " + str(d.get("tags", "") or "")
    if any(k in body for k in ASSET_KW):
        return False, ""                       # 資產保護（負面清單）
    if _is_protected(body):
        return False, ""                       # 資安／P0／P1 保護（CIO RF8／詞邊界 RF-4）
    is_asset = False
    is_eng = any(k in body for k in ENG_MARK)  # 必須正向命中工程標記
    try:
        dt = datetime.strptime(d_date, "%Y-%m-%d").date()
    except Exception:
        return False, ""
    if status not in STATUS_OPEN:
        return False, ""
    due = str(d.get("due_date") or "")
    if not due:
        # 2026-10-12（CIO 二輪 RF-3）：無 due_date 者一律 advisory-only（由 auto_close 的
        #   老化警報處理），**不進入自動歸檔分支**。舊版會被 OVERDUE_LIMIT 搶先歸檔，
        #   使「逾 45 天只警報」對任何工程卡皆不可達 → 需求與行為不一致。
        return False, ""
    if due >= today.isoformat():
        return False, ""                       # 檢視日未到 → 不判逾期、不歸檔
    days = (today - dt).days
    if status == "待處理" and days > OVERDUE_LIMIT["待處理"]:
        if is_asset or not is_eng:
            return False, ""                   # 資產類／無法歸類 → 只留警報，交 CEO 裁示
        return True, f"逾期 {days} 天未結案（工程/治理類），自動歸檔"
    if status == "已確認" and days > OVERDUE_LIMIT["已確認"]:
        if is_asset or not is_eng:
            return False, ""
        return True, f"已確認但逾期 {days} 天未結案（工程/治理類），自動歸檔"

    return False, ""

def auto_close():
    decisions = load_json_strict(DECISIONS, "pending_decisions.json")
    updated, archived_items = [], []
    closed = 0
    alerts = []
    today = date.today()

    for d in decisions:
        auto_close, reason = check_conditions(d, decisions)
        if auto_close:
            closed += 1
            # 更新 Notion
            title = d.get("title", "")
            try:
                import subprocess
                subprocess.run(
                    [sys.executable, str(NOTION_LOG), f"✅ {title}", f"自動閉環：{reason}", "", ""],
                    capture_output=True, text=True, timeout=10
                )
            except:
                pass
            # 2026-10-11：閉環一律先歸檔（寫入 archive）再從正本移除，維持可追溯性。
            _it = dict(d)
            _it["status"] = f"🗑 自動歸檔({today})：{reason}｜原狀態：{d.get('status', '')}"
            _it["cleanup_reason"] = f"decision_auto_close：{reason}"
            _it["updated_at"] = datetime.now().isoformat(timespec="seconds")
            archived_items.append(_it)
            print(f"  ✅ {title} → {reason}")
        else:
            # 逾期警報（2026-10-11：改以 due_date 判定。原條件 "等待/進行中" in status
            #   在四態正規化後永不存在 → 警報靜默失效）
            status = str(d.get("status", ""))
            if status in STATUS_OPEN:
                due = str(d.get("due_date") or "")
                if due:
                    try:
                        dd = datetime.strptime(due[:10], "%Y-%m-%d").date()
                        over = (today - dd).days
                        if over > 0:
                            alerts.append(
                                f"⚠️ {d.get('title', '')} 檢視日 {due[:10]} 已逾期 {over} 天（未結案）")
                    except Exception:
                        pass
                else:
                    # 2026-10-11（CIO RF6）：無檢視日的卡過去永遠不老化也不提醒。
                    # 改以 last_confirmed（無則建立日）計齡，超過門檻只列警報（advisory，不歸檔）。
                    _ref = str(d.get("last_confirmed") or d.get("date") or "")
                    try:
                        _rd = datetime.strptime(_ref[:10], "%Y-%m-%d").date()
                        _age = (today - _rd).days
                        if _age > NO_DUE_ALERT_DAYS:
                            alerts.append(
                                f"⚠️ {d.get('title', '')} 無檢視日、已 {_age} 天未更新"
                                f"（基準 {_ref[:10]}）→ 請補 due_date 或結案")
                    except Exception:
                        pass
            updated.append(d)

    # 歸檔（append）→ 驗證成功 → 才寫回正本
    # 2026-10-11 硬化：fail-closed。任一步失敗（暫存寫入／JSON 不合法／筆數不符／置換後複核
    # 失敗）一律 raise，且**不執行** save_json(DECISIONS) → 正本維持原樣，絕不資料遺失。
    if archived_items:
        _arc = load_json_strict(ARCHIVE, "pending_decisions_archive.json")
        # 冪等去重（2026-10-11 RF3）＋ 內容身分（2026-10-12 CIO 三輪 blocking）：
        #   舊版以 **title 單欄** 去重 → 若「不同卡剛好同名」，會被誤判成「已歸檔」
        #   而只自正本移除 → 該卡兩檔皆無、靜默遺失（實測 detail 永久消失）。
        #   現改以 (title, date, detail[:120]) 判定同一張卡：只有**確定同卡**才跳過寫入。
        # 2026-10-12（CIO 四輪 blocking / 三輪 RF）：卡別身分改為**全卡 sha256**（排除
        #   歸檔時會被改寫的三個欄位 status/cleanup_reason/updated_at）。
        #   先前用 title → 誤判「不同卡同名」為同卡；改用 detail[:120] → 仍會漏掉尾段差異。
        #   現為全欄位正規化比對：任何欄位差異即視為不同卡 → 一律寫入 archive。
        #   失效方向因此改為**可復原的重複**（寧可重複、不可漏寫）；真正同一張卡
        #   （含寫入中斷造成的兩檔並存）仍可冪等收斂。
        _VOLATILE = ("status", "cleanup_reason", "updated_at")

        def _card_key(x):
            _payload = {k: v for k, v in x.items() if k not in _VOLATILE}
            return hashlib.sha256(
                json.dumps(_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

        _seen = {_card_key(x) for x in _arc if isinstance(x, dict)}
        _new_items = [x for x in archived_items if _card_key(x) not in _seen]
        _before = len(_arc)
        _want = _before + len(_new_items)
        if not _new_items:
            print("  ℹ️ 歸檔項內容已存在於 archive（同一張卡）→ 僅自正本移除（冪等，不重複歸檔）")
        else:
            _arc.extend(_new_items)
            _atomic_write(ARCHIVE, json.dumps(_arc, ensure_ascii=False, indent=1))
        _after = load_json_strict(ARCHIVE, "pending_decisions_archive.json")
        if len(_after) != _want:
            raise RuntimeError("archive 置換後複核失敗｜正本未動")
        # 成對不變量（CIO 三輪 RF-3）：「加入 archive」與「自 pending 移除」必須是同一單位。
        #   機器可驗證：每個被自正本移除的卡，其內容必須確實存在於 archive；否則 raise。
        _after_keys = {_card_key(x) for x in _after if isinstance(x, dict)}
        _lost = [str(x.get("title", "")) for x in archived_items if _card_key(x) not in _after_keys]
        if _lost:
            raise RuntimeError(
                f"歸檔成對性驗證失敗：{_lost[:2]} 未落 archive → 正本未動（fail-closed）")

    save_json(DECISIONS, updated)

    print(f"\n📋 決策摘要：{len(decisions)} 筆，自動閉環 {closed} 筆，"
          f"歸檔 {len(archived_items)} 筆，進行中 {len(updated)} 筆")
    for a in alerts:
        print(f"  {a}")

    return closed, alerts

if __name__ == "__main__":
    print(f"🔍 決策自動閉環掃描 — {date.today()}")
    try:
        auto_close()
    except Exception as _e:
        # 2026-10-12（CIO 三輪 RF-4）：fail-closed 改動後，本檔由 morning_batch.py（08:05）呼叫。
        #   損壞時必須是「大聲告警」而非靜默：先輸出一行可讀告警，再以非零碼結束（不吞例外）。
        print(f"❌ 決策自動閉環掃描失敗（fail-closed：未寫入任何檔案，正本與 archive 皆未變更）：{_e}",
              file=sys.stderr)
        raise SystemExit(2)
