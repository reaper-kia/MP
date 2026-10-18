# gateway

Единственная точка входа снаружи: HTTP API `/api/v1/*`, WebSocket `/ws/v1`, Swagger `/docs`.
Проверяет JWT, собирает RequestContext, вызывает сервисы по gRPC, превращает ошибки gRPC в HTTP.
