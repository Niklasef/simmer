"""
area_mapper.py — Interactive tool for mapping rectangular areas on a reference image.

Usage:
    python -m simmer.area_mapper [image_path]

Controls:
    Left-click + drag on empty space  → draw a new rectangle
    Left-click + drag on a rectangle  → move it
    Left-click + drag on a corner handle → resize from that corner
    Right-click a rectangle            → delete it
    Ctrl+Z                             → undo last action
    Ctrl+A                             → print all rectangles to stdout
    C                                  → clear all rectangles
    Q / Escape                         → quit
    Scroll wheel                       → zoom in / out (centred on cursor)
    + / -                              → zoom in / out
    0                                  → reset zoom to fit

Coordinates are always reported in image-space (origin = top-left of image).
"""

import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk

# ── Constants ────────────────────────────────────────────────────────────────

HANDLE_RADIUS = 7       # px radius of corner resize handles
HANDLE_HIT    = 10      # px pick distance for handles
MIN_SIZE      = 10      # minimum rectangle side length in image-px

ZOOM_STEP     = 1.25    # multiply / divide scale by this per zoom step
ZOOM_MIN      = 0.05
ZOOM_MAX      = 16.0

COLORS = [
    "#e74c3c", "#3498db", "#2ecc71", "#f39c12",
    "#9b59b6", "#1abc9c", "#e67e22", "#e91e63",
]


# ── Data model ───────────────────────────────────────────────────────────────

class Rect:
    """A rectangle defined by two corners in image-space."""

    _counter = 0

    def __init__(self, x1: float, y1: float, x2: float, y2: float, label: str = ""):
        Rect._counter += 1
        self.id    = Rect._counter
        self.label = label or f"area_{self.id}"
        self.color = COLORS[(self.id - 1) % len(COLORS)]
        # Store normalised so x1<=x2, y1<=y2
        self.x1 = min(x1, x2)
        self.y1 = min(y1, y2)
        self.x2 = max(x1, x2)
        self.y2 = max(y1, y2)

    # Corners in image-space (floats)
    @property
    def corners(self):
        return {
            "top_left":     (self.x1, self.y1),
            "top_right":    (self.x2, self.y1),
            "bottom_right": (self.x2, self.y2),
            "bottom_left":  (self.x1, self.y2),
        }

    def corner_list(self):
        """Return corners as list of (x, y) ints."""
        return [(int(self.x1), int(self.y1)),
                (int(self.x2), int(self.y1)),
                (int(self.x2), int(self.y2)),
                (int(self.x1), int(self.y2))]

    def to_dict(self):
        return {
            "label":        self.label,
            "top_left":     (int(self.x1), int(self.y1)),
            "top_right":    (int(self.x2), int(self.y1)),
            "bottom_right": (int(self.x2), int(self.y2)),
            "bottom_left":  (int(self.x1), int(self.y2)),
            "width":        int(self.x2 - self.x1),
            "height":       int(self.y2 - self.y1),
        }

    def __repr__(self):
        d = self.to_dict()
        return (
            f"Rect({d['label']!r}: "
            f"TL={d['top_left']} TR={d['top_right']} "
            f"BR={d['bottom_right']} BL={d['bottom_left']} "
            f"W={d['width']} H={d['height']})"
        )


# ── Main application ──────────────────────────────────────────────────────────

