# vid-transcode 🎬

Video transcoding tool — convert and process MP4 files with ease.

## Features

- **Codec conversion**: H.264 ↔ H.265 (HEVC) and more
- **Resolution scaling**: Downscale or upscale video
- **Quality control**: Adjust CRF, bitrate, preset
- **Batch processing**: Process multiple files at once
- **Audio handling**: Extract, replace, or remove audio tracks
- **Subtitle support**: Burn-in or extract subtitles

## Installation

```bash
pip install -r requirements.txt
```

Requires [FFmpeg](https://ffmpeg.org/) installed and available in PATH.

## Usage

```bash
# Basic transcoding
python main.py input.mp4 -o output.mp4

# Convert to H.265 with quality control
python main.py input.mp4 -o output.mp4 --codec h265 --crf 23

# Batch process all MP4s in a folder
python main.py ./videos/ -o ./output/ --codec h264 --preset medium
```

## License

MIT
