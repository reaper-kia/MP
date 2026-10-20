# Дополнительные корневые сертификаты для сборщика

Монтируется в контейнер `collector_service` как `/certs` (только чтение).

TLS к MAX Bot API может требовать корневой сертификат Минцифры (Russian Trusted Root CA).
Если в логах сборщика `CERTIFICATE_VERIFY_FAILED` при обращении к MAX:

1. Скачать PEM с сайта Госуслуг (раздел «Сертификаты Минцифры») и положить сюда, например
   `russian_trusted_root_ca.pem`.
2. В `.env` (или в окружении перед `make deploy`): `HTTP_CA_BUNDLE=/certs/russian_trusted_root_ca.pem`.
3. `docker compose up -d collector_service`.

Сертификат добавляется к certifi и системным корням (`infra/http.py`), остальные площадки не затрагивает.
Если `HTTP_CA_BUNDLE` указывает на несуществующий файл, сборщик не запустится — это сделано нарочно.
