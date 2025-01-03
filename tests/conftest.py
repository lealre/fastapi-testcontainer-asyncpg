from collections.abc import AsyncGenerator, Generator
from typing import Literal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from src.app import app
from src.database import get_session
from src.models import Base


@pytest.fixture(scope='session')
def anyio_backend() -> Literal['asyncio']:
    return 'asyncio'


@pytest.fixture(scope='session')
def postgres_container(
    anyio_backend: Literal['asyncio'],
) -> Generator[PostgresContainer, None, None]:
    with PostgresContainer('postgres:16', driver='asyncpg') as postgres:
        yield postgres


@pytest.fixture
async def async_session(
    postgres_container: PostgresContainer,
) -> AsyncGenerator[AsyncSession, None]:
    db_url = postgres_container.get_connection_url()
    async_engine = create_async_engine(db_url)

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with async_session() as session:
        yield session

    await async_engine.dispose()


@pytest.fixture
async def async_client(
    async_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_session] = lambda: async_session
    _transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=_transport, base_url='http://test', follow_redirects=True
    ) as client:
        yield client

    app.dependency_overrides.clear()
