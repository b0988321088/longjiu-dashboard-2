"""External Comparator — 對標外部理財機器人/大盤 (Task 2)"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BENCHMARK_PATH = Path(__file__).parent / "comparator_benchmark.json"


class ExternalComparator:
    def __init__(self) -> None:
        if BENCHMARK_PATH.exists():
            self.benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
        else:
            self.benchmark = {
                "twii_ytd_return": 5.2,
                "sox_ytd_return": 3.1,
                "peers": [
                    {"name": "元大00878", "dividend_yield": 6.5, "expense_ratio": 0.5},
                    {"name": "元大0050", "dividend_yield": 1.8, "expense_ratio": 0.32},
                    {"name": "凱基台股", "dividend_yield": 2.1, "expense_ratio": 0.68},
                ],
            }

    def compare(self, my: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
        my_return = my.get("twii_return_ytd", 0)
        bench_return = benchmark.get("twii_return_ytd")
        if bench_return is None:
            bench_return = my_return  # no benchmark -> par
        diff = my_return - bench_return
        verdict = "beat" if diff > 0 else "underperform" if diff < 0 else "par"
        return {
            "my_return": my_return,
            "benchmark_return": bench_return,
            "diff_pct": round(diff, 2),
            "verdict": verdict,
        }

    def compare_peers(self, my_fund: dict[str, Any], peers: list[dict[str, Any]]) -> dict[str, Any]:
        my_yield = my_fund.get("dividend_yield", 0)
        my_expense = my_fund.get("expense_ratio", 0)
        ranked = sorted(peers, key=lambda x: x.get("dividend_yield", 0), reverse=True)
        better = [p for p in ranked if p.get("dividend_yield", 0) > my_yield]
        return {
            "my_dividend_yield": my_yield,
            "my_expense_ratio": my_expense,
            "peers_count": len(peers),
            "rank": len(better) + 1,
            "better_peers": [p["name"] for p in better[:3]],
        }
