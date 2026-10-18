class UnauthenticatedError(Exception):
    pass


class PermissionDeniedError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class RefreshTokenInvalidError(Exception):
    pass


class UserNotFoundError(Exception):
    pass
