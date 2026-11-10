"""Run the MarketMind web app (API + built front end) with one command.

    python -m api                     # http://localhost:8000, this computer only
    python -m api --port 8080
    python -m api --reload            # restart on code changes (development)
    python -m api --host 0.0.0.0      # share on your network: anyone who can reach it can run studies
"""
from __future__ import annotations

import argparse
import os
import sys

LOOPBACK = ("127.0.0.1", "localhost", "::1")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m api", description="Serve the MarketMind web app.")
    parser.add_argument("--host", default=os.getenv("MARKETMIND_HOST", "127.0.0.1"),
                        help="interface to listen on (default 127.0.0.1: this computer only)")
    parser.add_argument("--port", type=int, default=int(os.getenv("MARKETMIND_PORT", "8000")))
    parser.add_argument("--reload", action="store_true", help="restart when the Python code changes")
    args = parser.parse_args(argv)

    if args.host not in LOOPBACK:
        print(f"Warning: serving on {args.host}. Anyone who can reach this address can read the runs and start "
              "studies. API keys stay on the server.", file=sys.stderr)
        os.environ.setdefault("MARKETMIND_ALLOWED_HOSTS", "*")

    import uvicorn
    shown = "localhost" if args.host in LOOPBACK else args.host
    print(f"MarketMind web app: http://{shown}:{args.port}  (API docs: /api/docs)", flush=True)
    uvicorn.run("api.app:create_app", factory=True, host=args.host, port=args.port, reload=args.reload,
                reload_dirs=["api", "marketmind"] if args.reload else None, log_level="info")


if __name__ == "__main__":
    main()
