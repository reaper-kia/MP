"""Ответ LLM → строгий JSON → pydantic → один ретрай. Кривой ответ = LlmAnswerError, не падение."""

import json
import logging
import re

from pydantic import BaseModel, ValidationError

from ml_service.providers.base import LLM

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LlmAnswerError(Exception):
    """Модель ответила не по схеме дважды подряд."""


def extract_json(raw: str) -> object:
    """Снимает ```json-обёртку и мусор вокруг первого {...}."""
    text = _FENCE_RE.sub("", raw.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


async def ask_json[M: BaseModel](
    llm: LLM, system: str, user: str, schema: type[M], *, max_tokens: int = 1024
) -> M:
    """MlUnavailableError (сеть, модель) пробрасывается: решает вызывающий."""
    prompt = user
    for attempt in (1, 2):
        raw = await llm.complete_json(system, prompt, max_tokens=max_tokens)
        try:
            return schema.model_validate(extract_json(raw))
        except (json.JSONDecodeError, ValidationError) as e:
            error = str(e).splitlines()[0][:300]
            logger.warning(
                "LLM: ответ не по схеме %s (попытка %d): %s", schema.__name__, attempt, error
            )
            prompt = (
                f"{user}\n\nТвой прошлый ответ не прошёл проверку: {error}\n"
                "Верни ТОЛЬКО JSON строго по описанной схеме, без пояснений."
            )
    raise LlmAnswerError(f"{schema.__name__}: два ответа подряд не по схеме")
