"""
Geometry / cutting list tab — reads driver, box params and port config
from the shared ProjectState set in the Simulation tab.

Construction convention:
  - Top and Bottom span the full W x D footprint
  - Left and Right sides sit BETWEEN top and bottom (height = H_int)
  - Back sits BETWEEN left/right and top/bottom (W_int x H_int)
  - Front baffle spans the full W x H_ext

Coordinate system:  X = width, Y = depth, Z = height. All values metres.
"""
import math
import numpy as np

from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QRadioButton,
    QScrollArea, QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QToolTip

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.patches import Patch

from ...core.geometry import (
    cutting_list, gross_volume as calc_gross_volume,
    solve_dimensions, standing_wave_resonances,
    solve_wedge_dimensions, bracing_displacement,
    check_fit,
)
from ...core.units import litre_to_m3, mm_to_m, m_to_mm
from ...data.database import list_drivers, get_driver
from ..theme import get_theme
from ..project_state import get_state
from ..scale import s, sf, font_size
from ..collapsible import CollapsibleSection


# ---------------------------------------------------------------------------
# Panel solid helpers
# ---------------------------------------------------------------------------

def _box_faces(x0, x1, y0, y1, z0, z1):
    return [
        [[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0]],
        [[x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]],
        [[x0,y0,z0],[x1,y0,z0],[x1,y0,z1],[x0,y0,z1]],
        [[x0,y1,z0],[x1,y1,z0],[x1,y1,z1],[x0,y1,z1]],
        [[x0,y0,z0],[x0,y1,z0],[x0,y1,z1],[x0,y0,z1]],
        [[x1,y0,z0],[x1,y1,z0],[x1,y1,z1],[x1,y0,z1]],
    ]


def _build_panels(W, D, t, H_int, double_front):
    ft    = 2 * t if double_front else t
    H_ext = t + H_int + t
    panels = [
        ("Bottom",       "#4FC3F7", 0.55, _box_faces(0, W, 0, D, 0, t)),
        ("Top",          "#29B6F6", 0.55, _box_faces(0, W, 0, D, t + H_int, H_ext)),
        ("Left side",    "#81C784", 0.55, _box_faces(0, t, 0, D, t, t + H_int)),
        ("Right side",   "#66BB6A", 0.55, _box_faces(W - t, W, 0, D, t, t + H_int)),
        ("Back",         "#FFB74D", 0.55, _box_faces(t, W - t, D - t, D, t, t + H_int)),
        ("Front baffle", "#EF5350", 0.60, _box_faces(0, W, 0, ft, 0, H_ext)),
    ]
    return panels, H_ext


# ---------------------------------------------------------------------------
# Port geometry helpers
# ---------------------------------------------------------------------------

def _cylinder_faces(cx, cy, cz, axis, r, length, n=24):
    """Faces of a cylinder. axis = 'x'|'y'|'z', pointing inward from face."""
    a  = [2 * math.pi * i / n for i in range(n)]
    ca = [math.cos(v) for v in a]
    sa = [math.sin(v) for v in a]
    if axis == 'y':
        f0 = [(cx + r*c, cy,        cz + r*s) for c,s in zip(ca,sa)]
        f1 = [(cx + r*c, cy+length, cz + r*s) for c,s in zip(ca,sa)]
    elif axis == 'x':
        f0 = [(cx,        cy + r*c, cz + r*s) for c,s in zip(ca,sa)]
        f1 = [(cx+length, cy + r*c, cz + r*s) for c,s in zip(ca,sa)]
    else:
        f0 = [(cx + r*c, cy + r*s, cz)        for c,s in zip(ca,sa)]
        f1 = [(cx + r*c, cy + r*s, cz+length) for c,s in zip(ca,sa)]
    faces = [f0, f1]
    for i in range(n):
        j = (i+1) % n
        faces.append([f0[i], f0[j], f1[j], f1[i]])
    return faces


def _slot_faces(cx, cy, cz, axis, sw, sh, length):
    """Faces of a rectangular (slot) port tube."""
    hw, hh = sw/2, sh/2
    if axis == 'y':
        corners0 = [(cx-hw,cy,cz-hh),(cx+hw,cy,cz-hh),(cx+hw,cy,cz+hh),(cx-hw,cy,cz+hh)]
        corners1 = [(cx-hw,cy+length,cz-hh),(cx+hw,cy+length,cz-hh),
                    (cx+hw,cy+length,cz+hh),(cx-hw,cy+length,cz+hh)]
    elif axis == 'x':
        corners0 = [(cx,cy-hw,cz-hh),(cx,cy+hw,cz-hh),(cx,cy+hw,cz+hh),(cx,cy-hw,cz+hh)]
        corners1 = [(cx+length,cy-hw,cz-hh),(cx+length,cy+hw,cz-hh),
                    (cx+length,cy+hw,cz+hh),(cx+length,cy-hw,cz+hh)]
    else:
        corners0 = [(cx-hw,cy-hh,cz),(cx+hw,cy-hh,cz),(cx+hw,cy+hh,cz),(cx-hw,cy+hh,cz)]
        corners1 = [(cx-hw,cy-hh,cz+length),(cx+hw,cy-hh,cz+length),
                    (cx+hw,cy+hh,cz+length),(cx-hw,cy+hh,cz+length)]
    faces = [corners0, corners1]
    n = 4
    for i in range(n):
        j = (i+1) % n
        faces.append([corners0[i], corners0[j], corners1[j], corners1[i]])
    return faces


