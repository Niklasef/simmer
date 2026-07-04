# simmer

Automated 2-player The Sims bot. Plays the game without human input.

## Purpose

Simmer drives a running Sims instance by reading the screen and sending
mouse/keyboard actions. The first version uses fixed coordinate mappings
derived from a reference screenshot of the game at a known resolution and
zoom level. A simple rule-based bot decides what to do; actual ML/AI play
comes later.

## How it works

1. **Reference view** — a canonical screenshot (`ref-view.png`) taken at a
   fixed in-game zoom level. All action and UI areas are mapped relative to
   this view.

2. **Area mapper** (`area-mapper <image>`) — GUI tool for the bot
   creator/admin to draw and label rectangular regions on the reference view
   (action targets, input fields, status areas, etc.). Outputs pixel
   coordinates that the bot uses at runtime.

3. **Zoom calibration** — at startup the bot matches the live game view to
   the reference view so that the fixed mappings translate correctly to the
   current screen.

4. **Rule-based bot** — uses the mapped areas to decide and execute actions
   (click, type, etc.). First version is simple rules; no ML yet.

## Tools

| Command | Description |
|---|---|
| `area-mapper [image]` | Map action/input areas on a reference image |

## Area Mapper controls

| Input | Action |
|---|---|
| Left-click + drag (empty) | Draw new rectangle |
| Left-click + drag (rect) | Move rectangle |
| Left-click + drag (corner) | Resize from corner |
| Right-click rect | Delete rectangle |
| Scroll wheel | Zoom in / out (centred on cursor) |
| `+` / `-` | Zoom in / out |
| `0` | Reset zoom to fit |
| `Ctrl+Z` | Undo |
| `Ctrl+A` | Print all coordinates to stdout |
| `C` | Clear all rectangles |
| `Q` / `Escape` | Quit |
