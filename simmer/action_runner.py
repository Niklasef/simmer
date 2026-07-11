"""
action_runner.py — executes named click sequences from coords.ACTIONS.

Each action is an ordered list of {"button": "L"|"R", "pos": (x, y)} dicts.
Clicks are sent via pynput to whatever window is currently focused (the game).

Usage
-----
    from simmer import action_runner
    action_runner.run("sleep")
"""

import time
from pynput.mouse import Button, Controller as MouseController

import coords

_mouse = MouseController()

# Seconds to wait between successive clicks in a sequence.
CLICK_DELAY = 0.15


def run(action_name: str) -> None:
    """Execute a named action sequence from coords.ACTIONS.

    Parameters
    ----------
    action_name:
        Key in ``coords.ACTIONS`` (e.g. ``"sleep"``).

    Raises
    ------
    KeyError
        If *action_name* is not found in ``coords.ACTIONS``.
    """
    steps = coords.ACTIONS[action_name]
    print(f"[action runner] running '{action_name}' ({len(steps)} click(s))")
    for i, step in enumerate(steps):
        x, y = step["pos"]
        btn = Button.left if step["button"] == "L" else Button.right
        _mouse.position = (x, y)
        time.sleep(0.05)          # short settle before click
        _mouse.press(btn)
        _mouse.release(btn)
        print(f"[action runner]   step {i + 1}/{len(steps)}: {step['button']} ({x}, {y})")
        if i < len(steps) - 1:
            time.sleep(CLICK_DELAY)
    print(f"[action runner] '{action_name}' done.")
