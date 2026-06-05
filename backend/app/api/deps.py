from fastapi import Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.session import get_db
from ..core.security import verify_session_token, SESSION_COOKIE_NAME


async def get_current_user(request: Request) -> str:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    username = verify_session_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return username


CurrentUser = Depends(get_current_user)
DB = Depends(get_db)
