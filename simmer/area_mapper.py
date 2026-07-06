"""
area_mapper.py — Interactive tool for mapping rectangular and free-form areas on a reference image.

Usage:
    python -m simmer.area_mapper [image_path]

Controls:
    T                                  → toggle between Rectangle and Free-form tool
    Left-click + drag on empty space   → draw a new rectangle  (Rectangle tool)
    Left-click on empty space          → place a polygon point  (Free-form tool)
    Left-click near first point        → close / finish polygon (Free-form tool, ≥3 points)
    Escape (while drawing polygon)     → cancel current polygon in progress
    Left-click + drag on a rectangle/polygon → move it
    Left-click + drag on a corner handle    → resize rectangle / move polygon vertex
    Right-click a rectangle/polygon    → delete it
    Ctrl+Z                             → undo last action
    Ctrl+A                             → print all shapes to stdout
    C                                  → clear all shapes
    Q / Escape                         → quit (only when not mid-polygon)
    Scroll wheel                       → zoom in / out (centred on cursor)
    + / -                              → zoom in / out
    0                                  → reset zoom to fit

Coordinates are always reported in image-space (origin = top-left of image).
"""

import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import math

# ── Constants ────────────────────────────────────────────────────────────────

HANDLE_RADIUS   = 7       # px radius of corner/vertex handles
HANDLE_HIT      = 10      # px pick distance for handles
MIN_SIZE        = 10      # minimum rectangle side length in image-px
CLOSE_HIT       = 14      # px canvas distance to snap-close a polygon

ZOOM_STEP       = 1.25    # multiply / divide scale by this per zoom step
ZOOM_MIN        = 0.05
ZOOM_MAX        = 16.0

COLORS = [
    "#e74c3c", "#3498db", "#2ecc71", "#f39c12",
    "#9b59b6", "#1abc9c", "#e67e22", "#e91e63",
]

# Shared counter for both shape types
_shape_counter = 0

def _next_id():
    global _shape_counter
    _shape_counter += 1
    return _shape_counter

def _color_for(shape_id: int) -> str:
    return COLORS[(shape_id - 1) % len(COLORS)]


# ── Data models ───────────────────────────────────────────────────────────────

class Rect:
    """A rectangle defined by two corners in image-space."""

    def __init__(self, x1: float, y1: float, x2: float, y2: float, label: str = ""):
        self.id    = _next_id()
        self.label = label or f"area_{self.id}"
        self.color = _color_for(self.id)
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
            "type":         "rect",
            "label":        self.label,
            "top_left":     (int(self.x1), int(self.y1)),
            "top_right":    (int(self.x2), int(self.y1)),
            "bottom_right": (int(self.x2), int(self.y2)),
            "bottom_left":  (int(self.x1), int(self.y2)),
            "width":        int(self.x2 - self.x1),
            "height":       int(self.y2 - self.y1),
        }

    def contains(self, ix: float, iy: float) -> bool:
        return self.x1 <= ix <= self.x2 and self.y1 <= iy <= self.y2

    def __repr__(self):
        d = self.to_dict()
        return (
            f"Rect({d['label']!r}: "
            f"TL={d['top_left']} TR={d['top_right']} "
            f"BR={d['bottom_right']} BL={d['bottom_left']} "
            f"W={d['width']} H={d['height']})"
        )


class Poly:
    """A free-form closed polygon defined by an ordered list of image-space points."""

    def __init__(self, points: list[tuple[float, float]], label: str = ""):
        self.id     = _next_id()
        self.label  = label or f"poly_{self.id}"
        self.color  = _color_for(self.id)
        self.points: list[tuple[float, float]] = list(points)

    def to_dict(self):
        pts = [(int(x), int(y)) for x, y in self.points]
        return {
            "type":   "poly",
            "label":  self.label,
            "points": pts,
        }

    def contains(self, ix: float, iy: float) -> bool:
        """Point-in-polygon test (ray casting)."""
        pts = self.points
        n = len(pts)
        inside = False
        x, y = ix, iy
        j = n - 1
        for i in range(n):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
                inside = not inside
            j = i
        return inside

    def bbox(self):
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return min(xs), min(ys), max(xs), max(ys)

    def __repr__(self):
        pts = [(int(x), int(y)) for x, y in self.points]
        return f"Poly({self.label!r}: {pts})"


