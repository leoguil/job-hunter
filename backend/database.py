import logging
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

# ── Mode production : PostgreSQL Supabase ─────────────────────
if DATABASE_URL:
    _is_postgres = DATABASE_URL.startswith(("postgresql", "postgres"))
    _connect_args = {}
    _engine_kwargs: dict = {
        "pool_size": 3,       # conservateur — Supabase free = 20 connexions max
        "max_overflow": 2,
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

# ── Mode développement local : SQLite ─────────────────────────
else:
    logger.warning(
        "DATABASE_URL non défini — utilisation de SQLite local (mode dev uniquement)"
    )
    DATABASE_URL = "sqlite:///./job_hunter_dev.db"
    _is_postgres = False
    _connect_args = {"check_same_thread": False}
    _engine_kwargs = {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    **_engine_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
