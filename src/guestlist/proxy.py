"""Analysis proxies: small, constant-frame-rate, faststart H.264 — the only thing ever uploaded."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def probe(path: str | Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def video_info(path: str | Path) -> dict:
    """{width, height (as displayed), fps, frames, duration}."""
    p = probe(path)
    v = next(s for s in p["streams"] if s["codec_type"] == "video")
    w, h = int(v["width"]), int(v["height"])
    rotation = abs(int((v.get("tags") or {}).get("rotate", 0) or 0))
    for sd in v.get("side_data_list") or []:
        rotation = abs(int(sd.get("rotation", rotation) or rotation))
    if rotation in (90, 270):
        w, h = h, w
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    duration = float(p["format"]["duration"])
    frames = int(v.get("nb_frames") or round(duration * num / den))
    return {"width": w, "height": h, "fps": num / den, "frames": frames, "duration": duration}


def make_proxy(src: str | Path, dst: str | Path, *, start: float = 0.0, duration: float | None = None,
               short_side: int = 720, fps: int = 12, crf: int = 26) -> Path:
    """Scale so the short side is `short_side`, resample to `fps` CFR, AAC audio, moov atom up front."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    scale = (f"scale='if(gt(iw,ih),-2,{short_side})':'if(gt(iw,ih),{short_side},-2)':flags=lanczos,"
             f"fps={fps},format=yuv420p")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-i", str(src)]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-map", "0:v:0", "-map", "0:a:0?", "-vf", scale, "-c:v", "libx264", "-preset", "veryfast",
            "-crf", str(crf), "-g", str(fps * 2), "-c:a", "aac", "-b:a", "96k", "-ac", "2",
            "-movflags", "+faststart", "-map_metadata", "-1", str(dst)]
    subprocess.run(cmd, check=True)
    return dst


def extract_wav(src: str | Path, dst: str | Path, *, rate: int = 24000) -> Path:
    """Mono 16-bit PCM WAV for Muse Voice Transcribe."""
    dst = Path(dst)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-ac", "1",
                    "-ar", str(rate), "-c:a", "pcm_s16le", "-map_metadata", "-1", str(dst)], check=True)
    return dst


def frame_at(src: str | Path, frame: int, fps: float, dst: str | Path) -> Path:
    """Grab one frame (by index at `fps`) as a PNG."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{frame / fps:.4f}",
                    "-i", str(src), "-frames:v", "1", str(dst)], check=True)
    return dst
