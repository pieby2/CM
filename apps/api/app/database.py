from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.engine.url import make_url

from app.config import settings


class Base(DeclarativeBase):
    pass


def _is_local_host(host: str | None) -> bool:
    return host in {None, "", "localhost", "127.0.0.1"}


db_url = make_url(settings.database_url)
engine_kwargs: dict = {
    "future": True,
    "pool_pre_ping": True,
    "pool_timeout": 20,
}

connect_args: dict = {}
if db_url.get_backend_name().startswith("postgresql"):
    connect_args["connect_timeout"] = max(1, int(settings.db_connect_timeout_seconds))
    if not _is_local_host(db_url.host) and "sslmode" not in db_url.query:
        connect_args["sslmode"] = "require"

if connect_args:
    engine_kwargs["connect_args"] = connect_args

engine = create_engine(
    settings.database_url,
    **engine_kwargs,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
