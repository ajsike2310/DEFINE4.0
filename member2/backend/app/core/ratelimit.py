"""Tiny in-memory sliding-window limiter for the public sign-up endpoint (one process; resets on restart)."""
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float, clock=time.monotonic):
        self.limit, self.window, self._clock = limit, window_seconds, clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> int | None:
        """Record one request. Returns None when allowed, else the seconds to wait before retrying."""
        now = self._clock()
        q = self._hits[key]
        while q and now - q[0] >= self.window:
            q.popleft()
        if len(q) >= self.limit:
            return max(1, int(self.window - (now - q[0])) + 1)
        q.append(now)
        if len(self._hits) > 5000:                      # bound memory: drop idle keys
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
                self._hits.pop(k, None)
        return None
