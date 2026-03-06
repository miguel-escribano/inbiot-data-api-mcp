"""Retry logic with exponential backoff for API calls."""

import asyncio
from functools import wraps
from typing import Callable, Optional, Tuple, Type, TypeVar
import httpx
from pydantic import BaseModel, Field

T = TypeVar("T")


class RetryConfig(BaseModel):
    """Configuration for retry behavior."""

    max_attempts: int = Field(default=3, ge=1, le=10)
    initial_delay: float = Field(default=1.0, gt=0)
    max_delay: float = Field(default=30.0, gt=0)
    exponential_base: float = Field(default=2.0, gt=1)
    retry_on_status: Tuple[int, ...] = (429, 500, 502, 503, 504)


def retry_with_backoff(
    config: Optional[RetryConfig] = None,
    retry_exceptions: Tuple[Type[Exception], ...] = (httpx.TimeoutException, httpx.ConnectError),
) -> Callable:
    """
    Decorator for retrying async functions with exponential backoff.

    Args:
        config: Retry configuration (uses defaults if None)
        retry_exceptions: Tuple of exceptions that trigger a retry

    Returns:
        Decorated async function with retry logic

    Example:
        @retry_with_backoff()
        async def fetch_data():
            # API call logic
            pass
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            delay = config.initial_delay
            last_exception = None

            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)

                except retry_exceptions as e:
                    last_exception = e

                    if attempt == config.max_attempts - 1:
                        # Final attempt failed
                        raise

                    # Wait before retrying
                    await asyncio.sleep(delay)
                    delay = min(delay * config.exponential_base, config.max_delay)

                except httpx.HTTPStatusError as e:
                    last_exception = e

                    # Only retry on specific status codes
                    if e.response.status_code in config.retry_on_status:
                        if attempt == config.max_attempts - 1:
                            # Final attempt failed
                            raise

                        # Special handling for 429 (rate limit)
                        if e.response.status_code == 429:
                            retry_after = e.response.headers.get("Retry-After")
                            if retry_after:
                                try:
                                    # Retry-After can be seconds (int) or HTTP date
                                    delay = float(retry_after)
                                except ValueError:
                                    # If it's a date string, use default delay
                                    pass

                        # Wait before retrying
                        await asyncio.sleep(delay)
                        delay = min(delay * config.exponential_base, config.max_delay)
                    else:
                        # Don't retry non-retryable status codes
                        raise

            # This should never be reached, but just in case
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


async def retry_async(
    func: Callable[[], T],
    config: Optional[RetryConfig] = None,
    retry_exceptions: Tuple[Type[Exception], ...] = (httpx.TimeoutException, httpx.ConnectError),
) -> T:
    """
    Functional interface for retrying an async function.

    Args:
        func: Async function to retry
        config: Retry configuration
        retry_exceptions: Exceptions that trigger retry

    Returns:
        Result of successful function call

    Raises:
        Exception from final failed attempt

    Example:
        result = await retry_async(
            lambda: client.get("https://api.example.com"),
            config=RetryConfig(max_attempts=5)
        )
    """
    if config is None:
        config = RetryConfig()

    decorated_func = retry_with_backoff(config, retry_exceptions)(func)
    return await decorated_func()
