"""SQLite state with separate entities for source adoption, business cases and fulfillment."""
import sqlite3
from pathlib import Path
from .policy import TABLES

def connect(path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    t=TABLES
    db.executescript(f"""
    CREATE TABLE IF NOT EXISTS source_event(
      source_id TEXT, revision INTEGER, digest TEXT, raw TEXT, captured_at TEXT,
      PRIMARY KEY(source_id,revision));
    CREATE TABLE IF NOT EXISTS source_conflict(
      id INTEGER PRIMARY KEY, source_id TEXT, revision INTEGER, digest TEXT, reason TEXT);
    CREATE TABLE IF NOT EXISTS map_source(
      source_id TEXT NOT NULL, revision INTEGER NOT NULL, digest TEXT NOT NULL, raw TEXT NOT NULL,
      PRIMARY KEY(source_id,revision));
    CREATE TABLE IF NOT EXISTS map_sheet(
      source_id TEXT NOT NULL, revision INTEGER NOT NULL, sheet_id TEXT NOT NULL, tile_id TEXT NOT NULL,
      point_a TEXT NOT NULL, point_b TEXT NOT NULL, low REAL NOT NULL, high REAL NOT NULL,
      remeasure_cost REAL NOT NULL,
      PRIMARY KEY(source_id,revision,sheet_id),
      FOREIGN KEY(source_id,revision) REFERENCES map_source(source_id,revision));
    CREATE TABLE IF NOT EXISTS {t['notice']}(
      id TEXT PRIMARY KEY, current_revision INTEGER NOT NULL, state TEXT NOT NULL,
      changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS {t['revision']}(
      source_id TEXT, revision INTEGER, published_at TEXT, effective_from TEXT,
      effective_until TEXT, digest TEXT, state TEXT, reason TEXT, payload TEXT,
      PRIMARY KEY(source_id,revision));
    CREATE TABLE IF NOT EXISTS {t['case']}(
      id TEXT PRIMARY KEY, source_id TEXT NOT NULL, at TEXT NOT NULL,
      facts TEXT NOT NULL, input_hash TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS {t['assessment']}(
      id INTEGER PRIMARY KEY, case_id TEXT NOT NULL, source_revision INTEGER,
      state TEXT NOT NULL, outcome TEXT NOT NULL, detail TEXT NOT NULL,
      stale INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS {t['obligation']}(
      id TEXT PRIMARY KEY, assessment_id INTEGER NOT NULL, target TEXT NOT NULL,
      deadline TEXT NOT NULL, required INTEGER NOT NULL, meta TEXT NOT NULL,
      state TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS {t['receipt']}(
      event_key TEXT PRIMARY KEY, obligation_id TEXT NOT NULL, at TEXT NOT NULL,
      version INTEGER, amount INTEGER NOT NULL, payload TEXT NOT NULL,
      digest TEXT NOT NULL, verdict TEXT NOT NULL, reason TEXT NOT NULL);
    """)
    return db

