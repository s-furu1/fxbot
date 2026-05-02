from __future__ import annotations

from fxbot.heartbeat import touch_heartbeat


def test_touch_heartbeat_writes_file(tmp_path):
    path = tmp_path / "fxbot_heartbeat"

    touch_heartbeat(path)

    assert path.exists()
    assert path.read_text(encoding="utf-8")
