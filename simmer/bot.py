"""
bot.py — rule-based automation loop for The Sims 2.

Runs at ~1 fps. On each tick it reads the energy bar; if energy drops
below 50 % it fires the sleep action sequence and then pauses the loop
for 5 minutes (letting the Sim sleep without interference).

The loop runs in a daemon thread so the CLI hotkey listener stays
responsive. Start/stop it from cli.py via start() / stop().
"""

import threading
import time

from simmer import coords
from simmer import bar_reader, action_runner

# --- tunables -----------------------------------------------------------

TICK_INTERVAL = 1.0          # seconds between loop iterations (~1 fps)
ENERGY_THRESHOLD = 0.50      # trigger sleep when energy < 50 %
SLEEP_PAUSE = 5 * 60         # seconds to pause the loop after sleep macro

# ------------------------------------------------------------------------

_stop_event = threading.Event()
_thread: threading.Thread | None = None
_lock = threading.Lock()


def _loop() -> None:
    print("[bot] loop started.")
    sleeping_until: float = 0.0          # monotonic time when pause ends

    while not _stop_event.is_set():
        now = time.monotonic()

        if now < sleeping_until:
            remaining = sleeping_until - now
            # Print a reminder once per minute while paused.
            if int(remaining) % 60 == 0 and int(remaining) > 0:
                print(f"[bot] sleeping pause — {int(remaining) // 60}m remaining.")
            time.sleep(TICK_INTERVAL)
            continue

        # --- read energy bar ---
        energy = bar_reader.read(coords.AREAS["energy_bar"])
        pct = f"{energy:.0%}" if energy >= 0 else "n/a"
        print(f"[bot] energy: {pct}")

        if energy >= 0 and energy < ENERGY_THRESHOLD:
            print(f"[bot] energy below {ENERGY_THRESHOLD:.0%} — triggering sleep macro.")
            action_runner.run("sleep")
            sleeping_until = time.monotonic() + SLEEP_PAUSE
            mins = SLEEP_PAUSE // 60
            print(f"[bot] loop paused for {mins} min while Sim sleeps.")

        time.sleep(TICK_INTERVAL)

    print("[bot] loop stopped.")


def is_running() -> bool:
    with _lock:
        return _thread is not None and _thread.is_alive()


def start() -> None:
    """Start the bot loop in a background thread."""
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            print("[bot] already running.")
            return
        _stop_event.clear()
        _thread = threading.Thread(target=_loop, name="bot-loop", daemon=True)
        _thread.start()
    print("[bot] started. Energy threshold: "
          f"{ENERGY_THRESHOLD:.0%}, sleep pause: {SLEEP_PAUSE // 60} min.")


def stop() -> None:
    """Signal the bot loop to stop and wait for it to exit."""
    global _thread
    with _lock:
        if _thread is None:
            return
    _stop_event.set()
    _thread.join(timeout=TICK_INTERVAL + 1)
    with _lock:
        _thread = None
    print("[bot] stopped.")
