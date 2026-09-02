"""decision_json.py — dashboard_decisions.json 安全讀寫

2026-09-02 事故後新增：
- notion_bridge.py 每小時整點同步（intel_sync_wrapper）把正常 dict 誤判為舊格式，
  else 分支將 pending_decisions/decisions 全數清空重寫（17:00 空寫事故，第三次）。
- 統一由此模組讀寫，內建「空寫防護」：舊檔有 pending 而新版 pending 歸零，
  或新舊皆空但有舊內容 → 中止寫入 + 自動備份 .bak + 拋例外。
- 所有寫方：notion_bridge / decision_handler / decision_buttons / complete_operation
"""
import json
from datetime import datetime
from pathlib import Path


def load_decisions(path):
    """讀取決策檔，回傳完整 dict 結構（含相容舊純 list 格式）"""
    p = Path(path)
    if not p.exists():
        return {"pending_decisions": [], "decisions": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"pending_decisions": [], "decisions": []}
    if isinstance(data, list):  # 2026-08-27 前的純 list 格式 → 包回 dict
        data = {"pending_decisions": [], "decisions": data}
    if not isinstance(data, dict):
        data = {"pending_decisions": [], "decisions": []}
    data.setdefault("pending_decisions", [])
    data.setdefault("decisions", [])
    return data


def safe_save_decisions(path, data, allow_pending_clear=False):
    """空寫防護寫入。

    破壞性寫入判定（任一成立即中止並備份）：
      1. 舊檔有 pending 且新檔 pending 歸零（allow_pending_clear=False 時）
      2. 新檔 pending/decisions 皆空，但舊檔有內容
    """
    p = Path(path)
    if not isinstance(data, dict):
        data = {
            "pending_decisions": [],
            "decisions": data if isinstance(data, list) else [],
        }
    new_p = len(data.get("pending_decisions", [])) if isinstance(data.get("pending_decisions"), list) else 0
    new_d = len(data.get("decisions", [])) if isinstance(data.get("decisions"), list) else 0

    old_p = old_d = 0
    if p.exists():
        old = load_decisions(p)
        old_p = len(old.get("pending_decisions", []))
        old_d = len(old.get("decisions", []))

    def _backup():
        bak = str(p) + f".bak_{datetime.now():%Y%m%d_%H%M%S}"
        Path(bak).write_text(json.dumps(load_decisions(p), ensure_ascii=False, indent=2), encoding="utf-8")
        return bak

    if not allow_pending_clear and old_p > 0 and new_p == 0:
        bak = _backup()
        raise ValueError(
            f"⚠️ 空寫防護：pending_decisions 將從 {old_p} 筆被寫成 0 筆"
            f"（原 {old_d} 筆 decisions 不受影響）— 已中止並備份：{bak}"
        )
    if new_p == 0 and new_d == 0 and (old_p + old_d) > 0:
        bak = _backup()
        raise ValueError(
            f"⚠️ 空寫防護：決策檔將被寫成完全空結構（原 {old_p} pending + {old_d} decisions）"
            f"— 已中止並備份：{bak}"
        )
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
