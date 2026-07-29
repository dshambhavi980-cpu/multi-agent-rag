import logging
import re
import sys
from typing import Any, cast

import structlog

SENSITIVE_KEYS = re.compile(
    r"(authorization|api[_-]?key|secret|password|jwt|access[_-]?token|refresh[_-]?token|signed[_-]?url|content|document_text)",
    re.IGNORECASE,
)
JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
BEARER_PATTERN = re.compile(r"Bearer\s+\S+", re.IGNORECASE)
SIGNED_QUERY_PATTERN = re.compile(r"([?&](?:token|signature|sig)=)[^&\s]+", re.IGNORECASE)


def _redact(value: Any, *, key: str = "") -> Any:
    if SENSITIVE_KEYS.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): _redact(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value[:50]]
    if isinstance(value, str):
        sanitized = BEARER_PATTERN.sub("Bearer [REDACTED]", value)
        sanitized = JWT_PATTERN.sub("[REDACTED_JWT]", sanitized)
        sanitized = SIGNED_QUERY_PATTERN.sub(r"\1[REDACTED]", sanitized)
        return sanitized[:1000]
    return value


def redact_sensitive_data(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    return cast(dict[str, Any], _redact(event_dict))


def configure_logging(level: str, environment: str) -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        redact_sensitive_data,
    ]

    renderer: Any
    if environment == "local":
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    else:
        renderer = structlog.processors.JSONRenderer()

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level),
        force=True,
    )
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger() -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger())
