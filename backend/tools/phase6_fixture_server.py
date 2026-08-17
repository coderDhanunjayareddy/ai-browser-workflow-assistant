from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.certification.fixtures import FixtureServer


def main() -> int:
    server = FixtureServer().start()
    print(server.base_url, flush=True)
    stopped = False

    def stop(*_args) -> None:
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while not stopped:
            time.sleep(0.25)
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
