"""Tests for CSV and Excel export service."""
import pytest
from unittest.mock import MagicMock
from app.services.export_service import build_csv, build_excel


def make_mock_run():
    run = MagicMock()
    run.id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    run.run_type = "manual"
    run.status = "completed"
    run.started_at = None
    run.completed_at = None
    run.parameters = {"candidate_max_goals": 5}
    pool_config = MagicMock()
    pool_config.name = "Test Pool"
    pool_config.candidate_max_goals = 5
    pool_config.ranking_metric = "expected_points"
    pool_config.scoring_mode = "standard"

    rule1 = MagicMock()
    rule1.code = "exact_score"
    rule1.label = "Exact Score"
    rule1.points = 10.0
    rule1.enabled = True
    rule1.display_specificity_rank = 1
    rule1.description = "Exact score"

    pool_config.scoring_rules = [rule1]
    run.pool_config = pool_config
    return run


def make_mock_fit(match_label="Spain vs Japan", n_recs=5):
    fit = MagicMock()
    fit.match_id = "00000000-0000-0000-0000-000000000001"
    fit.fit_status = "good"
    fit.lambda_home = 1.5
    fit.lambda_away = 0.9
    fit.fitted_home_win_prob = 0.63
    fit.fitted_draw_prob = 0.22
    fit.fitted_away_win_prob = 0.15
    fit.market_home_win_prob = 0.64
    fit.market_draw_prob = 0.21
    fit.market_away_win_prob = 0.15
    fit.fit_error = 0.001
    fit.diagnostics = {
        "rmse": 0.015,
        "market_targets": {"home_win": 0.64, "draw": 0.21, "away_win": 0.15, "over_2_5": 0.50},
        "fitted_probabilities": {"home_win": 0.63, "draw": 0.22, "away_win": 0.15, "over_2_5": 0.51},
        "warnings": [],
    }

    match = MagicMock()
    home_team = MagicMock()
    home_team.name = "Spain"
    away_team = MagicMock()
    away_team.name = "Japan"
    match.home_team = home_team
    match.away_team = away_team
    match.home_placeholder = None
    match.away_placeholder = None
    match.manual_overrides = []
    fit.match = match

    recs = []
    for i in range(n_recs):
        rec = MagicMock()
        rec.rank = i + 1
        rec.predicted_home_goals = i % 3
        rec.predicted_away_goals = max(0, i % 2)
        rec.expected_points = 5.0 - i * 0.5
        rec.variance_points = 1.0
        rec.zero_point_probability = 0.2
        rec.score_probability = 0.05
        recs.append(rec)
    fit.score_recommendations = recs

    return fit


class TestBuildCsv:
    def test_returns_bytes(self):
        run = make_mock_run()
        fits = [make_mock_fit()]
        result = build_csv(run, fits)
        assert isinstance(result, bytes)

    def test_csv_has_header(self):
        run = make_mock_run()
        fits = [make_mock_fit()]
        result = build_csv(run, fits).decode("utf-8")
        assert "match_id" in result
        assert "rank" in result
        assert "expected_points" in result

    def test_csv_contains_match_name(self):
        run = make_mock_run()
        fits = [make_mock_fit()]
        result = build_csv(run, fits).decode("utf-8")
        assert "Spain vs Japan" in result

    def test_csv_top_n_respected(self):
        run = make_mock_run()
        fits = [make_mock_fit(n_recs=10)]
        # top_n=2 -> only 2 rows per match
        result = build_csv(run, fits, top_n=2).decode("utf-8")
        lines = [l for l in result.strip().split("\n") if l and "Spain" in l]
        assert len(lines) == 2

    def test_csv_empty_fits(self):
        run = make_mock_run()
        result = build_csv(run, [])
        assert isinstance(result, bytes)
        # Should at least have header
        assert b"match_id" in result


class TestBuildExcel:
    def test_returns_bytes(self):
        run = make_mock_run()
        fits = [make_mock_fit()]
        result = build_excel(run, fits)
        assert isinstance(result, bytes)
        # Excel files start with PK (zip magic)
        assert result[:2] == b"PK"

    def test_excel_multiple_fits(self):
        run = make_mock_run()
        fits = [make_mock_fit("Spain vs Japan"), make_mock_fit("Germany vs Mexico")]
        result = build_excel(run, fits)
        assert isinstance(result, bytes)
        assert len(result) > 5000  # Should be a real xlsx

    def test_excel_with_no_fits(self):
        run = make_mock_run()
        result = build_excel(run, [])
        assert isinstance(result, bytes)
        assert result[:2] == b"PK"

    def test_excel_top_n_respected(self):
        run = make_mock_run()
        fits = [make_mock_fit(n_recs=10)]
        # Should not raise
        result = build_excel(run, fits, top_n=2)
        assert isinstance(result, bytes)
