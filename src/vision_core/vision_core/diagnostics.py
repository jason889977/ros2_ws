"""Diagnostic message helpers shared by vision nodes."""

from __future__ import annotations

import time
import threading
from typing import Any

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus

DIAGNOSTIC_LEVEL_NAMES = {
    0: 'OK',
    1: 'WARN',
    2: 'ERROR',
    3: 'STALE',
}


def diagnostic_level_name(level: int | bytes) -> str:
    """Return a human readable diagnostic level name."""
    if isinstance(level, bytes):
        level = int.from_bytes(level, byteorder='little')
    level = max(0, min(int(level), 3))
    return DIAGNOSTIC_LEVEL_NAMES.get(level, 'UNKNOWN')


def safe_diagnostic_level(level: int | bytes) -> int:
    """Normalize a diagnostic level to an int."""
    if isinstance(level, bytes):
        return int.from_bytes(level, byteorder='little')
    return int(level)


def dict_from_diagnostic_status(status: DiagnosticStatus) -> dict[str, Any]:
    """Convert a DiagnosticStatus into a JSON-friendly dictionary."""
    return {
        'name': status.name,
        'level': safe_diagnostic_level(status.level),
        'level_name': diagnostic_level_name(status.level),
        'message': status.message,
        'hardware_id': status.hardware_id,
        'values': {kv.key: kv.value for kv in status.values},
    }


class DiagnosticsSubscriber:
    """Track diagnostic messages and expose only fresh entries."""

    def setup_diagnostics_subscription(
        self, node: Any, topic: str, timeout_s: float = 5.0,
    ) -> None:
        if timeout_s <= 0.0:
            raise ValueError('diagnostic timeout must be greater than zero')
        self._diag_timeout_s = timeout_s
        self._diagnostics_clock = lambda: time.monotonic()
        self._diagnostics_lock = threading.RLock()
        self._latest_diagnostics: dict[str, tuple[Any, float]] = {}
        node.create_subscription(
            DiagnosticArray, topic, self._on_diagnostics, 10,
        )

    def _on_diagnostics(self, message: DiagnosticArray) -> None:
        now = self._diagnostics_clock()
        with self._diagnostics_lock:
            for status in message.status:
                self._latest_diagnostics[status.name] = (status, now)
            cutoff = now - self._diag_timeout_s * 3.0
            stale = [
                name for name, (_, received_at) in self._latest_diagnostics.items()
                if received_at < cutoff
            ]
            for name in stale:
                del self._latest_diagnostics[name]

    def get_fresh_diagnostics(
        self, now: float | None = None,
    ) -> dict[str, tuple[Any, float]]:
        if now is None:
            now = self._diagnostics_clock()
        with self._diagnostics_lock:
            return {
                name: item
                for name, item in self._latest_diagnostics.items()
                if now - item[1] <= self._diag_timeout_s
            }

    @property
    def latest_diagnostics(self) -> dict[str, tuple[Any, float]]:
        with self._diagnostics_lock:
            return dict(self._latest_diagnostics)

    def teardown(self) -> None:
        """Clear all cached diagnostics state."""
        with self._diagnostics_lock:
            self._latest_diagnostics.clear()
