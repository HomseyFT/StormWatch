"""
StormWatch — entry point.
Usage:
    python main.py
    python main.py --config /path/to/config.toml
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))



def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=[logging.FileHandler(".log"), logging.StreamHandler(sys.stderr)],
    )
    # Silence noisy third-party loggers
    for name in ("httpx", "httpcore", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)


def main() -> None:
    parser = argparse.ArgumentParser(description="StormWatch — terminal storm tracker")
    parser.add_argument(
        "--config", type=Path, default=None, help="Path to config.toml (default: ./config.toml)"
    )
    args = parser.parse_args()

    _configure_logging()

    from core.config import load_config
    config_path = args.config or Path(__file__).parent / "config.toml"
    config = load_config(config_path)

    from ui.app import StormWatchApp
    app = StormWatchApp(config=config)
    app.run()


if __name__ == "__main__":
    main()
