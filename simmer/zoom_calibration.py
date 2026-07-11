"""
Camera homing for The Sims 2.

Triggered by pressing 'u' three times in quick succession.
Homes the camera to a stable reference view of the demo Sims house environment
by resetting zoom and panning to a known position.
"""

import time
from pynput.keyboard import Controller
from simmer import bot

_keyboard = Controller()

ZOOM_OUT_PRESSES = 6
ZOOM_IN_PRESSES = 3
ZOOM_PRESS_DELAY = 0.1   # seconds between zoom key presses

W_HOLD_SECONDS = 30
S_HOLD_SECONDS = 6
D_HOLD_SECONDS = 3.5


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

    print(f"[zoom calibration] holding S for {S_HOLD_SECONDS}s...")
    _keyboard.press('s')
    time.sleep(S_HOLD_SECONDS)
    _keyboard.release('s')

    time.sleep(0.2)

    print(f"[zoom calibration] holding D for {D_HOLD_SECONDS}s...")
    _keyboard.press('d')
    time.sleep(D_HOLD_SECONDS)
    _keyboard.release('d')

    print("[zoom calibration] done.")
    bot.start()
