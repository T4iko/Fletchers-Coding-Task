import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")  # readers (polling UI) don't block the worker
    return con


def init_db(db_path: str) -> None:
    con = connect(db_path)
    with con:
        con.executescript(SCHEMA.read_text())
    con.close()