"""
bcrypt hash/verify and JWT (HS256, PyJWT) create/decode. Claims: sub, role, iat, exp. No personal data in tokens.

Owner: Joyal (M1)  |  Spec: Agile Spec v2.0
"""

from datetime import datetime, timedelta, timezone
from hashlib import sha256

import bcrypt
import jwt
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas import Role, TokenPayload


class TokenExpiredError(Exception):
    """Raised when a correctly signed access token has expired."""


class InvalidTokenError(Exception):
    """Raised when a token is malformed, tampered with, or has invalid claims."""


def _password_material(password: str) -> bytes:
    # Hashing first preserves the full schema-accepted password length within bcrypt's 72-byte input limit.
    return sha256(password.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(password: str) -> str:
    """Return a bcrypt hash of a password without storing the original password."""
    return bcrypt.hashpw(_password_material(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(_password_material(password), password_hash.encode("ascii"))
    except (UnicodeEncodeError, ValueError):
        return False


def _jwt_settings() -> tuple[str, str, int]:
    settings = get_settings()
    secret = settings.jwt_secret_key
    if secret is None:
        raise RuntimeError("JWT_SECRET_KEY is not configured in backend/.env.")
    secret_value = secret.get_secret_value()
    if (
        not secret_value
        or secret_value.startswith("change-me-")
        or len(secret_value.encode("utf-8")) < 32
    ):
        raise RuntimeError(
            "Set a private, randomly generated JWT_SECRET_KEY of at least 32 bytes in backend/.env."
        )
    return secret_value, settings.jwt_algorithm, settings.jwt_access_token_expire_minutes


def create_access_token(employee_id: int, role: Role) -> tuple[str, int]:
    """Create the spec's 60-minute JWT containing only sub, role, iat, and exp."""
    secret, algorithm, expires_minutes = _jwt_settings()
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=expires_minutes)
    payload = {
        "sub": str(employee_id),
        "role": role.value,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm=algorithm)
    return token, expires_minutes * 60


def decode_access_token(token: str) -> TokenPayload:
    """Verify the signature, expiry, algorithm, and required access-token claims."""
    secret, algorithm, _ = _jwt_settings()
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            options={"require": ["sub", "role", "iat", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError from exc

    try:
        return TokenPayload.model_validate(payload)
    except (ValidationError, TypeError, ValueError) as exc:
        raise InvalidTokenError from exc
