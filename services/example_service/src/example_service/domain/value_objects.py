from dataclasses import dataclass

from example_service.domain.exceptions import InvalidItemTitleError


@dataclass(frozen=True)
class ItemTitle:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        object.__setattr__(self, "value", normalized)

        if not 1 <= len(normalized) <= 200:
            raise InvalidItemTitleError("Title must be 1-200 characters")
