"""
coords.py — hardcoded screen coordinate mappings for The Sims 2.

All coordinates are absolute pixel positions captured at the reference
resolution and zoom level (see ref-view.png).

Sections
--------
AREAS   : named screen regions (rectangles / polygons) used for reading
          game state (e.g. status bars).
ACTIONS : named sequences of mouse clicks used to trigger in-game actions.
"""

# ---------------------------------------------------------------------------
# Screen regions
# ---------------------------------------------------------------------------

AREAS = {
    "energy_bar": {
        "type":         "rect",
        "top_left":     (790, 1169),
        "top_right":    (910, 1169),
        "bottom_right": (910, 1182),
        "bottom_left":  (790, 1182),
        "width":        119,
        "height":       13,
    },
}

# ---------------------------------------------------------------------------
# Action click sequences
# Each entry is a list of {"button": "L"|"R", "pos": (x, y)} dicts,
# executed in order.
# ---------------------------------------------------------------------------

ACTIONS = {
    "sleep": [
        {"button": "L", "pos": (1543, 578)},   # open needs/actions menu
        {"button": "L", "pos": (1708, 622)},   # select Sleep
    ],
}
