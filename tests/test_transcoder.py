"""Tests for vid_transcode.transcoder."""

from pathlib import Path

import pytest

from vid_transcode.transcoder import VideoInfo, get_encoder


class TestGetEncoder:
    def test_h264(self) -> None:
        assert get_encoder("h264") == "libx264"

    def test_h265(self) -> None:
        assert get_encoder("h265") == "libx265"

    def test_hevc_alias(self) -> None:
        assert get_encoder("hevc") == "libx265"

    def test_nvenc_h264(self) -> None:
        assert get_encoder("h264_nvenc") == "h264_nvenc"

    def test_nvenc_h265(self) -> None:
        assert get_encoder("h265_nvenc") == "hevc_nvenc"

    def test_unknown_passthrough(self) -> None:
        assert get_encoder("libaom-av1") == "libaom-av1"


class TestVideoInfo:
    def test_init_no_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            VideoInfo(Path("/nonexistent/video.mp4"))

    def test_probe_missing_ffprobe(self) -> None:
        """If ffprobe is missing, subprocess should fail."""
        import subprocess
        from pathlib import Path
        with pytest.raises(FileNotFoundError):
            VideoInfo(Path("tests/__init__.py"))


class TestTranscodeParams:
    """Verify transcoding command construction (without running ffmpeg)."""

    def test_basic_command_structure(self) -> None:
        from vid_transcode.transcoder import transcode
        import subprocess

        # Patch subprocess.run to inspect the command
        original_run = subprocess.run
        captured = None

        def mock_run(*args, **kwargs):
            nonlocal captured
            captured = args[0]
            # Return a mock result
            result = subprocess.CompletedProcess(args[0], 0)
            return result

        subprocess.run = mock_run
        try:
            transcode(Path("input.mp4"), Path("output.mp4"), codec="h264")
        except Exception:
            pass
        finally:
            subprocess.run = original_run

        assert captured is not None, "subprocess.run was not called"
        cmd = captured
        assert "-i" in cmd
        assert "input.mp4" in cmd
        assert "output.mp4" in cmd
        assert "-c:v" in cmd
        assert "libx264" in cmd
        assert "-crf" in cmd
        assert "23" in str(cmd)

    def test_h265_command(self) -> None:
        from vid_transcode.transcoder import transcode
        import subprocess

        original_run = subprocess.run
        captured = None

        def mock_run(*args, **kwargs):
            nonlocal captured
            captured = args[0]
            result = subprocess.CompletedProcess(args[0], 0)
            return result

        subprocess.run = mock_run
        try:
            transcode(Path("input.mp4"), Path("out.mp4"), codec="hevc", crf=28)
        except Exception:
            pass
        finally:
            subprocess.run = original_run

        assert captured is not None
        cmd = captured
        assert "libx265" in str(cmd)
        assert "28" in str(cmd)
