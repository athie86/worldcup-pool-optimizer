"""Tests for the market constraint layer (spec §7/§8)."""
import pytest

from app.services.market_constraints import build_constraints
from app.services.odds_normalization import BookmakerMarket, RawOutcome


def _h2h(bk, h, d, a):
    return BookmakerMarket(bk, "h2h", None,
                           [RawOutcome("home_win", h), RawOutcome("draw", d), RawOutcome("away_win", a)])


def _totals(bk, line, o, u):
    return BookmakerMarket(bk, "totals", line, [RawOutcome("over", o), RawOutcome("under", u)])


def test_result_constraints_built():
    bms = [_h2h("pinnacle", 1.7, 3.6, 5.5), _h2h("bet365", 1.72, 3.55, 5.3)]
    res = build_constraints(bms)
    types = {c.constraint_type for c in res.constraints}
    assert {"result_home_win", "result_draw", "result_away_win"} <= types
    # consensus target probabilities for a single market should ~sum to 1
    by = {c.constraint_type: c.target_value for c in res.constraints}
    total = by["result_home_win"] + by["result_draw"] + by["result_away_win"]
    assert total == pytest.approx(1.0, abs=1e-6)


def test_half_line_total_uses_probability():
    bms = [_h2h("a", 2, 3.4, 3.6), _totals("a", 2.5, 1.9, 1.95)]
    res = build_constraints(bms)
    totals = [c for c in res.constraints if c.market_family == "total_goals"]
    assert all(c.target_type == "probability" for c in totals)


def test_integer_line_total_uses_conditional_probability():
    bms = [_h2h("a", 2, 3.4, 3.6), _totals("a", 3.0, 2.0, 1.85)]
    res = build_constraints(bms)
    totals = [c for c in res.constraints if c.market_family == "total_goals"]
    assert totals
    assert all(c.target_type == "conditional_probability" for c in totals)


def test_coverage_and_used_markets():
    bms = [_h2h("a", 1.8, 3.5, 4.5), _totals("a", 2.5, 1.9, 1.95)]
    res = build_constraints(bms)
    assert "h2h" in res.used_markets
    assert "totals" in res.used_markets
    assert res.market_coverage_score > 0
    assert "team_totals" in res.missing_markets


def test_btts_constraints():
    bms = [BookmakerMarket("a", "btts", None,
                           [RawOutcome("btts_yes", 1.9), RawOutcome("btts_no", 1.9)])]
    res = build_constraints(bms)
    types = {c.constraint_type for c in res.constraints}
    assert {"btts_yes", "btts_no"} <= types


def test_outlier_downweighted():
    # one book wildly off on the home price
    bms = [_h2h("a", 1.7, 3.6, 5.5), _h2h("b", 1.72, 3.55, 5.3),
           _h2h("c", 1.7, 3.6, 5.5), _h2h("d", 1.71, 3.6, 5.4),
           _h2h("e", 5.0, 3.6, 1.7)]  # outlier (reversed favourite)
    res = build_constraints(bms)
    hw = next(c for c in res.constraints if c.constraint_type == "result_home_win")
    # consensus home-win prob should stay high (~0.57), not dragged toward the outlier
    assert hw.target_value > 0.5


def test_unknown_market_ignored_safely():
    bms = [BookmakerMarket("a", "player_props", None,
                           [RawOutcome("unknown", 1.9), RawOutcome("unknown", 1.9)])]
    res = build_constraints(bms)
    assert res.constraints == []
