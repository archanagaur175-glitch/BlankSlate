"""Console entrypoint for the BlankSlate daemon."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from blankslate.app import DaemonApp
from blankslate.config import DaemonConfig

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="blankslate", description="BlankSlate voice assistant daemon"
    )
    parser.add_argument("--config", type=str, default=None, help="path to config.json")
    parser.add_argument("--log-level", type=str, default=None, choices=LOG_LEVELS)
    args = parser.parse_args()

    config = DaemonConfig.load(args.config)
    if args.config and not config.data_dir:
        config.data_dir = str(Path(args.config).parent)
    if args.log_level:
        config.log_level = args.log_level

    log_dir = config.resolved_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        from logging.handlers import RotatingFileHandler

        fh = RotatingFileHandler(
            log_dir / "daemon.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        handlers.append(fh)
    except Exception:  # noqa: BLE001
        pass
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )

    # Surface any uncaught exception / thread error to the log file.
    import sys
    import threading

    def _log_crash(typ, value, tb):
        logging.getLogger(__name__).critical(
            "UNCAUGHT %s: %s", typ.__name__, value, exc_info=(typ, value, tb)
        )

    sys.excepthook = _log_crash
    threading.excepthook = lambda args: _log_crash(
        args.exc_type, args.exc_value, args.exc_traceback
    )

    app = DaemonApp(config)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("interrupted; shutting down")


if __name__ == "__main__":
    main()
