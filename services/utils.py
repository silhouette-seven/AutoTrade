"""
services.utils -- Shared utility functions for the trading platform.
"""

import time
from functools import wraps

def retry_on_error(max_retries=3, delay=2, backoff=2):
    """
    A robust decorator to retry a function if an exception occurs.
    Particularly useful for transient network timeouts or API rate limits.
    
    Args:
        max_retries (int): Maximum number of attempts before raising the exception.
        delay (int): Initial delay between retries in seconds.
        backoff (int): Multiplier for the delay after each failed attempt.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        # If this was the last attempt, raise the error
                        raise e
                    print(f"[RETRY] {func.__name__} failed (attempt {attempt+1}/{max_retries}): {e}")
                    print(f"[RETRY] Waiting {current_delay} seconds before next attempt...")
                    time.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator
