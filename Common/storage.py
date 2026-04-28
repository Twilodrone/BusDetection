import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class LoopEvent:
    ts_utc: str
    source_host: str
    active_count: int
    values: dict[str, str]


@dataclass
class BusEvent:
    ts_utc: str
    bus_detected: bool
    confidence: float
    image_path: str
    meta: dict[str, Any]


class DetectionStorage:
    """Общее хранилище для двух независимых компонентов: monitor + detector."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS loop_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_utc TEXT NOT NULL,
                    source_host TEXT NOT NULL,
                    active_count INTEGER NOT NULL,
                    values_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bus_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_utc TEXT NOT NULL,
                    bus_detected INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    image_path TEXT NOT NULL,
                    meta_json TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_loop_events_ts ON loop_events(ts_utc)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bus_events_ts ON bus_events(ts_utc)")
            conn.commit()

    def insert_loop_event(self, event: LoopEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO loop_events (ts_utc, source_host, active_count, values_json)
                VALUES (?, ?, ?, ?)
                """,
                (event.ts_utc, event.source_host, event.active_count, json.dumps(event.values, ensure_ascii=False)),
            )
            conn.commit()

    def insert_bus_event(self, event: BusEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO bus_events (ts_utc, bus_detected, confidence, image_path, meta_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.ts_utc,
                    int(event.bus_detected),
                    event.confidence,
                    event.image_path,
                    json.dumps(event.meta, ensure_ascii=False),
                ),
            )
            conn.commit()


def utc_now_iso_ms() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
