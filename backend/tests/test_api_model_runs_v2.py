"""End-to-end integration tests for the V2 model-run flow (spec §14, §22).

These exercise the full HTTP path against the configured database. They are
skipped automatically if the database is unreachable so the rest of the suite
still runs without a DB.
"""
import uuid
import pytest
from sqlalchemy import text
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.security import create_session_token, SESSION_COOKIE_NAME
from app.db.session import AsyncSessionLocal
from app.db import models


@pytest.fixture
def auth_cookies():
    return {SESSION_COOKIE_NAME: create_session_token("admin")}


async def _db_available() -> bool:
    try:
        async with AsyncSessionLocal() as s:
            await s.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _seed_match_with_odds(session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create a complete match with an h2h+totals odds snapshot and a pool."""
    home = models.Team(name=f"Home {uuid.uuid4().hex[:6]}")
    away = models.Team(name=f"Away {uuid.uuid4().hex[:6]}")
    session.add_all([home, away])
    await session.flush()

    match = models.Match(
        stage="group", home_team_id=home.id, away_team_id=away.id,
        status="scheduled", is_complete_for_optimization=True,
    )
    session.add(match)
    await session.flush()

    snap = models.OddsSnapshot(provider="test", status="success")
    session.add(snap)
    await session.flush()

    event = models.OddsEvent(
        odds_snapshot_id=snap.id, match_id=match.id, provider_event_id="evt1",
        sport_key="soccer", home_team=home.name, away_team=away.name,
    )
    session.add(event)
    await session.flush()

    # Two bookmakers each with h2h + totals(2.5)
    for bk in ("pinnacle", "bet365"):
        h2h = models.BookmakerMarket(odds_event_id=event.id, bookmaker_key=bk,
                                     bookmaker_title=bk, market_key="h2h")
        session.add(h2h)
        await session.flush()
        for ot, price in (("home_win", 1.7), ("draw", 3.6), ("away_win", 5.4)):
            session.add(models.MarketOutcome(bookmaker_market_id=h2h.id, outcome_name=ot,
                                             outcome_type=ot, price_decimal=price))
        tot = models.BookmakerMarket(odds_event_id=event.id, bookmaker_key=bk,
                                     bookmaker_title=bk, market_key="totals", line=2.5)
        session.add(tot)
        await session.flush()
        for ot, price in (("over", 1.9), ("under", 1.95)):
            session.add(models.MarketOutcome(bookmaker_market_id=tot.id, outcome_name=ot,
                                             outcome_type=ot, price_decimal=price))

    pool = models.PoolConfig(name=f"Pool {uuid.uuid4().hex[:6]}", candidate_max_goals=5)
    session.add(pool)
    await session.flush()
    rules = [
        ("exact_score", "Exact", 6.0, 1),
        ("correct_outcome", "Result", 3.0, 4),
        ("total_goals", "Total", 1.0, 6),
    ]
    for code, label, pts, rank in rules:
        session.add(models.ScoringRule(pool_config_id=pool.id, code=code, label=label,
                                       points=pts, enabled=True, display_specificity_rank=rank))
    await session.commit()
    return pool.id, match.id, snap.id


@pytest.fixture
async def seeded():
    if not await _db_available():
        pytest.skip("database not available")
    async with AsyncSessionLocal() as session:
        return await _seed_match_with_odds(session)


async def _run(pool_id, snapshot_id, version, cookies):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies=cookies) as ac:
        resp = await ac.post("/api/model-runs", json={
            "pool_config_id": str(pool_id),
            "odds_snapshot_id": str(snapshot_id),
            "run_type": "manual",
            "parameters": {"model_version": version},
        })
        return resp


async def test_v1_run_still_works(seeded, auth_cookies):
    pool_id, match_id, snap_id = seeded
    resp = await _run(pool_id, snap_id, "v1", auth_cookies)
    assert resp.status_code == 201
    run = resp.json()
    assert run["status"] in ("completed", "partial")


async def test_v2_run_persists_v2_fields(seeded, auth_cookies):
    pool_id, match_id, snap_id = seeded
    resp = await _run(pool_id, snap_id, "v2", auth_cookies)
    assert resp.status_code == 201
    run_id = resp.json()["id"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies=auth_cookies) as ac:
        full = await ac.get(f"/api/model-runs/{run_id}")
        assert full.status_code == 200
        fits = full.json()["match_model_fits"]
        assert fits, "expected at least one model fit"
        fit = fits[0]
        assert fit["model_type"] == "market_score_model_v2"
        assert fit["model_version"] == "2.0.0"
        assert fit["fit_tier"] in ("T0_rich", "T1_standard")
        assert fit["final_home_xg"] is not None
        # Full actual grid is 13x13 even though candidates stay 0-5
        assert len(fit["score_matrix"]) == 13

        diag = await ac.get(f"/api/model-runs/{run_id}/diagnostics/{match_id}")
        assert diag.status_code == 200
        d = diag.json()
        assert d["model_version"] == "2.0.0"
        assert d["constraint_details"]
        assert len(d["score_matrix"]) == 13

        recs = await ac.get(f"/api/model-runs/{run_id}/recommendations")
        assert recs.status_code == 200
        grouped = recs.json()
        assert grouped
        assert grouped[0]["fit_tier"] in ("T0_rich", "T1_standard")


async def test_v2_matrix_sums_to_one_in_db(seeded, auth_cookies):
    pool_id, match_id, snap_id = seeded
    resp = await _run(pool_id, snap_id, "v2", auth_cookies)
    run_id = resp.json()["id"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies=auth_cookies) as ac:
        full = await ac.get(f"/api/model-runs/{run_id}")
        matrix = full.json()["match_model_fits"][0]["score_matrix"]
        total = sum(sum(row) for row in matrix)
        assert abs(total - 1.0) < 1e-6
