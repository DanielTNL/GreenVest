"""CLI for running ETL jobs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import get_settings
from db import initialize_knowledge_bases, initialize_market_database
from ingestion import DataIngestionPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run data ingestion tasks.")
    parser.add_argument("--stocks", nargs="*", help="Stock symbols to ingest.")
    parser.add_argument("--commodities", nargs="*", help="Commodity symbols to ingest from FMP.")
    parser.add_argument("--eodhd-commodities", nargs="*", help="Commodity symbols to ingest from EODHD.")
    parser.add_argument("--include-intraday", action="store_true", help="Also fetch intraday prices.")
    parser.add_argument("--skip-geopolitical", action="store_true", help="Skip configured geopolitical risk series ingestion.")
    parser.add_argument("--skip-polymarket", action="store_true", help="Skip Polymarket ingestion.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = get_settings()
    initialize_market_database(settings)
    initialize_knowledge_bases(settings)
    pipeline = DataIngestionPipeline(settings)
    pipeline.run_full_etl(
        stock_symbols=args.stocks,
        include_intraday=args.include_intraday,
        commodity_symbols=args.commodities,
        eodhd_symbols=args.eodhd_commodities,
        include_geopolitical=not args.skip_geopolitical,
        include_polymarket=not args.skip_polymarket,
    )
    status_parts: list[str] = []
    if args.skip_geopolitical:
        status_parts.append("without configured geopolitical series")
    if args.skip_polymarket:
        status_parts.append("without Polymarket")
    suffix = f" ({', '.join(status_parts)})" if status_parts else ""
    print(f"Ingestion completed{suffix}.")


if __name__ == "__main__":
    main()
