"""Crash-safe storage for the last terminal risk state."""

from __future__ import annotations

import json
import os
from pathlib import Path
from time import time


class HaltedStateStore:
    """Persists risk halts atomically; operators must intentionally clear a prior halt before restart."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_halted_reason(self) -> str | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return payload.get("halted_reason")

    def save_halt(self, reason: str) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"halted_reason": reason, "halted_at": time()}), encoding="utf-8")
        os.replace(temporary, self.path)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
