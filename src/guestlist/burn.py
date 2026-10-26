"""The marked proxy: our track outlines and #tags burned into a copy of the analysis proxy.

Muse Spark watches the marked copy, so it names people by the tags our tracker gave them instead
of inventing its own P1/P2 labels (visual prompting). That turns "which P is which track" from a
guess into a check: every person Spark mentions is a tag we can test against SAM's geometry.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy as np

from .draw import color_for, draw_outline, draw_tag
from .tracks import Track


def legend(tracks: list[Track]) -> dict[str, str]:
    """tag -> colour name, for the prompt."""
    return {t.label: color_for(t.label)[0] for t in sorted(tracks, key=lambda t: (len(t.label), t.label))}


def burn_ids(video: str | Path, tracks: list[Track], out: str | Path, *,
             masks: dict[tuple[int, str], np.ndarray] | None = None) -> Path:
    """Re-encode `video` with each track's outline and tag on every frame it is seen; audio is copied."""
    video, out = Path(video), Path(out)
    cap = cv2.VideoCapture(str(video))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    scale = w / 720  # tags must survive Spark's downscaling: ~40 px tall on a 720-wide proxy
    font_scale, text_thick, line_thick = 1.5 * scale, max(2, round(3 * scale)), max(2, round(4 * scale))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part.mp4")
    enc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", f"{fps:g}", "-i", "-",
         "-i", str(video), "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
         "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", "-map_metadata", "-1", "-shortest",
         str(tmp)],
        stdin=subprocess.PIPE)
    frame = 0
    try:
        while True:
            ok, img = cap.read()
            if not ok:
                break
            for t in tracks:
                box = t.box_at(frame)
                if box is None:
                    continue
                _, color = color_for(t.label)
                draw_outline(img, box, (masks or {}).get((frame, t.track_id)), color, line_thick)
                draw_tag(img, t.label, box, color, font_scale, text_thick)
            enc.stdin.write(img.tobytes())
            frame += 1
    finally:
        cap.release()
        enc.stdin.close()
        if enc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed writing {out}")
    tmp.rename(out)
    return out
