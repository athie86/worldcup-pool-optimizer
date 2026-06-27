"""Horizon-consistent knockout model (spec: Full Horizon-Consistent Knockout Model).

The 90-minute score matrix alone cannot score a pool whose rules may be settled
on three different bases (90 minutes / after extra time / after penalties). This
module is the single source of truth for the *full* match-state distribution and
for evaluating scoring rules against it in a basis-consistent way.

Key invariant
-------------
Penalty-shootout goals are **never** added to a football scoreline. Penalties
decide the *advancing team*, not the score. Therefore the model exposes three
surfaces:

  * ``score_matrix_90``   — score after regulation
  * ``score_matrix_120``  — score after extra time (penalty goals excluded)
  * ``terminal_states``   — the joint distribution over (score_90, score_120,
    extra time, penalties, penalty winner, advancing team)

The optimizer evaluates every candidate prediction against every terminal state,
so expected points, variance and zero-point probability are all consistent with
the selected scoring basis.

The 90-minute engine itself is unchanged — this module consumes its output
(a normalized ``P90`` matrix + expected goals) and builds everything else around
it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
from scipy.stats import poisson  # type: ignore[import]

from .scoring import (
    ScoringRule,
    result,
    COMBINE_ADDITIVE,
    COMBINE_BEST,
    KNOCKOUT_BONUS_CODES,
    applies as _score_applies,
)


# ── Horizon vocabulary ──────────────────────────────────────────────────────


class ScoringBasis(str, Enum):
    NINETY_MINUTES = "ninety_minutes"
    NINETY_MINUTES_EXTRA_TIME = "ninety_minutes_extra_time"
    NINETY_MINUTES_EXTRA_TIME_PENALTIES = "ninety_minutes_extra_time_penalties"


class ScoreHorizon(str, Enum):
    REGULATION_90 = "regulation_90"
    AFTER_EXTRA_TIME_120 = "after_extra_time_120"


class OutcomeHorizon(str, Enum):
    REGULATION_90 = "regulation_90"
    AFTER_EXTRA_TIME_120 = "after_extra_time_120"
    ADVANCEMENT = "advancement"


class TerminalStateKind(str, Enum):
    DECIDED_IN_90 = "decided_in_90"
    DECIDED_IN_EXTRA_TIME = "decided_in_extra_time"
    DECIDED_ON_PENALTIES = "decided_on_penalties"


def basis_to_horizons(scoring_basis: ScoringBasis | str) -> tuple[ScoreHorizon, OutcomeHorizon]:
    """Map a scoring basis to the (score horizon, outcome horizon) it consumes."""
    basis = ScoringBasis(scoring_basis)
    if basis == ScoringBasis.NINETY_MINUTES:
        return ScoreHorizon.REGULATION_90, OutcomeHorizon.REGULATION_90
    if basis == ScoringBasis.NINETY_MINUTES_EXTRA_TIME:
        return ScoreHorizon.AFTER_EXTRA_TIME_120, OutcomeHorizon.AFTER_EXTRA_TIME_120
    if basis == ScoringBasis.NINETY_MINUTES_EXTRA_TIME_PENALTIES:
        return ScoreHorizon.AFTER_EXTRA_TIME_120, OutcomeHorizon.ADVANCEMENT
    raise ValueError(f"Unsupported scoring basis: {scoring_basis}")


# ── Model output contract ───────────────────────────────────────────────────


@dataclass
class TerminalOutcomeState:
    score_90_home: int
    score_90_away: int

    score_120_home: int
    score_120_away: int

    went_to_extra_time: bool
    went_to_penalties: bool

    advancing_team: Optional[str]   # "home" | "away" | None
    penalty_winner: Optional[str]   # "home" | "away" | None

    state_kind: str                 # TerminalStateKind value
    probability: float


@dataclass
class HorizonModelResult:
    model_type: str
    model_version: str

    score_matrix_90: np.ndarray
    score_matrix_120: np.ndarray

    terminal_states: list[TerminalOutcomeState]

    p_home_win_90: float
    p_draw_90: float
    p_away_win_90: float

    p_home_win_120: float
    p_draw_120: float
    p_away_win_120: float

    p_goes_to_extra_time: float
    p_goes_to_penalties: float

    p_home_advances: float
    p_away_advances: float

    p_home_wins_penalties_given_pens: float
    p_away_wins_penalties_given_pens: float

    diagnostics: dict

    # ── Backward-compat / convenience ──────────────────────────────────────
    # ``score_matrix`` aliases ``score_matrix_90`` so existing callers (DB
    # writes, diagnostics, heatmaps) keep working unchanged.
    fit_tier: Optional[str] = None
    lambda_home: Optional[float] = None
    lambda_away: Optional[float] = None

    @property
    def score_matrix(self) -> np.ndarray:
        return self.score_matrix_90


@dataclass
class CandidatePrediction:
    predicted_home: int
    predicted_away: int
    predicted_penalty_winner: Optional[str] = None


# ── Extra-time distribution ─────────────────────────────────────────────────

# Extra time is 30 minutes and lower intensity than a linear time-scaled
# continuation of regulation. r_ET shrinks the scaled rate accordingly.
DEFAULT_ET_RATE = 0.70
DEFAULT_ET_MAX = 4


def build_extra_time_distribution(
    lambda_home: float,
    lambda_away: float,
    et_max: int = DEFAULT_ET_MAX,
    *,
    r_et: float = DEFAULT_ET_RATE,
    rho: float = 0.0,
) -> np.ndarray:
    """P(home ET goals = u, away ET goals = v | tied after 90), an (et_max+1)² grid.

    Extra-time goal rates are the 90-minute rates scaled by 30/90 and an ET
    intensity multiplier ``r_et``. A small Dixon-Coles ``rho`` correction is
    applied to the low-score cells when provided.
    """
    mu_home = max(1e-6, float(lambda_home) * (30.0 / 90.0) * r_et)
    mu_away = max(1e-6, float(lambda_away) * (30.0 / 90.0) * r_et)

    rng = np.arange(et_max + 1)
    grid = np.outer(poisson.pmf(rng, mu_home), poisson.pmf(rng, mu_away))

    if rho:
        # Dixon-Coles low-score correction (same form as the 90-minute model).
        if et_max >= 1:
            grid[0, 0] *= max(0.0, 1.0 - mu_home * mu_away * rho)
            grid[0, 1] *= max(0.0, 1.0 + mu_home * rho)
            grid[1, 0] *= max(0.0, 1.0 + mu_away * rho)
            grid[1, 1] *= max(0.0, 1.0 - rho)

    total = grid.sum()
    if total > 1e-12:
        grid /= total
    return grid


# ── Penalty shootout probability ────────────────────────────────────────────

_PEN_INFERRED_CLIP = (0.25, 0.75)
_PEN_FALLBACK_CLIP = (0.40, 0.60)
_PEN_FALLBACK_TILT = 0.35


def infer_penalty_probability(
    lambda_home: float,
    lambda_away: float,
    *,
    p_home_win_90: float,
    p_draw_90: float,
    p_home_wins_et_given_et: float,
    p_still_draw_after_et_given_et: float,
    p_home_adv_market: Optional[float] = None,
    reliability: float = 0.0,
) -> float:
    """Estimate q = P(home wins shootout | match goes to penalties).

    When an advancement (``to_qualify``) market is available, invert the
    advancement identity to back out q, then bound and shrink toward 0.5 by the
    market ``reliability``. Otherwise fall back to a goal-rate tilt clipped tight
    around 0.5 — shootouts are close to a coin flip.
    """
    denom = p_draw_90 * p_still_draw_after_et_given_et
    if p_home_adv_market is not None and denom > 1e-9:
        q = (
            p_home_adv_market
            - p_home_win_90
            - p_draw_90 * p_home_wins_et_given_et
        ) / denom
        q = float(np.clip(q, *_PEN_INFERRED_CLIP))
        rel = float(np.clip(reliability, 0.0, 1.0))
        return 0.5 + rel * (q - 0.5)

    total = float(lambda_home) + float(lambda_away)
    q_raw = (float(lambda_home) / total) if total > 0 else 0.5
    q = 0.5 + _PEN_FALLBACK_TILT * (q_raw - 0.5)
    return float(np.clip(q, *_PEN_FALLBACK_CLIP))


# ── Terminal-state generation ───────────────────────────────────────────────


def build_terminal_states(
    p90: np.ndarray,
    pet: np.ndarray,
    q_home_pens: float,
    *,
    prob_floor: float = 1e-12,
) -> list[TerminalOutcomeState]:
    """Build the full terminal-state distribution from P90, PET and q.

    Each regulation cell either decides the tie in 90 minutes or (if level) opens
    an extra-time sub-distribution, which in turn either decides the tie in ET or
    goes to penalties (split by ``q_home_pens``). Penalty goals are never added
    to a scoreline; only ``advancing_team`` / ``penalty_winner`` change.
    """
    p90 = np.asarray(p90, dtype=float)
    pet = np.asarray(pet, dtype=float)
    n = p90.shape[0]
    et_n = pet.shape[0]
    states: list[TerminalOutcomeState] = []

    for i in range(n):
        for j in range(n):
            p = float(p90[i, j])
            if p <= prob_floor:
                continue

            if i > j:
                states.append(TerminalOutcomeState(
                    score_90_home=i, score_90_away=j,
                    score_120_home=i, score_120_away=j,
                    went_to_extra_time=False, went_to_penalties=False,
                    advancing_team="home", penalty_winner=None,
                    state_kind=TerminalStateKind.DECIDED_IN_90.value,
                    probability=p,
                ))
            elif i < j:
                states.append(TerminalOutcomeState(
                    score_90_home=i, score_90_away=j,
                    score_120_home=i, score_120_away=j,
                    went_to_extra_time=False, went_to_penalties=False,
                    advancing_team="away", penalty_winner=None,
                    state_kind=TerminalStateKind.DECIDED_IN_90.value,
                    probability=p,
                ))
            else:
                # Level after 90 → extra time.
                for u in range(et_n):
                    for v in range(et_n):
                        pe = float(pet[u, v])
                        if pe <= prob_floor:
                            continue
                        base = p * pe
                        h120, a120 = i + u, j + v
                        if u > v:
                            states.append(TerminalOutcomeState(
                                score_90_home=i, score_90_away=j,
                                score_120_home=h120, score_120_away=a120,
                                went_to_extra_time=True, went_to_penalties=False,
                                advancing_team="home", penalty_winner=None,
                                state_kind=TerminalStateKind.DECIDED_IN_EXTRA_TIME.value,
                                probability=base,
                            ))
                        elif u < v:
                            states.append(TerminalOutcomeState(
                                score_90_home=i, score_90_away=j,
                                score_120_home=h120, score_120_away=a120,
                                went_to_extra_time=True, went_to_penalties=False,
                                advancing_team="away", penalty_winner=None,
                                state_kind=TerminalStateKind.DECIDED_IN_EXTRA_TIME.value,
                                probability=base,
                            ))
                        else:
                            states.append(TerminalOutcomeState(
                                score_90_home=i, score_90_away=j,
                                score_120_home=h120, score_120_away=a120,
                                went_to_extra_time=True, went_to_penalties=True,
                                advancing_team="home", penalty_winner="home",
                                state_kind=TerminalStateKind.DECIDED_ON_PENALTIES.value,
                                probability=base * q_home_pens,
                            ))
                            states.append(TerminalOutcomeState(
                                score_90_home=i, score_90_away=j,
                                score_120_home=h120, score_120_away=a120,
                                went_to_extra_time=True, went_to_penalties=True,
                                advancing_team="away", penalty_winner="away",
                                state_kind=TerminalStateKind.DECIDED_ON_PENALTIES.value,
                                probability=base * (1.0 - q_home_pens),
                            ))
    return states


def derive_score_matrix_90(states: list[TerminalOutcomeState], n: int) -> np.ndarray:
    mat = np.zeros((n, n), dtype=float)
    for s in states:
        if s.score_90_home < n and s.score_90_away < n:
            mat[s.score_90_home, s.score_90_away] += s.probability
    return mat


def derive_score_matrix_120(states: list[TerminalOutcomeState], n: int) -> np.ndarray:
    mat = np.zeros((n, n), dtype=float)
    for s in states:
        h = min(s.score_120_home, n - 1)
        a = min(s.score_120_away, n - 1)
        mat[h, a] += s.probability
    return mat


@dataclass
class _TerminalSummary:
    p_home_win_90: float
    p_draw_90: float
    p_away_win_90: float
    p_home_win_120: float
    p_draw_120: float
    p_away_win_120: float
    p_goes_to_extra_time: float
    p_goes_to_penalties: float
    p_home_advances: float
    p_away_advances: float


def summarize_terminal_states(states: list[TerminalOutcomeState]) -> _TerminalSummary:
    hw90 = dr90 = aw90 = 0.0
    hw120 = dr120 = aw120 = 0.0
    p_et = p_pens = 0.0
    p_home_adv = p_away_adv = 0.0
    for s in states:
        p = s.probability
        # 90-minute result
        if s.score_90_home > s.score_90_away:
            hw90 += p
        elif s.score_90_home == s.score_90_away:
            dr90 += p
        else:
            aw90 += p
        # 120-minute result
        if s.score_120_home > s.score_120_away:
            hw120 += p
        elif s.score_120_home == s.score_120_away:
            dr120 += p
        else:
            aw120 += p
        if s.went_to_extra_time:
            p_et += p
        if s.went_to_penalties:
            p_pens += p
        if s.advancing_team == "home":
            p_home_adv += p
        elif s.advancing_team == "away":
            p_away_adv += p
    return _TerminalSummary(
        hw90, dr90, aw90, hw120, dr120, aw120, p_et, p_pens, p_home_adv, p_away_adv,
    )


def validate_terminal_states(
    states: list[TerminalOutcomeState],
    score_matrix_90: np.ndarray,
    score_matrix_120: np.ndarray,
    summary: _TerminalSummary,
    *,
    tol: float = 1e-6,
) -> list[str]:
    """Return a list of validation warnings (empty when everything checks out)."""
    warnings: list[str] = []
    total = sum(s.probability for s in states)
    if abs(total - 1.0) > tol:
        warnings.append(f"Terminal state probabilities sum to {total:.8f}, not 1.")
    if abs(score_matrix_90.sum() - 1.0) > tol:
        warnings.append(f"score_matrix_90 sums to {score_matrix_90.sum():.8f}, not 1.")
    if abs(score_matrix_120.sum() - 1.0) > tol:
        warnings.append(f"score_matrix_120 sums to {score_matrix_120.sum():.8f}, not 1.")
    adv = summary.p_home_advances + summary.p_away_advances
    if abs(adv - 1.0) > tol:
        warnings.append(f"Advancement probabilities sum to {adv:.8f}, not 1.")
    return warnings


# ── Rule metadata ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RuleDefinition:
    code: str
    score_dependent: bool
    outcome_dependent: bool
    terminal_dependent: bool
    valid_phases: frozenset
    valid_scoring_bases: frozenset


_ALL_BASES = frozenset({b.value for b in ScoringBasis})
_BOTH_PHASES = frozenset({"group", "knockout"})
_KO_ONLY = frozenset({"knockout"})
_ET_PENS_ONLY = frozenset({ScoringBasis.NINETY_MINUTES_EXTRA_TIME_PENALTIES.value})


RULE_DEFINITIONS: dict[str, RuleDefinition] = {
    "exact_score": RuleDefinition("exact_score", True, False, False, _BOTH_PHASES, _ALL_BASES),
    "goal_difference": RuleDefinition("goal_difference", True, False, False, _BOTH_PHASES, _ALL_BASES),
    "outcome_team_goals": RuleDefinition("outcome_team_goals", True, True, False, _BOTH_PHASES, _ALL_BASES),
    "correct_outcome": RuleDefinition("correct_outcome", False, True, False, _BOTH_PHASES, _ALL_BASES),
    "team_goals": RuleDefinition("team_goals", True, False, False, _BOTH_PHASES, _ALL_BASES),
    "total_goals": RuleDefinition("total_goals", True, False, False, _BOTH_PHASES, _ALL_BASES),
    "advance": RuleDefinition("advance", False, False, True, _KO_ONLY, _ET_PENS_ONLY),
    "penalty_winner": RuleDefinition("penalty_winner", False, False, True, _KO_ONLY, _ET_PENS_ONLY),
}


def rule_is_valid_for_basis(code: str, phase: str, scoring_basis: ScoringBasis | str) -> bool:
    """Whether a rule code can be scored for a given phase + knockout basis.

    Unknown codes default to valid so a future component can never silently
    break an existing pool. Group-phase rules always score at 90 minutes.
    """
    definition = RULE_DEFINITIONS.get(code)
    if definition is None:
        return True
    if phase not in definition.valid_phases:
        return False
    if phase == "group":
        return True
    basis = ScoringBasis(scoring_basis).value
    return basis in definition.valid_scoring_bases


# ── Candidate generation ────────────────────────────────────────────────────


def generate_candidates(candidate_max: int, scoring_basis: ScoringBasis | str) -> list[CandidatePrediction]:
    """Enumerate candidate predictions for a scoring basis.

    Under the extra-time-plus-penalties basis a predicted draw is ambiguous about
    who advances, so each draw is expanded into a home-pens and an away-pens
    variant. All other bases generate plain score candidates.
    """
    basis = ScoringBasis(scoring_basis)
    candidates: list[CandidatePrediction] = []
    for ph in range(candidate_max + 1):
        for pa in range(candidate_max + 1):
            if basis == ScoringBasis.NINETY_MINUTES_EXTRA_TIME_PENALTIES and ph == pa:
                candidates.append(CandidatePrediction(ph, pa, "home"))
                candidates.append(CandidatePrediction(ph, pa, "away"))
            else:
                candidates.append(CandidatePrediction(ph, pa, None))
    return candidates


# ── Basis-aware actual / predicted helpers ──────────────────────────────────


def actual_score_for_basis(state: TerminalOutcomeState, score_horizon: ScoreHorizon) -> tuple[int, int]:
    if score_horizon == ScoreHorizon.REGULATION_90:
        return state.score_90_home, state.score_90_away
    if score_horizon == ScoreHorizon.AFTER_EXTRA_TIME_120:
        return state.score_120_home, state.score_120_away
    raise ValueError(score_horizon)


def actual_outcome_for_basis(state: TerminalOutcomeState, outcome_horizon: OutcomeHorizon) -> str:
    if outcome_horizon == OutcomeHorizon.REGULATION_90:
        return result(state.score_90_home, state.score_90_away)
    if outcome_horizon == OutcomeHorizon.AFTER_EXTRA_TIME_120:
        return result(state.score_120_home, state.score_120_away)
    if outcome_horizon == OutcomeHorizon.ADVANCEMENT:
        if state.advancing_team == "home":
            return "home_win"
        if state.advancing_team == "away":
            return "away_win"
        raise ValueError("Terminal advancement outcome missing")
    raise ValueError(outcome_horizon)


def predicted_outcome_for_basis(pred: CandidatePrediction, outcome_horizon: OutcomeHorizon) -> Optional[str]:
    if outcome_horizon in (OutcomeHorizon.REGULATION_90, OutcomeHorizon.AFTER_EXTRA_TIME_120):
        return result(pred.predicted_home, pred.predicted_away)
    if outcome_horizon == OutcomeHorizon.ADVANCEMENT:
        if pred.predicted_home > pred.predicted_away:
            return "home_win"
        if pred.predicted_away > pred.predicted_home:
            return "away_win"
        if pred.predicted_penalty_winner == "home":
            return "home_win"
        if pred.predicted_penalty_winner == "away":
            return "away_win"
        # Draw prediction with no penalty pick: advancement is undefined.
        return None
    raise ValueError(outcome_horizon)


# ── Rule scoring against a terminal state ───────────────────────────────────


def _rule_applies(
    code: str,
    pred: CandidatePrediction,
    state: TerminalOutcomeState,
    actual_score: tuple[int, int],
    predicted_outcome: Optional[str],
    actual_outcome: str,
    config: Optional[dict],
) -> bool:
    """Horizon-aware rule predicate.

    Score-only components delegate to the shared ``scoring.applies`` using the
    basis-appropriate actual score (so penalty goals never leak in). Outcome and
    terminal components are evaluated against the basis-appropriate outcome and
    the terminal state fields.
    """
    ph, pa = pred.predicted_home, pred.predicted_away
    ah, aa = actual_score

    if code in ("exact_score", "goal_difference", "team_goals", "total_goals"):
        return _score_applies(code, ph, pa, ah, aa, config=config)

    if code == "correct_outcome":
        return predicted_outcome is not None and predicted_outcome == actual_outcome

    if code == "outcome_team_goals":
        is_exact = (ph == ah and pa == aa)
        team_goal_match = (ph == ah or pa == aa)
        return (
            predicted_outcome is not None
            and predicted_outcome == actual_outcome
            and actual_outcome != "draw"
            and team_goal_match
            and not is_exact
        )

    if code == "advance":
        pred_adv = _predicted_advancer(pred)
        return pred_adv is not None and state.advancing_team is not None and pred_adv == state.advancing_team

    if code == "penalty_winner":
        if pred.predicted_home != pred.predicted_away:
            return False
        if not state.went_to_penalties:
            return False
        ppw = pred.predicted_penalty_winner
        return ppw is not None and state.penalty_winner is not None and ppw == state.penalty_winner

    return False


def _predicted_advancer(pred: CandidatePrediction) -> Optional[str]:
    if pred.predicted_home > pred.predicted_away:
        return "home"
    if pred.predicted_away > pred.predicted_home:
        return "away"
    return pred.predicted_penalty_winner


def score_prediction_against_state(
    pred: CandidatePrediction,
    state: TerminalOutcomeState,
    rules: list[ScoringRule],
    score_horizon: ScoreHorizon,
    outcome_horizon: OutcomeHorizon,
    *,
    scoring_basis: ScoringBasis,
    combine_mode: str,
    cap: Optional[float],
    phase: str,
) -> tuple[float, dict[str, float]]:
    """Points the prediction earns against one terminal state, plus a breakdown.

    Per-match score components combine by ``combine_mode``; knockout progression
    bonuses (advance / penalty_winner) always sum on top; the total is capped.
    The breakdown carries the raw component points (uncapped) for attribution.
    """
    actual_score = actual_score_for_basis(state, score_horizon)
    actual_outcome = actual_outcome_for_basis(state, outcome_horizon)
    predicted_outcome = predicted_outcome_for_basis(pred, outcome_horizon)

    score_components: list[tuple[str, float]] = []
    bonus_total = 0.0
    breakdown: dict[str, float] = {}

    for rule in rules:
        if not rule.enabled or rule.phase != phase:
            continue
        if not rule_is_valid_for_basis(rule.code, phase, scoring_basis):
            continue
        if not _rule_applies(
            rule.code, pred, state, actual_score, predicted_outcome, actual_outcome, rule.config,
        ):
            continue
        if rule.code in KNOCKOUT_BONUS_CODES:
            bonus_total += rule.points
            breakdown[rule.code] = rule.points
        else:
            score_components.append((rule.code, rule.points))

    if combine_mode == COMBINE_ADDITIVE:
        base = sum(points for _, points in score_components)
        for code, points in score_components:
            breakdown[code] = points
    else:
        if score_components:
            code, base = _select_best_component(score_components, rules)
            breakdown[code] = base
        else:
            base = 0.0

    total = base + bonus_total
    if cap is not None:
        total = min(total, cap)
    return total, breakdown


def _select_best_component(
    components: list[tuple[str, float]], rules: list[ScoringRule]
) -> tuple[str, float]:
    """Pick the highest-value matching component, tie-broken by specificity."""
    best_points = max(points for _, points in components)
    rank = {r.code: r.display_specificity_rank for r in rules}
    best_code = min(
        (code for code, points in components if points == best_points),
        key=lambda c: rank.get(c, 999),
    )
    return best_code, best_points


# ── Expected points over the terminal-state distribution ────────────────────


# Import here to avoid a circular import at module load (optimizer imports this
# module indirectly only at call time).
def compute_expected_points_from_terminal_states(
    model: HorizonModelResult,
    rules: list[ScoringRule],
    scoring_basis: ScoringBasis | str,
    candidate_max: int,
    *,
    combine_mode: str = COMBINE_BEST,
    cap: Optional[float] = None,
    phase: str = "knockout",
):
    """Rank candidate predictions by expected points over the terminal states.

    Returns ``optimizer.Recommendation`` objects (imported lazily to avoid a
    circular import). Variance and zero-point probability are computed from the
    full terminal-state distribution, so every scoring basis is handled
    consistently.
    """
    from .optimizer import Recommendation  # local import: optimizer imports horizon

    basis = ScoringBasis(scoring_basis)
    score_horizon, outcome_horizon = basis_to_horizons(basis)
    candidates = generate_candidates(candidate_max, basis)

    # Probability of each exact score at the score horizon (for tie-break / display).
    if score_horizon == ScoreHorizon.REGULATION_90:
        score_mat = model.score_matrix_90
    else:
        score_mat = model.score_matrix_120
    mat_n = score_mat.shape[0]

    recommendations = []
    for pred in candidates:
        ep = 0.0
        ep2 = 0.0
        p_zero = 0.0
        breakdown: dict[str, float] = {}

        for state in model.terminal_states:
            pts, component_points = score_prediction_against_state(
                pred, state, rules, score_horizon, outcome_horizon,
                scoring_basis=basis, combine_mode=combine_mode, cap=cap, phase=phase,
            )
            p = state.probability
            ep += p * pts
            ep2 += p * pts * pts
            if pts == 0:
                p_zero += p
            for code, cpts in component_points.items():
                breakdown[code] = breakdown.get(code, 0.0) + p * cpts

        variance = max(0.0, ep2 - ep * ep)
        if pred.predicted_home < mat_n and pred.predicted_away < mat_n:
            score_prob = float(score_mat[pred.predicted_home, pred.predicted_away])
        else:
            score_prob = 0.0

        recommendations.append(Recommendation(
            predicted_home=pred.predicted_home,
            predicted_away=pred.predicted_away,
            rank=0,
            expected_points=ep,
            variance=variance,
            zero_point_probability=p_zero,
            score_probability=score_prob,
            scoring_breakdown=breakdown,
            penalties_winner=pred.predicted_penalty_winner,
            predicted_advancer=_predicted_advancer(pred),
        ))

    recommendations.sort(key=lambda r: (
        -r.expected_points,
        r.zero_point_probability,
        r.variance,
        -r.score_probability,
        r.predicted_home + r.predicted_away,
    ))
    for i, r in enumerate(recommendations):
        r.rank = i + 1
    return recommendations


# ── Pool-config / rule consistency validation ───────────────────────────────


def validate_pool_config_scoring_consistency(
    knockout_scoring_basis: str,
    rules: list,
) -> list[str]:
    """Validate that enabled knockout rules are consistent with the pool's basis.

    ``rules`` items only need ``code``, ``enabled`` and ``phase`` attributes
    (works with ORM rows and the service ``ScoringRule`` dataclass alike).
    """
    errors: list[str] = []
    try:
        basis = ScoringBasis(knockout_scoring_basis).value
    except ValueError:
        return [f"Unknown knockout scoring basis: {knockout_scoring_basis}"]

    def _enabled_ko(codes: set[str]) -> bool:
        return any(
            getattr(r, "enabled", False)
            and getattr(r, "phase", "group") == "knockout"
            and getattr(r, "code", None) in codes
            for r in rules
        )

    for rule in rules:
        if not getattr(rule, "enabled", False):
            continue
        if getattr(rule, "phase", "group") != "knockout":
            continue
        code = getattr(rule, "code", None)
        definition = RULE_DEFINITIONS.get(code)
        if definition is None:
            continue
        if basis not in definition.valid_scoring_bases:
            errors.append(f"Rule '{code}' is not valid for knockout basis '{basis}'.")

    if basis == ScoringBasis.NINETY_MINUTES.value and _enabled_ko({"advance", "penalty_winner"}):
        errors.append("advance and penalty_winner require the extra-time-plus-penalties basis.")
    if basis == ScoringBasis.NINETY_MINUTES_EXTRA_TIME.value and _enabled_ko({"penalty_winner"}):
        errors.append("penalty_winner requires the extra-time-plus-penalties basis.")

    # De-duplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out
