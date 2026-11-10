#!/usr/bin/env python
"""Build a SQLite database from the research datasets and saved runs (schema: docs/schemas/database.sql).

    python scripts/export_sqlite.py                      # clean data + latest run -> outputs/marketmind.db
    python scripts/export_sqlite.py --all-runs           # every saved run
    python scripts/export_sqlite.py --db my.db --run 20261104-144556
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marketmind.config import DEFAULT_CLIENT, OUTPUTS  # noqa: E402
from marketmind.core.store import list_runs, load_run  # noqa: E402
from marketmind.sql_export import clean_datasets, connect, create_schema, load_datasets, load_run as load_run_rows  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", type=Path, default=OUTPUTS / "marketmind.db")
    ap.add_argument("--run", help="run id to load (default: latest)")
    ap.add_argument("--all-runs", action="store_true", help="load every saved run")
    args = ap.parse_args()
    if args.db.exists():
        args.db.unlink()  # rebuilt from scratch each time
    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(args.db)
    create_schema(conn)
    runs = list_runs()
    chosen = [r["run_id"] for r in runs] if args.all_runs else ([args.run] if args.run else [r["run_id"] for r in runs[:1]])
    client = load_run(chosen[0]).meta.get("client") if chosen else DEFAULT_CLIENT
    for table, n in load_datasets(conn, clean_datasets(), client).items():
        print(f"  {table:<26} {n:>8,} rows")
    for run_id in chosen:
        counts = load_run_rows(conn, load_run(run_id))
        print(f"  run {run_id}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    problems = conn.execute("PRAGMA foreign_key_check").fetchall()
    print(f"\nSQLite database: {args.db} - foreign-key violations: {len(problems)}")
    conn.close()
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
