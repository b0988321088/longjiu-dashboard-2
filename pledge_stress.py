"""質押壓力情境計算（單一實作，供 snapshot 更新器／bbd 季檢／緊急應變共用）。

口徑（2026-10-30 使用者裁定；2026-11-03 維持率級距收斂）：
- 借款一律採「實撥」金額（5,900,000），不得用表定 540 萬。
- 池市值採 snapshot.cathay_pledge_0911.擔保池（含資料日），不得手寫。
- **兩套方向相反的指標，不得混用**：
    維持率% ＝ 池市值 ÷ 借款 × 100（銀行簡訊用這個）
    LTV%   ＝ 借款 ÷ 池市值 × 100（內部 thresholds 用這個）
- 銀行級距（使用者 2026-11-02 確認）：通知 160%（LTV 62.5%）／追繳 140%（LTV 71.4%）。
  維持率計算公式、補繳期限仍待銀行書面（E1）。
- 內部停止線：LTV 53%（＝維持率 188.7%），屬內部政策、非銀行線，比銀行通知線更早觸發。
- ⛔ 舊假設（2026-11-03 superseded）：LTV 70% 追繳／130% 追繳 皆不得作為現行門檻。
- 單池：三檔按市值比例分配借款（假設；銀行認列成數／單池分池規則未取得）→ 任一池單獨下跌時的該池 LTV 與同期加總 LTV 必須分開呈現。
"""

from __future__ import annotations

from pathlib import Path
import json

LTV_INTERNAL_STOP = 0.53   # 內部停止線（LTV）
MAINT_WARN = 1.60          # 銀行通知線（維持率）
MAINT_CALL = 1.40          # 銀行追繳線（維持率）
LTV_LINE_LEGACY = 0.70     # ⛔ 舊保守假設，僅供對照，不得作為門檻
DROPS = (0.20, 0.30, 0.35)


def _f(x: float) -> str:
    return f"{x:,.0f}"


def overall(loan: float, pool: float) -> dict:
    """整體（三檔加總）壓力情境。維持率與 LTV 並列，級距以銀行 160/140 為準。"""
    if loan <= 0 or pool <= 0:
        return {}
    ltv_now = loan / pool * 100
    maint_now = pool / loan * 100
    out = {
        "現況": f"LTV {ltv_now:.2f}%（維持率 {maint_now:.1f}%）｜內部綠燈 ≤53%",
        "定義": "維持率%＝池市值÷借款×100（銀行簡訊）；LTV%＝借款÷池市值×100（內部）。兩者互為倒數，不得混用。",
        "銀行級距": (f"通知 {MAINT_WARN*100:.0f}%（LTV {100/MAINT_WARN:.1f}%）／"
                     f"追繳 {MAINT_CALL*100:.0f}%（LTV {100/MAINT_CALL:.1f}%）"
                     f" — 使用者 2026-11-02 確認；公式與補繳期限待銀行書面（E1）"),
        "內部停止線": f"LTV {LTV_INTERNAL_STOP*100:.0f}%（＝維持率 {100/LTV_INTERNAL_STOP:.1f}%）— 內部政策，非銀行線",
        "距離": (f"距內部53%：池需跌 {(1-(loan/LTV_INTERNAL_STOP)/pool)*100:.2f}%"
                 f"（池 {_f(loan/LTV_INTERNAL_STOP)}）｜"
                 f"距銀行通知160%：跌 {(1-(loan*MAINT_WARN)/pool)*100:.2f}%（池 {_f(loan*MAINT_WARN)}）｜"
                 f"距銀行追繳140%：跌 {(1-(loan*MAINT_CALL)/pool)*100:.2f}%（池 {_f(loan*MAINT_CALL)}）"),
        "追繳線70%": "⛔ 舊假設（2026-11-03 superseded）— LTV 70% 不再作為門檻，正式級距見「銀行級距」",
        "計算基準": f"借款 {_f(loan)}（實撥）／池市值 {_f(pool)}",
        "追繳公式": ("銀行級距：通知 160%／追繳 140%（使用者 2026-11-02 確認）。"
                     "維持率計算公式、補繳期限、認列成數仍待銀行書面（E1/E2）；"
                     "LTV 70% 與 130% 均為歷史假設，已停用。"),
        "假設": "壓力情境＝池市值下跌、借款不變、不計配息再投入、不新增借款；三檔認列成數與單池分池規則未取得",
    }
    for d in DROPS:
        p = pool * (1 - d)
        ltv = loan / p * 100
        maint = p / loan * 100
        band = "內部綠 ≤53%" if ltv <= 53 else ("內部黃 54-58%" if ltv <= 58 else "內部紅 ≥59%")
        flags = []
        if maint < MAINT_CALL * 100:
            flags.append("破銀行追繳140%")
        elif maint < MAINT_WARN * 100:
            flags.append("破銀行通知160%")
        flag_txt = ("・" + "・".join(flags)) if flags else ""
        gap_stop = max(0.0, loan - LTV_INTERNAL_STOP * p)
        gap_warn = max(0.0, loan - p / MAINT_WARN)
        gap_call = max(0.0, loan - p / MAINT_CALL)
        gap_txt = ("無需還本" if gap_stop <= 0 else
                   f"回內部53% 需還 {_f(gap_stop)}／回通知160% 需還 {_f(gap_warn)}"
                   f"／回追繳140% 需還 {_f(gap_call) if gap_call > 0 else '—（未破）'}")
        out[f"跌{int(d * 100)}%"] = (f"池 {_f(p)} → LTV {ltv:.2f}%／維持率 {maint:.1f}%"
                                    f"（{band}{flag_txt}）｜{gap_txt}")
    return out


