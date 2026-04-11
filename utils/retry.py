"""Retry decorator for transient failures."""

import logging
import time
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _looks_like_captcha_error(error: Exception) -> bool:
    text = str(error).lower()
    triggers = [
        'captcha',
        'verify you are human',
        'are you a human',
        'challenge',
        'login wall',
        'sign in to linkedin',
    ]
    return any(token in text for token in triggers)


def retry(max_attempts: int = 3, delay: float = 1.0):
    """Retry decorator for functions that may fail temporarily.

    Args:
        max_attempts: Maximum number of attempts before re-raising.
        delay: Seconds to wait between attempts.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            did_headful_retry = False
            did_api_switch = False

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    target = args[0] if args else None
                    is_captcha = _looks_like_captcha_error(e)

                    if is_captcha and target is not None and hasattr(target, 'config'):
                        if not did_headful_retry and hasattr(target, 'start_browser'):
                            did_headful_retry = True
                            logger.warning(
                                'CAPTCHA/login wall detected. Retrying once in headful mode for manual solving.'
                            )
                            try:
                                if hasattr(target, 'close_browser'):
                                    target.close_browser()
                                storage_state = target.config.get('storage_state')
                                target.start_browser(headless=False, storage_state=storage_state)
                                # Small pause to allow challenge rendering before retry.
                                time.sleep(max(2.0, delay))
                                continue
                            except Exception as switch_err:
                                logger.warning(f'Unable to retry headful after CAPTCHA: {switch_err}')

                        if not did_api_switch:
                            source_mode = str(target.config.get('source_mode', '')).lower().strip()
                            if source_mode != 'rapidapi':
                                did_api_switch = True
                                target.config['source_mode'] = 'rapidapi'
                                logger.warning(
                                    'CAPTCHA persisted after headful retry. Switching to API mode.'
                                )
                                continue

                    if attempt == max_attempts:
                        logger.error(f"Failed after {max_attempts} attempts: {e}")
                        raise
                    wait_s = delay * (2 ** (attempt - 1))
                    logger.warning(f"Attempt {attempt} failed: {e}. Retrying in {wait_s:.1f}s...")
                    time.sleep(wait_s)
        return wrapper
    return decorator
