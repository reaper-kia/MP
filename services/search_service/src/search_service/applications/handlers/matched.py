from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Iterable

from search_service.applications.ports.uow import UnitOfWork
from search_service.domain.enums import IN_SELECTION


async def recount_matched(
    uow: UnitOfWork, search_id: uuid.UUID, target_ids: Iterable[uuid.UUID] | None = None
) -> None:
    """`SearchTarget.matched` = сколько постов цели в подборке: прямая / косвенная / спорная
    связь и не исключены вручную (B2-07). Меняется только это поле: параллельные цели
    не затираем."""
    wanted = set(target_ids) if target_ids is not None else None
    async with uow:
        results = await uow.results.get_by_search(search_id)
        matched = Counter(
            r.target_id for r in results if r.relevance in IN_SELECTION and not r.excluded
        )
        for target in await uow.targets.list_by_search(search_id):
            if wanted is not None and target.id not in wanted:
                continue
            count = matched.get(target.id, 0)
            if target.matched != count:
                await uow.targets.set_matched(target.id, count)
        await uow.commit()
