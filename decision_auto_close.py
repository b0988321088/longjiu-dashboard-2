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
import json, sys
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
ENG_KW = ("技術債", "守門", "閘門", "發布", "驗證器", "治理", "沙箱", "寫死", "硬編碼",
          "回歸", "測試", "死碼", "docstring", "註解", "AST", "producer", "隔離", "備份",
          "版控", "事件鏈", "審計", "顯示層", "事故", "CLI", "schema", "鏡像", "追溯",
          "dirty", "cron", "遮罩", "fallback", "重產", "repository", "repo")

def load_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except:
        return []

def save_json(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def check_conditions(d, _all_decisions=None):
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
        other_titles = [x.get("title", "") for x in _all_decisions if x is not d]
        refinance_done = all(
            "轉貸" not in t and "築巢" not in t and "台銀" not in t
            for t in other_titles
        )
        if refinance_done and today >= date(2026, 10, 1):
            return True, "前序轉貸已完成，可啟動信貸套利"
        return False, ""

    # ── 其他：逾期自動歸檔（僅限工程／治理類，2026-10-11 修復）──
    d_date = d.get("date", "")
    text = str(title) + str(d.get("tags", "")) + str(d.get("detail", ""))[:200]
    is_asset = any(k in text for k in ASSET_KW)
    is_eng = any(k in text for k in ENG_KW)
    try:
        dt = datetime.strptime(d_date, "%Y-%m-%d").date()
    except Exception:
        return False, ""
    if status not in STATUS_OPEN:
        return False, ""
    due = str(d.get("due_date") or "")
    if due and due >= today.isoformat():
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
    decisions = load_json(DECISIONS)
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
            updated.append(d)

    # 歸檔（append）→ 驗證成功 → 才寫回正本
    # 2026-10-11 硬化：fail-closed。任一步失敗（暫存寫入／JSON 不合法／筆數不符／置換後複核
    # 失敗）一律 raise，且**不執行** save_json(DECISIONS) → 正本維持原樣，絕不資料遺失。
    if archived_items:
        _arc = load_json(ARCHIVE)
        if not isinstance(_arc, list):
            _arc = []
        _before = len(_arc)
        _want = _before + len(archived_items)
        _arc.extend(archived_items)
        _tmp = ARCHIVE.with_name(ARCHIVE.name + ".tmp")
        _tmp.write_text(json.dumps(_arc, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            _chk = json.loads(_tmp.read_text(encoding="utf-8"))
        except Exception as _e:
            raise RuntimeError(f"archive 讀回驗證失敗（JSON 不合法）：{_e}｜正本未動") from _e
        if not isinstance(_chk, list) or len(_chk) != _want:
            raise RuntimeError(
                f"archive 筆數驗證失敗：預期 {_want}、實得 "
                f"{len(_chk) if isinstance(_chk, list) else 'n/a'}｜正本未動")
        _tmp.replace(ARCHIVE)
        _after = load_json(ARCHIVE)
        if not isinstance(_after, list) or len(_after) != _want:
            raise RuntimeError("archive 置換後複核失敗｜正本未動")

    save_json(DECISIONS, updated)

    print(f"\n📋 決策摘要：{len(decisions)} 筆，自動閉環 {closed} 筆，"
          f"歸檔 {len(archived_items)} 筆，進行中 {len(updated)} 筆")
    for a in alerts:
        print(f"  {a}")

    return closed, alerts

if __name__ == "__main__":
    print(f"🔍 決策自動閉環掃描 — {date.today()}")
    auto_close()
