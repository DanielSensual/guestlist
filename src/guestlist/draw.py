"""Shared drawing: one colour per guest label, mask outlines and id tags, sized to read after downscaling."""

from __future__ import annotations

import cv2
import numpy as np

# (name, BGR). Picked to stand out under purple/blue/red club light; the names go into Spark prompts.
PALETTE = [
    ("gold", (0, 200, 255)), ("lime", (60, 255, 120)), ("cyan", (255, 230, 0)), ("white", (255, 255, 255)),
    ("orange", (0, 130, 255)), ("pink", (190, 120, 255)), ("sky blue", (255, 180, 80)), ("yellow", (0, 255, 255)),
]
CROWD = ("grey", (150, 150, 150))


def color_for(label: str) -> tuple[str, tuple[int, int, int]]:
    if label.startswith("#") and label[1:].isdigit():
        return PALETTE[(int(label[1:]) - 1) % len(PALETTE)]
    return CROWD


def draw_outline(img: np.ndarray, box: tuple[int, int, int, int], mask: np.ndarray | None,
                 color: tuple[int, int, int], thickness: int, *, offset: tuple[int, int] = (0, 0),
                 scale: float = 1.0) -> None:
    """Mask contour when we have the mask, else the box. `offset`/`scale` map frame pixels into `img`."""
    ox, oy = offset
    l, t, r, b = box
    if mask is not None and mask.any():
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        moved = [((c + np.array([l - ox, t - oy])) * scale).astype(np.int32) for c in contours]
        cv2.drawContours(img, moved, -1, color, thickness, cv2.LINE_AA)
    else:
        p0 = (int((l - ox) * scale), int((t - oy) * scale))
        p1 = (int((r - 1 - ox) * scale), int((b - 1 - oy) * scale))
        cv2.rectangle(img, p0, p1, color, thickness, cv2.LINE_AA)


def tag_rect(box: tuple[int, int, int, int], text_wh: tuple[int, int], frame_wh: tuple[int, int],
             pad: int) -> tuple[int, int, int, int]:
    """Where the tag goes: above the box's top-left corner, or just inside the top when there is no room."""
    tw, th = text_wh
    fw, fh = frame_wh
    w, h = tw + 2 * pad, th + 2 * pad
    x0 = min(max(0, box[0]), max(0, fw - w))
    y0 = box[1] - h - 2 if box[1] - h - 2 >= 0 else min(box[1] + 2, max(0, fh - h))
    return x0, y0, x0 + w, y0 + h


def draw_tag(img: np.ndarray, text: str, box: tuple[int, int, int, int], color: tuple[int, int, int],
             font_scale: float, thickness: int) -> None:
    font = cv2.FONT_HERSHEY_DUPLEX
    (tw, th), base = cv2.getTextSize(text, font, font_scale, thickness)
    pad = max(4, th // 4)
    x0, y0, x1, y1 = tag_rect(box, (tw, th + base), (img.shape[1], img.shape[0]), pad)
    cv2.rectangle(img, (x0, y0), (x1, y1), color, -1)
    cv2.putText(img, text, (x0 + pad, y1 - pad - base), font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)
