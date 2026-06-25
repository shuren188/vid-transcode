"""FastAPI router for video upload, async transcoding with progress, and download."""

from __future__ import annotations

import asyncio
import os
import time
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

# Limits
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
_concurrency_sem = asyncio.Semaphore(1)  # Only 1 transcode at a time (free tier)

# In-memory job store
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


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: float
    input_name: str
    output_filename: Optional[str] = None
    output_size_mb: Optional[float] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


def _get_video_duration(input_path: Path) -> float:
    info = VideoInfo(input_path)
    return info.duration or 0.0


async def _run_transcode(job_id: str) -> None:
    """Run FFmpeg, streaming progress into the job store.

    千牛/淘宝视频上传要求 (official):
      - Format: MP4 H.264 High Profile
      - Resolution: ≥ 720p (keep original)
      - Average bitrate: > 0.56 Mbps (min 600k)
      - Frame rate: ≤ 30 fps
      - Audio: AAC ≤ 128k
      - File size: ≤ 120 MB
    """
    job = _jobs[job_id]
    input_path = job["input_path"]
    output_path = job["output_path"]
    total_duration = job.get("total_duration", 0.0)

    # ── 拼多多兼容编码（确保有音频轨）──
    # 很多平台(包括拼多多)的转码器遇到无音轨视频会崩溃。
    # 强制添加一条静音AAC音轨，确保平台转码流程正常。
    target_w = 1920
    target_h = 1080
    scale = f"scale=min({target_w}\\,iw):min({target_h}\\,ih)"
    vf = (
        f"fps=30,"
        f"{scale}:force_original_aspect_ratio=decrease,"
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        # 生成静音音频轨
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        # ── 视频 ──
        "-map", "0:v:0",
        "-c:v", "libx264",
        "-profile:v", "main",
        "-level:v", "4.0",
        "-preset", "fast",
        "-crf", "23",
        "-threads", "2",
        "-vf", vf,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        # ── 清理SEI和元数据 ──
        "-bsf:v", "filter_units=remove_types=6",
        "-map_metadata", "-1",
        "-map_chapters", "-1",
        # ── 音频：用生成的静音轨 ──
        "-map", "1:a:0",
        "-c:a", "aac",
        "-b:a", "64k",
        "-ar", "44100",
        "-ac", "2",
        # 以视频长度为准
        "-shortest",
        "-progress", "pipe:1",
        "-nostats",
        str(output_path),
    ]

    async with _concurrency_sem:
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


@router.get("/version")
def get_version():
    return {"version": __version__}


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
    # Stream-write in chunks to avoid OOM on large files
    total_bytes = 0
    with dest.open("wb") as f:
        while chunk := await file.read(8 * 1024 * 1024):
            total_bytes += len(chunk)
            if total_bytes > MAX_FILE_SIZE:
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"File too large (max {MAX_FILE_SIZE // (1024*1024)}MB)")
            f.write(chunk)
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
        "input_name": input_path.name,
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
    download_name = f"{orig.stem}_h264.mp4"
    return FileResponse(path=output_path, filename=download_name, media_type="video/mp4")


async def cleanup_task_runner() -> None:
    """Periodically purge files & stale job records older than 2 hours."""
    while True:
        await asyncio.sleep(3600)
        cutoff = time.time() - 7200
        # Clean up uploaded / transcoded files
        for d in (UPLOAD_DIR, OUTPUT_DIR):
            if d.is_dir():
                for f in d.iterdir():
                    if f.is_file() and f.stat().st_mtime < cutoff:
                        f.unlink(missing_ok=True)
        # Clean up completed / failed job records
        for job_id, job in list(_jobs.items()):
            completed_at = job.get("completed_at")
            if completed_at:
                try:
                    ts = datetime.fromisoformat(completed_at).timestamp()
                    if ts < cutoff:
                        del _jobs[job_id]
                except (ValueError, TypeError):
                    pass
