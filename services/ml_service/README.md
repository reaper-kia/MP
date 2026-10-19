# ml_service

Разбор запроса, оценка связи постов с запросом, группировка. Владелец — ML (`docs/tasks/ML.md`).
gRPC: `contracts/ml/v1/ml_service.proto` (справочник — `docs/GRPC.md`). Порт 50055. Своей БД нет.

```
src/ml_service/
  core/              ← чистая логика без gRPC: можно гонять из eval/ и тестов
    models.py        ← QueryAnalysis, Post, PostScore, Span, PostGroup ...
    text.py          ← токены/основы слов, предложения
    region.py        ← справочник Красноярского края
    excerpt.py       ← выдержка и подсветка (позиции в исходном тексте)
    query.py         ← analyze_query: эвристика (ML-01) → LLM (ML-03)
    scoring.py       ← score_posts: эвристика (ML-01) → эмбеддинги (ML-04) → LLM-судья (ML-05)
    same_news.py     ← «та же новость / другое событие» (ML-06)
    grouping.py      ← группы одинаковых новостей (ML-07)
  providers/         ← LLM и эмбеддинги за Protocol: stub | ollama | yandex
  engine.py          ← MlEngine: выбирает путь (модель или эвристика), выставляет degraded
  dependencies.py    ← сборка из настроек
  transport/grpc/    ← servicer (proto ⇄ core), mappers, errors, server
```

Инварианты ответа `ScorePosts` (проверяются в `engine.py` и тестах): один `PostScore` на пост, тот же
порядок и `id`; span'ы внутри `text`, `start < end`; выдержка ≤ 300 символов.