class AreaMapper:
    def __init__(self, root: tk.Tk, image_path: str | None = None):
        self.root = root
        self.root.title("Area Mapper")

        # State
        self.image_orig: Image.Image | None = None   # original PIL image
        self.image_path: str | None = None
        self.scale      = 1.0   # display_px = image_px * scale
        self.offset_x   = 0.0   # image-space x of canvas (0,0) — always 0 (no free pan)
        self.offset_y   = 0.0   # image-space y of canvas (0,0) — always 0 (no free pan)

        self.rects: list[Rect] = []
        self._undo_stack: list[list[Rect]] = []     # snapshots for undo

        # Interaction state
        self._drag_mode   = None   # "draw" | "move" | "resize"
        self._active_rect: Rect | None = None
        self._resize_corner: str | None = None      # which corner being dragged
        self._drag_start_canvas = (0, 0)
        self._drag_start_img    = (0, 0)
        self._drag_rect_origin  = None              # rect coords at drag start
        self._rubber_band_start = None              # image coords of draw origin
        self._rubber_band       = None              # (x1,y1,x2,y2) in image coords

        self._build_ui()
        self._bind_events()

        if image_path:
            self._load_image(image_path)

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # Top toolbar
        toolbar = tk.Frame(self.root, bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        tk.Button(toolbar, text="Open Image",   command=self._open_image).pack(side=tk.LEFT, padx=4, pady=2)
        tk.Button(toolbar, text="Clear All (C)", command=self._clear_all).pack(side=tk.LEFT, padx=4, pady=2)
        tk.Button(toolbar, text="Print Coords (Ctrl+A)", command=self._print_all).pack(side=tk.LEFT, padx=4, pady=2)
        tk.Button(toolbar, text="Undo (Ctrl+Z)",  command=self._undo).pack(side=tk.LEFT, padx=4, pady=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)
        tk.Button(toolbar, text="−", width=2, command=lambda: self._zoom_by(1/ZOOM_STEP)).pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="+", width=2, command=lambda: self._zoom_by(ZOOM_STEP)).pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="Fit (0)", command=self._fit_image).pack(side=tk.LEFT, padx=4, pady=2)
        self.zoom_label = tk.Label(toolbar, text="100%", width=6, anchor=tk.W)
        self.zoom_label.pack(side=tk.LEFT, padx=4, pady=2)

        # Canvas area with scrollbars
        frame = tk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(frame, bg="#1a1a2e", cursor="crosshair")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vbar = tk.Scrollbar(frame, orient=tk.VERTICAL,   command=self.canvas.yview)
        hbar = tk.Scrollbar(self.root, orient=tk.HORIZONTAL, command=self.canvas.xview)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)

        # Bottom status bar
        self.status_var = tk.StringVar(value="Open an image to begin.")
        status_bar = tk.Label(self.root, textvariable=self.status_var,
                              anchor=tk.W, relief=tk.SUNKEN, font=("Courier", 10))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Right-side panel: rectangle list
        panel = tk.Frame(self.root, width=260, bd=1, relief=tk.SUNKEN)
        panel.pack(side=tk.RIGHT, fill=tk.Y)
        panel.pack_propagate(False)

        tk.Label(panel, text="Rectangles", font=("TkDefaultFont", 11, "bold")).pack(pady=6)

        self.rect_list_var = tk.StringVar()
        self.rect_listbox  = tk.Listbox(panel, listvariable=self.rect_list_var,
                                        selectmode=tk.SINGLE, font=("Courier", 9),
                                        activestyle="none")
        self.rect_listbox.pack(fill=tk.BOTH, expand=True, padx=4)
        self.rect_listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

        # Coord detail label
        self.coord_detail = tk.Text(panel, height=12, font=("Courier", 9),
                                    state=tk.DISABLED, wrap=tk.WORD)
        self.coord_detail.pack(fill=tk.X, padx=4, pady=4)

        # Label edit
        lbl_frame = tk.Frame(panel)
        lbl_frame.pack(fill=tk.X, padx=4, pady=2)
        tk.Label(lbl_frame, text="Label:").pack(side=tk.LEFT)
        self.label_entry = tk.Entry(lbl_frame)
        self.label_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(lbl_frame, text="Set", command=self._set_label).pack(side=tk.LEFT)

        tk.Button(panel, text="Delete Selected", command=self._delete_selected).pack(pady=4)

    # ── Event binding ────────────────────────────────────────────────────────

    def _bind_events(self):
        c = self.canvas
        c.bind("<ButtonPress-1>",   self._on_lbdown)
        c.bind("<B1-Motion>",       self._on_lbmove)
        c.bind("<ButtonRelease-1>", self._on_lbup)
        c.bind("<ButtonPress-3>",   self._on_rbdown)
        c.bind("<Motion>",          self._on_mouse_move)

        self.root.bind("<Control-z>", lambda e: self._undo())
        self.root.bind("<Control-Z>", lambda e: self._undo())
        self.root.bind("<Control-a>", lambda e: self._print_all())
        self.root.bind("<Control-A>", lambda e: self._print_all())
        self.root.bind("<c>",         lambda e: self._clear_all())
        self.root.bind("<C>",         lambda e: self._clear_all())
        self.root.bind("<Escape>",    lambda e: self.root.quit())
        self.root.bind("<q>",         lambda e: self.root.quit())
        self.root.bind("<Q>",         lambda e: self.root.quit())

        # Zoom keys
        self.root.bind("<plus>",      lambda e: self._zoom_by(ZOOM_STEP))
        self.root.bind("<equal>",     lambda e: self._zoom_by(ZOOM_STEP))   # unshifted +
        self.root.bind("<minus>",     lambda e: self._zoom_by(1/ZOOM_STEP))
        self.root.bind("<0>",         lambda e: self._fit_image())

        # Mouse-wheel zoom (centred on cursor)
        self.canvas.bind("<MouseWheel>",        self._on_mousewheel)        # Windows/macOS
        self.canvas.bind("<Button-4>",          self._on_mousewheel)        # Linux scroll up
        self.canvas.bind("<Button-5>",          self._on_mousewheel)        # Linux scroll down

    # ── Image loading ────────────────────────────────────────────────────────

    def _open_image(self):
        path = filedialog.askopenfilename(
            title="Select image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff"), ("All files", "*.*")]
        )
        if path:
            self._load_image(path)

    def _load_image(self, path: str):
        try:
            img = Image.open(path).convert("RGBA")
        except Exception as e:
            messagebox.showerror("Error", f"Cannot open image:\n{e}")
            return

        self.image_orig = img
        self.image_path = path
        self.rects.clear()
        self._undo_stack.clear()
        self._fit_image()
        self.root.title(f"Area Mapper — {path}")

    def _fit_image(self):
        """Scale image to fit current canvas size, preserving aspect ratio."""
        if self.image_orig is None:
            return
        self.root.update_idletasks()
        cw = self.canvas.winfo_width()  or 900
        ch = self.canvas.winfo_height() or 700
        iw, ih = self.image_orig.size
        scale = min(cw / iw, ch / ih, 1.0)   # never upscale beyond 1:1
        self.scale = scale
        self._render_image()
        self.status_var.set(
            f"Loaded: {self.image_path}  |  {iw}×{ih} px  |  Scale: {scale:.2f}x  |  "
            f"Scroll to zoom   Draw: click+drag   Move: drag rect   Resize: drag corner   Delete: right-click"
        )

    def _render_image(self):
        """Re-render the PIL image at the current scale and refresh the canvas."""
        if self.image_orig is None:
            return
        iw, ih = self.image_orig.size
        display_w = max(1, int(iw * self.scale))
        display_h = max(1, int(ih * self.scale))

        resized = self.image_orig.resize((display_w, display_h), Image.LANCZOS)
        self._tk_image = ImageTk.PhotoImage(resized)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self._tk_image, tags="image")
        self.canvas.configure(scrollregion=(0, 0, display_w, display_h))
        self._redraw()
        if hasattr(self, "zoom_label"):
            self.zoom_label.config(text=f"{int(self.scale * 100)}%")

    # ── Zoom ─────────────────────────────────────────────────────────────────

    def _zoom_by(self, factor: float, canvas_cx: float | None = None,
                 canvas_cy: float | None = None):
        """Multiply the current scale by *factor*, keeping the given canvas
        point fixed in image-space (defaults to canvas centre)."""
        if self.image_orig is None:
            return

        new_scale = max(ZOOM_MIN, min(ZOOM_MAX, self.scale * factor))
        if new_scale == self.scale:
            return

        # If no focus point given, use visible centre of the canvas
        if canvas_cx is None or canvas_cy is None:
            canvas_cx = self.canvas.canvasx(self.canvas.winfo_width()  / 2)
            canvas_cy = self.canvas.canvasy(self.canvas.winfo_height() / 2)

        # Image-space point under the cursor must stay fixed
        img_cx = canvas_cx / self.scale
        img_cy = canvas_cy / self.scale

        self.scale = new_scale
        self._render_image()

        # Scroll so that img_cx/img_cy lands back under canvas_cx/cy
        new_canvas_x = img_cx * self.scale
        new_canvas_y = img_cy * self.scale
        iw, ih = self.image_orig.size
        total_w = iw * self.scale
        total_h = ih * self.scale
        self.canvas.xview_moveto((new_canvas_x - canvas_cx + self.canvas.canvasx(0)) / total_w)
        self.canvas.yview_moveto((new_canvas_y - canvas_cy + self.canvas.canvasy(0)) / total_h)

    def _on_mousewheel(self, event):
        if self.image_orig is None:
            return
        # Determine scroll direction
        if event.num == 4:          # Linux scroll up
            delta = 1
        elif event.num == 5:        # Linux scroll down
            delta = -1
        else:                       # Windows / macOS
            delta = 1 if event.delta > 0 else -1

        factor = ZOOM_STEP if delta > 0 else 1 / ZOOM_STEP
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        self._zoom_by(factor, cx, cy)

    # ── Coordinate helpers ───────────────────────────────────────────────────

    def _canvas_to_img(self, cx: float, cy: float) -> tuple[float, float]:
        s = self.scale
        return cx / s, cy / s

    def _img_to_canvas(self, ix: float, iy: float) -> tuple[int, int]:
        s = self.scale
        return int(ix * s), int(iy * s)

    # ── Hit testing ──────────────────────────────────────────────────────────

    def _hit_handle(self, cx: float, cy: float) -> tuple["Rect | None", "str | None"]:
        """Return (rect, corner_name) if canvas point is near a handle."""
        corners_order = ["top_left", "top_right", "bottom_right", "bottom_left"]
        for r in reversed(self.rects):
            for name, (ix, iy) in r.corners.items():
                hcx, hcy = self._img_to_canvas(ix, iy)
                if abs(cx - hcx) <= HANDLE_HIT and abs(cy - hcy) <= HANDLE_HIT:
                    return r, name
        return None, None

    def _hit_rect(self, cx: float, cy: float) -> "Rect | None":
        """Return topmost rect whose interior contains the canvas point."""
        ix, iy = self._canvas_to_img(cx, cy)
        for r in reversed(self.rects):
            if r.x1 <= ix <= r.x2 and r.y1 <= iy <= r.y2:
                return r
        return None

    # ── Mouse events ─────────────────────────────────────────────────────────

    def _on_lbdown(self, event):
        if self.image_orig is None:
            return
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self._drag_start_canvas = (cx, cy)
        ix, iy = self._canvas_to_img(cx, cy)
        self._drag_start_img = (ix, iy)

        # Priority: handle → body → draw
        r, corner = self._hit_handle(cx, cy)
        if r is not None:
            self._save_undo()
            self._drag_mode    = "resize"
            self._active_rect  = r
            self._resize_corner = corner
            self._drag_rect_origin = (r.x1, r.y1, r.x2, r.y2)
            return

        r = self._hit_rect(cx, cy)
        if r is not None:
            self._save_undo()
            self._drag_mode   = "move"
            self._active_rect = r
            self._drag_rect_origin = (r.x1, r.y1, r.x2, r.y2)
            return

        # Start drawing new rectangle
        self._save_undo()
        self._drag_mode = "draw"
        self._rubber_band_start = (ix, iy)
        self._active_rect = None

    def _on_lbmove(self, event):
        if self.image_orig is None or self._drag_mode is None:
            return
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        ix, iy = self._canvas_to_img(cx, cy)
        iw, ih = self.image_orig.size

        if self._drag_mode == "draw":
            sx, sy = self._rubber_band_start
            # Clamp to image
            ix = max(0.0, min(ix, iw))
            iy = max(0.0, min(iy, ih))
            self._rubber_band = (sx, sy, ix, iy)
            self._redraw()

        elif self._drag_mode == "move":
            r = self._active_rect
            ox1, oy1, ox2, oy2 = self._drag_rect_origin
            six, siy = self._drag_start_img
            dx = ix - six
            dy = iy - siy
            w = ox2 - ox1
            h = oy2 - oy1
            nx1 = max(0.0, min(ox1 + dx, iw - w))
            ny1 = max(0.0, min(oy1 + dy, ih - h))
            r.x1, r.y1 = nx1, ny1
            r.x2, r.y2 = nx1 + w, ny1 + h
            self._redraw()

        elif self._drag_mode == "resize":
            r = self._active_rect
            ox1, oy1, ox2, oy2 = self._drag_rect_origin
            six, siy = self._drag_start_img
            dx = ix - six
            dy = iy - siy
            nx1, ny1, nx2, ny2 = ox1, oy1, ox2, oy2

            corner = self._resize_corner
            if "left"   in corner: nx1 = min(ox1 + dx, ox2 - MIN_SIZE)
            if "right"  in corner: nx2 = max(ox2 + dx, ox1 + MIN_SIZE)
            if "top"    in corner: ny1 = min(oy1 + dy, oy2 - MIN_SIZE)
            if "bottom" in corner: ny2 = max(oy2 + dy, oy1 + MIN_SIZE)

            nx1 = max(0.0, nx1); ny1 = max(0.0, ny1)
            nx2 = min(iw, nx2);  ny2 = min(ih, ny2)
            r.x1, r.y1, r.x2, r.y2 = nx1, ny1, nx2, ny2
            self._redraw()

        # Update status with live image coords
        self.status_var.set(f"Image coords: ({int(ix)}, {int(iy)})")

    def _on_lbup(self, event):
        if self.image_orig is None:
            return
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        ix, iy = self._canvas_to_img(cx, cy)

        if self._drag_mode == "draw":
            sx, sy = self._rubber_band_start
            iw, ih = self.image_orig.size
            ix = max(0.0, min(ix, iw))
            iy = max(0.0, min(iy, ih))
            if abs(ix - sx) >= MIN_SIZE and abs(iy - sy) >= MIN_SIZE:
                r = Rect(sx, sy, ix, iy)
                self.rects.append(r)
                self._active_rect = r
                self._update_panel()
            else:
                # Too small — discard undo snapshot
                self._undo_stack.pop()
            self._rubber_band = None

        self._drag_mode = None
        self._redraw()
        self._update_panel()

    def _on_rbdown(self, event):
        if self.image_orig is None:
            return
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        # Check handle first (corner delete = delete whole rect)
        r, _ = self._hit_handle(cx, cy)
        if r is None:
            r = self._hit_rect(cx, cy)
        if r is not None:
            self._save_undo()
            self.rects.remove(r)
            if self._active_rect is r:
                self._active_rect = None
            self._redraw()
            self._update_panel()

    def _on_mouse_move(self, event):
        if self.image_orig is None:
            return
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        ix, iy = self._canvas_to_img(cx, cy)
        iw, ih = self.image_orig.size
        if 0 <= ix <= iw and 0 <= iy <= ih:
            # Change cursor near handles
            r, corner = self._hit_handle(cx, cy)
            if r is not None:
                cursors = {
                    "top_left":     "top_left_corner",
                    "top_right":    "top_right_corner",
                    "bottom_left":  "bottom_left_corner",
                    "bottom_right": "bottom_right_corner",
                }
                self.canvas.config(cursor=cursors.get(corner, "crosshair"))
            elif self._hit_rect(cx, cy) is not None:
                self.canvas.config(cursor="fleur")
            else:
                self.canvas.config(cursor="crosshair")
            if self._drag_mode is None:
                self.status_var.set(f"Image coords: ({int(ix)}, {int(iy)})")

    # ── Drawing ──────────────────────────────────────────────────────────────

    def _redraw(self):
        self.canvas.delete("rect")
        self.canvas.delete("handle")
        self.canvas.delete("rubber")
        self.canvas.delete("label")

        for r in self.rects:
            is_active = (r is self._active_rect)
            self._draw_rect(r, is_active)

        # Rubber-band preview
        if self._drag_mode == "draw" and self._rubber_band:
            x1, y1, x2, y2 = self._rubber_band
            cx1, cy1 = self._img_to_canvas(x1, y1)
            cx2, cy2 = self._img_to_canvas(x2, y2)
            self.canvas.create_rectangle(cx1, cy1, cx2, cy2,
                                         outline="#ffffff", dash=(4, 4),
                                         width=1, tags="rubber")

        self._update_coord_detail()

    def _draw_rect(self, r: Rect, active: bool = False):
        cx1, cy1 = self._img_to_canvas(r.x1, r.y1)
        cx2, cy2 = self._img_to_canvas(r.x2, r.y2)

        width = 2 if active else 1
        # tkinter canvas has no alpha — use stipple for a transparent fill effect
        self.canvas.create_rectangle(cx1, cy1, cx2, cy2,
                                     outline=r.color,
                                     fill=r.color,
                                     stipple="gray25",
                                     width=width, tags="rect")

        # Label in top-left corner
        self.canvas.create_text(cx1 + 4, cy1 + 4, anchor=tk.NW,
                                text=r.label, fill=r.color,
                                font=("Courier", 9, "bold"), tags="label")

        # Corner handles
        for name, (ix, iy) in r.corners.items():
            hcx, hcy = self._img_to_canvas(ix, iy)
            self.canvas.create_oval(
                hcx - HANDLE_RADIUS, hcy - HANDLE_RADIUS,
                hcx + HANDLE_RADIUS, hcy + HANDLE_RADIUS,
                fill=r.color, outline="#ffffff", width=1, tags="handle"
            )
            # Coord tooltip next to each handle
            self.canvas.create_text(hcx + HANDLE_RADIUS + 2, hcy,
                                    anchor=tk.W,
                                    text=f"({int(ix)},{int(iy)})",
                                    fill=r.color,
                                    font=("Courier", 8), tags="handle")

    # ── Side-panel ───────────────────────────────────────────────────────────

    def _update_panel(self):
        labels = [f"{i+1}. {r.label}  W={int(r.x2-r.x1)} H={int(r.y2-r.y1)}"
                  for i, r in enumerate(self.rects)]
        self.rect_list_var.set(labels)
        self._update_coord_detail()

    def _update_coord_detail(self):
        r = self._active_rect
        self.coord_detail.config(state=tk.NORMAL)
        self.coord_detail.delete("1.0", tk.END)
        if r is not None:
            d = r.to_dict()
            lines = [
                f"[{r.label}]\n",
                f"TL: {d['top_left']}\n",
                f"TR: {d['top_right']}\n",
                f"BR: {d['bottom_right']}\n",
                f"BL: {d['bottom_left']}\n",
                f"W:  {d['width']} px\n",
                f"H:  {d['height']} px\n",
            ]
            self.coord_detail.insert(tk.END, "".join(lines))
        self.coord_detail.config(state=tk.DISABLED)

    def _on_listbox_select(self, _event):
        sel = self.rect_listbox.curselection()
        if sel:
            idx = sel[0]
            if 0 <= idx < len(self.rects):
                self._active_rect = self.rects[idx]
                self._redraw()
                self._update_coord_detail()

    def _set_label(self):
        r = self._active_rect
        if r is None:
            return
        new_label = self.label_entry.get().strip()
        if new_label:
            r.label = new_label
            self.label_entry.delete(0, tk.END)
            self._update_panel()
            self._redraw()

    def _delete_selected(self):
        sel = self.rect_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(self.rects):
            self._save_undo()
            r = self.rects.pop(idx)
            if self._active_rect is r:
                self._active_rect = None
            self._redraw()
            self._update_panel()

    # ── Actions ──────────────────────────────────────────────────────────────

    def _clear_all(self):
        if not self.rects:
            return
        self._save_undo()
        self.rects.clear()
        self._active_rect = None
        self._redraw()
        self._update_panel()
        self.status_var.set("All rectangles cleared.")

    def _print_all(self):
        if not self.rects:
            print("# No rectangles defined.")
            return
        print("\n# ── Area Mapper output ──────────────────────────────────")
        for r in self.rects:
            d = r.to_dict()
            print(f"# {d['label']}")
            print(f"{d['label'].upper()}_TL = {d['top_left']}")
            print(f"{d['label'].upper()}_TR = {d['top_right']}")
            print(f"{d['label'].upper()}_BR = {d['bottom_right']}")
            print(f"{d['label'].upper()}_BL = {d['bottom_left']}")
            print(f"{d['label'].upper()}_W  = {d['width']}")
            print(f"{d['label'].upper()}_H  = {d['height']}")
            print()
        print("# ── dict form ───────────────────────────────────────────")
        print("AREAS = {")
        for r in self.rects:
            d = r.to_dict()
            print(f"    {d['label']!r}: {{")
            print(f"        'top_left':     {d['top_left']},")
            print(f"        'top_right':    {d['top_right']},")
            print(f"        'bottom_right': {d['bottom_right']},")
            print(f"        'bottom_left':  {d['bottom_left']},")
            print(f"        'width':        {d['width']},")
            print(f"        'height':       {d['height']},")
            print(f"    }},")
        print("}")
        print("# ─────────────────────────────────────────────────────────\n")
        self.status_var.set(f"Printed {len(self.rects)} rectangle(s) to stdout.")

    # ── Undo ─────────────────────────────────────────────────────────────────

    def _save_undo(self):
        import copy
        self._undo_stack.append(copy.deepcopy(self.rects))
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)

    def _undo(self):
        if not self._undo_stack:
            self.status_var.set("Nothing to undo.")
            return
        self.rects = self._undo_stack.pop()
        self._active_rect = None
        self._redraw()
        self._update_panel()
        self.status_var.set("Undo.")


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    image_path = sys.argv[1] if len(sys.argv) > 1 else None

    root = tk.Tk()
    root.geometry("1280x800")
    root.minsize(800, 600)

    app = AreaMapper(root, image_path)

    # After window is visible, fit the image properly
    if image_path:
        root.after(100, app._fit_image)

    root.mainloop()


if __name__ == "__main__":
    main()
