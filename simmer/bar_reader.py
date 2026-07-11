"""
bar_reader.py — general horizontal bar fill reader for The Sims 2 UI.

Takes a screen region dict (from coords.AREAS) and returns the filled
fraction of the bar as a float 0.0–1.0, measured by scanning the middle
row of pixels for "filled" colour.

The Sims 2 need bars are horizontal, left-to-right fill, coloured green
(positive) or orange/red (negative). The approach here is colour-agnostic:
it finds the rightmost non-background pixel in the middle row of the region,
treating the top-left corner pixel as the background reference colour.

Usage
-----
    from simmer import bar_reader
    import coords

    fill = bar_reader.read(coords.AREAS["energy_bar"])
    print(f"energy: {fill:.0%}")
"""

from PIL import Image, ImageGrab


# Colour distance threshold: pixels further than this from the background
# colour (Euclidean distance in RGB space) are considered "filled".
_BG_DISTANCE_THRESHOLD = 40


def _colour_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def read(area: dict, *, screenshot: Image.Image | None = None) -> float:
    """Return the fill fraction (0.0–1.0) of a horizontal bar region.

    Parameters
    ----------
    area:
        A rect entry from coords.AREAS with keys ``top_left``, ``bottom_right``,
        ``width``, and ``height``.
    screenshot:
        Optional pre-captured PIL image of the full screen. If omitted a
        fresh screenshot is taken. Pass one in when reading multiple bars
        in a single frame to avoid redundant captures.

    Returns
    -------
    float
        0.0 = empty, 1.0 = completely full.
        Returns -1.0 if the region cannot be read.
    """
    x1, y1 = area["top_left"]
    x2, y2 = area["bottom_right"]

    if screenshot is None:
        screenshot = ImageGrab.grab(bbox=(x1, y1, x2, y2)).convert("RGB")
        crop = screenshot
    else:
        crop = screenshot.crop((x1, y1, x2, y2)).convert("RGB")

    w, h = crop.size
    if w == 0 or h == 0:
        return -1.0

    # Use the top-left corner as the background colour reference.
    bg = crop.getpixel((0, 0))

    # Scan the middle row left-to-right; find the rightmost filled pixel.
    mid_y = h // 2
    rightmost_filled = -1
    for x in range(w):
        pixel = crop.getpixel((x, mid_y))
        if _colour_distance(pixel, bg) > _BG_DISTANCE_THRESHOLD:
            rightmost_filled = x

    if rightmost_filled < 0:
        return 0.0

    return (rightmost_filled + 1) / w
