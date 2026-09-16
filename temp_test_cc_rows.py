
import sys
import os
import json
import pathlib
from datetime import date, datetime, timedelta

# This is necessary for run_daily to find its modules (e.g., scripts.components.moneybook_io)
sys.path.insert(0, str(pathlib.Path(__file__).parent.resolve()))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.resolve()))

# Mimic the BASE variable from run_daily.py
BASE = pathlib.Path(__file__).parent.resolve()

# Simplified build_cc_rows function to ensure no external dependencies beyond snapshot.json
def build_cc_rows_isolated() -> str:
    _rows = []
    _cc_rows_from_mb = [] # Simulate no moneybook rows

    if not _cc_rows_from_mb:
        try:
            _snap_path = BASE / "snapshot.json"
            if not _snap_path.exists():
                print(f"[ERROR] snapshot.json not found at {_snap_path}")
                return ""
            
            _snap = json.loads(_snap_path.read_text(encoding="utf-8"))
            _cc = _snap.get("credit_card") or {}

            _banks = (
                ("玉山銀行", "玉山", "Unicard / UNI"),
                ("台新銀行", "台新", "Richart"),
                ("永豐銀行", "永豐", "SPORT"),
                ("台北富邦", "富邦", "momo / J"),
                ("國泰世華", "國泰", "CUBE"),
            )
            for _bank, _kw, _cardname in _banks:
                _amt = 0.0
                for _card, _v in (_cc.items() if isinstance(_cc, dict) else []):
                    if _kw in str(_card):
                        try:
                            _amt += float(_v or 0)
                        except (TypeError, ValueError):
                            pass
                _status = "🔄 待扣繳" if _amt < 0 else ("✅ 無欠款（溢繳）" if _amt > 0 else "✅ 無欠款")
                _rows.append(f'          <tr><td>{_bank}</td><td>{_cardname}</td><td>—</td><td class="num">{int(abs(_amt)):,}</td><td>{_status}</td></tr>')
        except Exception as e:
            print(f"[ERROR] Failed to build CC rows from snapshot: {e}")
            pass
    return "\n".join(_rows)

if __name__ == "__main__":
    print(build_cc_rows_isolated())
