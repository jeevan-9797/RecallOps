"""
RecallOps - Database Connection & Session Management
Member 3: Database & Data Engineering

Provides resilient connection management, connection pooling, and FastAPI session dependencies.
Supports PostgreSQL (Supabase, local Docker, cloud PG) and safe fallback for testing.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator, Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from database.models import Base

# Load environment variables
load_dotenv()

logger = logging.getLogger("recallops.database")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def get_database_url() -> str:
    """
    Retrieve and normalize the DATABASE_URL environment variable.
    Handles 'postgres://' -> 'postgresql://' and default configurations.
    """
    url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/recallops")
    
    # Modern SQLAlchemy requires postgresql:// instead of legacy postgres://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
        
    return url


_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker[Session]] = None


def get_engine(url: Optional[str] = None, echo: bool = False) -> Engine:
    """
    Get or create the singleton SQLAlchemy Engine with production-ready connection pool settings.
    """
    global _engine
    target_url = url or get_database_url()
    
    # If engine already exists for this URL, return it
    if _engine is not None and str(_engine.url) == target_url:
        return _engine
        
    is_sqlite = target_url.startswith("sqlite")
    
    connect_args = {}
    pool_kwargs = {}
    
    if is_sqlite:
        connect_args = {"check_same_thread": False}
    else:
        # PostgreSQL pool configuration
        pool_kwargs = {
            "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
            "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
            "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
            "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
            "pool_pre_ping": True,
        }
        
    _engine = create_engine(
        target_url,
        echo=echo,
        connect_args=connect_args,
        **pool_kwargs,
    )
    return _engine


def get_session_factory(engine: Optional[Engine] = None) -> sessionmaker[Session]:
    """
    Get or create the sessionmaker factory.
    """
    global _session_factory
    eng = engine or get_engine()
    if _session_factory is None or _session_factory.kw.get("bind") != eng:
        _session_factory = sessionmaker(
            bind=eng,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


@contextmanager
def get_session(engine: Optional[Engine] = None) -> Generator[Session, None, None]:
    """
    Context manager for database sessions with automatic commit and rollback.
    """
    factory = get_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session rolled back due to error: {e}")
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session.
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def check_connection(engine: Optional[Engine] = None, timeout: int = 5) -> bool:
    """
    Test whether the database connection is live and healthy.
    """
    eng = engine or get_engine()
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
            return True
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return False


def init_db(engine: Optional[Engine] = None, drop_all: bool = False) -> None:
    """
    Initialize all database tables defined in SQLAlchemy models.
    """
    eng = engine or get_engine()
    if drop_all:
        logger.info("Dropping all existing database tables...")
        Base.metadata.drop_all(bind=eng)
    logger.info("Creating all database tables...")
    Base.metadata.create_all(bind=eng)
    logger.info("Database schema initialized successfully.")
