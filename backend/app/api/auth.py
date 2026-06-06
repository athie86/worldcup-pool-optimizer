from fastapi import APIRouter, Response, HTTPException, Depends
from ..schemas.auth import LoginRequest, AuthResponse
from ..core.security import create_session_token, SESSION_COOKIE_NAME, SESSION_MAX_AGE
from ..core.config import settings
from .deps import get_current_user

router = APIRouter()


def should_secure_cookie() -> bool:
    app_base_url = str(getattr(settings, "APP_BASE_URL", ""))
    environment = getattr(settings, "ENVIRONMENT", "development")
    return app_base_url.startswith("https://") or environment == "production"


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, response: Response):
    if not settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=500, detail="Server misconfiguration: ADMIN_PASSWORD not set")

    if body.password != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_session_token("admin")
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=should_secure_cookie(),
    )
    return AuthResponse(authenticated=True, username="admin")


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return {"message": "Logged out"}


@router.get("/me", response_model=AuthResponse)
async def me(username: str = Depends(get_current_user)):
    return AuthResponse(authenticated=True, username=username)
