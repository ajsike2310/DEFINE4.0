"""In-memory cache of synthesised speech, keyed by (text, sample rate).

Fixed lines (goodbyes, clarification prompts) repeat on every call, and a campaign greeting repeats for every
participant, so caching removes the ~2 s synthesis delay before the first word and saves ElevenLabs quota.
"""
import threading
from collections import OrderedDict
from collections.abc import Callable


class TtsCache:
    def __init__(self, synth: Callable[[str, int], bytes], max_items: int = 256):
        self._synth, self._max = synth, max_items
        self._items: OrderedDict[tuple[str, int], bytes] = OrderedDict()
        self._lock = threading.Lock()

    def speak(self, text: str, rate: int) -> bytes:
        key = (text, rate)
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]
        pcm = self._synth(text, rate)
        with self._lock:
            self._items[key] = pcm
            while len(self._items) > self._max:
                self._items.popitem(last=False)
        return pcm

    def prewarm(self, texts: list[str], rate: int = 8000) -> threading.Thread:
        """Synthesise in the background so the first caller hears the greeting immediately."""
        def work() -> None:
            for t in texts:
                try:
                    self.speak(t, rate)
                except Exception:           # a failed warm-up only costs latency later
                    pass
        th = threading.Thread(target=work, daemon=True)
        th.start()
        return th
