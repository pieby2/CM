from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.database import engine


@dataclass
class MigrationFile:
    version: str
    name: str
    path: Path
    checksum: str


def main() -> None:
    migrations = _discover_migrations()
    _ensure_migrations_table()

    applied = _applied_versions()
    pending = [migration for migration in migrations if migration.version not in applied]

    if not pending:
        print("No pending migrations.")
        return

    for migration in pending:
        _apply_migration(migration)
        print(f"Applied migration {migration.version} ({migration.name})")

    print(f"Migration run complete. Applied {len(pending)} migration(s).")


def _discover_migrations() -> list[MigrationFile]:
    migrations_dir = Path(__file__).resolve().parent.parent / "db" / "migrations"
    sql_files = sorted(migrations_dir.glob("*.sql"))

    migrations: list[MigrationFile] = []
    versions_seen: set[str] = set()

    for sql_file in sql_files:
        version = sql_file.stem.split("_", maxsplit=1)[0]
        if not version.isdigit():
            raise ValueError(f"Migration filename must start with numeric version: {sql_file.name}")
        if version in versions_seen:
            raise ValueError(f"Duplicate migration version: {version}")
        versions_seen.add(version)

        checksum = hashlib.sha256(sql_file.read_bytes()).hexdigest()
        migrations.append(
            MigrationFile(
                version=version,
                name=sql_file.name,
                path=sql_file,
                checksum=checksum,
            )
        )

    return migrations


def _ensure_migrations_table() -> None:
    create_sql = """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version VARCHAR(32) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        checksum VARCHAR(128) NOT NULL,
        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """
    with engine.begin() as conn:
        conn.exec_driver_sql(create_sql)


def _applied_versions() -> set[str]:
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT version FROM schema_migrations")).all()
    return {str(row[0]) for row in rows}


def _apply_migration(migration: MigrationFile) -> None:
    statements = _split_sql_statements(migration.path.read_text(encoding="utf-8"))
    if not statements:
        raise ValueError(f"Migration has no executable statements: {migration.name}")

    with engine.begin() as conn:
        for statement in statements:
            conn.exec_driver_sql(statement)

        conn.execute(
            text(
                """
                INSERT INTO schema_migrations (version, name, checksum, applied_at)
                VALUES (:version, :name, :checksum, :applied_at)
                """
            ),
            {
                "version": migration.version,
                "name": migration.name,
                "checksum": migration.checksum,
                "applied_at": datetime.now(timezone.utc),
            },
        )


def _split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False

    for char in sql:
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote

        if char == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            continue

        current.append(char)

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)

    return statements


if __name__ == "__main__":
    main()
