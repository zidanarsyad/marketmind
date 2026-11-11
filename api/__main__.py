"""Run the MarketMind web app (API + built front end) with one command.

    python -m api                     # http://localhost:8000, this computer only
    python -m api --port 8080
    python -m api --reload            # restart on code changes (development)
    python -m api --host 0.0.0.0      # share on your network, behind an access token (the start-up message has it)
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys

import marketmind.config  # noqa: F401  (loads .env, so MARKETMIND_HOST, _PORT and _ACCESS_TOKEN can be set there)
from marketmind.core.access import TOKEN_ENV

LOOPBACK = ("127.0.0.1", "localhost", "::1")
ANY_INTERFACE = ("0.0.0.0", "::")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m api", description="Serve the MarketMind web app.")
    parser.add_argument("--host", default=os.getenv("MARKETMIND_HOST", "127.0.0.1"),
                        help="interface to listen on (default 127.0.0.1: this computer only)")
    parser.add_argument("--port", type=int, default=int(os.getenv("MARKETMIND_PORT", "8000")))
    parser.add_argument("--reload", action="store_true", help="restart when the Python code changes")
    args = parser.parse_args(argv)

    token = os.getenv(TOKEN_ENV, "").strip()
    if args.host not in LOOPBACK:
        os.environ.setdefault("MARKETMIND_ALLOWED_HOSTS", "*")
        if not token:   # shared on a network, never without a token: make one up for this session
            token = secrets.token_urlsafe(18)
            os.environ[TOKEN_ENV] = token     # create_app reads it, in the --reload worker process too

    import uvicorn
    shown = "localhost" if args.host in LOOPBACK + ANY_INTERFACE else args.host
    print(f"MarketMind web app: http://{shown}:{args.port}  (API docs: /api/docs)", flush=True)
    if token:
        elsewhere = ("; from another computer, use this computer's network address instead of localhost"
                     if args.host in ANY_INTERFACE else "")
        print(f"Access token required. Open http://{shown}:{args.port}/?token={token} once in each browser{elsewhere}.\n"
              "Anyone with the token can read the runs and start studies; API keys stay on this computer.",
              file=sys.stderr, flush=True)
    uvicorn.run("api.app:create_app", factory=True, host=args.host, port=args.port, reload=args.reload,
                reload_dirs=["api", "marketmind"] if args.reload else None, log_level="info")


if __name__ == "__main__":
    main()
