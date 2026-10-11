from __future__ import annotations

import os
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/lxscale_development"


def get_db_url() -> str:
    url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres://") and not url.startswith("postgres+"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


engine = create_engine(get_db_url(), echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
