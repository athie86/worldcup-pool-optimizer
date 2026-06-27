"""Test configuration and fixtures."""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.scoring import ScoringRule


@pytest.fixture
def default_rules() -> list[ScoringRule]:
    """Standard World Cup scoring rules."""
    return [
        ScoringRule(code="exact_score", label="Exact Score", points=10.0, enabled=True, display_specificity_rank=1),
        ScoringRule(code="correct_winner_goal_difference", label="Correct Winner + GD", points=6.0, enabled=True, display_specificity_rank=2),
        ScoringRule(code="correct_winner_winner_goals", label="Correct Winner + WG", points=5.0, enabled=True, display_specificity_rank=3),
        ScoringRule(code="correct_winner_any_team_goals", label="Correct Winner + Any Team Goals", points=4.0, enabled=True, display_specificity_rank=4),
        ScoringRule(code="correct_winner_only", label="Correct Winner Only", points=3.0, enabled=True, display_specificity_rank=5),
        ScoringRule(code="correct_winner_basic_a", label="Correct Winner (A)", points=3.0, enabled=True, display_specificity_rank=6),
        ScoringRule(code="correct_winner_basic_b", label="Correct Winner (B)", points=3.0, enabled=True, display_specificity_rank=7),
        ScoringRule(code="correct_draw", label="Correct Draw", points=4.0, enabled=True, display_specificity_rank=8),
        ScoringRule(code="wrong_result_team_goal", label="Wrong Result, Team Goal", points=1.0, enabled=True, display_specificity_rank=9),
        ScoringRule(code="wrong_result", label="Wrong Result", points=0.0, enabled=True, display_specificity_rank=10),
    ]


@pytest.fixture
async def client():
    """Async test client that doesn't require a real DB."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
