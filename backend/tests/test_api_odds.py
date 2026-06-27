"""Integration tests for the Odds & Overrides match-odds endpoints.

These exercise the full HTTP path against the configured database and are
skipped automatically when the database is unreachable so the rest of the
suite still runs without a DB.
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


async def _add_h2h(session, event_id, bk, home, draw, away):
    market = models.BookmakerMarket(
        odds_event_id=event_id, bookmaker_key=bk, bookmaker_title=bk, market_key="h2h"
    )
    session.add(market)
    await session.flush()
    for ot, price in (("home_win", home), ("draw", draw), ("away_win", away)):
        session.add(models.MarketOutcome(
            bookmaker_market_id=market.id, outcome_name=ot, outcome_type=ot,
            price_decimal=price,
        ))


async def _seed_two_snapshots(session):
    """One match with odds in two snapshots (older + newer) so we can test
    snapshot scoping and the latest-by-default behaviour."""
    home = models.Team(name=f"Home {uuid.uuid4().hex[:6]}")
    away = models.Team(name=f"Away {uuid.uuid4().hex[:6]}")
    session.add_all([home, away])
    await session.flush()

    match = models.Match(stage="group", home_team_id=home.id, away_team_id=away.id,
                         status="scheduled")
    session.add(match)
    await session.flush()

    from datetime import datetime, timezone, timedelta
    older = models.OddsSnapshot(provider="test", status="success",
                                fetched_at=datetime.now(timezone.utc) - timedelta(hours=2))
    newer = models.OddsSnapshot(provider="test", status="success",
                                fetched_at=datetime.now(timezone.utc))
    session.add_all([older, newer])
    await session.flush()

    for snap, prices in ((older, (1.5, 4.0, 7.0)), (newer, (1.9, 3.4, 4.2))):
        event = models.OddsEvent(
            odds_snapshot_id=snap.id, match_id=match.id, provider_event_id=f"evt-{snap.id}",
            sport_key="soccer", home_team=home.name, away_team=away.name,
        )
        session.add(event)
        await session.flush()
        await _add_h2h(session, event.id, "pinnacle", *prices)

    await session.commit()
    return match.id, older.id, newer.id


@pytest.fixture
async def seeded():
    if not await _db_available():
        pytest.skip("database not available")
    async with AsyncSessionLocal() as session:
        return await _seed_two_snapshots(session)


class TestMatchOddsUnauthenticated:
    async def test_get_match_odds_requires_auth(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/odds/matches/00000000-0000-0000-0000-000000000001")
        assert resp.status_code == 401

    async def test_create_override_requires_auth(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/odds/matches/00000000-0000-0000-0000-000000000001/overrides",
                json={"market_key": "h2h", "outcome_type": "home_win", "price_decimal": 2.0},
            )
        assert resp.status_code == 401


async def test_latest_snapshot_by_default(seeded, auth_cookies):
    match_id, older_id, newer_id = seeded
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies=auth_cookies) as ac:
        resp = await ac.get(f"/api/odds/matches/{match_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["snapshot_id"] == str(newer_id)
    assert len(data["bookmaker_markets"]) == 1
    # Consensus reflects the newer (1.9/3.4/4.2) prices, normalized to sum 1.
    # Shorter price => higher probability, so home > draw > away.
    cp = data["consensus_probabilities"]
    assert cp["home_win"] is not None
    assert cp["home_win"] > cp["draw"] > cp["away_win"]
    assert abs(cp["home_win"] + cp["draw"] + cp["away_win"] - 1.0) < 1e-6


async def test_snapshot_scoping(seeded, auth_cookies):
    match_id, older_id, newer_id = seeded
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies=auth_cookies) as ac:
        resp = await ac.get(f"/api/odds/matches/{match_id}?snapshot_id={older_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["snapshot_id"] == str(older_id)
    # Older snapshot had a much shorter home price → higher home consensus.
    assert data["consensus_probabilities"]["home_win"] > 0.6


async def test_override_changes_consensus(seeded, auth_cookies):
    match_id, older_id, newer_id = seeded
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies=auth_cookies) as ac:
        # Override the full h2h market so the draw is heavily favoured.
        for ot, price in (("home_win", 6.0), ("draw", 1.3), ("away_win", 6.0)):
            r = await ac.post(
                f"/api/odds/matches/{match_id}/overrides",
                json={"market_key": "h2h", "outcome_type": ot, "price_decimal": price},
            )
            assert r.status_code == 200

        listed = await ac.get(f"/api/odds/matches/{match_id}/overrides")
        assert listed.status_code == 200
        assert len(listed.json()) == 3

        resp = await ac.get(f"/api/odds/matches/{match_id}")
    cp = resp.json()["consensus_probabilities"]
    assert cp["draw"] > cp["home_win"]
    assert cp["draw"] > cp["away_win"]


async def test_override_upsert_is_idempotent(seeded, auth_cookies):
    match_id, older_id, newer_id = seeded
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies=auth_cookies) as ac:
        first = await ac.post(
            f"/api/odds/matches/{match_id}/overrides",
            json={"market_key": "h2h", "outcome_type": "home_win", "price_decimal": 2.0},
        )
        second = await ac.post(
            f"/api/odds/matches/{match_id}/overrides",
            json={"market_key": "h2h", "outcome_type": "home_win", "price_decimal": 2.5},
        )
        assert first.status_code == 200 and second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        assert second.json()["price_decimal"] == 2.5

        listed = await ac.get(f"/api/odds/matches/{match_id}/overrides")
    assert len(listed.json()) == 1