def single_pool(pools: dict, loan: float) -> dict:
    """單池壓力：借款按市值比例分配（假設），逐檔與加總分開呈現。"""
    total = sum(v for v in pools.values() if isinstance(v, (int, float)))
    if total <= 0 or loan <= 0:
        return {}
    rows = {}
    worst = None
    for name, v in pools.items():
        if not isinstance(v, (int, float)) or v <= 0:
            continue
        share = loan * v / total
        now = share / v * 100
        row = {"市值": v, "分配借款": round(share), "現況LTV_pct": round(now, 2)}
        for d in DROPS:
            single = share / (v * (1 - d)) * 100
            agg = loan / (total - v * d) * 100
            row[f"單池跌{int(d * 100)}%_LTV_pct"] = round(single, 2)
            row[f"同期加總_跌{int(d * 100)}%_pct"] = round(agg, 2)
            if d == 0.30 and (worst is None or agg < worst[1]):
                worst = (name, agg, single)
        rows[name] = row
    _ltv30 = (rows[next(iter(rows))]["單池跌30%_LTV_pct"] if rows else 0)
    _maint30 = (10000 / _ltv30) if _ltv30 else 0
    return {
        "說明": "單池風險與整體風險分開呈現：銀行可能對各池分別判定（thresholds_2026_0915 判定單位＝各池分別判定）",
        "假設": "借款按三檔市值比例分配；銀行認列成數／單池分池規則未取得（E2 未解除）→ 數值為內部試算，不得標示為安全",
        "逐檔": rows,
        "結論": (
            f"任一池單獨跌 30% → 該池 LTV {_ltv30:.2f}%（＝維持率 {_maint30:.1f}%，"
            f"破銀行追繳 140%／LTV 71.4%），"
            f"但同期加總僅 {min(r['同期加總_跌30%_pct'] for r in rows.values()) if rows else 0:.2f}%"
            f"～{max(r['同期加總_跌30%_pct'] for r in rows.values()) if rows else 0:.2f}%（內部綠燈 <53%）"
            f" → 不得以加總綠燈視為安全"
        ),
    }


def snapshot_blocks(snap: dict) -> tuple[dict, dict]:
    """從 snapshot 取真值，回傳（整體情境, 單池情境）兩個可寫回 snapshot 的 dict。"""
    c = (snap.get("cathay_pledge_0911") or {})
    loan = float(c.get("實際撥款金額") or c.get("可貸金額") or 0)
    pools = {k: v for k, v in ((c.get("擔保池") or {}).items()) if isinstance(v, (int, float))}
    pool_total = float(c.get("擔保池", {}).get("合計") or sum(pools.values()))
    pools_only = {k: v for k, v in pools.items() if k != "合計"}
    ov = overall(loan, pool_total)
    sp = single_pool(pools_only, loan)
    return ov, sp


