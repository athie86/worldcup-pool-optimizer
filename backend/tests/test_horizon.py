"""Tests for the full horizon-consistent knockout model."""
import numpy as np
import pytest

from app.services.scoring import ScoringRule, COMBINE_BEST, COMBINE_ADDITIVE
from app.services.horizon import (
    ScoringBasis,
    ScoreHorizon,
    OutcomeHorizon,
    TerminalStateKind,
    TerminalOutcomeState,
    CandidatePrediction,
    basis_to_horizons,
    build_extra_time_distribution,
    infer_penalty_probability,
    build_terminal_states,
    derive_score_matrix_90,
    derive_score_matrix_120,
    summarize_terminal_states,
    validate_terminal_states,
    generate_candidates,
    rule_is_valid_for_basis,
    actual_score_for_basis,
    actual_outcome_for_basis,
    predicted_outcome_for_basis,
    score_prediction_against_state,
    compute_expected_points_from_terminal_states,
    validate_pool_config_scoring_consistency,
    HorizonModelResult,
)


# ── small helpers ────────────────────────────────────────────────────────────


def _simple_p90(n: int = 4) -> np.ndarray:
    """A tiny well-defined 90-minute matrix."""
    mat = np.zeros((n, n))
    mat[1, 0] = 0.50   # home win 1-0
    mat[0, 0] = 0.20   # draw 0-0
    mat[1, 1] = 0.10   # draw 1-1
    mat[0, 1] = 0.20   # away win 0-1
    return mat


def _knockout_rules() -> list[ScoringRule]:
    return [
        ScoringRule("exact_score", "Exact", 6.0, True, 1, phase="knockout"),
        ScoringRule("goal_difference", "GD", 4.0, True, 2, phase="knockout"),
        ScoringRule("outcome_team_goals", "OTG", 3.0, True, 3, phase="knockout"),
        ScoringRule("correct_outcome", "Result", 2.0, True, 4, phase="knockout"),
        ScoringRule("team_goals", "Team goals", 1.0, True, 5, phase="knockout"),
        ScoringRule("advance", "Advance", 3.0, True, 7, phase="knockout"),
        ScoringRule("penalty_winner", "Pens", 3.0, True, 8, phase="knockout"),
    ]


# ── horizon mapping ──────────────────────────────────────────────────────────


class TestHorizonMapping:
    def test_ninety_minutes(self):
        s, o = basis_to_horizons(ScoringBasis.NINETY_MINUTES)
        assert s == ScoreHorizon.REGULATION_90
        assert o == OutcomeHorizon.REGULATION_90

    def test_extra_time(self):
        s, o = basis_to_horizons(ScoringBasis.NINETY_MINUTES_EXTRA_TIME)
        assert s == ScoreHorizon.AFTER_EXTRA_TIME_120
        assert o == OutcomeHorizon.AFTER_EXTRA_TIME_120

    def test_extra_time_penalties(self):
        # Result-shaped components score on the 120' on-pitch result, not on which
        # team advances; a penalties-decided tie is a draw for those components.
        # Advancement is handled solely by the advance / penalty_winner bonuses.
        s, o = basis_to_horizons(ScoringBasis.NINETY_MINUTES_EXTRA_TIME_PENALTIES)
        assert s == ScoreHorizon.AFTER_EXTRA_TIME_120
        assert o == OutcomeHorizon.AFTER_EXTRA_TIME_120

    def test_accepts_raw_string(self):
        assert basis_to_horizons("ninety_minutes")[0] == ScoreHorizon.REGULATION_90


# ── extra-time distribution & penalty inference ──────────────────────────────


class TestExtraTimeDistribution:
    def test_sums_to_one(self):
        pet = build_extra_time_distribution(1.5, 1.2, et_max=4)
        assert pet.shape == (5, 5)
        assert abs(pet.sum() - 1.0) < 1e-9

    def test_lower_intensity_than_regulation(self):
        # ET goal mass should be modest: 0-0 is the most likely ET sub-score.
        pet = build_extra_time_distribution(1.5, 1.2, et_max=4)
        assert pet[0, 0] == pet.max()


