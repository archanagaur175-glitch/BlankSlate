"""Bounded sample FIFO used as a rolling audio buffer."""

from __future__ import annotations

from collections import deque

import numpy as np


class RingBuffer:
    """Holds up to ``max_samples`` mono float32 samples, dropping the oldest."""

    def __init__(self, max_samples: int) -> None:
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        self.max_samples = int(max_samples)
        self._blocks: deque = deque()
        self._n = 0

    def append(self, samples: np.ndarray) -> None:
        block = np.asarray(samples, dtype=np.float32).reshape(-1)
        if block.size == 0:
            return
        self._blocks.append(block)
        self._n += block.size
        while self._n > self.max_samples:
            oversized = self._n - self.max_samples
            first = self._blocks[0]
            if first.size <= oversized:
                self._blocks.popleft()
                self._n -= first.size
            else:
                self._blocks[0] = first[oversized:]
                self._n -= oversized

    def get_all(self) -> np.ndarray:
        return self.get_last(self._n)

    def get_last(self, count: int) -> np.ndarray:
        if count <= 0 or self._n == 0:
            return np.zeros(0, dtype=np.float32)
        count = min(count, self._n)
        blocks: list[np.ndarray] = list(self._blocks)
        keep = 0
        total = 0
        for block in reversed(blocks):
            total += block.size
            keep += 1
            if total >= count:
                break
        tail = np.concatenate(blocks[len(blocks) - keep :])
        return tail[-count:]

    @property
    def filled(self) -> int:
        return self._n

    def reset(self) -> None:
        self._blocks.clear()
        self._n = 0
