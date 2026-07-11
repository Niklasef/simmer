"""
simmer CLI - steer The Sims 2 from the command line.

Hotkeys (global, work while the game window is focused):
  u u u   -> zoom calibration (left/right arrow key sequence)
  m m m   -> toggle mouse click recorder (prints coords to terminal)
  ctrl+c  -> quit
"""

import time
from collections import deque

from pynput import keyboard
from pynput.keyboard import Key

from simmer import zoom_calibration, mouse_recorder, bot

# Window of time (seconds) in which three presses must occur
TRIPLE_KEY_WINDOW = 1.5

_u_times: deque = deque(maxlen=3)
_m_times: deque = deque(maxlen=3)


def _on_press(key: Key) -> None:
    try:
        ch = key.char
    except AttributeError:
        return  # special key, ignore

    now = time.monotonic()

    if ch == "u":
        _u_times.append(now)
        if len(_u_times) == 3 and (now - _u_times[0]) <= TRIPLE_KEY_WINDOW:
            _u_times.clear()
            zoom_calibration.run()

    elif ch == "m":
        _m_times.append(now)
        if len(_m_times) == 3 and (now - _m_times[0]) <= TRIPLE_KEY_WINDOW:
            _m_times.clear()
            mouse_recorder.toggle()


def main() -> None:
    print(
        "simmer running.\n"
        "  u u u -> zoom calibration (bot starts when complete)\n"
        "  m m m -> toggle mouse click recorder\n"
        "  Ctrl+C -> quit"
    )
    with keyboard.Listener(on_press=_on_press) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            if mouse_recorder.is_running():
                mouse_recorder.stop()
            bot.stop()
            print("\nsimmer stopped.")


if __name__ == "__main__":
    main()
