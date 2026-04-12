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
                                'CAPTCHA/login wall detected. Refreshing session state and retrying once in headful mode.'
                            )
                            try:
                                storage_state = str(
                                    target.config.get('storage_state') or 'linkedin_state.json'
                                )

                                # Step 1: refresh persisted LinkedIn session from env creds when available.
                                if hasattr(target, '_refresh_storage_state_from_env'):
                                    try:
                                        target._refresh_storage_state_from_env(storage_state)
                                    except Exception as refresh_err:
                                        logger.warning(
                                            f'Failed to refresh LinkedIn state before headful retry: {refresh_err}'
                                        )

                                # Step 2: one headful retry for manual intervention.
                                if hasattr(target, 'close_browser'):
                                    target.close_browser()
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
                                    'CAPTCHA/login wall persisted after headful retry. Aborting browser path and switching to API mode.'
                                )
                                if hasattr(target, 'close_browser'):
                                    try:
                                        target.close_browser()
                                    except Exception:
                                        pass
                                continue

                    if attempt == max_attempts:
                        logger.error(f"Failed after {max_attempts} attempts: {e}")
                        raise
                    wait_s = delay * (2 ** (attempt - 1))
                    logger.warning(f"Attempt {attempt} failed: {e}. Retrying in {wait_s:.1f}s...")
                    time.sleep(wait_s)
        return wrapper
    return decorator
