import bcrypt
from itsdangerous import URLSafeTimedSerializer
from .config import settings

SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = 86400 * 7  # 7 days


def is_supported_password_hash(hashed: str) -> bool:
    return hashed.startswith(("$2b$", "$2a$", "$2y$")) and len(hashed) == 60


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


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