class TestPenaltyInference:
    def test_fallback_close_to_coinflip(self):
        q = infer_penalty_probability(
            2.0, 1.0,
            p_home_win_90=0.5, p_draw_90=0.25,
            p_home_wins_et_given_et=0.4, p_still_draw_after_et_given_et=0.4,
        )
        assert 0.40 <= q <= 0.60

    def test_market_inference_and_shrinkage(self):
        # With a strong home advancement market and full reliability, q should
        # exceed 0.5 but stay bounded.
        q = infer_penalty_probability(
            1.3, 1.3,
            p_home_win_90=0.30, p_draw_90=0.30,
            p_home_wins_et_given_et=0.30, p_still_draw_after_et_given_et=0.40,
            p_home_adv_market=0.70, reliability=1.0,
        )
        assert 0.5 < q <= 0.75

    def test_no_market_reliability_zero_pulls_to_half(self):
        q = infer_penalty_probability(
            1.3, 1.3,
            p_home_win_90=0.30, p_draw_90=0.30,
            p_home_wins_et_given_et=0.30, p_still_draw_after_et_given_et=0.40,
            p_home_adv_market=0.70, reliability=0.0,
        )
        assert q == pytest.approx(0.5)


# ── terminal-state generation ────────────────────────────────────────────────


class TestTerminalStates:
    def test_probabilities_sum_to_one(self):
        p90 = _simple_p90()
        pet = build_extra_time_distribution(1.0, 1.0, et_max=3)
        states = build_terminal_states(p90, pet, 0.55)
        total = sum(s.probability for s in states)
        assert abs(total - 1.0) < 1e-9

    def test_derived_matrices_sum_to_one(self):
        p90 = _simple_p90()
        pet = build_extra_time_distribution(1.0, 1.0, et_max=3)
        states = build_terminal_states(p90, pet, 0.55)
        m90 = derive_score_matrix_90(states, 4)
        m120 = derive_score_matrix_120(states, 4 + 3)
        assert abs(m90.sum() - 1.0) < 1e-9
        assert abs(m120.sum() - 1.0) < 1e-9

    def test_advancement_sums_to_one(self):
        p90 = _simple_p90()
        pet = build_extra_time_distribution(1.0, 1.0, et_max=3)
        states = build_terminal_states(p90, pet, 0.55)
        s = summarize_terminal_states(states)
        assert abs(s.p_home_advances + s.p_away_advances - 1.0) < 1e-9

    def test_no_draw_means_no_extra_time(self):
        # P90 with zero draw mass → never goes to extra time / penalties.
        p90 = np.zeros((3, 3))
        p90[1, 0] = 0.6
        p90[2, 1] = 0.4   # both home wins; no draw
        pet = build_extra_time_distribution(1.0, 1.0, et_max=3)
        states = build_terminal_states(p90, pet, 0.5)
        s = summarize_terminal_states(states)
        assert s.p_goes_to_extra_time == 0.0
        assert s.p_goes_to_penalties == 0.0

    def test_zero_et_draw_means_no_penalties(self):
        # If the ET distribution can never end level, no match reaches penalties.
        p90 = _simple_p90()
        pet = np.zeros((2, 2))
        pet[1, 0] = 1.0   # ET always 1-0 home → never level
        states = build_terminal_states(p90, pet, 0.5)
        s = summarize_terminal_states(states)
        assert s.p_goes_to_penalties == 0.0
        assert s.p_goes_to_extra_time > 0.0

    def test_score_120_excludes_penalty_goals(self):
        # A penalty-decided state keeps its 120' score level (penalties add 0).
        p90 = np.zeros((2, 2))
        p90[0, 0] = 1.0   # always 0-0 after 90
        pet = np.zeros((2, 2))
        pet[0, 0] = 1.0   # always 0-0 after ET → penalties
        states = build_terminal_states(p90, pet, 0.7)
        assert len(states) == 2  # home-pens + away-pens
        for st in states:
            assert st.went_to_penalties
            assert (st.score_120_home, st.score_120_away) == (0, 0)
        assert states[0].probability == pytest.approx(0.7)
        assert states[1].probability == pytest.approx(0.3)

    def test_validation_passes_for_well_formed(self):
        p90 = _simple_p90()
        pet = build_extra_time_distribution(1.0, 1.0, et_max=3)
        states = build_terminal_states(p90, pet, 0.55)
        m90 = derive_score_matrix_90(states, 4)
        m120 = derive_score_matrix_120(states, 7)
        s = summarize_terminal_states(states)
        assert validate_terminal_states(states, m90, m120, s) == []


