"""
Zoom calibration for The Sims 2.

Triggered by pressing 'u' three times in quick succession.
Sends a short left/right arrow key sequence to test camera zoom response.
"""

import time
from pynput.keyboard import Key, Controller

_keyboard = Controller()

ARROW_PRESSES = 3
PRESS_DELAY = 0.1  # seconds between each key press


def run() -> None:
    """Send left/right arrow key presses to the active window."""
    print("[zoom calibration] sending arrow keys...")
    for _ in range(ARROW_PRESSES):
        _keyboard.press(Key.left)
        _keyboard.release(Key.left)
        time.sleep(PRESS_DELAY)

    time.sleep(0.2)

    for _ in range(ARROW_PRESSES):
        _keyboard.press(Key.right)
        _keyboard.release(Key.right)
        time.sleep(PRESS_DELAY)

    print("[zoom calibration] done.")
