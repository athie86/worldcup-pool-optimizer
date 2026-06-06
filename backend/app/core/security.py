from itsdangerous import URLSafeTimedSerializer
from .config import settings

SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = 86400 * 7  # 7 days


def create_session_token(username: str) -> str:
    serializer = URLSafeTimedSerializer(settings.SESSION_SECRET)
    return serializer.dumps({"username": username})


def verify_session_token(token: str) -> str | None:
    serializer = URLSafeTimedSerializer(settings.SESSION_SECRET)
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE)
        return data.get("username")
    except Exception:
        return None