# ── candidate generation ─────────────────────────────────────────────────────


class TestCandidateGeneration:
    def test_ninety_no_penalty_candidates(self):
        cands = generate_candidates(3, ScoringBasis.NINETY_MINUTES)
        assert len(cands) == 16
        assert all(c.predicted_penalty_winner is None for c in cands)

    def test_extra_time_no_penalty_candidates(self):
        cands = generate_candidates(3, ScoringBasis.NINETY_MINUTES_EXTRA_TIME)
        assert len(cands) == 16
        assert all(c.predicted_penalty_winner is None for c in cands)

    def test_pens_basis_expands_draws(self):
        cands = generate_candidates(3, ScoringBasis.NINETY_MINUTES_EXTRA_TIME_PENALTIES)
        # 16 base cells + 4 draws each duplicated once = 20.
        assert len(cands) == 20
        draws = [c for c in cands if c.predicted_home == c.predicted_away]
        assert len(draws) == 8
        winners = {c.predicted_penalty_winner for c in draws}
        assert winners == {"home", "away"}
        non_draws = [c for c in cands if c.predicted_home != c.predicted_away]
        assert all(c.predicted_penalty_winner is None for c in non_draws)


# ── rule validity by basis ───────────────────────────────────────────────────


class TestRuleValidity:
    def test_advance_only_pens(self):
        assert not rule_is_valid_for_basis("advance", "knockout", "ninety_minutes")
        assert not rule_is_valid_for_basis("advance", "knockout", "ninety_minutes_extra_time")
        assert rule_is_valid_for_basis("advance", "knockout", "ninety_minutes_extra_time_penalties")

    def test_penalty_winner_only_pens(self):
        assert not rule_is_valid_for_basis("penalty_winner", "knockout", "ninety_minutes_extra_time")
        assert rule_is_valid_for_basis("penalty_winner", "knockout", "ninety_minutes_extra_time_penalties")

    def test_score_rules_valid_everywhere(self):
        for basis in ScoringBasis:
            assert rule_is_valid_for_basis("exact_score", "knockout", basis)
            assert rule_is_valid_for_basis("correct_outcome", "knockout", basis)

    def test_bonus_invalid_in_group(self):
        assert not rule_is_valid_for_basis("advance", "group", "ninety_minutes")


# ── basis-aware actual/predicted helpers ─────────────────────────────────────


class TestBasisHelpers:
    def _pen_state(self):
        return TerminalOutcomeState(
            score_90_home=1, score_90_away=1,
            score_120_home=2, score_120_away=2,
            went_to_extra_time=True, went_to_penalties=True,
            advancing_team="home", penalty_winner="home",
            state_kind=TerminalStateKind.DECIDED_ON_PENALTIES.value,
            probability=1.0,
        )

    def test_actual_score_by_horizon(self):
        st = self._pen_state()
        assert actual_score_for_basis(st, ScoreHorizon.REGULATION_90) == (1, 1)
        assert actual_score_for_basis(st, ScoreHorizon.AFTER_EXTRA_TIME_120) == (2, 2)

    def test_actual_outcome_advancement(self):
        st = self._pen_state()
        assert actual_outcome_for_basis(st, OutcomeHorizon.AFTER_EXTRA_TIME_120) == "draw"
        assert actual_outcome_for_basis(st, OutcomeHorizon.ADVANCEMENT) == "home_win"

    def test_predicted_outcome_advancement_needs_pen_winner(self):
        draw_no_pen = CandidatePrediction(1, 1, None)
        assert predicted_outcome_for_basis(draw_no_pen, OutcomeHorizon.ADVANCEMENT) is None
        draw_pen = CandidatePrediction(1, 1, "away")
        assert predicted_outcome_for_basis(draw_pen, OutcomeHorizon.ADVANCEMENT) == "away_win"


