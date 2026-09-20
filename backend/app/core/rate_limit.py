import time
from collections import defaultdict, deque

from fastapi import HTTPException, status


class FailureLimiter:
    """Blocks a key for a while after too many recent failures.

    Kept in memory, so it is per server process: fine for a single instance,
    but it would need a shared store (e.g. Redis) once the API runs several.
    """

    def __init__(self, max_failures: int = 5, window_seconds: int = 300) -> None:
        self._max_failures = max_failures
        self._window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        failures = self._recent(key)
        if len(failures) >= self._max_failures:
            retry_after = max(1, int(failures[0] + self._window - time.monotonic()))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed attempts. Please wait a few minutes and try again.",
                headers={"Retry-After": str(retry_after)},
            )

    def record(self, key: str) -> None:
        self._failures[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)

    def _recent(self, key: str) -> deque[float]:
        failures = self._failures[key]
        while failures and failures[0] < time.monotonic() - self._window:
            failures.popleft()
        return failures


login_limiter = FailureLimiter()
two_factor_limiter = FailureLimiter()
