from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from autodev.config import Settings
from autodev.db import models as _models  # noqa: F401
from autodev.db.base import Base
from autodev.db.session import Database
from autodev.main import create_app


@pytest.fixture
async def database() -> AsyncIterator[Database]:
    database = Database.__new__(Database)
    database.engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    database.session_factory = async_sessionmaker(
        database.engine, expire_on_commit=False, class_=AsyncSession
    )
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield database
    await database.dispose()


@pytest.fixture
async def client(database: Database) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        database_url="sqlite+aiosqlite://",
        credential_key=SecretStr(Fernet.generate_key().decode("ascii")),
    )
    application = create_app(settings, database)
    async with (
        application.router.lifespan_context(application),
        AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as test_client,
    ):
        yield test_client
