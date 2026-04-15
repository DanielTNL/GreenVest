"""CLI for daily risk metric calculation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from audits.daily_audit import run_daily_audit
from config import get_settings
from db import initialize_knowledge_bases, initialize_market_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Run daily risk calculations and audit checks.")
    parser.add_argument("--lookback", type=int, default=252, help="Lookback window for risk calculations.")
    args = parser.parse_args()
    settings = get_settings()
    initialize_market_database(settings)
    initialize_knowledge_bases(settings)
    results = run_daily_audit(settings=settings, lookback=args.lookback)
    print(f"Audit completed for {len(results)} symbols.")


if __name__ == "__main__":
    main()
