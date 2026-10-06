"""
alembic/env.py
─────────────────────────────────────────────────────────────────────────────
PURPOSE: Alembic migration environment configuration.

Alembic is the database migration tool for SQLAlchemy. It tracks changes to
your database schema over time — like Git but for database tables.

HOW TO USE:
  Generate a migration:  alembic revision --autogenerate -m "add column X"
  Apply migrations:      alembic upgrade head
  Rollback last:         alembic downgrade -1

WHY we need this:
  When you change models.py (add/remove columns), the database doesn't update
  automatically. Alembic compares your models to the DB and generates SQL
  ALTER TABLE scripts to bring the DB up to date safely.

CONNECTED TO:
  - database.py  → imports Base (which has all table metadata)
  - models.py    → imported to register all ORM models on Base.metadata
  - alembic.ini  → provides the database URL configuration
  - .env         → DATABASE_URL overrides alembic.ini at runtime
─────────────────────────────────────────────────────────────────────────────
"""

import asyncio

import os

import sys

from logging.config import fileConfig

from sqlalchemy import pool

from sqlalchemy.engine import Connection

from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# noqa: F401 → tells the linter not to warn about "imported but unused" (it IS used via metadata).
from database import Base  # noqa: F401

# noqa: F401 → suppress "unused import" lint warning.
import models  # noqa: F401 — registers all ORM classes on Base.metadata

config = context.config

db_url = os.getenv("DATABASE_URL", "")  # read from environment
if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)  # apply logging config from alembic.ini

target_metadata = Base.metadata



def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL script)."""
    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,                           # target database connection string
        target_metadata=target_metadata,   # our SQLAlchemy models schema
        literal_binds=True,               # embed values directly in SQL (no %s placeholders)
        dialect_opts={"paramstyle": "named"},  # use :name style parameters for readability
    )

    with context.begin_transaction():
        context.run_migrations()  # generates/executes SQL for pending migrations



def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,           # live database connection
        target_metadata=target_metadata  # our SQLAlchemy models (desired schema)
    )
    with context.begin_transaction():
        context.run_migrations()  # applies ALTER TABLE, CREATE TABLE, etc.


async def run_async_migrations() -> None:
    """Run migrations against a live async DB connection."""
    section = config.get_section(config.config_ini_section, {})
    if db_url:
        section["sqlalchemy.url"] = db_url

    connectable = async_engine_from_config(
        section,  # alembic.ini [alembic] settings with runtime DB URL
        prefix="sqlalchemy.",   # key prefix for engine settings (sqlalchemy.url, etc.)
        poolclass=pool.NullPool,  # no connection pool — connect once, migrate, disconnect
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)  # run the sync migration function

    await connectable.dispose()



def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())



if context.is_offline_mode():
    run_migrations_offline()  # generate SQL script without DB connection
else:
    run_migrations_online()   # apply migrations to the live database
