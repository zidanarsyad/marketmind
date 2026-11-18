"""Each enterprise's own database. Four keep relational SQLite files (each with its own schema and naming), the
marketplace keeps JSON documents: heterogeneous storage behind one small interface the enterprise code uses.

Tables are created from the first record written to them, so each enterprise's schema lives in its own code, in its
own vocabulary (``jumlah_set`` at the packaging maker, ``jumlahBatch`` at the contract manufacturer, ``pallets`` and ISO
weeks at the logistics company).
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check(name: str) -> str:
    if not _NAME.match(name):
        raise ValueError(f"bad table or column name {name!r}")
    return name


def _sql_type(v: Any) -> str:
    if isinstance(v, bool) or isinstance(v, int):
        return "INTEGER"
    if isinstance(v, float):
        return "REAL"
    return "TEXT"


def _encode(v: Any) -> Any:
    return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list, tuple)) else v


class SQLiteStore:
    kind = "SQLite (relational)"

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        # write-ahead log: a commit no longer waits for the disk every time, and a crash still loses nothing committed
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._columns: dict[str, set[str]] = {}

    def reset(self) -> None:
        with self._lock:
            for t in self.tables():
                self._db.execute(f'DROP TABLE IF EXISTS "{t}"')
            self._db.commit()
            self._columns.clear()

    def _ensure(self, table: str, row: dict) -> None:
        cols = self._columns.get(table)
        if cols is None:
            cols = {r["name"] for r in self._db.execute(f'PRAGMA table_info("{_check(table)}")')}
            self._columns[table] = cols
        if not cols:
            spec = ", ".join(f'"{_check(k)}" {_sql_type(v)}' for k, v in row.items())
            self._db.execute(f'CREATE TABLE "{table}" ({spec})')
            cols.update(row)
            return
        for k, v in row.items():
            if k not in cols:
                self._db.execute(f'ALTER TABLE "{table}" ADD COLUMN "{_check(k)}" {_sql_type(v)}')
                cols.add(k)

    def insert(self, table: str, row: dict) -> None:
        self.insert_many(table, [row])

    def insert_many(self, table: str, rows: list[dict]) -> None:
        if not rows:
            return
        with self._lock:
            for row in rows:
                self._ensure(table, row)
                keys = list(row)
                marks = ", ".join("?" for _ in keys)
                names = ", ".join(f'"{k}"' for k in keys)
                self._db.execute(f'INSERT INTO "{table}" ({names}) VALUES ({marks})', [_encode(row[k]) for k in keys])
            self._db.commit()

    def rows(self, table: str, limit: int | None = None, offset: int = 0) -> list[dict]:
        with self._lock:
            if table not in self.tables():
                return []
            sql = f'SELECT * FROM "{_check(table)}" LIMIT ? OFFSET ?'
            return [dict(r) for r in self._db.execute(sql, (-1 if limit is None else limit, offset))]

    def count(self, table: str) -> int:
        with self._lock:
            if table not in self.tables():
                return 0
            return self._db.execute(f'SELECT COUNT(*) FROM "{_check(table)}"').fetchone()[0]

    def tables(self) -> list[str]:
        with self._lock:
            return [r[0] for r in self._db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]

    def close(self) -> None:
        with self._lock:
            self._db.close()


class DocumentStore:
    """JSON documents, one JSON-lines file per collection (a stand-in for a document database such as MongoDB)."""

    kind = "JSON documents (document store)"

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._cache: dict[str, list[dict]] = {}

    def _file(self, collection: str) -> Path:
        return self.path / f"{_check(collection)}.jsonl"

    def reset(self) -> None:
        with self._lock:
            for f in self.path.glob("*.jsonl"):
                f.unlink()
            self._cache.clear()

    def insert(self, collection: str, doc: dict) -> None:
        self.insert_many(collection, [doc])

    def insert_many(self, collection: str, docs: list[dict]) -> None:
        if not docs:
            return
        with self._lock:
            self._load(collection).extend(docs)
            with self._file(collection).open("a", encoding="utf-8") as fh:
                for d in docs:
                    fh.write(json.dumps(d, ensure_ascii=False) + "\n")

    def _load(self, collection: str) -> list[dict]:
        if collection not in self._cache:
            f = self._file(collection)
            self._cache[collection] = ([json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line]
                                       if f.exists() else [])
        return self._cache[collection]

    def rows(self, collection: str, limit: int | None = None, offset: int = 0) -> list[dict]:
        with self._lock:
            docs = self._load(collection)
            end = None if limit is None else offset + limit
            return [{k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in d.items()}
                    for d in docs[offset:end]]

    def count(self, collection: str) -> int:
        with self._lock:
            return len(self._load(collection))

    def tables(self) -> list[str]:
        with self._lock:
            return sorted(f.stem for f in self.path.glob("*.jsonl"))

    def close(self) -> None:
        pass
