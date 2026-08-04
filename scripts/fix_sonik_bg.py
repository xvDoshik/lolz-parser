#!/usr/bin/env python3
"""Remove Pinterest checkerboard from sonik.jpg: medium mask + soft edge (blurred matte)."""
from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "sonik.jpg"
DST = ROOT / "sonik.jpg"
FILL = (10, 10, 10)

# Slightly stronger than “conservative”, still below old aggressive flood.
CHROMA_MAX = 26
MIN_CHANNEL = 156
NEIGH_MAX = 64

# Feather edge of foreground mask (PIL GaussianBlur radius ≈ σ)
EDGE_BLUR_RADIUS = 1.35


def is_light_neutral(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    if min(r, g, b) < MIN_CHANNEL:
        return False
    return max(r, g, b) - min(r, g, b) <= CHROMA_MAX


def flood_bg_mask(im: Image.Image) -> bytearray:
    w, h = im.size
    px = im.load()
    bg = bytearray(w * h)

    def ixy(x: int, y: int) -> int:
        return y * w + x

    q: deque[tuple[int, int]] = deque()
    for x in range(w):
        for y in (0, h - 1):
            if is_light_neutral(px[x, y]):
                j = ixy(x, y)
                if not bg[j]:
                    bg[j] = 1
                    q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            j = ixy(x, y)
            if bg[j]:
                continue
            if is_light_neutral(px[x, y]):
                bg[j] = 1
                q.append((x, y))

    while q:
        x, y = q.popleft()
        r, g, b = px[x, y]
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if nx < 0 or ny < 0 or nx >= w or ny >= h:
                    continue
                j = ixy(nx, ny)
                if bg[j]:
                    continue
                rn, gn, bn = px[nx, ny]
                if not is_light_neutral((rn, gn, bn)):
                    continue
                if max(abs(r - rn), abs(g - gn), abs(b - bn)) > NEIGH_MAX:
                    continue
                bg[j] = 1
                q.append((nx, ny))
    return bg


def main() -> None:
    im = Image.open(SRC).convert("RGB")
    w, h = im.size
    px = im.load()
    bg = flood_bg_mask(im)

    # Foreground mask L: 255 = sprite, 0 = background
    mask = Image.new("L", (w, h), 0)
    mp = mask.load()
    for y in range(h):
        row = y * w
        for x in range(w):
            if not bg[row + x]:
                mp[x, y] = 255

    mask_soft = mask.filter(ImageFilter.GaussianBlur(radius=EDGE_BLUR_RADIUS))

    fr, fg, fb = FILL
    out = Image.new("RGB", (w, h))
    op = out.load()
    ms = mask_soft.load()
    for y in range(h):
        for x in range(w):
            a = ms[x, y] / 255.0
            r, g, b = px[x, y]
            op[x, y] = (
                int(round(a * r + (1.0 - a) * fr)),
                int(round(a * g + (1.0 - a) * fg)),
                int(round(a * b + (1.0 - a) * fb)),
            )

    out.save(DST, format="JPEG", quality=92, optimize=True)
    n = sum(1 for b in bg if b)
    print(f"wrote {DST} bg_px={n} / {w*h} ({100.0 * n / (w*h):.1f}%) blur_r={EDGE_BLUR_RADIUS}")


if __name__ == "__main__":
    main()
