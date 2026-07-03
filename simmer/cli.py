"""
simmer CLI - steer The Sims 2 from the command line.

Hotkeys (global, work while the game window is focused):
  u u u   -> zoom calibration (left/right arrow key sequence)
  ctrl+c  -> quit
"""

import time
from collections import deque

from pynput import keyboard
from pynput.keyboard import Key

from simmer import zoom_calibration

# Window of time (seconds) in which three 'u' presses must occur
TRIPLE_U_WINDOW = 1.5

_u_times: deque = deque(maxlen=3)


def _on_press(key: Key) -> None:
    try:
        if key.char == "u":
            now = time.monotonic()
            _u_times.append(now)
            if len(_u_times) == 3 and (now - _u_times[0]) <= TRIPLE_U_WINDOW:
                _u_times.clear()
                zoom_calibration.run()
    except AttributeError:
        pass  # special key, ignore


def main() -> None:
    print("simmer running. Press 'u' three times to trigger zoom calibration. Ctrl+C to quit.")
    with keyboard.Listener(on_press=_on_press) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            print("\nsimmer stopped.")


if __name__ == "__main__":
    main()
