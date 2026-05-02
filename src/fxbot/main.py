from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from fxbot.config import DB_PATH, ConfigError, load_config
from fxbot.db import init_db, log_entry_rejection
from fxbot.heartbeat import touch_heartbeat
from fxbot.logger import configure_logging
from fxbot.oanda_client import OandaClientError, OandaReadOnlyClient
from fxbot.startup_checks import run_startup_checks


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fxbot")
    parser.add_argument("--check-only", action="store_true", help="run startup checks and exit")
    return parser


def _record_env_mismatch_if_possible(db_path, error: ConfigError, logger: logging.Logger) -> None:
    recorded = log_entry_rejection(
        db_path,
        pair="SYSTEM",
        direction="none",
        reason="env_mismatch",
        extra={"error": str(error)},
    )
    if not recorded:
        logger.error("startup check failed; DB rejection log unavailable: %s", error)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logger = configure_logging(os.getenv("LOG_LEVEL", "INFO"))

    try:
        config = load_config()
        client = OandaReadOnlyClient(
            api_key=config.oanda_api_key,
            account_id=config.oanda_account_id,
            environment=config.oanda_env,
        )

        # This guard must run before DB initialization or any trading logic.
        run_startup_checks(client, DB_PATH)

        init_db(config.db_path)
        touch_heartbeat(config.heartbeat_path)

        if args.check_only:
            logger.info("startup checks passed")
            return 0

        while True:
            touch_heartbeat(config.heartbeat_path)
            time.sleep(30)
    except OandaClientError as exc:
        config_error = ConfigError(str(exc))
        db_path = getattr(locals().get("config", None), "db_path", DB_PATH)
        _record_env_mismatch_if_possible(db_path, config_error, logger)
        return 2
    except ConfigError as exc:
        db_path = getattr(locals().get("config", None), "db_path", DB_PATH)
        _record_env_mismatch_if_possible(db_path, exc, logger)
        return 2
    except KeyboardInterrupt:
        logger.info("shutdown requested")
        return 0


if __name__ == "__main__":
    sys.exit(main())
