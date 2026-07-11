"""
Mouse click recorder for The Sims 2.

Triggered by pressing 'm' three times in quick succession.
Records left and right mouse click coordinates while the game window is focused,
printing each click to the terminal.  Press 'm' three times again to stop.
"""

import threading
from pynput import mouse

_listener: mouse.Listener | None = None
_lock = threading.Lock()


def _on_click(x: int, y: int, button: mouse.Button, pressed: bool) -> None:
    if pressed:
        btn = "L" if button == mouse.Button.left else "R" if button == mouse.Button.right else str(button)
        print(f"[mouse recorder] click {btn} ({x}, {y})")


def is_running() -> bool:
    with _lock:
        return _listener is not None and _listener.running


def start() -> None:
    """Start recording mouse clicks."""
    global _listener
    with _lock:
        if _listener is not None and _listener.running:
            return
        _listener = mouse.Listener(on_click=_on_click)
        _listener.start()
    print("[mouse recorder] recording started. Press 'm' three times to stop.")


def stop() -> None:
    """Stop recording mouse clicks."""
    global _listener
    with _lock:
        if _listener is None:
            return
        _listener.stop()
        _listener = None
    print("[mouse recorder] recording stopped.")


def toggle() -> None:
    """Toggle recording on or off."""
    if is_running():
        stop()
    else:
        start()
