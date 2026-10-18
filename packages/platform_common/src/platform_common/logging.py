import logging
import sys

from platform_common.context import request_id_var


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging(level: str = "INFO", service: str = "app") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(
        logging.Formatter(
            f"%(asctime)s %(levelname)-5s [{service}] [%(request_id)s] %(name)s: %(message)s"
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("aiokafka", "sqlalchemy.engine.Engine", "httpx", "alembic.runtime.plugins"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
