from fastapi import APIRouter, Response, HTTPException, Depends
from ..schemas.auth import LoginRequest, AuthResponse
from ..core.security import (
    verify_password,
    create_session_token,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE,
)
from ..core.config import settings
from .deps import get_current_user

router = APIRouter()


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, response: Response):
    if not settings.ADMIN_PASSWORD_HASH:
        raise HTTPException(status_code=500, detail="Server misconfiguration: ADMIN_PASSWORD_HASH not set")

    try:
        credentials_valid = body.username == "admin" and verify_password(
            body.password, settings.ADMIN_PASSWORD_HASH
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Server misconfiguration: ADMIN_PASSWORD_HASH is invalid")

    if not credentials_valid:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    try:
        token = create_session_token(body.username)
    except Exception:
        raise HTTPException(status_code=500, detail="Server misconfiguration: SESSION_SECRET is invalid")

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
    )
    return AuthResponse(authenticated=True, username=body.username)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return {"message": "Logged out"}


@router.get("/me", response_model=AuthResponse)
async def me(username: str = Depends(get_current_user)):
    return AuthResponse(authenticated=True, username=username)
