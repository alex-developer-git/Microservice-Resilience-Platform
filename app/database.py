from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.tracing import instrument_sqlalchemy_engine


def normalize_database_url(database_url: str) -> str:
    """Convert PostgreSQL URLs to the async SQLAlchemy driver format."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


def create_engine(database_url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine for the application database."""
    engine = create_async_engine(normalize_database_url(database_url), pool_pre_ping=True)
    instrument_sqlalchemy_engine(engine)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    """Create async sessions bound to the given engine."""
    return async_sessionmaker(engine, expire_on_commit=False)
