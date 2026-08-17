from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db, queue
from .api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    queue.start()
    yield
    queue.stop()


app = FastAPI(
    title="AI Design Compliance Agent",
    description=(
        "Detects the niche of a print-on-demand design and screens it for "
        "trademark, copyright, publicity-rights and platform-policy risk."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local tool; the API is not exposed publicly
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    return {"service": "ai-design-compliance", "docs": "/docs", "health": "/api/health"}
