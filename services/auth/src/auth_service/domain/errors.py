from platform_common.errors import (
    AlreadyExistsError,
    NotFoundError,
    UnauthenticatedError,
    ValidationError,
)


class InvalidEmailError(ValidationError):
    pass


class WeakPasswordError(ValidationError):
    pass


class InvalidNameError(ValidationError):
    pass


class EmailTakenError(AlreadyExistsError):
    code = "EMAIL_TAKEN"
    default_message = "Email is already registered"


class InvalidCredentialsError(UnauthenticatedError):
    code = "INVALID_CREDENTIALS"
    default_message = "Invalid email or password"


class InvalidRefreshTokenError(UnauthenticatedError):
    code = "INVALID_REFRESH_TOKEN"
    default_message = "Refresh token is invalid, expired or revoked"


class UserNotFoundError(NotFoundError):
    code = "USER_NOT_FOUND"
    default_message = "User not found"
