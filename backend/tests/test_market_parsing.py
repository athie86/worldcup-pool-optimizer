"""Tests for the canonical market parser (spec §13)."""
from app.services.market_parsing import parse_market, canonical_family


HOME, AWAY = "Brazil", "Croatia"


def test_canonical_family_mapping():
    assert canonical_family("h2h") == "result"
    assert canonical_family("h2h_3_way") == "result"
    assert canonical_family("alternate_totals") == "total_goals"
    assert canonical_family("team_totals") == "team_goals"
    assert canonical_family("btts") == "both_teams_to_score"
    assert canonical_family("draw_no_bet") == "result_conditional_no_draw"
    assert canonical_family("spreads") == "goal_difference"
    assert canonical_family("totally_unknown") == "unknown"


def test_parse_h2h_3_way():
    m = parse_market("h2h_3_way", [
        {"name": "Brazil", "price": 1.7},
        {"name": "Draw", "price": 3.6},
        {"name": "Croatia", "price": 5.2},
    ], HOME, AWAY)
    types = {o.outcome_type for o in m.outcomes}
    assert types == {"home_win", "draw", "away_win"}
    assert m.supported


def test_parse_totals_half_line():
    m = parse_market("totals", [
        {"name": "Over", "price": 1.9, "point": 2.5},
        {"name": "Under", "price": 1.95, "point": 2.5},
    ], HOME, AWAY)
    assert {o.outcome_type for o in m.outcomes} == {"over", "under"}
    assert all(o.line == 2.5 for o in m.outcomes)


def test_parse_team_totals_home_away():
    m = parse_market("team_totals", [
        {"name": "Over", "price": 1.8, "point": 1.5, "description": "Brazil"},
        {"name": "Under", "price": 2.0, "point": 1.5, "description": "Brazil"},
        {"name": "Over", "price": 2.6, "point": 1.5, "description": "Croatia"},
        {"name": "Under", "price": 1.5, "point": 1.5, "description": "Croatia"},
    ], HOME, AWAY)
    types = {o.outcome_type for o in m.outcomes}
    assert "home_over" in types and "away_under" in types


def test_parse_btts_yes_no():
    m = parse_market("btts", [
        {"name": "Yes", "price": 1.9},
        {"name": "No", "price": 1.9},
    ], HOME, AWAY)
    assert {o.outcome_type for o in m.outcomes} == {"btts_yes", "btts_no"}


def test_parse_draw_no_bet():
    m = parse_market("draw_no_bet", [
        {"name": "Brazil", "price": 1.3},
        {"name": "Croatia", "price": 3.4},
    ], HOME, AWAY)
    assert {o.outcome_type for o in m.outcomes} == {"home_dnb", "away_dnb"}


def test_parse_spreads_with_point():
    m = parse_market("spreads", [
        {"name": "Brazil", "price": 1.9, "point": -1.5},
        {"name": "Croatia", "price": 1.9, "point": 1.5},
    ], HOME, AWAY)
    assert {o.outcome_type for o in m.outcomes} == {"home_spread", "away_spread"}


def test_preserve_unknown_market_does_not_crash():
    m = parse_market("player_shots_on_target", [
        {"name": "Some Player Over 2.5", "price": 1.8, "point": 2.5},
    ], HOME, AWAY)
    assert not m.supported
    # outcome preserved as unknown rather than raising
    assert m.outcomes[0].outcome_type == "unknown"
    assert m.outcomes[0].raw_name == "Some Player Over 2.5"


def test_unknown_outcome_name_in_known_market():
    m = parse_market("h2h", [
        {"name": "Brazil", "price": 1.7},
        {"name": "Mystery", "price": 9.0},
    ], HOME, AWAY)
    types = [o.outcome_type for o in m.outcomes]
    assert "home_win" in types
    assert "unknown" in types  # does not crash
