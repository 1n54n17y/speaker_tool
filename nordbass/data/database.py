"""
SQLite CRUD for drivers and projects.
Auto-creates tables on first connection.
"""
import json
import sqlite3
from pathlib import Path
from typing import List, Optional

from ..core.models import Driver, Project
from . import DB_PATH


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Return a connection, auto-creating the DB file and tables."""
    p = db_path or DB_PATH
    _ensure_dir(p)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS drivers (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL
        );
        """
    )
    conn.commit()


# ── Drivers ──────────────────────────────────────────────────────────────

def save_driver(driver: Driver, conn: Optional[sqlite3.Connection] = None) -> None:
    c = conn or get_connection()
    c.execute(
        "INSERT OR REPLACE INTO drivers (id, data) VALUES (?, ?)",
        (driver.id, driver.model_dump_json()),
    )
    c.commit()
    if conn is None:
        c.close()


def get_driver(driver_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Driver]:
    c = conn or get_connection()
    row = c.execute("SELECT data FROM drivers WHERE id = ?", (driver_id,)).fetchone()
    if conn is None:
        c.close()
    if row is None:
        return None
    return Driver.model_validate_json(row["data"])


def list_drivers(conn: Optional[sqlite3.Connection] = None) -> List[Driver]:
    c = conn or get_connection()
    rows = c.execute("SELECT data FROM drivers ORDER BY rowid").fetchall()
    if conn is None:
        c.close()
    return [Driver.model_validate_json(r["data"]) for r in rows]


def delete_driver(driver_id: str, conn: Optional[sqlite3.Connection] = None) -> bool:
    c = conn or get_connection()
    cur = c.execute("DELETE FROM drivers WHERE id = ?", (driver_id,))
    c.commit()
    deleted = cur.rowcount > 0
    if conn is None:
        c.close()
    return deleted


# ── Projects ─────────────────────────────────────────────────────────────

def save_project(project: Project, conn: Optional[sqlite3.Connection] = None) -> None:
    c = conn or get_connection()
    c.execute(
        "INSERT OR REPLACE INTO projects (id, data) VALUES (?, ?)",
        (project.id, project.model_dump_json()),
    )
    c.commit()
    if conn is None:
        c.close()


def get_project(project_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Project]:
    c = conn or get_connection()
    row = c.execute("SELECT data FROM projects WHERE id = ?", (project_id,)).fetchone()
    if conn is None:
        c.close()
    if row is None:
        return None
    return Project.model_validate_json(row["data"])


def list_projects(conn: Optional[sqlite3.Connection] = None) -> List[Project]:
    c = conn or get_connection()
    rows = c.execute("SELECT data FROM projects ORDER BY rowid").fetchall()
    if conn is None:
        c.close()
    return [Project.model_validate_json(r["data"]) for r in rows]


def delete_project(project_id: str, conn: Optional[sqlite3.Connection] = None) -> bool:
    c = conn or get_connection()
    cur = c.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    c.commit()
    deleted = cur.rowcount > 0
    if conn is None:
        c.close()
    return deleted
