from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from fxbot.config import ConfigError, VALID_MODES


class StartupCheckClient(Protocol):
    def get_account_summary(self) -> dict[str, Any]: ...

    def list_open_positions(self) -> list[dict[str, Any]]: ...


def _require_env(env: dict[str, str | None], name: str) -> str:
    value = env.get(name)
    if not value:
        raise ConfigError(f"{name} is required")
    return value


def run_startup_checks(
    client: StartupCheckClient,
    db_path: Path,
    env: dict[str, str | None] | None = None,
) -> None:
    # Import lazily so tests can pass explicit env without mutating module globals.
    import os

    values = env if env is not None else os.environ

    mode = _require_env(values, "FXBOT_MODE")
    oanda_env = _require_env(values, "OANDA_ENV")
    account_id = _require_env(values, "OANDA_ACCOUNT_ID")
    expected_mode = _require_env(values, "FXBOT_EXPECTED_MODE")
    expected_account_id = _require_env(values, "FXBOT_EXPECTED_ACCOUNT_ID")
    db_env = _require_env(values, "FXBOT_DB_ENV")
    dry_run = _require_env(values, "DRY_RUN")

    if mode not in VALID_MODES:
        raise ConfigError("FXBOT_MODE must be practice or live")
    if oanda_env not in VALID_MODES:
        raise ConfigError("OANDA_ENV must be practice or live")
    if expected_mode != oanda_env:
        raise ConfigError("FXBOT_EXPECTED_MODE must match OANDA_ENV")
    if expected_account_id != account_id:
        raise ConfigError("FXBOT_EXPECTED_ACCOUNT_ID must match OANDA_ACCOUNT_ID")
    if db_env != mode:
        raise ConfigError("FXBOT_DB_ENV must match FXBOT_MODE")
    if dry_run.lower() != "true":
        raise ConfigError("DRY_RUN=false is not supported in Phase 1")
    if db_path != Path("/data/trades.db"):
        raise ConfigError("DB path must be /data/trades.db")

    try:
        summary = client.get_account_summary()
    except Exception as exc:
        raise ConfigError(f"failed to get OANDA AccountSummary: {exc}") from exc
    returned_id = str(summary.get("id") or summary.get("account", {}).get("id") or "")
    if returned_id != expected_account_id:
        raise ConfigError("OANDA account id does not match expected account id")

    try:
        open_positions = client.list_open_positions()
    except Exception as exc:
        raise ConfigError(f"failed to get OANDA openPositions: {exc}") from exc
    if open_positions:
        raise ConfigError("open positions exist; refusing startup")
