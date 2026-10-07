import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# Absolute path to data/ next to project root — works from any working directory
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_data_dir = os.path.join(_project_root, "data")
os.makedirs(_data_dir, exist_ok=True)

_db_url = f"sqlite+aiosqlite:///{os.path.join(_data_dir, 'market_research.db')}"

engine = create_async_engine(_db_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
