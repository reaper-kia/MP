"""Фейковые модели для тестов: детерминированные, без сети."""

import asyncio
import hashlib
import json
import math
import re
from collections.abc import Callable

from ml_service.core.similarity import BGE_M3, SimilarityThresholds
from ml_service.core.text import stems
from ml_service.errors import MlUnavailableError
from ml_service.providers.base import Kind

Script = Callable[[str, str], str]


class FakeLLM:
    def __init__(self, script: Script, *, delay: float = 0.0, available: bool = True) -> None:
        self.name = "fake"
        self.script = script
        self.delay = delay
        self.calls: list[tuple[str, str]] = []
        self._available = available

    @property
    def available(self) -> bool:
        return self._available

    async def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        self.calls.append((system, user))
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.script(system, user)

    async def aclose(self) -> None:
        return None


def failing_llm() -> FakeLLM:
    def script(system: str, user: str) -> str:
        raise MlUnavailableError("connection refused")

    return FakeLLM(script)


def post_count(user: str) -> int:
    return len(re.findall(r"^\[(\d+)\]", user, re.MULTILINE))


def judge_script(decide: Callable[[str], str], sentiment: str = "neutral") -> Script:
    """Судья: по тексту поста решает relevance; объяснение — из первых слов поста."""

    def script(system: str, user: str) -> str:
        blocks = re.split(r"^\[\d+\][^\n]*\n", user, flags=re.MULTILINE)[1:]
        items = [
            {
                "i": n,
                "relevance": decide(block),
                "explanation": "Пост о " + " ".join(block.split()[:4]),
                "sentiment": sentiment,
            }
            for n, block in enumerate(blocks, start=1)
        ]
        return json.dumps({"items": items}, ensure_ascii=False)

    return script


class FakeEmbedder:
    """«Мешок основ» → хэш-проекция: тексты с общими словами близки, без общих — далеки."""

    def __init__(
        self,
        dims: int = 256,
        *,
        available: bool = True,
        name: str = "fake-emb",
        thresholds: SimilarityThresholds = BGE_M3,
        salt: str = "",
    ) -> None:
        self.name = name
        self.dims = dims
        self.calls = 0
        self.kinds: list[str] = []
        self.thresholds = thresholds
        self.salt = salt  # другая «модель»: те же тексты — другие векторы
        self._available = available

    @property
    def available(self) -> bool:
        return self._available

    async def embed(self, texts: list[str], kind: Kind) -> list[list[float]]:
        self.calls += 1
        self.kinds.append(kind)
        result = []
        for text in texts:
            v = [0.0] * self.dims
            for s in stems(text):
                v[int(hashlib.md5((self.salt + s).encode()).hexdigest(), 16) % self.dims] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            result.append([x / norm for x in v])
        return result

    async def aclose(self) -> None:
        return None


class FailingAfterEmbedder(FakeEmbedder):
    """Отвечает first_ok раз, потом «ноут пропал»: MlUnavailableError и available=False."""

    def __init__(self, first_ok: int, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.first_ok = first_ok

    async def embed(self, texts: list[str], kind: Kind) -> list[list[float]]:
        if self.calls >= self.first_ok:
            self.calls += 1
            self.kinds.append(kind)
            self._available = False
            raise MlUnavailableError(f"{self.name}: connection refused")
        return await super().embed(texts, kind)


class ScriptedLLM(FakeLLM):
    """FakeLLM, который падает (MlUnavailableError) и выключает свой «автомат», пока fail=True."""

    def __init__(self, name: str, answer: str = "{}", *, fail: bool = False) -> None:
        super().__init__(lambda system, user: answer)
        self.name = name
        self.fail = fail
        self.breaker_open = False

    @property
    def available(self) -> bool:
        return not self.breaker_open

    async def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        self.calls.append((system, user))
        if self.fail:
            self.breaker_open = True
            raise MlUnavailableError(f"{self.name}: connection refused")
        return self.script(system, user)