# ── Main application ──────────────────────────────────────────────────────────

class AreaMapper:
    def __init__(self, root: tk.Tk, image_path: str | None = None):
        self.root = root
        self.root.title("Area Mapper")

        # State
        self.image_orig: Image.Image | None = None
        self.image_path: str | None = None
        self.scale      = 1.0
        self.offset_x   = 0.0
        self.offset_y   = 0.0

        self.shapes: list[Rect | Poly] = []   # all committed shapes
        self._undo_stack: list = []

        # Tool mode: "rect" or "poly"
        self._tool = "rect"

        # Interaction state (rect draw / move / resize)
        self._drag_mode   = None   # "draw" | "move" | "resize"
        self._active_shape: Rect | Poly | None = None
        self._resize_corner: str | None = None
        self._resize_vertex_idx: int | None = None   # for poly vertex drag
        self._drag_start_canvas = (0, 0)
        self._drag_start_img    = (0, 0)
        self._drag_shape_origin = None   # saved coords at drag start
        self._rubber_band_start = None
        self._rubber_band       = None

        # Free-form polygon in-progress state
        self._poly_pts: list[tuple[float, float]] = []   # placed points
        self._poly_cursor: tuple[float, float] | None = None  # live cursor pos

        self._build_ui()
        self._bind_events()

        if image_path:
            self._load_image(image_path)

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # Top toolbar
        toolbar = tk.Frame(self.root, bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        tk.Button(toolbar, text="Open Image",         command=self._open_image).pack(side=tk.LEFT, padx=4, pady=2)
        tk.Button(toolbar, text="Clear All (C)",      command=self._clear_all).pack(side=tk.LEFT, padx=4, pady=2)
        tk.Button(toolbar, text="Print Coords (Ctrl+A)", command=self._print_all).pack(side=tk.LEFT, padx=4, pady=2)
        tk.Button(toolbar, text="Undo (Ctrl+Z)",      command=self._undo).pack(side=tk.LEFT, padx=4, pady=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)

        # Tool toggle button
        self._tool_btn_var = tk.StringVar(value="Tool: Rectangle [T]")
        self._tool_btn = tk.Button(
            toolbar, textvariable=self._tool_btn_var,
            command=self._toggle_tool,
            relief=tk.RAISED, bg="#ddeeff", width=20,
        )
        self._tool_btn.pack(side=tk.LEFT, padx=4, pady=2)

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

        vbar = tk.Scrollbar(frame, orient=tk.VERTICAL,    command=self.canvas.yview)
        hbar = tk.Scrollbar(self.root, orient=tk.HORIZONTAL, command=self.canvas.xview)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)

        # Bottom status bar
        self.status_var = tk.StringVar(value="Open an image to begin.")
        status_bar = tk.Label(self.root, textvariable=self.status_var,
                              anchor=tk.W, relief=tk.SUNKEN, font=("Courier", 10))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Right-side panel
        panel = tk.Frame(self.root, width=260, bd=1, relief=tk.SUNKEN)
        panel.pack(side=tk.RIGHT, fill=tk.Y)
        panel.pack_propagate(False)

        tk.Label(panel, text="Shapes", font=("TkDefaultFont", 11, "bold")).pack(pady=6)

        self.rect_list_var = tk.StringVar()
        self.rect_listbox  = tk.Listbox(panel, listvariable=self.rect_list_var,
                                        selectmode=tk.SINGLE, font=("Courier", 9),
                                        activestyle="none")
        self.rect_listbox.pack(fill=tk.BOTH, expand=True, padx=4)
        self.rect_listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

        # Coord detail
        self.coord_detail = tk.Text(panel, height=14, font=("Courier", 9),
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
        self.root.bind("<t>",         lambda e: self._toggle_tool())
        self.root.bind("<T>",         lambda e: self._toggle_tool())
        self.root.bind("<Escape>",    self._on_escape)
        self.root.bind("<q>",         lambda e: self.root.quit())
        self.root.bind("<Q>",         lambda e: self.root.quit())

        # Zoom keys
        self.root.bind("<plus>",      lambda e: self._zoom_by(ZOOM_STEP))
        self.root.bind("<equal>",     lambda e: self._zoom_by(ZOOM_STEP))
        self.root.bind("<minus>",     lambda e: self._zoom_by(1/ZOOM_STEP))
        self.root.bind("<0>",         lambda e: self._fit_image())

        # Mouse-wheel zoom
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>",   self._on_mousewheel)
        self.canvas.bind("<Button-5>",   self._on_mousewheel)

    # ── Tool toggle ──────────────────────────────────────────────────────────

    def _toggle_tool(self):
        # Cancel any in-progress polygon before switching
        if self._poly_pts:
            self._poly_pts = []
            self._poly_cursor = None
            self._redraw()

        if self._tool == "rect":
            self._tool = "poly"
            self._tool_btn_var.set("Tool: Free-form [T]")
            self._tool_btn.config(bg="#ffeedd")
            self.canvas.config(cursor="crosshair")
            self.status_var.set("Free-form tool: click to place points, click near start to close.")
        else:
            self._tool = "rect"
            self._tool_btn_var.set("Tool: Rectangle [T]")
            self._tool_btn.config(bg="#ddeeff")
            self.canvas.config(cursor="crosshair")
            self.status_var.set("Rectangle tool: click+drag to draw.")

    # ── Escape handling ──────────────────────────────────────────────────────

    def _on_escape(self, event):
        if self._poly_pts:
            # Cancel in-progress polygon
            self._poly_pts = []
            self._poly_cursor = None
            self._redraw()
            self.status_var.set("Polygon cancelled. Click to place points.")
            return
        self.root.quit()

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
        self.shapes.clear()
        self._undo_stack.clear()
        self._poly_pts = []
        self._poly_cursor = None
        self._fit_image()
        self.root.title(f"Area Mapper — {path}")

    def _fit_image(self):
        if self.image_orig is None:
            return
        self.root.update_idletasks()
        cw = self.canvas.winfo_width()  or 900
        ch = self.canvas.winfo_height() or 700
        iw, ih = self.image_orig.size
        scale = min(cw / iw, ch / ih, 1.0)
        self.scale = scale
        self._render_image()
        tool_hint = (
            "T=toggle tool  |  Rect: click+drag  |  Free-form: click points, close=click start  "
            "|  Move: drag shape  |  Resize/vertex: drag handle  |  Delete: right-click"
        )
        self.status_var.set(
            f"Loaded: {self.image_path}  |  {iw}×{ih} px  |  Scale: {scale:.2f}x  |  {tool_hint}"
        )

    def _render_image(self):
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
        if self.image_orig is None:
            return
        new_scale = max(ZOOM_MIN, min(ZOOM_MAX, self.scale * factor))
        if new_scale == self.scale:
            return
        if canvas_cx is None or canvas_cy is None:
            canvas_cx = self.canvas.canvasx(self.canvas.winfo_width()  / 2)
            canvas_cy = self.canvas.canvasy(self.canvas.winfo_height() / 2)
        img_cx = canvas_cx / self.scale
        img_cy = canvas_cy / self.scale
        self.scale = new_scale
        self._render_image()
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
        if event.num == 4:
            delta = 1
        elif event.num == 5:
            delta = -1
        else:
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

    def _hit_rect_handle(self, cx: float, cy: float):
        """Return (Rect, corner_name) if canvas point is near a Rect corner handle."""
        for r in reversed(self.shapes):
            if not isinstance(r, Rect):
                continue
            for name, (ix, iy) in r.corners.items():
                hcx, hcy = self._img_to_canvas(ix, iy)
                if abs(cx - hcx) <= HANDLE_HIT and abs(cy - hcy) <= HANDLE_HIT:
                    return r, name
        return None, None

    def _hit_poly_vertex(self, cx: float, cy: float):
        """Return (Poly, vertex_index) if canvas point is near a polygon vertex handle."""
        for s in reversed(self.shapes):
            if not isinstance(s, Poly):
                continue
            for i, (ix, iy) in enumerate(s.points):
                hcx, hcy = self._img_to_canvas(ix, iy)
                if abs(cx - hcx) <= HANDLE_HIT and abs(cy - hcy) <= HANDLE_HIT:
                    return s, i
        return None, None

    def _hit_shape(self, cx: float, cy: float):
        """Return topmost shape whose interior contains the canvas point."""
        ix, iy = self._canvas_to_img(cx, cy)
        for s in reversed(self.shapes):
            if s.contains(ix, iy):
                return s
        return None

    def _near_poly_first_point(self, cx: float, cy: float) -> bool:
        """True if canvas point is within CLOSE_HIT px of the first polygon-in-progress point."""
        if len(self._poly_pts) < 3:
            return False
        fx, fy = self._poly_pts[0]
        hcx, hcy = self._img_to_canvas(fx, fy)
        dist = math.hypot(cx - hcx, cy - hcy)
        return dist <= CLOSE_HIT

    # ── Mouse events ─────────────────────────────────────────────────────────

    def _on_lbdown(self, event):
        if self.image_orig is None:
            return
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self._drag_start_canvas = (cx, cy)
        ix, iy = self._canvas_to_img(cx, cy)
        self._drag_start_img = (ix, iy)

        # ── Free-form polygon tool ────────────────────────────────────────
        if self._tool == "poly":
            # If a polygon is in progress, check close-first-point
            if self._poly_pts and self._near_poly_first_point(cx, cy):
                self._finish_polygon()
                return

            # Check if clicking an existing poly vertex handle (for drag)
            p, vidx = self._hit_poly_vertex(cx, cy)
            if p is not None:
                self._save_undo()
                self._drag_mode = "move_vertex"
                self._active_shape = p
                self._resize_vertex_idx = vidx
                self._drag_shape_origin = list(p.points)
                return

            # Check if clicking inside an existing shape (move)
            s = self._hit_shape(cx, cy)
            if s is not None and not self._poly_pts:
                self._save_undo()
                self._drag_mode = "move"
                self._active_shape = s
                self._drag_shape_origin = self._snapshot_shape(s)
                return

            # Place a new polygon point
            iw, ih = self.image_orig.size
            ix = max(0.0, min(ix, iw))
            iy = max(0.0, min(iy, ih))
            self._poly_pts.append((ix, iy))
            self._redraw()
            n = len(self._poly_pts)
            self.status_var.set(
                f"Point {n} placed at ({int(ix)}, {int(iy)})  —  "
                f"{'Click near start to close' if n >= 3 else f'Need {3 - n} more point(s)'}"
            )
            return

        # ── Rectangle tool ────────────────────────────────────────────────
        # Priority: handle → body → draw
        r, corner = self._hit_rect_handle(cx, cy)
        if r is not None:
            self._save_undo()
            self._drag_mode     = "resize"
            self._active_shape  = r
            self._resize_corner = corner
            self._drag_shape_origin = (r.x1, r.y1, r.x2, r.y2)
            return

        s = self._hit_shape(cx, cy)
        if s is not None:
            self._save_undo()
            self._drag_mode = "move"
            self._active_shape = s
            self._drag_shape_origin = self._snapshot_shape(s)
            return

        # Start drawing new rectangle
        self._save_undo()
        self._drag_mode = "draw"
        self._rubber_band_start = (ix, iy)
        self._active_shape = None

    def _on_lbmove(self, event):
        if self.image_orig is None or self._drag_mode is None:
            return
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        ix, iy = self._canvas_to_img(cx, cy)
        iw, ih = self.image_orig.size

        if self._drag_mode == "draw":
            sx, sy = self._rubber_band_start
            ix = max(0.0, min(ix, iw))
            iy = max(0.0, min(iy, ih))
            self._rubber_band = (sx, sy, ix, iy)
            self._redraw()

        elif self._drag_mode == "move":
            s = self._active_shape
            six, siy = self._drag_start_img
            dx = ix - six
            dy = iy - siy
            if isinstance(s, Rect):
                ox1, oy1, ox2, oy2 = self._drag_shape_origin
                w = ox2 - ox1
                h = oy2 - oy1
                nx1 = max(0.0, min(ox1 + dx, iw - w))
                ny1 = max(0.0, min(oy1 + dy, ih - h))
                s.x1, s.y1 = nx1, ny1
                s.x2, s.y2 = nx1 + w, ny1 + h
            elif isinstance(s, Poly):
                orig_pts = self._drag_shape_origin
                s.points = [(max(0.0, min(ox + dx, iw)),
                             max(0.0, min(oy + dy, ih)))
                            for ox, oy in orig_pts]
            self._redraw()

        elif self._drag_mode == "resize":
            r = self._active_shape
            ox1, oy1, ox2, oy2 = self._drag_shape_origin
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

        elif self._drag_mode == "move_vertex":
            s = self._active_shape
            vidx = self._resize_vertex_idx
            ix = max(0.0, min(ix, iw))
            iy = max(0.0, min(iy, ih))
            s.points[vidx] = (ix, iy)
            self._redraw()

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
                self.shapes.append(r)
                self._active_shape = r
                self._update_panel()
            else:
                self._undo_stack.pop()
            self._rubber_band = None

        self._drag_mode = None
        self._redraw()
        self._update_panel()

    def _on_rbdown(self, event):
        if self.image_orig is None:
            return
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        # Right-click cancels in-progress polygon
        if self._poly_pts:
            self._poly_pts = []
            self._poly_cursor = None
            self._redraw()
            self.status_var.set("Polygon cancelled.")
            return

        # Otherwise delete hit shape
        r, _ = self._hit_rect_handle(cx, cy)
        if r is None:
            p, _ = self._hit_poly_vertex(cx, cy)
            if p is not None:
                r = p
        if r is None:
            r = self._hit_shape(cx, cy)
        if r is not None:
            self._save_undo()
            self.shapes.remove(r)
            if self._active_shape is r:
                self._active_shape = None
            self._redraw()
            self._update_panel()

    def _on_mouse_move(self, event):
        if self.image_orig is None:
            return
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        ix, iy = self._canvas_to_img(cx, cy)
        iw, ih = self.image_orig.size
        if 0 <= ix <= iw and 0 <= iy <= ih:
            # Update rubber-band line for in-progress polygon
            if self._poly_pts:
                self._poly_cursor = (ix, iy)
                self._redraw()
                near = self._near_poly_first_point(cx, cy)
                n = len(self._poly_pts)
                if near:
                    self.status_var.set(f"Click to close polygon ({n} points)")
                    self.canvas.config(cursor="dotbox")
                else:
                    self.status_var.set(f"Image coords: ({int(ix)}, {int(iy)})  |  Points: {n}")
                    self.canvas.config(cursor="crosshair")
                return

            # Cursor changes for rect tool
            if self._tool == "rect":
                r, corner = self._hit_rect_handle(cx, cy)
                if r is not None:
                    cursors = {
                        "top_left":     "top_left_corner",
                        "top_right":    "top_right_corner",
                        "bottom_left":  "bottom_left_corner",
                        "bottom_right": "bottom_right_corner",
                    }
                    self.canvas.config(cursor=cursors.get(corner, "crosshair"))
                elif self._hit_shape(cx, cy) is not None:
                    self.canvas.config(cursor="fleur")
                else:
                    self.canvas.config(cursor="crosshair")
            else:
                # Poly tool — show vertex/move cursors
                p, _ = self._hit_poly_vertex(cx, cy)
                if p is not None:
                    self.canvas.config(cursor="fleur")
                elif self._hit_shape(cx, cy) is not None:
                    self.canvas.config(cursor="fleur")
                else:
                    self.canvas.config(cursor="crosshair")

            if self._drag_mode is None:
                self.status_var.set(f"Image coords: ({int(ix)}, {int(iy)})")

    # ── Polygon finishing ────────────────────────────────────────────────────

    def _finish_polygon(self):
        if len(self._poly_pts) < 3:
            return
        self._save_undo()
        p = Poly(self._poly_pts)
        self.shapes.append(p)
        self._active_shape = p
        self._poly_pts = []
        self._poly_cursor = None
        self._redraw()
        self._update_panel()
        self.status_var.set(f"Polygon '{p.label}' closed with {len(p.points)} points.")

    # ── Shape snapshot helper for move/undo ──────────────────────────────────

    def _snapshot_shape(self, s):
        if isinstance(s, Rect):
            return (s.x1, s.y1, s.x2, s.y2)
        elif isinstance(s, Poly):
            return list(s.points)

    # ── Drawing ──────────────────────────────────────────────────────────────

    def _redraw(self):
        self.canvas.delete("rect")
        self.canvas.delete("handle")
        self.canvas.delete("rubber")
        self.canvas.delete("label")
        self.canvas.delete("poly")
        self.canvas.delete("polyhandle")
        self.canvas.delete("polyrubber")

        for s in self.shapes:
            is_active = (s is self._active_shape)
            if isinstance(s, Rect):
                self._draw_rect(s, is_active)
            elif isinstance(s, Poly):
                self._draw_poly(s, is_active)

        # Rect rubber-band preview
        if self._drag_mode == "draw" and self._rubber_band:
            x1, y1, x2, y2 = self._rubber_band
            cx1, cy1 = self._img_to_canvas(x1, y1)
            cx2, cy2 = self._img_to_canvas(x2, y2)
            self.canvas.create_rectangle(cx1, cy1, cx2, cy2,
                                         outline="#ffffff", dash=(4, 4),
                                         width=1, tags="rubber")

        # Polygon in-progress preview
        if self._poly_pts:
            self._draw_poly_in_progress()

        self._update_coord_detail()

    def _draw_rect(self, r: Rect, active: bool = False):
        cx1, cy1 = self._img_to_canvas(r.x1, r.y1)
        cx2, cy2 = self._img_to_canvas(r.x2, r.y2)

        width = 2 if active else 1
        self.canvas.create_rectangle(cx1, cy1, cx2, cy2,
                                     outline=r.color,
                                     fill=r.color,
                                     stipple="gray25",
                                     width=width, tags="rect")

        # Label
        self.canvas.create_text(cx1 + 4, cy1 + 4, anchor=tk.NW,
                                text=r.label, fill=r.color,
                                font=("Courier", 9, "bold"), tags="label")

        # Corner handles with coord labels
        for name, (ix, iy) in r.corners.items():
            hcx, hcy = self._img_to_canvas(ix, iy)
            self.canvas.create_oval(
                hcx - HANDLE_RADIUS, hcy - HANDLE_RADIUS,
                hcx + HANDLE_RADIUS, hcy + HANDLE_RADIUS,
                fill=r.color, outline="#ffffff", width=1, tags="handle"
            )
            self.canvas.create_text(hcx + HANDLE_RADIUS + 2, hcy,
                                    anchor=tk.W,
                                    text=f"({int(ix)},{int(iy)})",
                                    fill=r.color,
                                    font=("Courier", 8), tags="handle")

    def _draw_poly(self, p: Poly, active: bool = False):
        if len(p.points) < 2:
            return
        flat = []
        for ix, iy in p.points:
            cx, cy = self._img_to_canvas(ix, iy)
            flat.extend([cx, cy])

        width = 2 if active else 1
        self.canvas.create_polygon(flat,
                                   outline=p.color,
                                   fill=p.color,
                                   stipple="gray25",
                                   width=width, tags="poly")

        # Label at centroid-ish (first point offset)
        cx0, cy0 = self._img_to_canvas(*p.points[0])
        self.canvas.create_text(cx0 + 4, cy0 + 4, anchor=tk.NW,
                                text=p.label, fill=p.color,
                                font=("Courier", 9, "bold"), tags="label")

        # Vertex handles with coord labels
        for i, (ix, iy) in enumerate(p.points):
            hcx, hcy = self._img_to_canvas(ix, iy)
            self.canvas.create_oval(
                hcx - HANDLE_RADIUS, hcy - HANDLE_RADIUS,
                hcx + HANDLE_RADIUS, hcy + HANDLE_RADIUS,
                fill=p.color, outline="#ffffff", width=1, tags="polyhandle"
            )
            self.canvas.create_text(hcx + HANDLE_RADIUS + 2, hcy,
                                    anchor=tk.W,
                                    text=f"({int(ix)},{int(iy)})",
                                    fill=p.color,
                                    font=("Courier", 8), tags="polyhandle")

    def _draw_poly_in_progress(self):
        pts = self._poly_pts
        color = "#ffffff"

        # Draw placed segments
        for i in range(len(pts) - 1):
            cx1, cy1 = self._img_to_canvas(*pts[i])
            cx2, cy2 = self._img_to_canvas(*pts[i + 1])
            self.canvas.create_line(cx1, cy1, cx2, cy2,
                                    fill=color, width=1, dash=(4, 4), tags="polyrubber")

        # Rubber-band line from last point to cursor
        if self._poly_cursor and pts:
            cx1, cy1 = self._img_to_canvas(*pts[-1])
            cx2, cy2 = self._img_to_canvas(*self._poly_cursor)
            self.canvas.create_line(cx1, cy1, cx2, cy2,
                                    fill=color, width=1, dash=(2, 4), tags="polyrubber")

        # Closing preview line (from cursor to first point) when close enough
        if self._poly_cursor and len(pts) >= 3:
            # Always show faint close-line when >=3 points
            cx_cur, cy_cur = self._img_to_canvas(*self._poly_cursor)
            fx, fy = self._img_to_canvas(*pts[0])
            near = self._near_poly_first_point(cx_cur, cy_cur)
            close_color = "#00ff00" if near else "#555555"
            self.canvas.create_line(cx_cur, cy_cur, fx, fy,
                                    fill=close_color, width=1, dash=(2, 4), tags="polyrubber")

        # Vertex dots for placed points
        for i, (ix, iy) in enumerate(pts):
            hcx, hcy = self._img_to_canvas(ix, iy)
            # First point gets a bigger "close" indicator
            r = HANDLE_RADIUS + 3 if i == 0 else HANDLE_RADIUS
            dot_color = "#00ff00" if i == 0 else color
            self.canvas.create_oval(
                hcx - r, hcy - r, hcx + r, hcy + r,
                fill=dot_color, outline="#000000", width=1, tags="polyrubber"
            )
            self.canvas.create_text(hcx + r + 2, hcy,
                                    anchor=tk.W,
                                    text=f"({int(ix)},{int(iy)})",
                                    fill=dot_color,
                                    font=("Courier", 8), tags="polyrubber")

    # ── Side-panel ───────────────────────────────────────────────────────────

    def _update_panel(self):
        labels = []
        for i, s in enumerate(self.shapes):
            if isinstance(s, Rect):
                labels.append(f"{i+1}. [R] {s.label}  {int(s.x2-s.x1)}×{int(s.y2-s.y1)}")
            elif isinstance(s, Poly):
                labels.append(f"{i+1}. [P] {s.label}  {len(s.points)}pts")
        self.rect_list_var.set(labels)
        self._update_coord_detail()

    def _update_coord_detail(self):
        s = self._active_shape
        self.coord_detail.config(state=tk.NORMAL)
        self.coord_detail.delete("1.0", tk.END)
        if s is not None:
            if isinstance(s, Rect):
                d = s.to_dict()
                lines = [
                    f"[R] {s.label}\n",
                    f"TL: {d['top_left']}\n",
                    f"TR: {d['top_right']}\n",
                    f"BR: {d['bottom_right']}\n",
                    f"BL: {d['bottom_left']}\n",
                    f"W:  {d['width']} px\n",
                    f"H:  {d['height']} px\n",
                ]
            elif isinstance(s, Poly):
                d = s.to_dict()
                lines = [f"[P] {s.label}\n"]
                for i, pt in enumerate(d["points"]):
                    lines.append(f"  P{i}: {pt}\n")
                x1, y1, x2, y2 = s.bbox()
                lines.append(f"bbox W: {int(x2-x1)} H: {int(y2-y1)}\n")
            else:
                lines = []
            self.coord_detail.insert(tk.END, "".join(lines))
        self.coord_detail.config(state=tk.DISABLED)

    def _on_listbox_select(self, _event):
        sel = self.rect_listbox.curselection()
        if sel:
            idx = sel[0]
            if 0 <= idx < len(self.shapes):
                self._active_shape = self.shapes[idx]
                self._redraw()
                self._update_coord_detail()

    def _set_label(self):
        s = self._active_shape
        if s is None:
            return
        new_label = self.label_entry.get().strip()
        if new_label:
            s.label = new_label
            self.label_entry.delete(0, tk.END)
            self._update_panel()
            self._redraw()

    def _delete_selected(self):
        sel = self.rect_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(self.shapes):
            self._save_undo()
            s = self.shapes.pop(idx)
            if self._active_shape is s:
                self._active_shape = None
            self._redraw()
            self._update_panel()

    # ── Actions ──────────────────────────────────────────────────────────────

    def _clear_all(self):
        if not self.shapes:
            return
        self._save_undo()
        self.shapes.clear()
        self._active_shape = None
        self._poly_pts = []
        self._poly_cursor = None
        self._redraw()
        self._update_panel()
        self.status_var.set("All shapes cleared.")

    def _print_all(self):
        if not self.shapes:
            print("# No shapes defined.")
            return
        print("\n# ── Area Mapper output ──────────────────────────────────")
        for s in self.shapes:
            if isinstance(s, Rect):
                d = s.to_dict()
                ul = d["label"].upper()
                print(f"# {d['label']}  (rectangle)")
                print(f"{ul}_TL = {d['top_left']}")
                print(f"{ul}_TR = {d['top_right']}")
                print(f"{ul}_BR = {d['bottom_right']}")
                print(f"{ul}_BL = {d['bottom_left']}")
                print(f"{ul}_W  = {d['width']}")
                print(f"{ul}_H  = {d['height']}")
                print()
            elif isinstance(s, Poly):
                d = s.to_dict()
                ul = d["label"].upper()
                print(f"# {d['label']}  (polygon, {len(d['points'])} points)")
                for i, pt in enumerate(d["points"]):
                    print(f"{ul}_P{i} = {pt}")
                print(f"{ul}_POINTS = {d['points']}")
                print()

        print("# ── dict form ───────────────────────────────────────────")
        print("AREAS = {")
        for s in self.shapes:
            if isinstance(s, Rect):
                d = s.to_dict()
                print(f"    {d['label']!r}: {{")
                print(f"        'type':         'rect',")
                print(f"        'top_left':     {d['top_left']},")
                print(f"        'top_right':    {d['top_right']},")
                print(f"        'bottom_right': {d['bottom_right']},")
                print(f"        'bottom_left':  {d['bottom_left']},")
                print(f"        'width':        {d['width']},")
                print(f"        'height':       {d['height']},")
                print(f"    }},")
            elif isinstance(s, Poly):
                d = s.to_dict()
                print(f"    {d['label']!r}: {{")
                print(f"        'type':   'poly',")
                print(f"        'points': {d['points']},")
                print(f"    }},")
        print("}")
        print("# ─────────────────────────────────────────────────────────\n")
        self.status_var.set(f"Printed {len(self.shapes)} shape(s) to stdout.")

    # ── Undo ─────────────────────────────────────────────────────────────────

    def _save_undo(self):
        import copy
        self._undo_stack.append(copy.deepcopy(self.shapes))
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)

    def _undo(self):
        if not self._undo_stack:
            self.status_var.set("Nothing to undo.")
            return
        self.shapes = self._undo_stack.pop()
        self._active_shape = None
        self._poly_pts = []
        self._poly_cursor = None
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

    if image_path:
        root.after(100, app._fit_image)

    root.mainloop()


if __name__ == "__main__":
    main()
