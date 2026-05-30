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

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))


def _configure_logging() -> None:
    # Only log to file, not to console (console interferes with Textual TUI)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=[logging.FileHandler(".stormwatch.log")],
    )
    # Silence noisy third-party loggers
    for name in ("httpx", "httpcore", "asyncio", "urllib3", "charset_normalizer"):
        logging.getLogger(name).setLevel(logging.WARNING)
    
    # Also silence our own debug logs in production
    logging.getLogger("api.open_meteo").setLevel(logging.WARNING)
    logging.getLogger("api.nws").setLevel(logging.WARNING)
    logging.getLogger("core.scheduler").setLevel(logging.WARNING)


def main() -> None:
    parser = argparse.ArgumentParser(description="StormWatch — terminal storm tracker")
    parser.add_argument(
        "--config", type=Path, default=None, help="Path to config.toml (default: ./config.toml)"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging to console"
    )
    args = parser.parse_args()

    if args.debug:
        # Debug mode: show logs in console (will interfere with TUI)
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
            handlers=[logging.FileHandler(".stormwatch.log"), logging.StreamHandler(sys.stderr)],
        )
    else:
        _configure_logging()

    from core.config import load_config
    config_path = args.config or Path(__file__).parent / "config.toml"
    config = load_config(config_path)

    from ui.app import StormWatchApp
    app = StormWatchApp(config=config)
    app.run()


if __name__ == "__main__":
    main()
