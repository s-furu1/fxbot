from __future__ import annotations

from pathlib import Path


def test_execution_module_is_not_created():
    assert not Path("src/fxbot/execution.py").exists()
