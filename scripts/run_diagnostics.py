"""Run backend readiness diagnostics."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from audits.diagnostics import run_backend_diagnostics
from config import get_settings


def main() -> None:
    diagnostics = run_backend_diagnostics(get_settings())
    print(json.dumps(diagnostics, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
