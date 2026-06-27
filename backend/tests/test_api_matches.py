"""Tests for the matches API endpoints."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.security import create_session_token, SESSION_COOKIE_NAME


@pytest.fixture
def auth_cookies():
    """Return cookies dict with valid session token."""
    token = create_session_token("admin")
    return {SESSION_COOKIE_NAME: token}


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestMatchesUnauthenticated:
    async def test_list_matches_requires_auth(self, client):
        response = await client.get("/api/matches")
        assert response.status_code == 401

    async def test_create_match_requires_auth(self, client):
        response = await client.post("/api/matches", json={"stage": "group"})
        assert response.status_code == 401

    async def test_update_match_requires_auth(self, client):
        response = await client.put("/api/matches/00000000-0000-0000-0000-000000000001", json={})
        assert response.status_code == 401

    async def test_delete_match_requires_auth(self, client):
        response = await client.delete("/api/matches/00000000-0000-0000-0000-000000000001")
        assert response.status_code == 401


class TestImportSchedule:
    async def test_provider_import_returns_message(self, auth_cookies):
        # With no ODDS_API_KEY configured the endpoint returns a clear,
        # human-readable message rather than raising.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies=auth_cookies) as ac:
            response = await ac.post("/api/matches/import-provider-schedule")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert isinstance(data["message"], str)

    async def test_provider_import_unauthenticated(self, client):
        response = await client.post("/api/matches/import-provider-schedule")
        assert response.status_code == 401

    async def test_file_import_unauthenticated(self, client):
        response = await client.post("/api/matches/import")
        assert response.status_code == 401

    async def test_dashboard_stats_unauthenticated(self, client):
        response = await client.get("/api/dashboard/stats")
        assert response.status_code == 401
