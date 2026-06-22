#!/usr/bin/env python3
"""FastAPI application entry point for vid-transcode web app."""

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from vid_transcode.api import router as api_router

app = FastAPI(
    title="vid-transcode",
    description="Video transcoding web app - convert videos to H.264 MP4",
    version="0.1.0",
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
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    main()
