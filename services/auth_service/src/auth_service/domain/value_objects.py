from dataclasses import dataclass

from auth_service.domain.exceptions import InvalidEmailError, InvalidNameError, WeakPasswordError


@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        object.__setattr__(self, "value", normalized)

        if not normalized:
            raise InvalidEmailError("Email can't be empty")
        local, _, domain = normalized.partition("@")
        if not local or "." not in domain or len(normalized) > 254:
            raise InvalidEmailError("Invalid email format")


@dataclass(frozen=True)
class UserName:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        object.__setattr__(self, "value", normalized)

        if not 1 <= len(normalized) <= 64:
            raise InvalidNameError("Name must be 1-64 characters")


@dataclass(frozen=True)
class RawPassword:
    value: str

    def __post_init__(self) -> None:
        if len(self.value) < 8:
            raise WeakPasswordError("Password must be at least 8 characters")
