"""
Zoom calibration for The Sims 2.

Triggered by pressing 'u' three times in quick succession.
Zooms all the way out (6x 'x'), then zooms in to the calibration position (3x 'z').
Then moves to the calibration position: hold W for 30s, 40x S, 19x D.
"""

import time
from pynput.keyboard import Controller

_keyboard = Controller()

ZOOM_OUT_PRESSES = 6
ZOOM_IN_PRESSES = 3
ZOOM_PRESS_DELAY = 0.1   # seconds between zoom key presses
MOVE_PRESS_DELAY = 0.5   # seconds between movement key presses

W_HOLD_SECONDS = 30
S_PRESSES = 40
D_PRESSES = 19


def run() -> None:
    """Send zoom and movement key presses to calibrate camera position."""
    print("[zoom calibration] zooming out...")
    for _ in range(ZOOM_OUT_PRESSES):
        _keyboard.press('x')
        _keyboard.release('x')
        time.sleep(ZOOM_PRESS_DELAY)

    time.sleep(0.2)

    print("[zoom calibration] zooming in...")
    for _ in range(ZOOM_IN_PRESSES):
        _keyboard.press('z')
        _keyboard.release('z')
        time.sleep(ZOOM_PRESS_DELAY)

    time.sleep(0.2)

    print(f"[zoom calibration] holding W for {W_HOLD_SECONDS}s...")
    _keyboard.press('w')
    time.sleep(W_HOLD_SECONDS)
    _keyboard.release('w')

    time.sleep(0.2)

    print(f"[zoom calibration] pressing S {S_PRESSES}x...")
    for _ in range(S_PRESSES):
        _keyboard.press('s')
        _keyboard.release('s')
        time.sleep(MOVE_PRESS_DELAY)

    time.sleep(0.2)

    print(f"[zoom calibration] pressing D {D_PRESSES}x...")
    for _ in range(D_PRESSES):
        _keyboard.press('d')
        _keyboard.release('d')
        time.sleep(MOVE_PRESS_DELAY)

    print("[zoom calibration] done.")
