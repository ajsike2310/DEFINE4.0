"""Keep real call placement under the provider's rate limit (Exotel documents 200 calls per minute)."""
import time


class Pacer:
    """Call `wait()` before each placement; it sleeps just long enough to stay within `per_minute`.
    The first call never waits."""

    def __init__(self, per_minute: int, clock=time.monotonic, sleep=time.sleep):
        self.interval = 60.0 / per_minute
        self._clock, self._sleep = clock, sleep
        self._next: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._next is not None and now < self._next:
            self._sleep(self._next - now)
            now = self._next
        self._next = now + self.interval


def for_provider(provider, settings) -> Pacer | None:
    """Real providers are paced; simulated ones (demo, browser demo) are not."""
    return None if getattr(provider, "is_simulated", True) else Pacer(settings.exotel_max_calls_per_minute)
