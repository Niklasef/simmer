"""
Zoom calibration for The Sims 2.

Triggered by pressing 'u' three times in quick succession.
Zooms all the way out (6x 'x'), then zooms in to the calibration position (3x 'z').
"""

import time
from pynput.keyboard import Controller

_keyboard = Controller()

ZOOM_OUT_PRESSES = 6
ZOOM_IN_PRESSES = 3
PRESS_DELAY = 0.1  # seconds between each key press


def run() -> None:
    """Send zoom out then zoom in key presses to the active window."""
    print("[zoom calibration] zooming out...")
    for _ in range(ZOOM_OUT_PRESSES):
        _keyboard.press('x')
        _keyboard.release('x')
        time.sleep(PRESS_DELAY)

    time.sleep(0.2)

    print("[zoom calibration] zooming in...")
    for _ in range(ZOOM_IN_PRESSES):
        _keyboard.press('z')
        _keyboard.release('z')
        time.sleep(PRESS_DELAY)

    print("[zoom calibration] done.")
