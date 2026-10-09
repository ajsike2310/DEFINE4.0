"""Telephony audio helpers: 16-bit mono PCM framing, energy-based utterance segmentation, WAV wrapping.

The segmenter is a simple energy gate, not a trained VAD. The threshold is a starting value to tune against
real call audio; noisy lines may need a higher one.
"""
import io
import wave
from collections.abc import Iterator

import numpy as np


def pcm_duration_ms(pcm: bytes, sample_rate: int) -> int:
    return int(len(pcm) / 2 / sample_rate * 1000)


def pcm16_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def chunk_pcm(pcm: bytes, sample_rate: int, chunk_ms: int = 100) -> Iterator[bytes]:
    size = max(2, int(sample_rate * chunk_ms / 1000) * 2)
    for i in range(0, len(pcm), size):
        yield pcm[i:i + size]


class UtteranceSegmenter:
    """Feed raw inbound PCM; get back complete utterances (speech followed by `end_silence_ms` of quiet)."""

    def __init__(self, sample_rate: int = 8000, frame_ms: int = 20, energy_threshold: float = 500.0,
                 end_silence_ms: int = 700, min_speech_ms: int = 200, max_utterance_ms: int = 12000):
        self.rate, self.frame_ms, self.threshold = sample_rate, frame_ms, energy_threshold
        self._frame_bytes = int(sample_rate * frame_ms / 1000) * 2
        self._end_frames = max(1, end_silence_ms // frame_ms)
        self._min_frames = max(1, min_speech_ms // frame_ms)
        self._max_frames = max(1, max_utterance_ms // frame_ms)
        self._pending = b""
        self._utt: list[bytes] = []
        self._speech_frames = 0
        self._silence_run = 0
        self.elapsed_ms = 0            # total inbound audio seen; doubles as the call clock

    @property
    def in_speech(self) -> bool:
        return self._speech_frames >= self._min_frames

    @property
    def speech_ms(self) -> int:
        return self._speech_frames * self.frame_ms

    def reset(self) -> None:
        self._utt, self._speech_frames, self._silence_run = [], 0, 0

    def _is_speech(self, frame: bytes) -> bool:
        samples = np.frombuffer(frame, dtype="<i2").astype(np.float64)
        return float(np.sqrt(np.mean(samples ** 2))) >= self.threshold

    def feed(self, pcm: bytes) -> list[bytes]:
        done: list[bytes] = []
        data = self._pending + pcm
        n = len(data) // self._frame_bytes * self._frame_bytes
        self._pending = data[n:]
        for i in range(0, n, self._frame_bytes):
            frame = data[i:i + self._frame_bytes]
            self.elapsed_ms += self.frame_ms
            if self._is_speech(frame):
                self._utt.append(frame)
                self._speech_frames += 1
                self._silence_run = 0
            elif self._utt:
                self._utt.append(frame)
                self._silence_run += 1
            if self._utt and (self._silence_run >= self._end_frames or len(self._utt) >= self._max_frames):
                if self._speech_frames >= self._min_frames:
                    done.append(b"".join(self._utt))
                self.reset()
        return done
