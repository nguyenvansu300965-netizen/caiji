from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.db.models import Base


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.execute("PRAGMA cache_size=-64000")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    migrations = {
        "collection_tasks": {
            "mode": "VARCHAR(20) NOT NULL DEFAULT 'single'",
            "target_count": "INTEGER NOT NULL DEFAULT 100000",
            "shard_total": "INTEGER NOT NULL DEFAULT 0",
            "shard_completed": "INTEGER NOT NULL DEFAULT 0",
            "duplicate_count": "INTEGER NOT NULL DEFAULT 0",
            "invalid_count": "INTEGER NOT NULL DEFAULT 0",
            "started_at": "DATETIME",
            "finished_at": "DATETIME",
        },
        "companies": {
            "category": "VARCHAR(120) NOT NULL DEFAULT ''",
            "website": "TEXT NOT NULL DEFAULT ''",
            "relevance": "VARCHAR(20) NOT NULL DEFAULT 'medium'",
        },
        "source_records": {
            "external_id": "VARCHAR(200) NOT NULL DEFAULT ''",
        },
    }
    with engine.begin() as connection:
        for table, columns in migrations.items():
            existing = {
                row[1]
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info({})".format(table)
                )
            }
            for name, definition in columns.items():
                if name not in existing:
                    connection.exec_driver_sql(
                        "ALTER TABLE {} ADD COLUMN {} {}".format(
                            table, name, definition
                        )
                    )
