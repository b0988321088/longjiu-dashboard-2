"""Failing tests for ExternalComparator (Task 2)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from external_comparator import ExternalComparator


def test_benchmark_comparison():
    comp = ExternalComparator()
    my = {"twii_return_ytd": 5.2}
    bench = {"twii_return_ytd": 3.1}
    result = comp.compare(my, bench)
    assert "verdict" in result
    assert result["verdict"] == "beat"


def test_benchmark_underperform():
    comp = ExternalComparator()
    my = {"twii_return_ytd": 2.0}
    bench = {"twii_return_ytd": 3.1}
    result = comp.compare(my, bench)
    assert result["verdict"] == "underperform"


def test_peer_comparison():
    comp = ExternalComparator()
    my_fund = {"dividend_yield": 3.2, "expense_ratio": 1.5}
    peers = [
        {"name": "元大00878", "dividend_yield": 6.5, "expense_ratio": 0.5},
        {"name": "元大0050", "dividend_yield": 1.8, "expense_ratio": 0.32},
    ]
    result = comp.compare_peers(my_fund, peers)
    assert result["rank"] >= 1
    assert result["rank"] <= len(peers)


def test_peer_ranking():
    comp = ExternalComparator()
    my_fund = {"dividend_yield": 7.0, "expense_ratio": 1.0}
    peers = [
        {"name": "A", "dividend_yield": 5.0},
        {"name": "B", "dividend_yield": 6.0},
        {"name": "C", "dividend_yield": 8.0},
    ]
    result = comp.compare_peers(my_fund, peers)
    assert result["rank"] == 2  # 6.0 < 7.0 < 8.0 -> better: C -> rank 2


def test_missing_peer_fields():
    comp = ExternalComparator()
    my_fund = {"dividend_yield": 3.0}
    peers = [{"name": "X"}]
    result = comp.compare_peers(my_fund, peers)
    assert result["rank"] == 1
    assert result["peers_count"] == 1


def test_empty_benchmark():
    comp = ExternalComparator()
    result = comp.compare({}, {})
    assert result["verdict"] == "par"
