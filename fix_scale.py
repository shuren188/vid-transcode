import pathlib
p = pathlib.Path("F:/Codex/vid-transcode/vid_transcode/api.py")
content = p.read_text("utf-8")

# Fix 1: Remove single quotes from scale filter
content = content.replace(
    "scale='min({target_width},iw)':min({target_height},ih)",
    "scale=min({target_width},iw):min({target_height},ih)"
)

# Fix 2: Single-line RuntimeError (Python 3.11 compatible)
old = """raise RuntimeError(f"FFmpeg error (exit {proc.returncode}):
{stderr_out[-2000:]}")"""
new = """raise RuntimeError(f"FFmpeg error (exit {proc.returncode}):\\n{stderr_out[-2000:]}")"""
content = content.replace(old, new)

p.write_text(content, "utf-8")
print("Fixes applied")

import ast
try:
    ast.parse(content)
    print("SYNTAX: OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
