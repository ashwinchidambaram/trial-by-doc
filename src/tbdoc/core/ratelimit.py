"""Token-bucket rate limiting + exponential backoff for API adapters.

Configured per model from configs/models.yaml:
  rate_limit: {rps: 2, burst: 5}
  retry: {max_attempts: 5, base_s: 1.0}
"""
from __future__ import annotations

import random
import time


class TokenBucket:
    def __init__(self, rps: float = 1.0, burst: int = 1):
        self.rate = max(rps, 0.001)
        self.capacity = max(burst, 1)
        self.tokens = float(self.capacity)
        self.last = time.monotonic()

    def acquire(self) -> float:
        """Block until a token is available; return seconds waited."""
        waited = 0.0
        while True:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens >= 1:
                self.tokens -= 1
                return waited
            need = (1 - self.tokens) / self.rate
            time.sleep(need)
            waited += need


class RetryableError(Exception):
    """Raise from _call_api for 429/5xx/timeouts to trigger backoff."""


def with_backoff(fn, *, max_attempts: int = 5, base_s: float = 1.0):
    """Call fn(); on RetryableError back off exponentially with jitter.

    Returns (result, n_retries). Non-retryable exceptions propagate immediately
    (the runner records them as error rows — never a silent gap).
    """
    retries = 0
    while True:
        try:
            return fn(), retries
        except RetryableError:
            retries += 1
            if retries >= max_attempts:
                raise
            time.sleep(base_s * (2 ** (retries - 1)) * (1 + random.random() * 0.25))
