"""FastAPI router for video upload, async transcoding with progress, and download."""

from __future__ import annotations

import asyncio
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from vid_transcode.transcoder import VideoInfo
from vid_transcode import __version__

# Paths
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Resolution presets
RESOLUTION_PRESETS = {
    "480p":  {"height": 480,  "width": 854,  "label": "480p (SD)"},
    "720p":  {"height": 720,  "width": 1280, "label": "720p (HD)"},
    "1080p": {"height": 1080, "width": 1920, "label": "1080p (Full HD)"},
}

# In-memory job store
# Each value is a dict: {job_id, status, progress, input_name, resolution, ...}
_jobs: dict[str, dict] = {}


class UploadResponse(BaseModel):
    filename: str
    file_id: str
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    size_mb: Optional[float] = None
    codec: Optional[str] = None


class TranscodeRequest(BaseModel):
    file_id: str
    resolution: str


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: float
    input_name: str
    resolution: str
    output_filename: Optional[str] = None
    output_size_mb: Optional[float] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


def _get_video_duration(input_path: Path) -> float:
    info = VideoInfo(input_path)
    return info.duration or 0.0


async def _run_transcode(job_id: str) -> None:
    """Run FFmpeg in a subprocess, streaming progress into the job store."""
    job = _jobs[job_id]
    input_path = job["input_path"]
    output_path = job["output_path"]
    resolution = job["resolution"]
    total_duration = job.get("total_duration", 0.0)

    preset = RESOLUTION_PRESETS[resolution]
    target_height = preset["height"]
    target_width = preset["width"]

    bs = "\\"
    scale_filter = (
        f"scale=min({target_width}{bs},iw):min({target_height}{bs},ih)"
        ":force_original_aspect_ratio=decrease"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-vf", scale_filter,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", "128k",
        "-progress", "pipe:1",
        "-nostats",
        str(output_path),
    ]

    try:
        job["status"] = "processing"
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdout is not None
        async for line_bytes in proc.stdout:
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if line.startswith("out_time_us="):
                try:
                    us = int(line.split("=", 1)[1])
                    elapsed_s = us / 1_000_000
                    if total_duration > 0:
                        job["progress"] = min(round((elapsed_s / total_duration) * 100, 1), 99.9)
                except (ValueError, IndexError):
                    pass
        await proc.wait()
        if proc.returncode != 0:
            stderr_out = (await proc.stderr.read()).decode("utf-8", errors="replace")
            raise RuntimeError(f"FFmpeg error (exit {proc.returncode}):\n{stderr_out[-2000:]}")
        job["status"] = "completed"
        job["progress"] = 100.0
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
        if output_path.exists():
            job["output_size_mb"] = round(output_path.stat().st_size / (1024 * 1024), 2)
            job["output_filename"] = output_path.name
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        job["progress"] = 0.0


router = APIRouter(prefix="/api")


@router.get("/resolutions")
def list_resolutions():
    return {k: {"width": v["width"], "height": v["height"], "label": v["label"]} for k, v in RESOLUTION_PRESETS.items()}


@router.post("/upload", response_model=UploadResponse)
async def upload_video(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "No file provided")
    allowed_ext = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_ext:
        raise HTTPException(400, f"Unsupported file type: {ext}")
    file_id = str(uuid.uuid4())
    safe_name = f"{file_id}{ext}"
    dest = UPLOAD_DIR / safe_name
    content = await file.read()
    dest.write_bytes(content)
    try:
        info = VideoInfo(dest)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not read video file: {e}")
    return UploadResponse(
        filename=file.filename, file_id=file_id,
        width=info.width, height=info.height,
        duration=info.duration, size_mb=info.size_mb, codec=info.codec,
    )


@router.post("/transcode", response_model=JobStatus)
async def start_transcode(req: TranscodeRequest):
    if req.resolution not in RESOLUTION_PRESETS:
        raise HTTPException(400, f"Invalid resolution: {req.resolution}")
    input_path: Optional[Path] = None
    for f in UPLOAD_DIR.iterdir():
        if f.stem == req.file_id and f.is_file():
            input_path = f
            break
    if input_path is None:
        raise HTTPException(404, "Uploaded file not found")
    duration = _get_video_duration(input_path)
    job_id = str(uuid.uuid4())
    output_path = OUTPUT_DIR / f"{job_id}.mp4"
    job = {
        "job_id": job_id, "status": "pending", "progress": 0.0,
        "input_name": input_path.name, "resolution": req.resolution,
        "output_filename": None, "output_size_mb": None, "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(), "completed_at": None,
        "input_path": input_path, "output_path": output_path, "total_duration": duration,
    }
    _jobs[job_id] = job
    asyncio.create_task(_run_transcode(job_id))
    return JobStatus(**{k: v for k, v in job.items() if k not in ("input_path", "output_path", "total_duration")})


@router.get("/jobs/{job_id}", response_model=JobStatus)
def get_job_status(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return JobStatus(**{k: v for k, v in job.items() if k not in ("input_path", "output_path", "total_duration")})


@router.get("/download/{job_id}")
def download_file(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job["status"] != "completed":
        raise HTTPException(400, "Transcoding not yet complete")
    output_path: Path = job["output_path"]
    if not output_path.exists():
        raise HTTPException(404, "Output file not found")
    orig = Path(job["input_name"])
    download_name = f"{orig.stem}_{job['resolution']}.mp4"
    return FileResponse(path=output_path, filename=download_name, media_type="video/mp4")


@router.get("/version")
def get_version():
    return {"version": __version__}
