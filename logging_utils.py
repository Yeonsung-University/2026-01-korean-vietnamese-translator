import logging
import re
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from app_config import APP_NAME, logs_dir


_recent_errors: deque[dict[str, str]] = deque(maxlen=50)
_logger: logging.Logger | None = None


SECRET_PATTERNS = [
    re.compile(r"gsk_[A-Za-z0-9_\-]+"),
    re.compile(r"(api[_\-\s]?key['\"]?\s*[:=]\s*['\"]?)([^'\"\s,}]+)", re.IGNORECASE),
]


def mask_sensitive(value: Any) -> str:
    text = str(value)
    for pattern in SECRET_PATTERNS:
        if pattern.pattern.startswith("(api"):
            text = pattern.sub(r"\1***", text)
        else:
            text = pattern.sub("gsk_***", text)
    return text


def current_log_path() -> Path:
    date = datetime.now().strftime("%Y%m%d")
    return logs_dir() / f"app-{date}.log"


def setup_logging() -> logging.Logger:
    global _logger
    if _logger:
        return _logger

    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = logging.FileHandler(current_log_path(), encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    _logger = logger
    return logger


def logger() -> logging.Logger:
    return setup_logging()


def record_error(category: str, message: str, exc: Exception | None = None) -> dict[str, str]:
    safe_message = mask_sensitive(message)
    if exc:
        safe_message = f"{safe_message}: {mask_sensitive(exc)}"

    item = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "category": category,
        "message": safe_message,
    }
    _recent_errors.appendleft(item)
    logger().error("[%s] %s", category, safe_message, exc_info=exc is not None)
    return item


def recent_errors(limit: int = 10) -> list[dict[str, str]]:
    return list(_recent_errors)[:limit]


def tail_log(lines: int = 80) -> list[str]:
    path = current_log_path()
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return [mask_sensitive(line) for line in content[-lines:]]
    except Exception as exc:
        return [f"log read failed: {mask_sensitive(exc)}"]
