import numpy as np
from .poisson_model import FitResult, MarketProbabilities, model_probabilities


def compute_diagnostics(fit_result: FitResult, market_probs: MarketProbabilities) -> dict:
    """Build a diagnostics dict with market vs model comparison."""
    fit_max = fit_result.score_matrix.shape[0] - 1
    model = model_probabilities(fit_result.lambda_home, fit_result.lambda_away, fit_max)

    rows = []
    target_map = {
        "home_win": "Home Win",
        "draw": "Draw",
        "away_win": "Away Win",
        "over_1_5": "Over 1.5",
        "under_1_5": "Under 1.5",
        "over_2_5": "Over 2.5",
        "under_2_5": "Under 2.5",
        "over_3_5": "Over 3.5",
        "under_3_5": "Under 3.5",
    }
    errors = []

    for key, label in target_map.items():
        market_val = (
            getattr(market_probs, key, None)
            or fit_result.diagnostics.get("market_targets", {}).get(key)
        )
        model_val = model.get(key)
        if market_val is not None and model_val is not None:
            error = model_val - market_val
            errors.append(error ** 2)
            rows.append({
                "target": label,
                "market": market_val,
                "model": model_val,
                "error": error,
            })

    rmse = float(np.sqrt(np.mean(errors))) if errors else 0.0

    if rmse <= 0.02:
        status = "good"
    elif rmse <= 0.04:
        status = "acceptable"
    else:
        status = "weak"

    return {
        "lambda_home": fit_result.lambda_home,
        "lambda_away": fit_result.lambda_away,
        "total_expected_goals": fit_result.lambda_home + fit_result.lambda_away,
        "rmse": rmse,
        "fit_status": status,
        "rows": rows,
        "warnings": fit_result.diagnostics.get("warnings", []),
        "score_matrix": fit_result.score_matrix.tolist(),
    }
