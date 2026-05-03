"""Client-side TPM throttle. Stays below provider's per-minute token cap."""

from __future__ import annotations

import threading
import time


class TokenBucket:
    """Sliding-window TPM throttle. `acquire(n)` blocks until n tokens are available."""

    def __init__(self, tpm: int, headroom: int = 1_000) -> None:
        self.capacity = max(1, tpm - headroom)
        self.window = 60.0
        self._events: list[tuple[float, int]] = []  # (timestamp, tokens)
        self._lock = threading.Lock()

    def _purge(self, now: float) -> int:
        cutoff = now - self.window
        while self._events and self._events[0][0] < cutoff:
            self._events.pop(0)
        return sum(n for _, n in self._events)

    def acquire(self, tokens: int) -> None:
        tokens = min(tokens, self.capacity)
        while True:
            with self._lock:
                now = time.time()
                in_use = self._purge(now)
                if in_use + tokens <= self.capacity:
                    self._events.append((now, tokens))
                    return
                # Sleep until oldest event ages out.
                wait = self.window - (now - self._events[0][0]) + 0.05
            time.sleep(max(0.1, wait))


class NoopBucket:
    def acquire(self, tokens: int) -> None:  # noqa: D401
        return
