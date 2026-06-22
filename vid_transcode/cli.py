"""CLI interface for vid-transcode using typer."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from vid_transcode.transcoder import VideoInfo, transcode

app = typer.Typer(
    name="vid-transcode",
    help="Video transcoding tool - convert and process MP4 files",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


def _resolve_paths(input_path: str) -> list[Path]:
    """Resolve input paths, supporting glob patterns for batch processing."""
    p = Path(input_path)
    if p.is_dir():
        return sorted(p.glob("*.mp4"))
    if p.is_file():
        return [p]
    # Try as glob pattern
    results = sorted(Path().glob(input_path))
    if results:
        return results
    console.print(f"[red]Error:[/] No files found matching [bold]{input_path}[/]")
    sys.exit(1)


def _make_output_path(
    input_path: Path,
    output_arg: Optional[str],
    codec: str,
) -> Path:
    """Determine output path from input and output arguments."""
    if output_arg:
        out = Path(output_arg)
        if out.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            suffix = codec.replace("_nvenc", "")
            return out / f"{input_path.stem}_{suffix}{input_path.suffix}"
        return out
    suffix = codec.replace("_nvenc", "")
    return input_path.with_stem(f"{input_path.stem}_{suffix}")


@app.command()
def info(
    input: str = typer.Argument(..., help="Path to video file or directory"),
) -> None:
    """Show media information for one or more video files."""
    paths = _resolve_paths(input)
    for p in paths:
        try:
            vi = VideoInfo(p)
            console.print(f"\n[bold cyan]{vi}[/]")
        except Exception as e:
            console.print(f"[red]Failed to probe {p.name}: {e}[/]")


@app.command()
def convert(
    input: str = typer.Argument(..., help="Input video file, directory, or glob"),
    output: Optional[str] = typer.Option(
        None, "-o", "--output", help="Output file or directory"
    ),
    codec: str = typer.Option(
        "h264", "-c", "--codec",
        help="Target video codec (h264, h265, hevc, h264_nvenc, h265_nvenc)",
    ),
    crf: int = typer.Option(
        23, "--crf", min=0, max=51,
        help="Constant Rate Factor (0-51, lower = better quality)",
    ),
    preset: str = typer.Option(
        "medium", "--preset",
        help="Encoding preset (ultrafast, fast, medium, slow, veryslow)",
    ),
    max_width: Optional[int] = typer.Option(
        None, "-W", "--max-width", help="Maximum output width"
    ),
    max_height: Optional[int] = typer.Option(
        None, "-H", "--max-height", help="Maximum output height"
    ),
    video_bitrate: Optional[str] = typer.Option(
        None, "-b", "--bitrate", help="Target video bitrate (e.g. 2M, 1000k)"
    ),
    audio_codec: str = typer.Option(
        "copy", "--audio-codec",
        help="Audio codec: copy, aac, mp3, none",
    ),
    remove_audio: bool = typer.Option(
        False, "--no-audio", help="Remove all audio streams"
    ),
    overwrite: bool = typer.Option(
        False, "-y", "--yes", help="Overwrite output files without asking"
    ),
    dry_run: bool = typer.Option(
        False, "-n", "--dry-run", help="Print the ffmpeg command without executing"
    ),
) -> None:
    """Transcode video files with specified parameters."""
    paths = _resolve_paths(input)

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )

    with progress:
        task = progress.add_task(
            f"Transcoding {len(paths)} file(s)...", total=len(paths)
        )

        for p in paths:
            out_path = _make_output_path(p, output, codec)
            progress.update(
                task, description=f"[cyan]Transcoding[/] {p.name} \u2192 {out_path.name}"
            )

            try:
                result = transcode(
                    p,
                    out_path,
                    codec=codec,
                    crf=crf,
                    preset=preset,
                    max_width=max_width,
                    max_height=max_height,
                    video_bitrate=video_bitrate,
                    audio_codec=audio_codec,
                    remove_audio=remove_audio,
                    overwrite=overwrite,
                    dry_run=dry_run,
                )
            except Exception as e:
                progress.console.print(f"[red]Error processing {p.name}: {e}[/]")

            progress.advance(task)

    console.print("\n[bold green]\u2713 Done![/]")


@app.command()
def batch(
    input_dir: str = typer.Argument(..., help="Directory containing video files"),
    output_dir: str = typer.Option(
        "./output", "-o", "--output", help="Output directory"
    ),
    pattern: str = typer.Option(
        "*.mp4", "-p", "--pattern", help="File glob pattern"
    ),
    codec: str = typer.Option(
        "h264", "-c", "--codec",
        help="Target video codec (h264, h265, hevc)",
    ),
    crf: int = typer.Option(23, "--crf", help="CRF value (0-51)"),
    preset: str = typer.Option("medium", "--preset", help="Encoding preset"),
    max_width: Optional[int] = typer.Option(
        None, "-W", "--max-width", help="Maximum width"
    ),
) -> None:
    """Batch transcode all matching videos in a directory."""
    src_dir = Path(input_dir)
    if not src_dir.is_dir():
        console.print(f"[red]Error:[/] [bold]{input_dir}[/] is not a directory")
        sys.exit(1)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(src_dir.glob(pattern))
    if not files:
        console.print(f"[yellow]No files matching [bold]{pattern}[/] in {src_dir}[/]")
        sys.exit(1)

    console.print(f"[bold]Batch processing[/] {len(files)} file(s)...\n")

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )

    with progress:
        task = progress.add_task("Batch transcoding...", total=len(files))

        for p in files:
            out_path = out_dir / f"{codec}_{p.name}"
            progress.update(
                task,
                description=f"Transcoding {p.name} \u2192 {out_path.name}",
            )
            try:
                transcode(p, out_path, codec=codec, crf=crf, preset=preset, max_width=max_width)
            except Exception as e:
                progress.console.print(f"[red]Error:[/] {p.name}: {e}[/]")
            progress.advance(task)

    console.print(f"\n[bold green]\u2713 Done![/] Output in [bold]{out_dir}[/]")


def main() -> None:
    app()
