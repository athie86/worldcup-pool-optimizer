from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer
from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(settings.SESSION_SECRET)

SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = 86400 * 7  # 7 days


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_session_token(username: str) -> str:
    return serializer.dumps({"username": username})


def verify_session_token(token: str) -> str | None:
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE)
        return data.get("username")
    except Exception:
        return None
