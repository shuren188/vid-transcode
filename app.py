#!/usr/bin/env python3
"""FastAPI application entry point for vid-transcode web app."""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from vid_transcode.api import cleanup_task_runner, router as api_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start background tasks on boot, clean up on shutdown."""
    cleanup_task = asyncio.create_task(cleanup_task_runner())
    yield
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="vid-transcode",
    description="Video transcoding web app - convert videos to H.264 MP4",
    version="0.1.8",
    lifespan=lifespan,
)

# CORS - allow dev frontend on different port
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(api_router)

# Serve frontend static files in production
FRONTEND_BUILD = Path(__file__).parent / "frontend" / "dist"
if FRONTEND_BUILD.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_BUILD), html=True), name="frontend")


def main() -> None:
    """Run the dev server."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
