"""Retry decorator for transient failures."""

import logging
import time
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)


def retry(max_attempts: int = 3, delay: float = 1.0):
    """Retry decorator for functions that may fail temporarily.

    Args:
        max_attempts: Maximum number of attempts before re-raising.
        delay: Seconds to wait between attempts.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts:
                        logger.error(f"Failed after {max_attempts} attempts: {e}")
                        raise
                    logger.warning(f"Attempt {attempt} failed: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
        return wrapper
    return decorator