# ── expected points over a synthetic distribution ────────────────────────────


class TestExpectedPointsSynthetic:
    """A 3-state distribution with hand-computable EV.

    50% home win 1-0 in 90; 25% 1-1 → home wins pens; 25% 1-1 → away wins pens.
    """

    def _model(self) -> HorizonModelResult:
        states = [
            TerminalOutcomeState(1, 0, 1, 0, False, False, "home", None,
                                 TerminalStateKind.DECIDED_IN_90.value, 0.50),
            TerminalOutcomeState(1, 1, 1, 1, True, True, "home", "home",
                                 TerminalStateKind.DECIDED_ON_PENALTIES.value, 0.25),
            TerminalOutcomeState(1, 1, 1, 1, True, True, "away", "away",
                                 TerminalStateKind.DECIDED_ON_PENALTIES.value, 0.25),
        ]
        m90 = derive_score_matrix_90(states, 3)
        m120 = derive_score_matrix_120(states, 3)
        s = summarize_terminal_states(states)
        return HorizonModelResult(
            model_type="t", model_version="t",
            score_matrix_90=m90, score_matrix_120=m120, terminal_states=states,
            p_home_win_90=s.p_home_win_90, p_draw_90=s.p_draw_90, p_away_win_90=s.p_away_win_90,
            p_home_win_120=s.p_home_win_120, p_draw_120=s.p_draw_120, p_away_win_120=s.p_away_win_120,
            p_goes_to_extra_time=s.p_goes_to_extra_time, p_goes_to_penalties=s.p_goes_to_penalties,
            p_home_advances=s.p_home_advances, p_away_advances=s.p_away_advances,
            p_home_wins_penalties_given_pens=0.5, p_away_wins_penalties_given_pens=0.5,
            diagnostics={},
        )

    def test_advance_ev_for_home_prediction(self):
        # Predict 1-0 (home advances). advance=3 pts. Home advances in
        # 0.50 + 0.25 = 0.75 of states → EV contribution 2.25.
        rules = [ScoringRule("advance", "Advance", 3.0, True, 7, phase="knockout")]
        recs = compute_expected_points_from_terminal_states(
            self._model(), rules, ScoringBasis.NINETY_MINUTES_EXTRA_TIME_PENALTIES, 2,
            combine_mode=COMBINE_ADDITIVE, phase="knockout",
        )
        pick = next(r for r in recs if (r.predicted_home, r.predicted_away) == (1, 0))
        assert pick.expected_points == pytest.approx(2.25)
        assert pick.scoring_breakdown["advance"] == pytest.approx(2.25)

    def test_penalty_winner_ev_for_draw_home_pens(self):
        # Predict 1-1, home on pens. penalty_winner=3. Only the 0.25 home-pens
        # state matches → EV 0.75.
        rules = [ScoringRule("penalty_winner", "Pens", 3.0, True, 8, phase="knockout")]
        recs = compute_expected_points_from_terminal_states(
            self._model(), rules, ScoringBasis.NINETY_MINUTES_EXTRA_TIME_PENALTIES, 2,
            combine_mode=COMBINE_ADDITIVE, phase="knockout",
        )
        pick = next(
            r for r in recs
            if (r.predicted_home, r.predicted_away) == (1, 1) and r.penalties_winner == "home"
        )
        assert pick.expected_points == pytest.approx(0.75)

    def test_zero_point_probability(self):
        # exact_score on 1-0 prediction: scores only in the 0.50 home-win state,
        # so zero-point probability is 0.50.
        rules = [ScoringRule("exact_score", "Exact", 6.0, True, 1, phase="knockout")]
        recs = compute_expected_points_from_terminal_states(
            self._model(), rules, ScoringBasis.NINETY_MINUTES_EXTRA_TIME_PENALTIES, 2,
            combine_mode=COMBINE_BEST, phase="knockout",
        )
        pick = next(r for r in recs if (r.predicted_home, r.predicted_away) == (1, 0))
        assert pick.zero_point_probability == pytest.approx(0.50)
        assert pick.expected_points == pytest.approx(3.0)

    def test_variance_includes_all_components(self):
        rules = [
            ScoringRule("exact_score", "Exact", 6.0, True, 1, phase="knockout"),
            ScoringRule("advance", "Advance", 3.0, True, 7, phase="knockout"),
        ]
        recs = compute_expected_points_from_terminal_states(
            self._model(), rules, ScoringBasis.NINETY_MINUTES_EXTRA_TIME_PENALTIES, 2,
            combine_mode=COMBINE_ADDITIVE, phase="knockout",
        )
        # Predict 1-0: points per state are
        #   1-0 home win:  exact 6 + advance 3 = 9   (p=0.50)
        #   1-1 home pens: advance 3                 (p=0.25)
        #   1-1 away pens: 0                         (p=0.25)
        pick = next(r for r in recs if (r.predicted_home, r.predicted_away) == (1, 0))
        ep = 0.5 * 9 + 0.25 * 3 + 0.25 * 0
        ep2 = 0.5 * 81 + 0.25 * 9 + 0.25 * 0
        assert pick.expected_points == pytest.approx(ep)
        assert pick.variance == pytest.approx(ep2 - ep * ep)


