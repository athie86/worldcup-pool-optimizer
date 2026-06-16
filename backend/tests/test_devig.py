"""Tests for the de-vig layer (spec §6)."""
import pytest

from app.services.devig import (
    devig, devig_proportional, devig_power, devig_shin,
    devig_odds_ratio, devig_exchange_mid,
)


def _three_way():
    # A typical 1X2 book with ~5% overround
    return {"home_win": 1.80, "draw": 3.60, "away_win": 5.00}


def test_proportional_sums_to_one():
    r = devig_proportional(_three_way())
    assert r.converged
    assert sum(r.probabilities.values()) == pytest.approx(1.0, abs=1e-9)
    assert r.margin > 0


def test_power_converges_and_sums_to_one():
    r = devig_power(_three_way())
    assert r.converged
    assert sum(r.probabilities.values()) == pytest.approx(1.0, abs=1e-6)


def test_shin_converges_or_falls_back():
    r = devig_shin(_three_way())
    assert sum(r.probabilities.values()) == pytest.approx(1.0, abs=1e-6)


def test_odds_ratio_sums_to_one():
    r = devig_odds_ratio(_three_way())
    assert sum(r.probabilities.values()) == pytest.approx(1.0, abs=1e-6)


def test_exchange_mid_uses_back_lay_midpoint():
    back = {"home_win": 2.00, "away_win": 2.10}
    lay = {"home_win": 2.04, "away_win": 2.14}
    r = devig_exchange_mid(back, lay)
    assert r.converged
    assert sum(r.probabilities.values()) == pytest.approx(1.0, abs=1e-9)


def test_exchange_mid_without_lay_falls_back():
    r = devig_exchange_mid({"home_win": 2.0, "away_win": 2.0}, None)
    assert r.converged
    assert any("proportional" in w for w in r.warnings)


def test_invalid_odds_dropped():
    r = devig({"home_win": 1.0}, method="power")  # single invalid outcome
    assert not r.converged
    assert r.probabilities == {}


def test_devig_dispatch_fallback_chain():
    # power should succeed for a normal book
    r = devig(_three_way(), method="power")
    assert r.converged
    assert r.method == "power"


def test_favourite_longshot_power_vs_proportional():
    odds = _three_way()
    p = devig_power(odds).probabilities
    pr = devig_proportional(odds).probabilities
    # Both normalised, but methods differ on the favourite's share
    assert p["home_win"] != pytest.approx(pr["home_win"], abs=1e-6)
