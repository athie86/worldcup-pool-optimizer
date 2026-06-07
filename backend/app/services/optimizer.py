from dataclasses import dataclass
import numpy as np
from .scoring import ScoringRule, score_points, applies, binary_score_points, result
from .score_model import CalibratedModelResult, CANDIDATE_MAX

# Backward-compat alias so any code that still references FitResult compiles.
FitResult = CalibratedModelResult


@dataclass
class Recommendation:
    predicted_home: int
    predicted_away: int
    rank: int
    expected_points: float
    variance: float
    zero_point_probability: float
    score_probability: float
    scoring_breakdown: dict


def compute_expected_points(
    fit: CalibratedModelResult,
    rules: list[ScoringRule],
    candidate_max: int = CANDIDATE_MAX,
    scoring_mode: str = "standard",
    binary_result_points: float = 1.0,
    binary_total_goals_points: float = 1.0,
) -> list[Recommendation]:
    """Enumerate candidate predictions 0-0 to candidate_max-candidate_max, compute expected points.

    ``scoring_mode`` selects the scoring scheme. "standard" uses the configurable
    ``rules`` (highest applicable rule wins). "binary" ignores ``rules`` and
    awards ``binary_result_points`` for a correct result plus
    ``binary_total_goals_points`` for the correct total goals, independently.
    """
    is_binary = scoring_mode == "binary"
    mat = fit.score_matrix
    fit_max = mat.shape[0] - 1

    results = []

    for ph in range(candidate_max + 1):
        for pa in range(candidate_max + 1):
            ep = 0.0
            ep2 = 0.0
            p_zero = 0.0
            scoring_breakdown: dict[str, float] = {}

            for ah in range(fit_max + 1):
                for aa in range(fit_max + 1):
                    p_actual = float(mat[ah, aa])
                    if p_actual == 0.0:
                        continue
                    if is_binary:
                        pts = binary_score_points(
                            ph, pa, ah, aa,
                            binary_result_points, binary_total_goals_points,
                        )
                    else:
                        pts = score_points(rules, ph, pa, ah, aa)
                    ep += p_actual * pts
                    ep2 += p_actual * pts * pts
                    if pts == 0:
                        p_zero += p_actual
                    # Track scoring breakdown (contribution to EP)
                    if pts > 0 and is_binary:
                        if result(ph, pa) == result(ah, aa) and binary_result_points > 0:
                            scoring_breakdown["correct_result"] = (
                                scoring_breakdown.get("correct_result", 0.0)
                                + p_actual * binary_result_points
                            )
                        if (ph + pa) == (ah + aa) and binary_total_goals_points > 0:
                            scoring_breakdown["correct_total_goals"] = (
                                scoring_breakdown.get("correct_total_goals", 0.0)
                                + p_actual * binary_total_goals_points
                            )
                    elif pts > 0:
                        for rule in rules:
                            if not rule.enabled:
                                continue
                            if applies(rule.code, ph, pa, ah, aa):
                                max_pts = score_points(rules, ph, pa, ah, aa)
                                if abs(rule.points - max_pts) < 1e-9 and rule.points > 0:
                                    scoring_breakdown[rule.code] = (
                                        scoring_breakdown.get(rule.code, 0.0) + p_actual * rule.points
                                    )

            variance = ep2 - ep * ep
            score_prob = float(mat[ph, pa]) if ph <= fit_max and pa <= fit_max else 0.0

            results.append(Recommendation(
                predicted_home=ph,
                predicted_away=pa,
                rank=0,
                expected_points=ep,
                variance=max(0.0, variance),
                zero_point_probability=p_zero,
                score_probability=score_prob,
                scoring_breakdown=scoring_breakdown,
            ))

    # Sort by ranking: EP desc, then zero_prob asc, then variance asc, then score_prob desc, then total goals asc
    results.sort(key=lambda r: (
        -r.expected_points,
        r.zero_point_probability,
        r.variance,
        -r.score_probability,
        r.predicted_home + r.predicted_away,
    ))

    for i, r in enumerate(results):
        r.rank = i + 1

    return results
