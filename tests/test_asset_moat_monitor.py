import pytest
"""Failing tests for AssetMoatMonitor (Task 1)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from asset_moat_monitor import AssetMoatMonitor


def test_runway_calculation():
    monitor = AssetMoatMonitor()
    snapshot = {
        "total_assets": 50689930,
        "monthly_expense": 141958,
        "liquid_assets": 3071343,
        "passive_income": 160100,
    }
    moat = monitor.compute(snapshot)
    assert moat["runway_months"] > 0
    assert moat["runway_months"] < 500


def test_liquid_runway_calculation():
    monitor = AssetMoatMonitor()
    snapshot = {
        "total_assets": 50689930,
        "monthly_expense": 141958,
        "liquid_assets": 3071343,
        "passive_income": 160100,
    }
    moat = monitor.compute(snapshot)
    assert moat["liquid_runway_months"] > 0
    assert moat["liquid_runway_months"] < 100


def test_coverage_ratio():
    monitor = AssetMoatMonitor()
    snapshot = {
        "total_assets": 50689930,
        "monthly_expense": 141958,
        "liquid_assets": 3071343,
        "passive_income": 160100,
    }
    moat = monitor.compute(snapshot)
    assert moat["coverage_ratio"] > 0
    assert moat["coverage_ratio"] == pytest.approx(160100 / 141958, rel=1e-4)


def test_semiconductor_exposure():
    monitor = AssetMoatMonitor()
    snapshot = {
        "total_assets": 50689930,
        "monthly_expense": 141958,
        "liquid_assets": 3071343,
        "passive_income": 160100,
        "securities": {
            "0050": 2000000,
            "006208": 500000,
            "etf_bond": 1000000,
        },
    }
    moat = monitor.compute(snapshot)
    assert "semiconductor_exposure_pct" in moat
    assert moat["semiconductor_exposure_pct"] >= 60  # 0050+006208 are semi-related
    assert moat["semiconductor_exposure_pct"] <= 80


def test_alert_generation():
    monitor = AssetMoatMonitor()
    snapshot = {
        "total_assets": 1000000,
        "monthly_expense": 500000,
        "liquid_assets": 100000,
        "passive_income": 30000,
        "securities": {"0050": 800000, "bond_etf": 200000},
        "debt_ratio": 0.6,
    }
    moat = monitor.compute(snapshot)
    alerts = moat["alert"]
    assert isinstance(alerts, list)
    assert any("RED" in a for a in alerts)
    assert any("semiconductor" in a.lower() for a in alerts)
    assert any("debt" in a.lower() for a in alerts)


def test_missing_fields_use_defaults():
    monitor = AssetMoatMonitor()
    moat = monitor.compute({})
    assert moat["runway_months"] == 0
    assert moat["coverage_ratio"] == 0
    assert moat["semiconductor_exposure_pct"] == 0
