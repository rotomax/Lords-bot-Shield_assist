"""
Timer Tracker
=============
Named countdown timers. Modules call set_timer / is_expired / remaining_minutes.
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class _Timer:
    name: str
    started_at: float
    duration_sec: float
    notes: str = ""

    @property
    def remaining(self) -> float:
        return max(0.0, self.duration_sec - (time.time() - self.started_at))

    @property
    def expired(self) -> bool:
        return self.remaining <= 0

    def remaining_minutes(self) -> float:
        return self.remaining / 60.0

    def __repr__(self):
        m, s = divmod(int(self.remaining), 60)
        h, m = divmod(m, 60)
        return f"Timer({self.name}: {h:02d}:{m:02d}:{s:02d} left)"


class TimerTracker:
    def __init__(self, logger: logging.Logger):
        self.log = logger
        self._timers: Dict[str, _Timer] = {}

    def set_timer(self, name: str, duration_sec: float, notes: str = ""):
        t = _Timer(name=name, started_at=time.time(),
                   duration_sec=duration_sec, notes=notes)
        self._timers[name] = t
        self.log.info(f"Timer '{name}' set for {duration_sec / 60:.1f} min. {notes}")

    def is_expired(self, name: str) -> bool:
        t = self._timers.get(name)
        return True if t is None else t.expired

    def remaining_seconds(self, name: str) -> float:
        t = self._timers.get(name)
        return t.remaining if t else 0.0

    def remaining_minutes(self, name: str) -> float:
        return self.remaining_seconds(name) / 60.0

    def cancel(self, name: str):
        if name in self._timers:
            del self._timers[name]

    def sync_from_ocr(self, name: str, remaining_sec: float):
        """Re-sync internal timer from a game-UI OCR reading."""
        self._timers[name] = _Timer(
            name=name, started_at=time.time(),
            duration_sec=remaining_sec, notes="synced from OCR",
        )
        self.log.info(f"Timer '{name}' synced: {remaining_sec / 60:.1f} min remaining.")

    def status(self, name: str) -> str:
        t = self._timers.get(name)
        return str(t) if t else f"Timer '{name}': not set"

    def all_statuses(self) -> str:
        return "\n".join(str(t) for t in self._timers.values()) or "No active timers."