# ── penalties never alter score-based rules ──────────────────────────────────


class TestPenaltiesDoNotAlterScore:
    def test_exact_score_uses_120_not_penalties(self):
        # 0-0 after ET, decided on penalties for home. exact_score for a 0-0
        # prediction must still apply (penalties add no goals).
        st = TerminalOutcomeState(0, 0, 0, 0, True, True, "home", "home",
                                  TerminalStateKind.DECIDED_ON_PENALTIES.value, 1.0)
        rules = [ScoringRule("exact_score", "Exact", 6.0, True, 1, phase="knockout")]
        pred = CandidatePrediction(0, 0, "home")
        pts, _ = score_prediction_against_state(
            pred, st, rules, ScoreHorizon.AFTER_EXTRA_TIME_120, OutcomeHorizon.ADVANCEMENT,
            scoring_basis=ScoringBasis.NINETY_MINUTES_EXTRA_TIME_PENALTIES,
            combine_mode=COMBINE_BEST, cap=None, phase="knockout",
        )
        assert pts == 6.0


# ── pool-config consistency validation ───────────────────────────────────────


class _Rule:
    def __init__(self, code, enabled=True, phase="knockout"):
        self.code = code
        self.enabled = enabled
        self.phase = phase


class TestPoolConfigConsistency:
    def test_advance_invalid_for_ninety(self):
        errs = validate_pool_config_scoring_consistency(
            "ninety_minutes", [_Rule("advance")]
        )
        assert errs

    def test_penalty_winner_invalid_for_extra_time(self):
        errs = validate_pool_config_scoring_consistency(
            "ninety_minutes_extra_time", [_Rule("penalty_winner")]
        )
        assert errs

    def test_valid_for_pens(self):
        errs = validate_pool_config_scoring_consistency(
            "ninety_minutes_extra_time_penalties",
            [_Rule("advance"), _Rule("penalty_winner"), _Rule("exact_score")],
        )
        assert errs == []

    def test_disabled_rules_ignored(self):
        errs = validate_pool_config_scoring_consistency(
            "ninety_minutes", [_Rule("advance", enabled=False)]
        )
        assert errs == []

    def test_group_rules_ignored(self):
        errs = validate_pool_config_scoring_consistency(
            "ninety_minutes", [_Rule("advance", phase="group")]
        )
        assert errs == []
