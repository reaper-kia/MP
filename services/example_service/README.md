# example_service

Образец сервиса: CRUD сущности Item (только владелец или admin), бизнес-правило со статусом,
вызов `auth_service` по gRPC за именем владельца (`infra/clients/auth_client.py`).

gRPC: `contracts/example/v1/example_service.proto`. Порт 50052.

Новый сервис делается копией этого: `make new-service name=orders entity=Order`.
