"""Failing tests for DynamicBalancer (Task 3)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dynamic_balancer import DynamicBalancer


def test_reduce_tech_trigger():
    balancer = DynamicBalancer()
    current = {"TW": 7.2, "US": 46.1, "BOND": 33.8, "DEF": 18.5}
    signals = {"semiconductor_exposure_pct": 72, "coverage_ratio": 1.2}
    suggestion = balancer.suggest(current, signals)
    assert "actions" in suggestion
    assert any(a["action"] == "REDUCE_TECH" for a in suggestion["actions"])
    assert any(a["priority"] == "P1" for a in suggestion["actions"])


def test_increase_dividend_trigger():
    balancer = DynamicBalancer()
    current = {"TW": 7.2, "US": 46.1, "BOND": 33.8, "DEF": 18.5}
    signals = {"semiconductor_exposure_pct": 50, "coverage_ratio": 0.85}
    suggestion = balancer.suggest(current, signals)
    assert any(a["action"] == "INCREASE_DIVIDEND" for a in suggestion["actions"])
    assert any(a["priority"] == "P0" for a in suggestion["actions"])


def test_deleverage_trigger():
    balancer = DynamicBalancer()
    current = {"TW": 7.2, "US": 46.1, "BOND": 33.8, "DEF": 18.5}
    signals = {"semiconductor_exposure_pct": 50, "coverage_ratio": 1.2, "debt_ratio_pct": 55}
    suggestion = balancer.suggest(current, signals)
    assert any(a["action"] == "DELEVERAGE" for a in suggestion["actions"])
    assert any(a["priority"] == "P0" for a in suggestion["actions"])


def test_no_action_when_healthy():
    balancer = DynamicBalancer()
    current = {"TW": 7.2, "US": 46.1, "BOND": 33.8, "DEF": 18.5}
    signals = {"semiconductor_exposure_pct": 55, "coverage_ratio": 1.15, "debt_ratio_pct": 35}
    suggestion = balancer.suggest(current, signals)
    assert len(suggestion["actions"]) == 0


def test_returns_allocation():
    balancer = DynamicBalancer()
    current = {"TW": 7.2, "US": 46.1}
    signals = {"semiconductor_exposure_pct": 72, "coverage_ratio": 0.8, "debt_ratio_pct": 55}
    suggestion = balancer.suggest(current, signals)
    assert suggestion["allocation"] == current


def test_apply_rules_from_missing_file():
    balancer = DynamicBalancer()
    result = balancer.apply_rules_from_file("nonexistent.json")
    assert result == []
