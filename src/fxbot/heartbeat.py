from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def touch_heartbeat(path: Path = Path("/tmp/fxbot_heartbeat")) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(datetime.now(UTC).isoformat(), encoding="utf-8")
