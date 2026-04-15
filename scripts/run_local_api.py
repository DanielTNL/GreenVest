"""Run the local JSON API used by the SwiftUI application."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import get_settings
from api.server import run_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local AI investment backend API.")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind.")
    parser.add_argument("--port", default=8000, type=int, help="Port to bind.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_server(get_settings(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