def _port_3d(face, pos, port_shape, W_ext, D_ext, H_ext, t, ft,
             radius_or_w, height_or_none, tube_len):
    """
    Return (faces, axis_str) for the port tube and hole.
    Positions:  bottom-left, bottom-right, top-left, top-right
    The port STARTS at the panel face and goes INWARD by tube_len.
    """
    is_slot = (port_shape == "slot")
    sw = radius_or_w * 2 if not is_slot else radius_or_w
    sh = sw if not is_slot else height_or_none
    r  = radius_or_w  # used for round

    margin_x = (sw if is_slot else r*2) * 0.8
    margin_z = (sh if is_slot else r*2) * 0.8

    if face == "front":
        # front baffle: x∈[0,W_ext], z∈[0,H_ext], panel at y=0..ft
        cx = W_ext*0.25 if "left"   in pos else W_ext*0.75
        cz = H_ext*0.25 if "bottom" in pos else H_ext*0.75
        cy_start = ft       # start AFTER the baffle thickness
        if is_slot:
            return _slot_faces(cx, cy_start, cz, 'y', sw, sh, tube_len), 'y'
        else:
            return _cylinder_faces(cx, cy_start, cz, 'y', r, tube_len), 'y'

    elif face == "back":
        # back panel at y = D_ext-t .. D_ext, tube points toward front (neg y)
        cx = W_ext*0.25 if "left"   in pos else W_ext*0.75
        cz = H_ext*0.25 if "bottom" in pos else H_ext*0.75
        cy_start = D_ext - t - tube_len   # tube tip, toward front
        if is_slot:
            return _slot_faces(cx, cy_start, cz, 'y', sw, sh, tube_len), 'y'
        else:
            return _cylinder_faces(cx, cy_start, cz, 'y', r, tube_len), 'y'

    elif face == "left":
        # left panel at x=0..t, tube points right (+x)
        cy = D_ext*0.25 if "left"   in pos else D_ext*0.75
        cz = H_ext*0.25 if "bottom" in pos else H_ext*0.75
        cx_start = t
        if is_slot:
            return _slot_faces(cx_start, cy, cz, 'x', sw, sh, tube_len), 'x'
        else:
            return _cylinder_faces(cx_start, cy, cz, 'x', r, tube_len), 'x'

    else:  # right
        cy = D_ext*0.25 if "left"   in pos else D_ext*0.75
        cz = H_ext*0.25 if "bottom" in pos else H_ext*0.75
        cx_start = W_ext - t - tube_len
        if is_slot:
            return _slot_faces(cx_start, cy, cz, 'x', sw, sh, tube_len), 'x'
        else:
            return _cylinder_faces(cx_start, cy, cz, 'x', r, tube_len), 'x'


# ---------------------------------------------------------------------------
# 3D canvas
# ---------------------------------------------------------------------------

class BoxCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(sf(4), sf(4)), tight_layout=True)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._last_args = None
        self._apply_mpl_theme()
        self.ax = self.fig.add_subplot(111, projection="3d")
        self._draw_empty()
        get_theme().register(self._on_theme_changed)

    def _apply_mpl_theme(self):
        self.fig.set_facecolor(get_theme().palette["mpl_bg"])

    def _on_theme_changed(self, _):
        self._apply_mpl_theme()
        if self._last_args:
            self.draw_box(**self._last_args)
        else:
            self._redraw_empty()

    def _redraw_empty(self):
        p = get_theme().palette
        self.fig.clear()
        self.fig.set_facecolor(p["mpl_bg"])
        self.ax = self.fig.add_subplot(111, projection="3d")
        self._draw_empty()

    def _draw_empty(self):
        p = get_theme().palette
        self.ax.clear()
        self.ax.set_facecolor(p["mpl_axes_bg"])
        self.fig.set_facecolor(p["mpl_bg"])
        self.ax.set_axis_off()
        self.ax.text2D(0.5, 0.5, "Enter dimensions\nand click Calculate",
                       ha="center", va="center",
                       transform=self.ax.transAxes,
                       color=p["mpl_text"], fontsize=10)
        self.fig.canvas.draw()

    def draw_box(self, W_ext, D_ext, t, H_int, double_front, port=None):
        """
        port = None | dict:
            shape       : 'round' | 'slot'
            face        : 'front'|'back'|'left'|'right'
            pos         : 'bottom-left' etc.
            radius      : float  (round — metres)
            slot_w      : float  (slot width metres)
            slot_h      : float  (slot height metres)
            tube_len    : float  (tube length INSIDE box, metres)
        """
        self._last_args = dict(W_ext=W_ext, D_ext=D_ext, t=t,
                               H_int=H_int, double_front=double_front, port=port)
        p        = get_theme().palette
        edge_col = "#AAAAAA" if get_theme().is_dark() else "#222222"
        ft       = 2 * t if double_front else t

        self.fig.clear()
        self.fig.set_facecolor(p["mpl_bg"])
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.ax.set_facecolor(p["mpl_axes_bg"])

        panels, H_ext = _build_panels(W_ext, D_ext, t, H_int, double_front)
        for name, colour, alpha, faces in panels:
            self.ax.add_collection3d(Poly3DCollection(
                faces, alpha=alpha, facecolor=colour,
                edgecolor=edge_col, linewidth=0.5))

        # ── Port ──────────────────────────────────────────────────────────
        if port and port.get("tube_len", 0) > 0:
            shape    = port["shape"]
            face     = port["face"]
            pos      = port["pos"]
            tube_len = port["tube_len"]

            if shape == "round":
                r = port["radius"]
                port_faces, _ = _port_3d(
                    face, pos, "round", W_ext, D_ext, H_ext, t, ft,
                    r, None, tube_len)
            else:
                sw = port["slot_w"]
                sh = port["slot_h"]
                port_faces, _ = _port_3d(
                    face, pos, "slot", W_ext, D_ext, H_ext, t, ft,
                    sw, sh, tube_len)

            self.ax.add_collection3d(Poly3DCollection(
                port_faces, alpha=0.85, facecolor="#AB47BC",
                edgecolor=edge_col, linewidth=0.4))

        pad = max(W_ext, D_ext, H_ext) * 0.12
        self.ax.set_xlim(-pad, W_ext + pad)
        self.ax.set_ylim(-pad, D_ext + pad)
        self.ax.set_zlim(-pad, H_ext + pad)

        self.ax.set_xlabel("Width",  fontsize=8, labelpad=2, color=p["mpl_text"])
        self.ax.set_ylabel("Depth",  fontsize=8, labelpad=2, color=p["mpl_text"])
        self.ax.set_zlabel("Height", fontsize=8, labelpad=2, color=p["mpl_text"])
        self.ax.set_title("Box assembly", fontsize=9, pad=4, color=p["mpl_text"])
        self.ax.tick_params(labelsize=7, colors=p["mpl_text"])
        for pane in (self.ax.xaxis.pane, self.ax.yaxis.pane, self.ax.zaxis.pane):
            pane.fill = False
            pane.set_edgecolor(p["mpl_spine"])

        lc = {"w": "#64B5F6" if get_theme().is_dark() else "#1565C0",
              "d": "#81C784" if get_theme().is_dark() else "#2E7D32",
              "h": "#EF9A9A" if get_theme().is_dark() else "#B71C1C"}
        self.ax.text(W_ext/2, -D_ext*0.18, -H_ext*0.15,
                     f"W {W_ext*1000:.0f} mm", color=lc["w"], fontsize=8, ha="center")
        self.ax.text(W_ext*1.18, D_ext/2, -H_ext*0.15,
                     f"D {D_ext*1000:.0f} mm", color=lc["d"], fontsize=8, ha="center")
        self.ax.text(-W_ext*0.18, -D_ext*0.15, H_ext/2,
                     f"H {H_ext*1000:.0f} mm", color=lc["h"], fontsize=8, ha="center")

        legend_els = [Patch(facecolor=c, edgecolor=edge_col, alpha=a, label=n)
                      for n, c, a, _ in panels]
        if port and port.get("tube_len", 0) > 0:
            legend_els.append(Patch(facecolor="#AB47BC", edgecolor=edge_col,
                                    alpha=0.85, label="Port"))
        self.ax.legend(handles=legend_els, loc="upper left", fontsize=7,
                       framealpha=0.6, facecolor=p["mpl_axes_bg"],
                       labelcolor=p["mpl_text"], edgecolor=p["mpl_spine"])
        self.ax.view_init(elev=28, azim=-50)
        self.fig.canvas.draw()


# ---------------------------------------------------------------------------
# Tab widget
# ---------------------------------------------------------------------------

