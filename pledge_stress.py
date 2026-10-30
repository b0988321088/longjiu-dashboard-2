"""質押壓力情境計算（單一實作，供 snapshot 更新器／bbd 季檢／緊急應變共用）。

口徑（2026-10-30 使用者裁定）：
- 借款一律採「實撥」金額（5,900,000），不得用表定 540 萬。
- 池市值採 snapshot.cathay_pledge_0911.擔保池（含資料日），不得手寫。
- 追繳門檻：銀行正式公式未取得 → 標 UNKNOWN，系統暫採 LTV 70%（＝維持率 143%）保守假設。
- 資金缺口＝使 LTV 回到 70% 所需還款；另列「回維持率 140%」所需還款做對照。
- 單池：三檔按市值比例分配借款（假設；銀行認列成數／單池分池規則未取得）→ 任一池單獨下跌時的該池 LTV 與同期加總 LTV 必須分開呈現。
"""

from __future__ import annotations

from pathlib import Path
import json

LTV_LINE = 0.70          # 追繳參考（保守假設，銀行公式 UNKNOWN）
MAINT_TARGET = 1.40      # 對照：回維持率 140%
DROPS = (0.20, 0.30, 0.35)


def _f(x: float) -> str:
    return f"{x:,.0f}"


def overall(loan: float, pool: float) -> dict:
    """整體（三檔加總）壓力情境。"""
    if loan <= 0 or pool <= 0:
        return {}
    out = {
        "現況": f"{loan / pool * 100:.2f}%（綠燈 ≤53%）",
        "追繳線70%": (
            f"池需跌破 {_f(loan / LTV_LINE)}（= 現值再跌 "
            f"{(1 - (loan / LTV_LINE) / pool) * 100:.1f}%）"
        ),
        "計算基準": f"借款 {_f(loan)}（實撥）／池市值 {_f(pool)}",
        "追繳公式": "UNKNOWN（銀行正式維持率／追繳／補繳期限書面未取得）→ 系統暫採 LTV 70% 保守假設",
        "假設": "壓力情境＝池市值下跌、借款不變、不計配息再投入、不新增借款；三檔認列成數與單池分池規則未取得",
    }
    for d in DROPS:
        p = pool * (1 - d)
        ltv = loan / p * 100
        gap70 = max(0.0, loan - LTV_LINE * p)
        gap140 = max(0.0, loan - p / MAINT_TARGET)
        band = "綠燈 ≤53%" if ltv <= 53 else ("黃燈 54-58%" if ltv <= 58 else "紅燈 ≥59%")
        note = "・破追繳參考70%" if ltv > 70 else ""
        gap_txt = ("無需補繳（LTV 仍在 70% 以下）" if gap70 <= 0
                   else f"回 70% 需還 {_f(gap70)}／回維持率140% 需還 {_f(gap140)}")
        out[f"跌{int(d * 100)}%"] = f"池 {_f(p)} → LTV {ltv:.2f}%（{band}{note}）｜資金缺口：{gap_txt}"
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
    return {
        "說明": "單池風險與整體風險分開呈現：銀行可能對各池分別判定（thresholds_2026_0915 判定單位＝各池分別判定）",
        "假設": "借款按三檔市值比例分配；銀行認列成數／單池分池規則未取得（E2 未解除）→ 數值為內部試算，不得標示為安全",
        "逐檔": rows,
        "結論": (
            f"任一池單獨跌 30% → 該池 LTV {rows[next(iter(rows))]['單池跌30%_LTV_pct'] if rows else 0:.2f}%（破追繳 70%），"
            f"但同期加總僅 {min(r['同期加總_跌30%_pct'] for r in rows.values()) if rows else 0:.2f}%"
            f"～{max(r['同期加總_跌30%_pct'] for r in rows.values()) if rows else 0:.2f}% 仍為綠燈 → 不得以加總綠燈視為安全"
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
    for k in ("緩衝現況", "動作", "修正記錄"):
        if k in old:
            new[k] = old[k]
    now = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    new["derived_at"] = now
    c["LTV壓力情境"] = new
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
        for k in ("現況", "跌20%", "跌30%", "跌35%", "追繳線70%"):
            print(" ", k, "=", r["整體"][k])
        print(" 單池結論:", r["單池"]["結論"])
    else:
        snap = json.loads(Path("snapshot.json").read_text(encoding="utf-8"))
        ov, sp = snapshot_blocks(snap)
        print(json.dumps({"整體": ov, "單池": sp}, ensure_ascii=False, indent=1))
