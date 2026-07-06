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
   creator/admin to draw and label regions on the reference view (action
   targets, input fields, status areas, etc.). Supports rectangular and
   free-form polygon areas. Outputs pixel coordinates that the bot uses at
   runtime.

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

### Tool selection

| Input | Action |
|---|---|
| `T` | Toggle between Rectangle and Free-form polygon tool |
| Toolbar button | Same toggle, shows active tool |

### Rectangle tool

| Input | Action |
|---|---|
| Left-click + drag (empty) | Draw new rectangle |
| Left-click + drag (rect body) | Move rectangle |
| Left-click + drag (corner handle) | Resize from that corner |
| Right-click rect | Delete rectangle |

### Free-form polygon tool

| Input | Action |
|---|---|
| Left-click (empty) | Place a polygon vertex |
| Left-click near first point | Close and commit polygon (requires ≥ 3 points) |
| Left-click + drag (vertex handle) | Move individual vertex |
| Left-click + drag (polygon body) | Move whole polygon |
| Right-click / `Escape` | Cancel polygon in progress |
| Right-click committed polygon | Delete polygon |

The first vertex is drawn in green and slightly larger as a close target.
The closing preview line turns green when the cursor is close enough to snap.

### General

| Input | Action |
|---|---|
| Scroll wheel | Zoom in / out (centred on cursor) |
| `+` / `-` | Zoom in / out |
| `0` | Reset zoom to fit |
| `Ctrl+Z` | Undo |
| `Ctrl+A` | Print all coordinates to stdout |
| `C` | Clear all shapes |
| `Q` / `Escape` | Quit (when not mid-polygon) |

### Output format

`Ctrl+A` prints both a flat constants form and an `AREAS` dict. Rectangles
include `top_left`, `top_right`, `bottom_right`, `bottom_left`, `width`, and
`height`. Polygons include an ordered `points` list and per-point constants
(`LABEL_P0`, `LABEL_P1`, …). Both shapes carry a `type` key (`'rect'` or
`'poly'`) in the dict form.
