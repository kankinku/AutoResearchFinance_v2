from __future__ import annotations

import threading


class ResourceManager:
    def __init__(self, *, max_concurrency: int) -> None:
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        self.max_concurrency = max_concurrency
        self._active = 0
        self._condition = threading.Condition()

    @property
    def active(self) -> int:
        with self._condition:
            return self._active

    def acquire(self) -> None:
        with self._condition:
            while self._active >= self.max_concurrency:
                self._condition.wait()
            self._active += 1

    def release(self) -> None:
        with self._condition:
            if self._active <= 0:
                raise RuntimeError("resource release without reservation")
            self._active -= 1
            self._condition.notify()
