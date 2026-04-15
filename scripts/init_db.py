"""Initialize the market, truth, and working databases."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import get_settings
from db import initialize_knowledge_bases, initialize_market_database


def main() -> None:
    settings = get_settings()
    initialize_market_database(settings)
    initialize_knowledge_bases(settings)
    print(f"Initialized market DB at {settings.database_path}")
    print(f"Initialized truth DB at {settings.truth_db_path}")
    print(f"Initialized working DB at {settings.working_db_path}")


if __name__ == "__main__":
    main()
