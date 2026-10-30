from __future__ import annotations

import threading
import time


class OperationCancelled(Exception):
    """Raised at a safe checkpoint when the user cancels a long-running task."""


class OperationControl:
    """Thread-safe pause, resume and cancel controller for long-running work."""

    def __init__(self, checkpoint_interval: float = 0.15):
        self._resume = threading.Event()
        self._resume.set()
        self._cancel = threading.Event()
        self._checkpoint_interval = max(0.02, checkpoint_interval)
        self._state_lock = threading.Lock()
        self._paused_at: float | None = None
        self._paused_seconds = 0.0

    @property
    def paused(self) -> bool:
        return not self._resume.is_set() and not self._cancel.is_set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def pause(self) -> None:
        with self._state_lock:
            if not self._cancel.is_set() and self._resume.is_set():
                self._paused_at = time.monotonic()
                self._resume.clear()

    def resume(self) -> None:
        with self._state_lock:
            if self._paused_at is not None:
                self._paused_seconds += max(0.0, time.monotonic() - self._paused_at)
                self._paused_at = None
            self._resume.set()

    def cancel(self) -> None:
        self._cancel.set()
        self.resume()

    def checkpoint(self) -> None:
        """Wait while paused; raise only between safe units of work."""
        while not self._resume.wait(self._checkpoint_interval):
            if self._cancel.is_set():
                raise OperationCancelled("Operation cancelled by the user.")
        if self._cancel.is_set():
            raise OperationCancelled("Operation cancelled by the user.")

    def elapsed_paused_seconds(self) -> float:
        with self._state_lock:
            total = self._paused_seconds
            if self._paused_at is not None:
                total += max(0.0, time.monotonic() - self._paused_at)
            return total