def write_snapshot(path: str = "snapshot.json") -> dict:
    """把整體＋單池壓力情境寫回 snapshot（保留政策文字欄位與原換行格式）。"""
    import datetime as _dt

    p = Path(path)
    raw = p.read_bytes()
    nl = b"\r\n" if b"\r\n" in raw[:400] else b"\n"
    snap = json.loads(raw.decode("utf-8"))
    ov, sp = snapshot_blocks(snap)
    c = snap["cathay_pledge_0911"]
    old = c.get("LTV壓力情境") or {}
    new = dict(ov)
    # 2026-11-03：緩衝現況改動態計算（原保留舊字串 → 會停在 1,140,016 的過時值）
    _cash = float(((snap.get("cash_layers") or {}).get("unrestricted_cash")) or 0)
    _floor = float((((snap.get("thresholds_2026_0915") or {}).get("現金_twd")) or {}).get("生活底線") or 700000)
    new["緩衝現況"] = (f"可動用 {_f(_cash)}（cash_layers.unrestricted_cash）；"
                      f"扣現金底線 {_f(_floor)} 後實際可補繳上限 {_f(max(0.0, _cash - _floor))}；"
                      f"指定用途款 900,000 不可當緩衝；質押撥款餘額已指定清償，不可當緩衝")
    for k in ("動作", "修正記錄"):
        if k in old:
            new[k] = old[k]
    now = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    new["derived_at"] = now
    c["LTV壓力情境"] = new
    # 2026-11-03 使用者核准：維持率級距收斂為單一真值（銀行 160/140、內部 LTV 53）
    c["維持率級距_單一真值_20261103"] = {
        "定義": "維持率%＝池市值÷借款×100（銀行簡訊）；LTV%＝借款÷池市值×100（內部）；互為倒數，不得混用",
        "對銀行": "一律講維持率（國泰簡訊顯示值）",
        "對內部": "一律講 LTV（thresholds_2026_0915.ltv分級_pct）",
        "級距": [
            {"維持率": "≥190%", "LTV": "≤52.6%", "性質": "正常", "動作": "每日檢視"},
            {"維持率": "188.7%", "LTV": "53%", "性質": "內部停止線（非銀行線）", "動作": "停止新增、備妥還本方案"},
            {"維持率": "165%", "LTV": "60.6%", "性質": "內部警示區（通知線+5pp，pledge_maintenance_alert.py）", "動作": "提前預警：備現金、縮減新增"},
            {"維持率": "160%", "LTV": "62.5%", "性質": "銀行通知線", "動作": "準備補繳或還本"},
            {"維持率": "140%", "LTV": "71.4%", "性質": "銀行追繳線", "動作": "限期還本（優先還本，不補擔保品）"},
        ],
        "現況": new.get("現況"),
        "距離": new.get("距離"),
        "資料基準": ("擔保池取 snapshot.cathay_pledge_0911.擔保池（11,779,326，9/28 報價）；"
                     "使用者 2026-11-03 提供池值 11,794,828（維持率 199.9%），差 15,502 為報價日差。"
                     "正式監控以銀行簡訊維持率為準；擔保池欄位待下次真值日同步。"),
        "敏感度": "借款不變下，池子每跌 1% ≈ 維持率 -2.0pp",
        "來源": "銀行級距＝使用者 2026-11-02 確認（通知160/追繳140）；2026-11-03 使用者核准收斂 LTV70% 與 130% 舊假設",
        "derived_at": now,
    }
    bf = snap.get("bid_funding_plan_20261102")
    if isinstance(bf, dict):
        bf["維持率_status"] = ("⛔ 舊假設（2026-11-03）：原採 130% 追繳，與使用者 2026-11-02 確認之 140% 不符。"
                              "現行級距見 cathay_pledge_0911.維持率級距_單一真值_20261103；本區塊數值僅為當時估算，不得引用為現行門檻。")
        bf["壓力測試_status"] = "⛔ 上述「破 130%」為舊假設；正式追繳線為 140%。"
    c["單池壓力_20261030"] = {
        **sp,
        "來源": "pledge_stress.py（由 擔保池＋實撥借款 派生，非人工填寫）",
        "derived_at": now,
    }
    out = json.dumps(snap, ensure_ascii=False, indent=1)
    if nl == b"\r\n":
        out = out.replace("\n", "\r\n")
    p.write_text(out, encoding="utf-8", newline="")
    return {"整體": new, "單池": c["單池壓力_20261030"]}


if __name__ == "__main__":
    import sys

    if "--write" in sys.argv:
        r = write_snapshot()
        print("✅ snapshot 已更新（LTV壓力情境／單池壓力_20261030）")
        for k in ("現況", "銀行級距", "內部停止線", "距離", "跌20%", "跌30%", "跌35%"):
            print(" ", k, "=", r["整體"][k])
        print(" 單池結論:", r["單池"]["結論"])
    else:
        snap = json.loads(Path("snapshot.json").read_text(encoding="utf-8"))
        ov, sp = snapshot_blocks(snap)
        print(json.dumps({"整體": ov, "單池": sp}, ensure_ascii=False, indent=1))
