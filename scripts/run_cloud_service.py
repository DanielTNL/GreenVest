"""Run the API and scheduler together for a single-machine cloud deployment."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _start_process(*args: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(args, cwd=str(PROJECT_ROOT))


def main() -> None:
    port = str(int(os.getenv("PORT", "8080")))
    run_scheduler = os.getenv("RUN_SCHEDULER", "true").lower() in {"1", "true", "yes", "on"}

    processes: list[subprocess.Popen[bytes]] = []
    shutting_down = False

    def shutdown(*_: object) -> None:
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    init_result = subprocess.run(
        [sys.executable, "scripts/init_db.py"],
        cwd=str(PROJECT_ROOT),
        check=False,
    )
    if init_result.returncode != 0:
        raise SystemExit(init_result.returncode)

    if run_scheduler:
        processes.append(_start_process(sys.executable, "scripts/run_scheduler.py"))

    api_process = _start_process(
        sys.executable,
        "scripts/run_local_api.py",
        "--host",
        "0.0.0.0",
        "--port",
        port,
    )
    processes.append(api_process)

    exit_code = 0
    try:
        while True:
            for process in processes:
                return_code = process.poll()
                if return_code is not None:
                    exit_code = return_code
                    shutdown()
                    raise SystemExit(exit_code)
            time.sleep(1)
    finally:
        shutdown()


if __name__ == "__main__":
    main()
