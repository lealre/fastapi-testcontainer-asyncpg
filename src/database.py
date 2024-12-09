from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DATABASE_URL = 'sqlite+aiosqlite:///db.sqlite3'

engine = create_async_engine(DATABASE_URL, future=True, echo=True)

AsyncSessionLocal = async_sessionmaker(
    autocommit=False,
    expire_on_commit=False,
    autoflush=True,
    bind=engine,
    class_=AsyncSession,
)


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session
