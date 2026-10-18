class ItemDomainError(Exception):
    pass


class InvalidItemTitleError(ItemDomainError):
    pass


class ItemAlreadyDoneError(ItemDomainError):
    pass