class GeometryTab(QWidget):
    def __init__(self):
        super().__init__()
        main_layout = QHBoxLayout(self)

        # ── Left: scroll area with collapsible sections ──────────────────
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.verticalScrollBar().setStyleSheet(
            "QScrollBar:vertical { width: 6px; } "
            "QScrollBar::handle:vertical { border-radius: 3px; }"
        )

        left = QWidget()
        ll   = QVBoxLayout(left)
        ll.setContentsMargins(4, 4, 4, 4)
        ll.setSpacing(2)
        left_scroll.setWidget(left)
        left_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        def sb(lo, hi, val, suf, dec=1):
            w = QDoubleSpinBox()
            w.setRange(lo, hi); w.setValue(val)
            w.setSuffix(suf); w.setDecimals(dec)
            return w

        # ── Sync banner ───────────────────────────────────────────────────
        self.lbl_sync = QLabel("")
        self.lbl_sync.setStyleSheet(f"font-size:{font_size(11)}; color: #2196F3;")
        self.lbl_sync.setWordWrap(True)
        ll.addWidget(self.lbl_sync)

        # ── Driver selector ───────────────────────────────────────────────
        sec_drv   = CollapsibleSection("Driver  (for fit check)", expanded=True)
        drv_inner = QWidget()
        drv_form  = QFormLayout(drv_inner)
        drv_form.setContentsMargins(0, 0, 0, 0)
        self.driver_combo    = QComboBox()
        self.btn_refresh_drv = QPushButton("Refresh")
        self.btn_refresh_drv.clicked.connect(self._load_drivers)
        drv_form.addRow("Driver:", self.driver_combo)
        drv_form.addRow(self.btn_refresh_drv)
        sec_drv.set_content(drv_inner)
        ll.addWidget(sec_drv)

        # ── Box parameters ────────────────────────────────────────────────
        sec_box   = CollapsibleSection("Box Parameters", expanded=True)
        box_inner = QWidget()
        f         = QFormLayout(box_inner)
        f.setContentsMargins(0, 0, 0, 0)
        self.spin_volume    = sb(1, 5000, 100, " L")
        self.spin_thickness = sb(6, 50, 18, " mm", 0)
        self.chk_double     = QCheckBox("Double front baffle")
        self.chk_double.setChecked(True)
        
        self.chk_wedge      = QCheckBox("Wedge (angled back)")
        self.chk_wedge.toggled.connect(self._on_wedge_toggled)
        
        self.spin_width  = sb(0, 2000, 0, " mm  (0 = auto)", 0)
        self.spin_depth  = sb(0, 2000, 0, " mm  (0 = auto)", 0)
        self.spin_depth_top = sb(0, 2000, 0, " mm  (top)", 0)
        self.spin_height = sb(0, 2000, 0, " mm  (0 = auto)", 0)
        
        f.addRow("Net volume:",           self.spin_volume)
        f.addRow("Panel thickness:",      self.spin_thickness)
        f.addRow("",                      self.chk_double)
        f.addRow("",                      self.chk_wedge)
        f.addRow("Max external width:",   self.spin_width)
        self.row_depth = f.addRow("Max external depth:",   self.spin_depth)
        self.row_depth_top = f.addRow("External depth top:", self.spin_depth_top)
        f.addRow("Max external height:",  self.spin_height)
        
        self.spin_depth_top.setVisible(False)
        self.label_depth_top = f.labelForField(self.spin_depth_top)
        if self.label_depth_top: self.label_depth_top.setVisible(False)

        dim_note = QLabel("Fixed dimensions are external (available space).")
        dim_note.setStyleSheet(f"font-size:{font_size(11)}; color: gray;")
        dim_note.setWordWrap(True)
        f.addRow(dim_note)
        sec_box.set_content(box_inner)
        ll.addWidget(sec_box)

        # ── Bracing ───────────────────────────────────────────────────────
        sec_brace = CollapsibleSection("Internal Bracing", expanded=False)
        brace_inner = QWidget()
        bf = QFormLayout(brace_inner)
        bf.setContentsMargins(0,0,0,0)
        self.spin_brace_count = sb(0, 20, 0, "", 0)
        self.spin_brace_t     = sb(6, 50, 18, " mm", 0)
        self.spin_brace_cut   = sb(0, 95, 40, " % cutout", 0)
        bf.addRow("# shelf braces:", self.spin_brace_count)
        bf.addRow("Brace thickness:", self.spin_brace_t)
        bf.addRow("Window cutout:",   self.spin_brace_cut)
        sec_brace.set_content(brace_inner)
        ll.addWidget(sec_brace)

        # ── Port placement ────────────────────────────────────────────────
        sec_port   = CollapsibleSection("Port Placement  (vented boxes)", expanded=False)
        port_inner = QWidget()
        port_vbox  = QVBoxLayout(port_inner)
        port_vbox.setContentsMargins(0, 0, 0, 0)

        self.chk_port = QCheckBox("Show port in 3D view / fit check")
        self.chk_port.setChecked(False)
        self.chk_port.toggled.connect(self._on_port_toggle)
        port_vbox.addWidget(self.chk_port)

        # Port shape indicator (read-only — driven by Simulation tab)
        self.lbl_port_shape = QLabel("Port type: —  (set in Simulation tab)")
        self.lbl_port_shape.setStyleSheet(f"font-size:{font_size(11)}; color: gray;")
        port_vbox.addWidget(self.lbl_port_shape)

        # Port dimensions (read-only display + editable override)
        psize_form = QFormLayout()
        self.lbl_port_dims = QLabel("—")
        self.lbl_port_dims.setStyleSheet(f"font-size:{font_size(11)};")
        psize_form.addRow("Port dims:", self.lbl_port_dims)

        # Port length — total including panel contribution
        self.lbl_port_len_calc = QLabel("—")
        self.lbl_port_len_calc.setStyleSheet(f"font-size:{font_size(11)};")
        psize_form.addRow("Total port length:", self.lbl_port_len_calc)
        port_vbox.addLayout(psize_form)

        # Face selector
        face_lbl = QLabel("Face:")
        face_row = QHBoxLayout()
        self.radio_front = QRadioButton("Front")
        self.radio_back  = QRadioButton("Back")
        self.radio_left  = QRadioButton("Left")
        self.radio_right = QRadioButton("Right")
        self.radio_back.setChecked(True)
        self._face_group = QButtonGroup()
        for i, rb in enumerate([self.radio_front, self.radio_back,
                                 self.radio_left, self.radio_right]):
            self._face_group.addButton(rb, i)
            face_row.addWidget(rb)
        port_vbox.addWidget(face_lbl)
        port_vbox.addLayout(face_row)
        self._face_group.buttonClicked.connect(self._on_face_changed)

        # Position dropdown
        pos_form = QFormLayout()
        self.combo_port_pos = QComboBox()
        self.combo_port_pos.addItems(
            ["Bottom-left", "Bottom-right", "Top-left", "Top-right"])
        pos_form.addRow("Position:", self.combo_port_pos)
        port_vbox.addLayout(pos_form)
        sec_port.set_content(port_inner)
        ll.addWidget(sec_port)

        # ── Calculate ─────────────────────────────────────────────────────
        self.btn_calc = QPushButton("  Calculate")
        self.btn_calc.setStyleSheet(f"font-weight:bold;padding:{s(6)}px")
        self.btn_calc.clicked.connect(self._calculate)
        ll.addWidget(self.btn_calc)

        self.lbl_dims = QLabel("-")
        self.lbl_dims.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_dims.setWordWrap(True)
        ll.addWidget(self.lbl_dims)

        self.lbl_fit = QLabel("")
        self.lbl_fit.setWordWrap(True)
        self.lbl_fit.setStyleSheet(f"font-size:{font_size(12)}; font-weight:bold;")
        ll.addWidget(self.lbl_fit)

        sec_res    = CollapsibleSection("Resonances", expanded=True)
        self.lbl_resonances = QLabel("")
        self.lbl_resonances.setWordWrap(True)
        self.lbl_resonances.setStyleSheet(f"font-size:{font_size(11)};")
        sec_res.set_content(self.lbl_resonances)
        ll.addWidget(sec_res)

        sec_cut  = CollapsibleSection("Cutting List", expanded=True)
        self.cut_table = QTableWidget(0, 5)
        self.cut_table.setHorizontalHeaderLabels(
            ["Panel", "Qty", "Length mm", "Width mm", "Notes"])
        self.cut_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        sec_cut.set_content(self.cut_table)
        ll.addWidget(sec_cut)
        ll.addStretch()

        # ── Right: 3D preview (in splitter) ──────────────────────────────
        right = QWidget()
        rl    = QVBoxLayout(right)
        rl.setContentsMargins(4, 4, 4, 4)
        # ── Info button (top-left of 3D panel) ──────────────────────────
        info_row = QHBoxLayout()
        info_btn = QPushButton("\u24d8")
        info_btn.setFixedSize(s(26), s(26))
        info_btn.setToolTip(
            "Each panel shown with actual thickness.\n"
            "Top & bottom span the full width and depth.\n"
            "Left & right sides sit between them.\n"
            "Back sits between the sides.\n"
            "Front baffle spans the full external width and height.\n"
            "Drag to rotate the 3D view."
        )
        info_btn.setStyleSheet(
            f"QPushButton {{ border-radius: {s(13)}px; font-size: {s(14)}px; "
            f"font-weight: bold; padding: 0; }}"
        )
        info_btn.clicked.connect(
            lambda: QToolTip.showText(
                info_btn.mapToGlobal(QPoint(0, info_btn.height())),
                info_btn.toolTip(),
                info_btn
            )
        )
        info_row.addWidget(info_btn)
        info_row.addStretch()
        rl.addLayout(info_row)
        self.canvas = BoxCanvas()
        rl.addWidget(self.canvas, stretch=1)
        rl.addWidget(QLabel(
            "<b>Colours:</b>  "
            "<span style='color:#29B6F6'>&#9632; Top</span>  "
            "<span style='color:#4FC3F7'>&#9632; Bottom</span>  "
            "<span style='color:#66BB6A'>&#9632; Sides</span>  "
            "<span style='color:#FFB74D'>&#9632; Back</span>  "
            "<span style='color:#EF5350'>&#9632; Front</span>  "
            "<span style='color:#AB47BC'>&#9632; Port</span>"))

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([s(400), s(400)])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        main_layout.addWidget(splitter)

        self._drivers = []
        self._load_drivers()
        self._on_port_toggle(False)

        # Register for state changes from Simulation tab
        get_state().register(self._on_state_changed)

    # ── Reset ─────────────────────────────────────────────────────────────

    def collect_state(self):
        """Read all widget values into ProjectState (called before every save)."""
        st = get_state()
        g  = st.geometry
        g.volume_l           = self.spin_volume.value()
        g.thickness_mm       = self.spin_thickness.value()
        g.double_front       = self.chk_double.isChecked()
        g.is_wedge           = self.chk_wedge.isChecked()
        g.fixed_width_mm     = self.spin_width.value()
        g.fixed_depth_mm     = self.spin_depth.value()
        g.fixed_depth_top_mm = self.spin_depth_top.value()
        g.fixed_height_mm    = self.spin_height.value()
        
        g.num_braces           = int(self.spin_brace_count.value())
        g.brace_thickness_mm   = self.spin_brace_t.value()
        g.brace_window_percent = self.spin_brace_cut.value()
        
        g.port_face       = self._get_port_face()
        g.port_position   = self.combo_port_pos.currentText().lower()
        st.panel_thickness_mm = g.thickness_mm

    def reset_ui(self):
        """Reset all widgets to defaults (called on New Project / Load Project)."""
        st = get_state()
        g  = st.geometry
        self._load_drivers()
        self.spin_volume.setValue(g.volume_l)
        self.spin_thickness.setValue(g.thickness_mm)
        self.chk_double.setChecked(g.double_front)
        self.chk_wedge.setChecked(g.is_wedge)
        self.spin_width.setValue(g.fixed_width_mm)
        self.spin_depth.setValue(g.fixed_depth_mm)
        self.spin_depth_top.setValue(g.fixed_depth_top_mm)
        self.spin_height.setValue(g.fixed_height_mm)
        
        self.spin_brace_count.setValue(g.num_braces)
        self.spin_brace_t.setValue(g.brace_thickness_mm)
        self.spin_brace_cut.setValue(g.brace_window_percent)
        face_map = {"front": self.radio_front, "back": self.radio_back,
                    "left": self.radio_left,   "right": self.radio_right}
        face_map.get(g.port_face, self.radio_back).setChecked(True)
        pos_map = {"bottom-left": 0, "bottom-right": 1,
                   "top-left": 2,    "top-right": 3}
        self.combo_port_pos.setCurrentIndex(pos_map.get(g.port_position, 0))
        self.lbl_dims.setText("-")
        self.lbl_fit.setText("")
        self.lbl_resonances.setText("")
        self.lbl_sync.setText("")
        self.cut_table.setRowCount(0)
        self.canvas._draw_empty()
        self._update_port_display()

    # ── State sync ────────────────────────────────────────────────────────

    def _on_state_changed(self):
        """Called by ProjectState.notify() after simulation runs."""
        st = get_state()
        synced = []

        # Sync volume
        if st.volume_l > 0:
            self.spin_volume.setValue(st.volume_l)
            synced.append(f"Volume: {st.volume_l:.1f} L")

        # Sync driver selection
        if st.driver_id:
            for i, d in enumerate(self._drivers):
                if d.id == st.driver_id:
                    self.driver_combo.setCurrentIndex(i + 1)  # +1 for "None" item
                    break
            synced.append(f"Driver: {st.driver_name}")

        # Update port shape display
        self._update_port_display()

        if synced:
            self.lbl_sync.setText("Synced from Simulation tab: " + ",  ".join(synced))
        else:
            self.lbl_sync.setText("")

    def _update_port_display(self):
        """Refresh the port shape/dims labels from ProjectState."""
        st = get_state()
        p  = st.port
        if p.shape == "round":
            self.lbl_port_shape.setText(f"Port type: Round  (from Simulation tab)")
            self.lbl_port_dims.setText(f"ø {p.diameter_mm:.0f} mm  ×  {p.count} port(s)")
        else:
            self.lbl_port_shape.setText(f"Port type: Slot  (from Simulation tab)")
            self.lbl_port_dims.setText(
                f"{p.slot_w_mm:.0f} × {p.slot_h_mm:.0f} mm  ×  {p.count} port(s)")
        self._update_port_len_label()

    def _update_port_len_label(self):
        """
        Show total port length = panel contribution + tube inside box.
        Panel contribution:
          front (double) = 2×t,  front (single) = t,  all others = t
        """
        st   = get_state()
        t_mm = self.spin_thickness.value()
        dbl  = self.chk_double.isChecked()
        face = self._get_port_face()

        if face == "front":
            panel_contrib_mm = t_mm * 2 if dbl else t_mm
        else:
            panel_contrib_mm = t_mm

        tube_mm  = st.port.length_m * 1000.0
        total_mm = tube_mm + panel_contrib_mm

        if tube_mm > 0:
            self.lbl_port_len_calc.setText(
                f"{total_mm:.0f} mm total  "
                f"({panel_contrib_mm:.0f} mm panel + {tube_mm:.0f} mm tube)")
        else:
            self.lbl_port_len_calc.setText(
                "Run simulation first to get calculated port length")

    def _on_face_changed(self, _btn=None):
        self._update_port_len_label()

    # ── Port toggle ───────────────────────────────────────────────────────

    def _on_port_toggle(self, enabled):
        for w in (self.radio_front, self.radio_back, self.radio_left,
                  self.radio_right, self.combo_port_pos):
            w.setEnabled(enabled)

    def _on_wedge_toggled(self, checked):
        # When wedge is on, spin_depth is Bottom Depth, spin_depth_top is Top Depth
        self.spin_depth_top.setVisible(checked)
        if self.label_depth_top: self.label_depth_top.setVisible(checked)
        if checked:
            self.spin_depth.setSuffix(" mm (bottom)")
        else:
            self.spin_depth.setSuffix(" mm (0 = auto)")

    # ── Driver loader ─────────────────────────────────────────────────────

    def _load_drivers(self):
        self._drivers = list_drivers()
        self.driver_combo.clear()
        self.driver_combo.addItem("— None (skip fit check) —")
        for d in self._drivers:
            self.driver_combo.addItem(
                f"{d.name} ({d.manufacturer})" if d.manufacturer else d.name)
        # Re-select from state
        st = get_state()
        if st.driver_id:
            for i, d in enumerate(self._drivers):
                if d.id == st.driver_id:
                    self.driver_combo.setCurrentIndex(i + 1)
                    break

    def _get_selected_driver(self):
        idx = self.driver_combo.currentIndex()
        if idx <= 0 or idx - 1 >= len(self._drivers):
            return None
        return self._drivers[idx - 1]

    def _get_port_face(self):
        if self.radio_front.isChecked(): return "front"
        if self.radio_left.isChecked():  return "left"
        if self.radio_right.isChecked(): return "right"
        return "back"

    # ── Calculate ─────────────────────────────────────────────────────────

    def _calculate(self):
        t      = mm_to_m(self.spin_thickness.value())
        double = self.chk_double.isChecked()
        ft     = 2 * t if double else t

        # Update panel thickness in state so port label stays in sync
        get_state().panel_thickness_mm = self.spin_thickness.value()
        st = get_state()
        box_type = st.box_type
        self.lbl_sync.setText(f"Active enclosure: {box_type.upper()}")

        fw = mm_to_m(self.spin_width.value())  if self.spin_width.value()  > 0 else None
        fd = mm_to_m(self.spin_depth.value())  if self.spin_depth.value()  > 0 else None
        fh = mm_to_m(self.spin_height.value()) if self.spin_height.value() > 0 else None

        net_vol = litre_to_m3(self.spin_volume.value())

        # Adjust gross volume based on box type
        if box_type == "bp4":
            rear_vol = litre_to_m3(getattr(st, "volume_rear", 50.0) / 1000.0) # Assume state stores volume in L
            gv = calc_gross_volume(net_vol + rear_vol, 0.0005, 0.0, [])
        else:
            gv = calc_gross_volume(net_vol, 0.0005, 0.0, [])

        # Bracing volume
        bracing_vol = bracing_displacement(
            int(self.spin_brace_count.value()),
            mm_to_m(self.spin_brace_t.value()),
            fw if fw else 0.4, # approx
            fd if fd else 0.4,
            self.spin_brace_cut.value()
        )
        gv += bracing_vol
        if self.chk_wedge.isChecked():
            # Wedge box
            if not fw or not fh:
                self.lbl_dims.setText("<b style='color:red'>Wedge box needs Fixed Width and Height.</b>")
                return
            dt_ext = mm_to_m(self.spin_depth_top.value()) if self.spin_depth_top.value() > 0 else None
            db_ext = fd # spin_depth
            
            # Convert external to internal for solver
            dt_int = dt_ext - ft - t if dt_ext else None
            db_int = db_ext - ft - t if db_ext else None
            
            H_int, W_int, D_top_int, D_bot_int = solve_wedge_dimensions(
                gv, t, fw - 2*t, fh - 2*t, dt_int, db_int)
            
            D_int = (D_top_int + D_bot_int) / 2 # average for resonances
            H_ext = H_int + 2 * t
            W_ext = W_int + 2 * t
            D_ext = D_int + ft + t
            
            self.lbl_dims.setText(
                f"<b>Internal:</b> W {m_to_mm(W_int):.0f}  H {m_to_mm(H_int):.0f}<br>"
                f"Depth Top: {m_to_mm(D_top_int):.0f}  Bottom: {m_to_mm(D_bot_int):.0f} mm<br>"
                f"<b>Gross volume:</b>  {gv*1000:.2f} L")
            
        else:
            H_int, W_int, D_int = solve_dimensions(
                gv, t, double, fw, fd, fh, external_dims=True)

            H_ext = H_int + 2 * t
            W_ext = W_int + 2 * t
            D_ext = D_int + ft + t

            self.lbl_dims.setText(
                f"<b>Internal:</b>  H {m_to_mm(H_int):.0f}  ×  "
                f"W {m_to_mm(W_int):.0f}  ×  D {m_to_mm(D_int):.0f} mm<br>"
                f"<b>External:</b>  H {m_to_mm(H_ext):.0f}  ×  "
                f"W {m_to_mm(W_ext):.0f}  ×  D {m_to_mm(D_ext):.0f} mm<br>"
                f"<b>Gross volume:</b>  {gv*1000:.2f} L")

        # Update port length label now we have actual dimensions
        self._update_port_len_label()

        # ── Fit checks ────────────────────────────────────────────────────
        driver = self._get_selected_driver()
        st = get_state()
        ps = st.port
        
        # Build PortConfig list from state for check_fit
        ports_to_check = []
        if self.chk_port.isChecked() and ps.length_m > 0:
            from ...core.models import PortConfig
            ports_to_check.append(PortConfig(
                shape="round" if ps.shape == "round" else "slot",
                diameter=ps.diameter_mm / 1000.0,
                width=ps.slot_w_mm / 1000.0,
                height=ps.slot_h_mm / 1000.0,
                length=ps.length_m,
                count=ps.count
            ))

        face = self._get_port_face()
        warnings, oks = check_fit(
            driver, ports_to_check, H_int, W_int, D_int, t, double, port_face=face
        )

        # Build port dict for 3D view
        port_args = None
        if ports_to_check:
            p = ports_to_check[0]
            panel_contrib = ft if face == "front" else t
            tube_len = max(0.0, p.length - panel_contrib)
            pos = self.combo_port_pos.currentText().lower()
            
            if p.shape == "round":
                port_args = dict(shape="round", face=face, pos=pos,
                                 radius=p.diameter/2.0,
                                 tube_len=tube_len)
            else:
                port_args = dict(shape="slot", face=face, pos=pos,
                                 slot_w=p.width,
                                 slot_h=p.height,
                                 tube_len=tube_len)

        color = "#E53935" if warnings else ("#388E3C" if (oks or port_args) else "gray")
        self.lbl_fit.setStyleSheet(f"font-size:{font_size(12)}; font-weight:bold; color:{color};")
        self.lbl_fit.setText("\n".join(warnings + oks))

        # ── Resonances ────────────────────────────────────────────────────
        res   = standing_wave_resonances(H_int, W_int, D_int)
        lines = []
        for axis, key in [("Front-Back","front_back"),
                          ("Top-Bottom","top_bottom"),
                          ("Side-Side","side_side")]:
            lines.append(f"{axis}: {', '.join(f'{f:.0f}' for f in res[key])} Hz")
        for w in res["warnings"]:
            lines.append(f"  {w}")
        self.lbl_resonances.setText("\n".join(lines))

        # ── Cutting list ──────────────────────────────────────────────────
        panels = cutting_list(H_int, W_int, D_int, t, double)
        self.cut_table.setRowCount(len(panels))
        for row, p in enumerate(panels):
            self.cut_table.setItem(row, 0, QTableWidgetItem(p["panel_name"]))
            self.cut_table.setItem(row, 1, QTableWidgetItem(
                str(p["qty"]) if p["qty"] > 0 else "-"))
            self.cut_table.setItem(row, 2, QTableWidgetItem(f"{p['length_mm']:.1f}"))
            self.cut_table.setItem(row, 3, QTableWidgetItem(f"{p['width_mm']:.1f}"))
            self.cut_table.setItem(row, 4, QTableWidgetItem(p["notes"]))

        self.canvas.draw_box(W_ext, D_ext, t, H_int, double, port=port_args)
