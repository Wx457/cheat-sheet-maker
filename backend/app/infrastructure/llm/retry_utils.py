import logging
import time
from typing import Callable, TypeVar

from app.core.config import settings

logger = logging.getLogger(__name__)
T = TypeVar("T")

RETRYABLE_CLASS_NAMES = {
    "APITimeoutError",
    "APIConnectionError",
    "InternalServerError",
    "RateLimitError",
    "ServiceUnavailable",
    "ResourceExhausted",
}

RETRYABLE_MESSAGE_KEYWORDS = (
    "resource exhausted",
    "rate limit",
    "quota exceeded",
    "service unavailable",
    "temporarily unavailable",
    "deadline exceeded",
    "connection reset",
    "connection aborted",
    "connection refused",
    "timed out",
    "timeout",
    "429",
    "500",
    "502",
    "503",
    "504",
)


def is_retryable_llm_error(exception: Exception) -> bool:
    if isinstance(exception, TimeoutError):
        return True

    if exception.__class__.__name__ in RETRYABLE_CLASS_NAMES:
        return True

    error_str = str(exception).lower()
    return any(keyword in error_str for keyword in RETRYABLE_MESSAGE_KEYWORDS)


def run_with_exponential_backoff(
    operation_name: str,
    func: Callable[[], T],
    sleep_fn: Callable[[float], None] = time.sleep,
) -> T:
    last_exception: Exception | None = None

    for attempt in range(1, settings.LLM_MAX_RETRIES + 1):
        try:
            return func()
        except Exception as exc:  # noqa: PERF203
            last_exception = exc
            is_last_attempt = attempt == settings.LLM_MAX_RETRIES

            if not is_retryable_llm_error(exc) or is_last_attempt:
                raise

            delay_seconds = min(
                settings.LLM_INITIAL_RETRY_DELAY_SECONDS * (2 ** (attempt - 1)),
                settings.LLM_MAX_RETRY_DELAY_SECONDS,
            )

            logger.warning(
                "%s failed on attempt %d/%d: %s; retry in %.1fs",
                operation_name,
                attempt,
                settings.LLM_MAX_RETRIES,
                exc,
                delay_seconds,
            )
            sleep_fn(delay_seconds)

    raise (
        last_exception
        if last_exception
        else RuntimeError(f"{operation_name} failed without exception")
    )
