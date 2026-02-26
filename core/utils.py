import asyncio
import logging
import random
from typing import Optional


def setup_logging(level: int = logging.INFO, logger_name: str = "yandex_search") -> logging.Logger:
    logger = logging.getLogger(logger_name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def jitter(min_seconds: float, max_seconds: float) -> float:
    if min_seconds > max_seconds:
        min_seconds, max_seconds = max_seconds, min_seconds
    return random.uniform(min_seconds, max_seconds)


async def async_sleep(min_seconds: float, max_seconds: Optional[float] = None) -> None:
    if max_seconds is None:
        duration = min_seconds
    else:
        duration = jitter(min_seconds, max_seconds)
    await asyncio.sleep(max(duration, 0.0))
