"""G2DTC application entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import default_config_path
from .ui import G2DTCApplication


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="General 2D Material Transfer Controller"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="configuration JSON path",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        application = G2DTCApplication(args.config.expanduser().resolve())
        application.mainloop()
        return 0
    except Exception as exc:
        print(f"G2DTC failed to start: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
