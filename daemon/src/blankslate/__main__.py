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

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = DaemonApp(config)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("interrupted; shutting down")


if __name__ == "__main__":
    main()
