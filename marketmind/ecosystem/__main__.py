"""The multi-enterprise ecosystem from the command line.

    python -m marketmind.ecosystem run                       # every scenario, local vs ecosystem, in one process
    python -m marketmind.ecosystem run --scenario stress --json outputs/ecosystem/stress.json
    python -m marketmind.ecosystem up                        # seven servers: six enterprises + the Control Center
    python -m marketmind.ecosystem serve kirana --port 8101  # one of them

``up`` starts each enterprise on its own port with its own database under outputs/ecosystem, waits until every
server answers, then plays a first comparison (the normal scenario) so the dashboards have something to show.
Open the Control Center at http://localhost:8100 and each enterprise at its own address.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import marketmind.config  # noqa: F401  (loads .env)

from .enterprises import ENTERPRISES, ORDER, PORTS
from .server import transport_urls
from .world import SCENARIOS


def cmd_run(args) -> None:
    from . import compare, run
    scenarios = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    out = {}
    print(f"{'scenario':<18}{'fill rate':>22}{'orders lost':>20}{'ecosystem profit (Rp bn)':>30}{'replans':>9}")
    for sc in scenarios:
        local, eco = run(sc, "local", args.seed), run(sc, "ecosystem", args.seed)
        a, b = local["ecosystem"], eco["ecosystem"]
        print(f"{sc:<18}{a['fill_rate']:>10.1%} -> {b['fill_rate']:<8.1%}{a['lost_units']:>9,} -> {b['lost_units']:<8,}"
              f"{a['total_profit_idr'] / 1e9:>15.2f} -> {b['total_profit_idr'] / 1e9:<10.2f}{b['replans']:>6}")
        out[sc] = {"local": local, "ecosystem": eco, "comparison": compare(local, eco)}
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
        print(f"\nFull results (KPIs, plans, negotiations, every message): {args.json}")


def cmd_serve(args) -> None:
    import uvicorn
    port = args.port or PORTS[args.node]
    if args.node == "control":
        from .control import create_control_app
        app = create_control_app()
    else:
        from .server import create_enterprise_app
        app = create_enterprise_app(args.node, args.data_dir, args.seed, args.research_run)
    name = "Global Agentic Control Center" if args.node == "control" else ENTERPRISES[args.node].name
    print(f"{name}: http://localhost:{port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def cmd_up(args) -> None:
    import httpx
    procs = []
    base = [sys.executable, "-m", "marketmind.ecosystem", "serve"]
    try:
        for node in ("control", *ORDER):
            extra = ([] if node == "control" else ["--seed", str(args.seed), "--research-run", args.research_run]
                     + (["--data-dir", args.data_dir] if args.data_dir else []))
            procs.append(subprocess.Popen(base + [node, *extra]))
        deadline = time.time() + 90
        local = transport_urls()          # by address: "localhost" costs Windows two seconds a connection
        pending = {n: f"{local[n]}/api/node" for n in ("control", *ORDER)}
        while pending and time.time() < deadline:
            for n, url in list(pending.items()):
                try:
                    if httpx.get(url, timeout=2).status_code == 200:
                        pending.pop(n)
                except httpx.HTTPError:
                    pass
            time.sleep(0.5)
        if pending:
            raise SystemExit(f"these servers did not start: {', '.join(pending)}")
        if not args.no_initial_run:
            httpx.post(f"{local['control']}/api/control/runs",
                       json={"scenario": "normal", "mode": "compare", "seed": args.seed}, timeout=10)
        print("\nThe ecosystem is up:")
        print(f"  Global Agentic Control Center   http://localhost:{PORTS['control']}")
        for k in ORDER:
            print(f"  {ENTERPRISES[k].name:<32}http://localhost:{PORTS[k]}")
        print("\nPress Ctrl+C to stop every server.", flush=True)
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m marketmind.ecosystem", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="simulate scenarios in one process, local vs ecosystem")
    r.add_argument("--scenario", default="all", choices=["all", *SCENARIOS])
    r.add_argument("--seed", type=int, default=7)
    r.add_argument("--json", help="write the full results to this file")
    s = sub.add_parser("serve", help="serve one enterprise or the Control Center")
    s.add_argument("node", choices=["control", *ORDER])
    s.add_argument("--port", type=int)
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--data-dir", help="where the enterprise keeps its database (default outputs/ecosystem)")
    s.add_argument("--research-run", default="latest",
                   help="the MarketMind study the research agency sells: latest, defaults, or a run id")
    u = sub.add_parser("up", help="start every server (six enterprises and the Control Center)")
    u.add_argument("--seed", type=int, default=7)
    u.add_argument("--data-dir")
    u.add_argument("--research-run", default="latest")
    u.add_argument("--no-initial-run", action="store_true", help="do not play the first comparison")
    args = ap.parse_args(argv)
    if getattr(args, "research_run", None) == "defaults":
        args.research_run = None
    {"run": cmd_run, "serve": cmd_serve, "up": cmd_up}[args.cmd](args)


if __name__ == "__main__":
    main()
