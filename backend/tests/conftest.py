"""Test configuration and fixtures."""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.scoring import ScoringRule


@pytest.fixture
def default_rules() -> list[ScoringRule]:
    """A best-match scoring ladder using the unified component catalog."""
    return [
        ScoringRule(code="exact_score", label="Exact score", points=6.0, enabled=True, display_specificity_rank=1),
        ScoringRule(code="goal_difference", label="Result + goal difference", points=4.0, enabled=True, display_specificity_rank=2),
        ScoringRule(code="outcome_team_goals", label="Result + a team's goals", points=3.0, enabled=True, display_specificity_rank=3),
        ScoringRule(code="correct_outcome", label="Correct result", points=2.0, enabled=True, display_specificity_rank=4),
        ScoringRule(code="team_goals", label="A team's goals", points=1.0, enabled=True, display_specificity_rank=5),
        ScoringRule(code="total_goals", label="Correct total goals", points=1.0, enabled=False, display_specificity_rank=6),
    ]


@pytest.fixture
async def client():
    """Async test client that doesn't require a real DB."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
