"""Core transcoding logic for vid-transcode."""

from __future__ import annotations

import json
import subprocess
import shlex
from pathlib import Path
from typing import Optional


class VideoInfo:
    """Parsed media information from ffprobe."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data = self._probe()

    def _probe(self) -> dict:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(self.path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        result.check_returncode()
        return json.loads(result.stdout)

    @property
    def streams(self) -> list[dict]:
        return self._data.get("streams", [])

    @property
    def video_stream(self) -> Optional[dict]:
        for s in self.streams:
            if s.get("codec_type") == "video":
                return s
        return None

    @property
    def audio_stream(self) -> Optional[dict]:
        for s in self.streams:
            if s.get("codec_type") == "audio":
                return s
        return None

    @property
    def width(self) -> Optional[int]:
        vs = self.video_stream
        return int(vs["width"]) if vs and "width" in vs else None

    @property
    def height(self) -> Optional[int]:
        vs = self.video_stream
        return int(vs["height"]) if vs and "height" in vs else None

    @property
    def codec(self) -> Optional[str]:
        vs = self.video_stream
        return vs.get("codec_name") if vs else None

    @property
    def duration(self) -> Optional[float]:
        fmt = self._data.get("format", {})
        dur = fmt.get("duration")
        return float(dur) if dur else None

    @property
    def size_mb(self) -> Optional[float]:
        fmt = self._data.get("format", {})
        sz = fmt.get("size")
        return round(float(sz) / (1024 * 1024), 2) if sz else None

    def __str__(self) -> str:
        return (
            f"VideoInfo({self.path.name})\n"
            f"  Resolution: {self.width}\u00d7{self.height}\n"
            f"  Codec: {self.codec}\n"
            f"  Duration: {self.duration:.1f}s\n"
            f"  Size: {self.size_mb} MB"
        )


def get_encoder(codec: str) -> str:
    """Map short codec name to FFmpeg video encoder."""
    mapping = {
        "h264": "libx264",
        "h265": "libx265",
        "hevc": "libx265",
        "h264_nvenc": "h264_nvenc",
        "h265_nvenc": "hevc_nvenc",
    }
    return mapping.get(codec.lower(), codec)


def transcode(
    input_path: Path,
    output_path: Path,
    *,
    codec: str = "h264",
    crf: int = 23,
    preset: str = "medium",
    max_width: Optional[int] = None,
    max_height: Optional[int] = None,
    video_bitrate: Optional[str] = None,
    audio_codec: str = "copy",
    remove_audio: bool = False,
    dry_run: bool = False,
    overwrite: bool = False,
) -> subprocess.CompletedProcess:
    """Transcode a video file with the given parameters.

    Args:
        input_path: Source video file.
        output_path: Output video file.
        codec: Target video codec (h264, h265/hevc, h264_nvenc, h265_nvenc).
        crf: Constant Rate Factor (0-51, lower = better quality).
        preset: Encoding preset (ultrafast, fast, medium, slow, veryslow).
        max_width: Maximum width (maintains aspect ratio).
        max_height: Maximum height (maintains aspect ratio).
        video_bitrate: Target video bitrate (e.g. "2M", "1000k").
        audio_codec: Audio codec ("copy", "aac", "mp3", or "none").
        remove_audio: Remove all audio streams.
        dry_run: Print the ffmpeg command without executing.
        overwrite: Overwrite output file if it exists.
    """
    cmd = ["ffmpeg", "-i", str(input_path)]

    # Video codec
    video_opts = []
    encoder = get_encoder(codec)
    video_opts.extend(["-c:v", encoder])
    video_opts.extend(["-preset", preset])

    if video_bitrate:
        video_opts.extend(["-b:v", video_bitrate])
    else:
        video_opts.extend(["-crf", str(crf)])

    # Resolution scaling
    if max_width or max_height:
        scale_filter = []
        if max_width:
            scale_filter.append(f"min({max_width},iw)")
        if max_height:
            scale_filter.append(f"min({max_height},ih)")
        divider = ":"
        filters = f"scale={divider.join(scale_filter)}:force_original_aspect_ratio=decrease"
        video_opts.extend(["-vf", filters])

    cmd.extend(video_opts)

    # Audio
    if remove_audio or audio_codec == "none":
        cmd.extend(["-an"])
    else:
        cmd.extend(["-c:a", audio_codec])

    # Overwrite
    if overwrite:
        cmd.insert(1, "-y")

    cmd.append(str(output_path))


    if dry_run:
        print(" ".join(shlex.quote(str(part)) for part in cmd))
        return subprocess.CompletedProcess(cmd, 0)
    return subprocess.run(cmd, check=True)
