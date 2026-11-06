"""
Asynchronous Database Session Management (SQLAlchemy 2.0 + asyncpg).
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Optional
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.config import settings
from backend.app.db.base import Base

# Module-level engine and sessionmaker singletons
_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


def get_async_engine(database_url: Optional[str] = None) -> AsyncEngine:
    """Returns or initializes the async engine singleton."""
    global _engine
    if _engine is None or database_url is not None:
        url = database_url or settings.DATABASE_URL
        if not url:
            # Fallback for environments without configured database
            url = "sqlite+aiosqlite:///:memory:"

        # Convert standard postgres:// or postgresql:// to postgresql+asyncpg:// if needed
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

        connect_args = {}
        extra_kwargs = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            extra_kwargs["poolclass"] = StaticPool

        _engine = create_async_engine(
            url,
            echo=settings.DEBUG_MODE,
            future=True,
            connect_args=connect_args,
            **extra_kwargs,
        )
    return _engine


def get_session_factory(engine: Optional[AsyncEngine] = None) -> async_sessionmaker[AsyncSession]:
    """Returns or initializes the sessionmaker factory singleton."""
    global _sessionmaker
    if _sessionmaker is None or engine is not None:
        target_engine = engine or get_async_engine()
        _sessionmaker = async_sessionmaker(
            bind=target_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


@asynccontextmanager
async def transaction_scope(session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """Provides a transactional scope around a series of operations."""
    if session.in_transaction():
        yield session
    else:
        async with session.begin():
            yield session


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for obtaining an asynchronous database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db(engine: Optional[AsyncEngine] = None) -> None:
    """Initializes schema tables if not already created (used in testing & local runs)."""
    target_engine = engine or get_async_engine()
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Closes all database connections and disposes of engine."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
