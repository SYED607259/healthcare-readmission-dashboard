from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from pathlib import Path


DATABASE_PATH = Path(__file__).with_name("caresignal.db")


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return f"{salt.hex()}:{digest.hex()}"


def create_database() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Healthcare Analyst',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        exists = connection.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        if not exists:
            connection.execute(
                """
                INSERT INTO users (username, display_name, password_hash, role)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "admin",
                    "Demo Administrator",
                    _password_hash("CareSignal2026!"),
                    "Analytics Administrator",
                ),
            )


def create_user(username: str, display_name: str, password: str) -> tuple[bool, str]:
    username = username.strip().lower()
    display_name = display_name.strip()
    if len(username) < 3:
        return False, "Username must contain at least 3 characters."
    if len(password) < 8:
        return False, "Password must contain at least 8 characters."
    if not display_name:
        return False, "Please enter your full name."
    try:
        with _connect() as connection:
            connection.execute(
                "INSERT INTO users (username, display_name, password_hash) VALUES (?, ?, ?)",
                (username, display_name, _password_hash(password)),
            )
        return True, "Account created successfully. You can now sign in."
    except sqlite3.IntegrityError:
        return False, "That username is already registered."


def authenticate_user(username: str, password: str) -> dict | None:
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT id, username, display_name, password_hash, role
            FROM users WHERE username = ?
            """,
            (username.strip(),),
        ).fetchone()
    if not row:
        return None
    try:
        salt_hex, expected_hex = row["password_hash"].split(":", 1)
        candidate_hex = _password_hash(password, bytes.fromhex(salt_hex)).split(":", 1)[1]
    except (ValueError, TypeError):
        return None
    if not hmac.compare_digest(candidate_hex, expected_hex):
        return None
    return {key: row[key] for key in ("id", "username", "display_name", "role")}

