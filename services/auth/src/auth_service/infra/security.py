import hashlib
import secrets
from uuid import UUID

from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError

from auth_service.application.ports import AccessToken
from platform_common.security.jwt import JwtCodec


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._argon = _Argon2()

    def hash(self, password: str) -> str:
        return str(self._argon.hash(password))

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return bool(self._argon.verify(password_hash, password))
        except (VerificationError, InvalidHashError):
            return False


class JwtTokenService:
    def __init__(self, codec: JwtCodec) -> None:
        self._codec = codec

    def issue_access(self, user_id: UUID, role: str) -> AccessToken:
        issued = self._codec.issue(user_id, role)
        return AccessToken(token=issued.token, expires_at=issued.expires_at)

    def new_refresh_token(self) -> str:
        return secrets.token_urlsafe(48)

    def hash_refresh_token(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
