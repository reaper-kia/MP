class UserDomainError(Exception):
    pass


class UserAlreadyRegisterError(UserDomainError):
    pass


class InvalidEmailError(UserDomainError):
    pass


class InvalidNameError(UserDomainError):
    pass


class WeakPasswordError(UserDomainError):
    pass
