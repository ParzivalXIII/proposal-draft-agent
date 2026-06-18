from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from fastapi import Request
from typing import AsyncGenerator

from backend.core.config import settings

engine = create_async_engine(settings.database_url, echo=False)

async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine) as session:
        yield session

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)