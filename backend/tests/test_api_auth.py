"""Tests for the authentication API endpoints."""
import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.security import hash_password


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestLogin:
    async def test_login_success(self, client):
        hashed = hash_password("testpass123")
        with patch("app.api.auth.settings") as mock_settings:
            mock_settings.ADMIN_PASSWORD_HASH = hashed
            response = await client.post("/api/auth/login", json={"username": "admin", "password": "testpass123"})
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["username"] == "admin"

    async def test_login_sets_session_cookie(self, client):
        hashed = hash_password("testpass123")
        with patch("app.api.auth.settings") as mock_settings:
            mock_settings.ADMIN_PASSWORD_HASH = hashed
            response = await client.post("/api/auth/login", json={"username": "admin", "password": "testpass123"})
        assert response.status_code == 200
        assert "session" in response.cookies

    async def test_login_wrong_password(self, client):
        hashed = hash_password("testpass123")
        with patch("app.api.auth.settings") as mock_settings:
            mock_settings.ADMIN_PASSWORD_HASH = hashed
            response = await client.post("/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
        assert response.status_code == 401

    async def test_login_wrong_username(self, client):
        hashed = hash_password("testpass123")
        with patch("app.api.auth.settings") as mock_settings:
            mock_settings.ADMIN_PASSWORD_HASH = hashed
            response = await client.post("/api/auth/login", json={"username": "notadmin", "password": "testpass123"})
        assert response.status_code == 401

    async def test_login_no_hash_configured(self, client):
        with patch("app.api.auth.settings") as mock_settings:
            mock_settings.ADMIN_PASSWORD_HASH = ""
            response = await client.post("/api/auth/login", json={"username": "admin", "password": "anything"})
        assert response.status_code == 500
        assert response.json()["detail"] == "Server misconfiguration: ADMIN_PASSWORD_HASH not set"

    async def test_login_invalid_hash_configured(self, client):
        with patch("app.api.auth.settings") as mock_settings:
            mock_settings.ADMIN_PASSWORD_HASH = "replace_me"
            response = await client.post("/api/auth/login", json={"username": "admin", "password": "anything"})
        assert response.status_code == 500
        assert response.json()["detail"] == "Server misconfiguration: ADMIN_PASSWORD_HASH must be a valid bcrypt hash"


class TestLogout:
    async def test_logout_clears_cookie(self, client):
        hashed = hash_password("testpass123")
        with patch("app.api.auth.settings") as mock_settings:
            mock_settings.ADMIN_PASSWORD_HASH = hashed
            login_resp = await client.post("/api/auth/login", json={"username": "admin", "password": "testpass123"})
        assert login_resp.status_code == 200

        logout_resp = await client.post("/api/auth/logout")
        assert logout_resp.status_code == 200


class TestMe:
    async def test_me_unauthenticated(self, client):
        response = await client.get("/api/auth/me")
        assert response.status_code == 401

    async def test_me_authenticated(self, client):
        hashed = hash_password("testpass123")
        with patch("app.api.auth.settings") as mock_settings:
            mock_settings.ADMIN_PASSWORD_HASH = hashed
            login_resp = await client.post("/api/auth/login", json={"username": "admin", "password": "testpass123"})

        assert login_resp.status_code == 200
        # Use the session cookie from login
        me_resp = await client.get("/api/auth/me")
        assert me_resp.status_code == 200
        data = me_resp.json()
        assert data["authenticated"] is True
