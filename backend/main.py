from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from arq import create_pool
from arq.connections import RedisSettings
from contextlib import asynccontextmanager

from backend.core.config import settings
from backend.core.db import init_db, engine
from backend.routers import api, ui

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq_pool = await create_pool(
        RedisSettings(host=settings.redis_host, port=settings.redis_port)
    )
    app.state.templates = Jinja2Templates(directory="backend/templates")
    await init_db()
    yield
    await app.state.arq_pool.close()
    await engine.dispose()

app = FastAPI(lifespan=lifespan)

# Mount static files for Tailwind CSS
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include modular routers
app.include_router(api.router)
app.include_router(ui.router)