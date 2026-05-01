"""
Simulation tab - driver selector, box params, calculate button,
results panel, and embedded matplotlib frequency-response charts.
Supports both round and slot (rectangular) ports.
"""
import math
import numpy as np
import matplotlib.ticker as ticker
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox,
    QPushButton, QComboBox, QScrollArea, QSizePolicy, QRadioButton,
    QButtonGroup, QFormLayout, QDialog, QDialogButtonBox, QCheckBox,
    QStackedWidget,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

from nordbass.core.models import Driver
from nordbass.core.ts_box import (
    effective_driver_params,
    sealed_spl_array,
    sealed_params,
    vented_spl_array,
    vented_alignment,
    bandpass_4th_spl_array,
    passive_radiator_spl_array,
    port_air_velocity_array,
    pr_excursion_array,
    cone_excursion_array,
    impedance_array,
    apply_room_gain,
    find_f3,
)
from nordbass.core.ports import (
    equivalent_diameter,
    slot_port_area,
    chuffing_velocity_limit,
    compression_velocity_limit,
)
from nordbass.data.database import list_drivers
from nordbass.gui.project_state import get_state
from nordbass.gui.theme import get_theme
from nordbass.gui.scale import s, sf, font_size

FREQ_MIN   = 10
FREQ_MAX   = 2000
FREQ_TICKS = [10, 20, 30, 50, 80, 100, 150, 200, 300, 500, 800, 1000, 2000]

_autofill_warned: bool = False


# ── Auto-fill warning dialog ───────────────────────────────────────────────────

class _AutoFillInfoDialog(QDialog):
    """Explains what Auto-fill does and its caveats."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Auto-fill — How it works")
        self.setMinimumWidth(s(420))
        layout = QVBoxLayout(self)
        layout.setSpacing(s(10))

        title = QLabel("What does Auto-fill do?")
        title.setFont(QFont("", font_size(13), QFont.Weight.Bold))
        layout.addWidget(title)

        body = QLabel(
            "Auto-fill calculates the ideal enclosure volume (Vb) and tuning "
            "frequency (Fb) based on the selected alignment (e.g. QB3, SC4, B4).<br><br>"
            "<b>When to use it:</b><br>"
            "&bull; You want a quick, theory-based starting point.<br>"
            "&bull; You are unfamiliar with the driver\u2019s T/S parameters.<br><br>"
            "<b>Important caveats:</b><br>"
            "&bull; Alignment formulas assume ideal, linear driver behaviour.<br>"
            "&bull; Real-world results may differ — always verify with measurements.<br>"
            "&bull; The calculated values are a starting point, not a final design.<br>"
            "&bull; Some alignments require a specific Qts range to function correctly."
        )
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(body)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)


# ── Worker thread ──────────────────────────────────────────────────────────────

class _SimWorker(QThread):
    result_ready = Signal(object)
    error        = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn   = fn
        self._args = args
        self._kw   = kwargs

    def run(self):
        try:
            self.result_ready.emit(self._fn(*self._args, **self._kw))
        except Exception as e:          # noqa: BLE001
            self.error.emit(str(e))


# ── Canvas ─────────────────────────────────────────────────────────────────────

class PlotCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(sf(5), sf(8)), tight_layout=True)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._comparison_data = None
        self._bg = None
        self._apply_mpl_theme()
        self.line_spl = None
        self.line_exc = None
        self.line_vel = None
        self.line_imp = None
        self.line_xmax = None
        self.line_chuff = None
        self.line_comp = None
        self.line_fb = []
        self.line_comp_spl = None
        self.line_comp_exc = None
        self.line_comp_vel = None
        self.line_comp_imp = None
        self._build_axes()
        get_theme().register(self._on_theme_changed)
        self.mpl_connect("motion_notify_event", self._on_mouse_move)
        self.mpl_connect("draw_event", self._on_draw)
        self._cursor_vlines = []

    def set_comparison(self, freqs, spl, excursion, velocity, impedance):
        self._comparison_data = (freqs, spl, excursion, velocity, impedance)

    def clear_comparison(self):
        self._comparison_data = None

    def _on_draw(self, event):
        if event is not None and event.canvas != self:
            return
        self._bg = self.copy_from_bbox(self.fig.bbox)
        self._draw_cursor()

    def _on_mouse_move(self, event):
        if not event.inaxes or not self._cursor_vlines or self._bg is None:
            return
        x = event.xdata
        for line in self._cursor_vlines:
            line.set_xdata([x, x])
            line.set_visible(True)
        self.restore_region(self._bg)
        for ax in (self.ax_spl, self.ax_exc, self.ax_vel, self.ax_imp):
            for line in self._cursor_vlines:
                if line in ax.get_lines():
                    ax.draw_artist(line)
        self.blit(self.fig.bbox)

    def _draw_cursor(self):
        for ax in (self.ax_spl, self.ax_exc, self.ax_vel, self.ax_imp):
            for line in self._cursor_vlines:
                if line in ax.get_lines():
                    ax.draw_artist(line)

    def _apply_mpl_theme(self):
        p = get_theme().palette
        self.fig.set_facecolor(p["mpl_bg"])

    def _on_theme_changed(self, _name):
        self._apply_mpl_theme()
        self._build_axes()
        self.draw()

    def _build_axes(self):
        p = get_theme().palette
        self.fig.clear()
        self.fig.set_facecolor(p["mpl_bg"])
        self.ax_spl, self.ax_exc, self.ax_vel, self.ax_imp = self.fig.subplots(4, 1, sharex=True)
        self._cursor_vlines = []
        for ax in (self.ax_spl, self.ax_exc, self.ax_vel, self.ax_imp):
            ax.set_facecolor(p["mpl_axes_bg"])
            ax.set_xscale("log")
            ax.set_xticks(FREQ_TICKS)
            ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: str(int(x))))
            ax.xaxis.set_minor_locator(ticker.NullLocator())
            ax.grid(True, which="major", linestyle="--", alpha=0.45, color=p["mpl_grid"])
            ax.set_xlim(FREQ_MIN, FREQ_MAX)
            ax.tick_params(axis="x", labelsize=7, rotation=45, colors=p["mpl_text"])
            ax.tick_params(axis="y", colors=p["mpl_text"], labelsize=7)
            for spine in ax.spines.values():
                spine.set_edgecolor(p["mpl_spine"])
            v_line = ax.axvline(x=10, color="gray", linestyle="-", alpha=0.3, visible=False, animated=True)
            self._cursor_vlines.append(v_line)
        self.ax_spl.set_ylabel("SPL (dB)", fontsize=8, color=p["mpl_text"])
        self.ax_spl.set_title("Frequency Response", fontsize=9, color=p["mpl_text"])
        self.ax_exc.set_ylabel("Exc. (mm)", fontsize=8, color=p["mpl_text"])
        self.ax_exc.set_title("Cone Excursion", fontsize=9, color=p["mpl_text"])
        self.ax_vel.set_ylabel("Vel. (m/s)", fontsize=8, color=p["mpl_text"])
        self.ax_vel.set_title("Port Air Velocity", fontsize=9, color=p["mpl_text"])
        self.ax_imp.set_ylabel("Imp. (\u03a9)", fontsize=8, color=p["mpl_text"])
        self.ax_imp.set_title("Electrical Impedance", fontsize=9, color=p["mpl_text"])
        self.ax_imp.set_xlabel("Frequency (Hz)", fontsize=8, color=p["mpl_text"])
        self.line_spl,  = self.ax_spl.plot([], [], color="#2196F3", linewidth=1.6)
        self.line_exc,  = self.ax_exc.plot([], [], color="#4CAF50", linewidth=1.6, label="Driver Xpeak")
        # PR excursion: initialised hidden; label suppressed until PR mode active
        self.line_pr_exc, = self.ax_exc.plot([], [], color="#FF9800", linewidth=1.2,
                                              linestyle="-.", label="_nolegend_", visible=False)
        self.line_vel,  = self.ax_vel.plot([], [], color="#9C27B0", linewidth=1.6, label="Port Velocity")
        self.line_imp,  = self.ax_imp.plot([], [], color="#FFD600", linewidth=1.6, label="Impedance")
        self.line_xmax  = self.ax_exc.axhline(0, color="#F44336", linestyle="--", linewidth=1.2, visible=False)
        self.line_chuff, = self.ax_vel.plot([], [], color="#FF5722", linestyle="--", linewidth=1.2)
        self.line_comp,  = self.ax_vel.plot([], [], color="#F44336", linestyle=":",  linewidth=1.2)
        kw_comp = {"color": "gray", "alpha": 0.4, "linestyle": "--", "linewidth": 1.2}
        self.line_comp_spl, = self.ax_spl.plot([], [], **kw_comp)
        self.line_comp_exc, = self.ax_exc.plot([], [], **kw_comp)
        self.line_comp_vel, = self.ax_vel.plot([], [], **kw_comp)
        self.line_comp_imp, = self.ax_imp.plot([], [], **kw_comp)
        self.line_fb = []

    def plot(self, freqs, spl, excursion, xmax_mm,
             port_velocity=None, chuff_limit=None, comp_limit=None,
             impedance=None, fb=None, box_type="vented", pr_excursion=None):

        self.line_spl.set_data(freqs, spl)
        self.line_exc.set_data(freqs, excursion)

        # PR excursion — only shown and labelled in PR mode
        if pr_excursion is not None:
            self.line_pr_exc.set_data(freqs, pr_excursion)
            self.line_pr_exc.set_visible(True)
            self.line_pr_exc.set_label("PR Xpeak")
        else:
            self.line_pr_exc.set_data([], [])
            self.line_pr_exc.set_visible(False)
            self.line_pr_exc.set_label("_nolegend_")

        # Port velocity — only shown for vented/bp4
        if port_velocity is not None and box_type not in ("sealed", "pr"):
            self.line_vel.set_data(freqs, port_velocity)
            self.line_vel.set_visible(True)
        else:
            self.line_vel.set_data([], [])
            self.line_vel.set_visible(False)

        if impedance is not None:
            self.line_imp.set_data(freqs, impedance)

        # Chuff limit
        if chuff_limit is not None and port_velocity is not None and box_type not in ("sealed", "pr"):
            self.line_chuff.set_data(freqs, np.full_like(freqs, chuff_limit))
            self.line_chuff.set_visible(True)
        else:
            self.line_chuff.set_data([], [])
            self.line_chuff.set_visible(False)

        # Compression limit
        if comp_limit is not None and port_velocity is not None and box_type not in ("sealed", "pr"):
            self.line_comp.set_data(freqs, np.full_like(freqs, comp_limit))
            self.line_comp.set_visible(True)
        else:
            self.line_comp.set_data([], [])
            self.line_comp.set_visible(False)

        # Comparison overlay
        if self._comparison_data:
            cf, cs, ce, cv, ci = self._comparison_data
            self.line_comp_spl.set_data(cf, cs)
            self.line_comp_exc.set_data(cf, ce)
            if cv is not None:
                self.line_comp_vel.set_data(cf, cv)
            if ci is not None:
                self.line_comp_imp.set_data(cf, ci)
        else:
            for ln in (self.line_comp_spl, self.line_comp_exc,
                       self.line_comp_vel, self.line_comp_imp):
                ln.set_data([], [])

        # Fb markers
        for ln in self.line_fb:
            try:
                ln.remove()
            except Exception:   # noqa: BLE001
                pass
        self.line_fb = []
        if fb is not None:
            p = get_theme().palette
            kw_fb = {"color": p.get("mpl_fb", "#80CBC4"), "linestyle": ":",
                     "linewidth": 1.2, "alpha": 0.8}
            for ax in (self.ax_spl, self.ax_exc):
                self.line_fb.append(ax.axvline(fb, **kw_fb))
            if box_type not in ("sealed", "pr"):
                self.line_fb.append(self.ax_vel.axvline(fb, **kw_fb))
            self.line_fb.append(self.ax_imp.axvline(fb, **kw_fb))

        # Xmax reference
        self.line_xmax.set_ydata([xmax_mm, xmax_mm])
        self.line_xmax.set_visible(True)

        # Axis limits
        s_max = np.nanmax(spl)
        self.ax_spl.set_ylim(max(s_max - 40, 60), s_max + 5)
        e_mask = freqs >= 20
        e_max  = np.nanmax(excursion[e_mask])
        if pr_excursion is not None:
            e_max = max(e_max, np.nanmax(pr_excursion[e_mask]))
        self.ax_exc.set_ylim(0, max(e_max * 1.2, xmax_mm * 1.2))
        if port_velocity is not None and box_type not in ("sealed", "pr"):
            v_max = np.nanmax(port_velocity[e_mask])
            self.ax_vel.set_ylim(0, max(v_max * 1.2, 30))
        else:
            self.ax_vel.set_ylim(0, 30)

        self.ax_spl.legend(fontsize=7, loc="lower right")
        self.ax_exc.legend(fontsize=7, loc="upper right")
        if port_velocity is not None and box_type not in ("sealed", "pr"):
            self.ax_vel.legend(fontsize=7, loc="upper right")
        else:
            leg = self.ax_vel.get_legend()
            if leg:
                leg.remove()
        if impedance is not None:
            self.ax_imp.legend(fontsize=7, loc="upper right")
        self.draw()


def _spinbox(mn, mx, val, suf, dec=0, step=None):
    sb = QDoubleSpinBox()
    sb.setRange(mn, mx)
    sb.setValue(val)
    sb.setSuffix(suf)
    sb.setDecimals(dec)
    if step is not None:
        sb.setSingleStep(step)
    return sb


# ── Main tab ───────────────────────────────────────────────────────────────────

class SimulationTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = []
        self._result_labels = {}
        self._drivers = []
        self._build_ui()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(s(4), s(4), s(4), s(4))
        main_layout.setSpacing(s(8))

        # ── Left panel (scrollable controls) ─────────────────────────────
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setMinimumWidth(s(280))
        left_scroll.setMaximumWidth(s(360))

        left_widget = QWidget()
        left_layout  = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(s(4), s(4), s(4), s(4))
        left_layout.setSpacing(s(6))
        left_scroll.setWidget(left_widget)

        # Driver selector
        drv_row = QHBoxLayout()
        drv_row.setSpacing(s(4))
        drv_lbl = QLabel("Driver:")
        drv_lbl.setFont(QFont("", font_size(10), QFont.Weight.Medium))
        self.driver_combo = QComboBox()
        self.driver_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        drv_row.addWidget(drv_lbl)
        drv_row.addWidget(self.driver_combo)
        left_layout.addLayout(drv_row)

        # Driver count + wiring
        dcw_row = QHBoxLayout()
        dcw_row.setSpacing(s(4))
        self.spin_drv_count = _spinbox(1, 12, 1, " driver(s)", dec=0, step=1)
        self.combo_wiring = QComboBox()
        self.combo_wiring.addItems(["Series", "Parallel"])
        dcw_row.addWidget(self.spin_drv_count)
        dcw_row.addWidget(self.combo_wiring)
        left_layout.addLayout(dcw_row)

        # Box-type radio buttons
        box_type_row = QHBoxLayout()
        box_type_row.setSpacing(s(4))
        self.radio_vented = QRadioButton("Vented")
        self.radio_sealed = QRadioButton("Sealed")
        self.radio_bp4    = QRadioButton("BP4")
        self.radio_pr     = QRadioButton("PR")
        self.radio_vented.setChecked(True)
        btn_grp = QButtonGroup(self)
        for rb in (self.radio_vented, self.radio_sealed, self.radio_bp4, self.radio_pr):
            btn_grp.addButton(rb)
            box_type_row.addWidget(rb)
        left_layout.addLayout(box_type_row)

        # Core spinboxes
        form = QFormLayout()
        form.setSpacing(s(4))
        self.spin_volume      = _spinbox(1,   500,  30,  " L",         dec=1, step=0.5)
        self.spin_volume_rear = _spinbox(1,   500,  50,  " L (rear)",  dec=1, step=0.5)
        self.spin_fb          = _spinbox(10,  200,  40,  " Hz",        dec=1, step=0.5)
        self.spin_power       = _spinbox(1, 5000, 100,  " W",          dec=0, step=10)
        form.addRow("Volume:",      self.spin_volume)
        form.addRow("Rear Volume:", self.spin_volume_rear)
        form.addRow("Tuning (Fb):", self.spin_fb)
        form.addRow("Input Power:", self.spin_power)
        left_layout.addLayout(form)

        # Alignment
        align_row = QHBoxLayout()
        align_row.setSpacing(s(4))
        align_lbl = QLabel("Alignment:")
        self.combo_alignment = QComboBox()
        self.combo_alignment.addItems(["QB3", "B4", "SC4", "Butterworth"])
        align_row.addWidget(align_lbl)
        align_row.addWidget(self.combo_alignment)
        left_layout.addLayout(align_row)

        # Auto-fill button row with compact warning icon
        auto_row = QHBoxLayout()
        auto_row.setSpacing(s(4))

        self.btn_auto = QPushButton("\u2728  Auto-fill from alignment")
        self.btn_auto.setToolTip(
            "Calculates Vb and Fb from the selected alignment formula.\n"
            "Click \u26a0 for important caveats."
        )
        self.btn_auto.setStyleSheet(
            f"QPushButton {{ font-size: {font_size(10)}px; padding: {s(4)}px {s(8)}px; }}"
        )
        self.btn_auto.clicked.connect(self._auto_fill)

        self.btn_warn = QPushButton("\u26a0")
        self.btn_warn.setFixedSize(s(26), s(26))
        self.btn_warn.setToolTip(
            "Auto-fill uses theoretical alignment formulas.\n"
            "Real results may differ \u2014 click for details."
        )
        self.btn_warn.setStyleSheet(
            f"QPushButton {{"
            f"  font-size: {font_size(14)}px; color: #FFA000;"
            f"  background: transparent; border: 1px solid transparent;"
            f"  border-radius: {s(4)}px; padding: 0;"
            f"}} "
            f"QPushButton:hover {{ border-color: #FFA000; }}"
        )
        self.btn_warn.setVisible(False)
        self.btn_warn.clicked.connect(self._show_warn_dialog)

        auto_row.addWidget(self.btn_auto, stretch=1)
        auto_row.addWidget(self.btn_warn)
        left_layout.addLayout(auto_row)

        # Room gain
        self.chk_room_gain = QCheckBox("Room gain correction")
        left_layout.addWidget(self.chk_room_gain)

        # Port section
        port_lbl = QLabel("Port")
        port_lbl.setFont(QFont("", font_size(10), QFont.Weight.Bold))
        left_layout.addWidget(port_lbl)

        port_form = QFormLayout()
        port_form.setSpacing(s(4))

        self.combo_port_shape = QComboBox()
        self.combo_port_shape.addItems(["Round", "Slot"])
        port_form.addRow("Shape:", self.combo_port_shape)

        self.spin_port_count = _spinbox(1, 8, 1, " port(s)", dec=0, step=1)
        port_form.addRow("Count:", self.spin_port_count)

        self.port_stack = QStackedWidget()

        round_w = QWidget()
        round_form = QFormLayout(round_w)
        round_form.setContentsMargins(0, 0, 0, 0)
        self.spin_port_diam = _spinbox(10, 500, 100, " mm", dec=1, step=1)
        round_form.addRow("Diameter:", self.spin_port_diam)

        slot_w = QWidget()
        slot_form = QFormLayout(slot_w)
        slot_form.setContentsMargins(0, 0, 0, 0)
        self.spin_slot_w = _spinbox(10, 1000, 100, " mm (W)", dec=1, step=1)
        self.spin_slot_h = _spinbox(10, 1000,  50, " mm (H)", dec=1, step=1)
        self.lbl_eq_diam = QLabel("Eq. diameter: --")
        self.lbl_eq_diam.setStyleSheet(f"color: gray; font-size: {font_size(9)}px;")
        slot_form.addRow("Width:",  self.spin_slot_w)
        slot_form.addRow("Height:", self.spin_slot_h)
        slot_form.addRow("",        self.lbl_eq_diam)

        self.port_stack.addWidget(round_w)
        self.port_stack.addWidget(slot_w)
        port_form.addRow(self.port_stack)
        left_layout.addLayout(port_form)
        self.combo_port_shape.currentIndexChanged.connect(self._on_port_shape_changed)

        # PR parameters
        pr_lbl = QLabel("Passive Radiator")
        pr_lbl.setFont(QFont("", font_size(10), QFont.Weight.Bold))
        left_layout.addWidget(pr_lbl)
        self.pr_widget = QWidget()
        pr_form = QFormLayout(self.pr_widget)
        pr_form.setSpacing(s(4))
        self.spin_pr_fs  = _spinbox(1,   200,  20,  " Hz (PR Fs)",  dec=1, step=0.1)
        self.spin_pr_vas = _spinbox(1,  2000, 100,  " L (PR Vas)",  dec=1, step=0.5)
        self.spin_pr_qms = _spinbox(0.1,  30,   5,  " (PR Qms)",    dec=2, step=0.01)
        self.spin_pr_sd  = _spinbox(10, 10000, 200, " cm\u00b2 (PR Sd)", dec=1, step=1.0)
        pr_form.addRow("PR Fs:",  self.spin_pr_fs)
        pr_form.addRow("PR Vas:", self.spin_pr_vas)
        pr_form.addRow("PR Qms:", self.spin_pr_qms)
        pr_form.addRow("PR Sd:",  self.spin_pr_sd)
        left_layout.addWidget(self.pr_widget)

        # Calculate button
        self.btn_calc = QPushButton("Calculate")
        self.btn_calc.setStyleSheet(
            f"QPushButton {{ font-size: {font_size(11)}px; font-weight: bold; "
            f"padding: {s(6)}px {s(12)}px; }}"
        )
        self.btn_calc.clicked.connect(self._calculate)
        left_layout.addWidget(self.btn_calc)

        # Results
        res_lbl = QLabel("Results")
        res_lbl.setFont(QFont("", font_size(10), QFont.Weight.Bold))
        left_layout.addWidget(res_lbl)
        res_form = QFormLayout()
        res_form.setSpacing(s(3))
        for key in (
            "F3", "F6", "F10",
            "Peak SPL", "Avg SPL (80-200 Hz)",
            "Max excursion", "Port length",
            "Peak port vel.", "Chuff limit",
            "Impedance @ Fb",
        ):
            lbl = QLabel("-")
            res_form.addRow(f"{key}:", lbl)
            self._result_labels[key] = lbl
        left_layout.addLayout(res_form)

        # Comparison controls
        comp_lbl = QLabel("Comparison")
        comp_lbl.setFont(QFont("", font_size(10), QFont.Weight.Bold))
        left_layout.addWidget(comp_lbl)
        comp_box = QHBoxLayout()
        comp_box.setSpacing(s(4))
        self.btn_pin = QPushButton("Pin current")
        self.btn_pin.clicked.connect(self._pin_comparison)
        self.btn_clear_comp = QPushButton("Clear")
        self.btn_clear_comp.clicked.connect(self._clear_comparison)
        comp_box.addWidget(self.btn_pin)
        comp_box.addWidget(self.btn_clear_comp)
        left_layout.addLayout(comp_box)
        left_layout.addStretch()
        main_layout.addWidget(left_scroll)

        # ── Right panel: hamburger toggle + toolbar + canvas ──────────────
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.canvas  = PlotCanvas()
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.toolbar.setStyleSheet("background-color: transparent; border: none;")

        toolbar_row = QHBoxLayout()
        toolbar_row.setContentsMargins(s(2), 0, s(2), 0)
        toolbar_row.setSpacing(0)

        self.btn_hamburger = QPushButton("\u2630")
        self.btn_hamburger.setFixedSize(s(28), s(28))
        self.btn_hamburger.setToolTip("Show / hide graph tools")
        self.btn_hamburger.setStyleSheet(
            f"QPushButton {{"
            f"  font-size: {font_size(14)}px; background: transparent;"
            f"  border: 1px solid transparent; border-radius: {s(4)}px; padding: 0;"
            f"}} "
            f"QPushButton:hover {{ border-color: gray; }}"
        )
        self.btn_hamburger.clicked.connect(self._toggle_toolbar)
        toolbar_row.addWidget(self.btn_hamburger)
        toolbar_row.addStretch()

        self.toolbar.setVisible(False)

        right_layout.addLayout(toolbar_row)
        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas, stretch=1)
        main_layout.addWidget(right_panel, stretch=1)

        # Wire signals
        for w in (self.spin_drv_count, self.spin_volume, self.spin_volume_rear,
                  self.spin_fb, self.spin_power, self.spin_port_count,
                  self.spin_port_diam, self.spin_slot_w, self.spin_slot_h,
                  self.spin_pr_fs, self.spin_pr_vas, self.spin_pr_qms, self.spin_pr_sd):
            w.valueChanged.connect(self._calculate)
        for w in (self.driver_combo, self.combo_wiring, self.combo_alignment,
                  self.combo_port_shape):
            w.currentIndexChanged.connect(self._calculate)
        self.radio_sealed.toggled.connect(self._calculate)
        self.radio_bp4.toggled.connect(self._calculate)
        self.radio_pr.toggled.connect(self._calculate)
        self.chk_room_gain.stateChanged.connect(self._calculate)

        self._drivers = []
        self._load_drivers()
        self._on_box_type_changed()
        self._on_port_shape_changed(0)

    # ── Hamburger toggle ──────────────────────────────────────────────────

    def _toggle_toolbar(self):
        self.toolbar.setVisible(not self.toolbar.isVisible())

    # ── Warning icon helpers ──────────────────────────────────────────────

    def _show_warn_dialog(self):
        dlg = _AutoFillInfoDialog(self)
        dlg.exec()

    # ── State helpers ─────────────────────────────────────────────────────

    def collect_state(self):
        st = get_state()
        if self.radio_sealed.isChecked():   st.box_type = "sealed"
        elif self.radio_bp4.isChecked():    st.box_type = "bp4"
        elif self.radio_pr.isChecked():     st.box_type = "pr"
        else:                               st.box_type = "vented"
        st.volume_l      = self.spin_volume.value()
        st.fb_hz         = self.spin_fb.value()
        st.input_power_w = self.spin_power.value()
        st.alignment     = self.combo_alignment.currentText()
        st.port.shape    = "round" if self.combo_port_shape.currentIndex() == 0 else "slot"
        st.port.count    = int(self.spin_port_count.value())
        st.port.diameter_mm = self.spin_port_diam.value()
        st.port.slot_w_mm   = self.spin_slot_w.value()
        st.port.slot_h_mm   = self.spin_slot_h.value()
        if self._drivers and self.driver_combo.currentIndex() >= 0:
            idx = self.driver_combo.currentIndex()
            if idx < len(self._drivers):
                d = self._drivers[idx]
                st.driver_id   = d.id
                st.driver_name = f"{d.name} ({d.manufacturer})" if d.manufacturer else d.name

    def reset_ui(self):
        st = get_state()
        self._load_drivers()
        if st.box_type == "sealed":    self.radio_sealed.setChecked(True)
        elif st.box_type == "bp4":     self.radio_bp4.setChecked(True)
        elif st.box_type == "pr":      self.radio_pr.setChecked(True)
        else:                          self.radio_vented.setChecked(True)
        self.spin_volume.setValue(st.volume_l)
        self.spin_fb.setValue(st.fb_hz)
        self.spin_power.setValue(st.input_power_w)
        idx = self.combo_alignment.findText(st.alignment)
        if idx >= 0:
            self.combo_alignment.setCurrentIndex(idx)
        shape_idx = 0 if st.port.shape == "round" else 1
        self.combo_port_shape.setCurrentIndex(shape_idx)
        self.spin_port_diam.setValue(st.port.diameter_mm)
        self.spin_port_count.setValue(st.port.count)
        self.spin_slot_w.setValue(st.port.slot_w_mm)
        self.spin_slot_h.setValue(st.port.slot_h_mm)
        for lbl in self._result_labels.values():
            lbl.setText("-")
        self.canvas._build_axes()
        self.canvas.draw()

    def _on_port_shape_changed(self, idx):
        self.port_stack.setCurrentIndex(idx)
        if idx == 1:
            self._update_eq_diam()

    def _update_eq_diam(self):
        w = self.spin_slot_w.value() / 1000.0
        h = self.spin_slot_h.value() / 1000.0
        eq_d = equivalent_diameter(slot_port_area(w, h)) * 1000.0
        self.lbl_eq_diam.setText(f"Eq. diameter: {eq_d:.1f} mm")

    def _on_box_type_changed(self):
        sealed = self.radio_sealed.isChecked()
        vented = self.radio_vented.isChecked()
        bp4    = self.radio_bp4.isChecked()
        pr     = self.radio_pr.isChecked()
        self.spin_fb.setEnabled(vented or bp4 or pr)
        self.combo_alignment.setEnabled(vented or bp4)
        self.spin_volume_rear.setEnabled(bp4)
        self.spin_port_count.setEnabled(not sealed and not pr)
        self.combo_port_shape.setEnabled(not sealed and not pr)
        self.port_stack.setEnabled(not sealed and not pr)
        self.pr_widget.setVisible(pr)
        self.btn_auto.setEnabled(vented)

    # ── Driver management ─────────────────────────────────────────────────

    def _load_drivers(self):
        prev_text = self.driver_combo.currentText()
        self.driver_combo.blockSignals(True)
        self.driver_combo.clear()
        try:
            self._drivers = list_drivers()
        except Exception:   # noqa: BLE001
            self._drivers = []
        for d in self._drivers:
            label = f"{d.name} ({d.manufacturer})" if d.manufacturer else d.name
            self.driver_combo.addItem(label)
        idx = self.driver_combo.findText(prev_text)
        if idx >= 0:
            self.driver_combo.setCurrentIndex(idx)
        self.driver_combo.blockSignals(False)

    def reload_drivers(self):
        self._load_drivers()
        self._calculate()

    # ── Auto-fill ─────────────────────────────────────────────────────────

    def _auto_fill(self):
        global _autofill_warned
        if not self._drivers or self.driver_combo.currentIndex() < 0:
            return
        idx = self.driver_combo.currentIndex()
        if idx >= len(self._drivers):
            return
        if not _autofill_warned:
            dlg = _AutoFillInfoDialog(self)
            dlg.exec()
            _autofill_warned = True

        driver    = self._drivers[idx]
        alignment = self.combo_alignment.currentText()
        try:
            vb_m3, fb = vented_alignment(driver, alignment)
            vb_l = vb_m3 * 1000.0
            self.spin_volume.setValue(vb_l)
            self.spin_fb.setValue(fb)
            self.btn_warn.setVisible(True)
        except Exception as e:  # noqa: BLE001
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Auto-fill failed", str(e))

    # ── Pin / clear comparison ────────────────────────────────────────────

    def _pin_comparison(self):
        if self.canvas.line_spl is None:
            return
        freqs = self.canvas.line_spl.get_xdata()
        spl   = self.canvas.line_spl.get_ydata()
        exc   = self.canvas.line_exc.get_ydata()
        vel   = self.canvas.line_vel.get_ydata() if self.canvas.line_vel else None
        imp   = self.canvas.line_imp.get_ydata() if self.canvas.line_imp else None
        self.canvas.set_comparison(freqs, spl, exc, vel, imp)
        self._calculate()

    def _clear_comparison(self):
        self.canvas.clear_comparison()
        self._calculate()

    # ── Calculate ─────────────────────────────────────────────────────────

    def _calculate(self):
        self._on_box_type_changed()
        if not self._drivers or self.driver_combo.currentIndex() < 0:
            return
        idx = self.driver_combo.currentIndex()
        if idx >= len(self._drivers):
            return
        driver = self._drivers[idx]
        self.collect_state()
        st = get_state()

        vb      = self.spin_volume.value() / 1000.0      # litres → m³
        vb_rear = self.spin_volume_rear.value() / 1000.0
        fb      = self.spin_fb.value()
        power   = self.spin_power.value()
        n_drv   = int(self.spin_drv_count.value())
        wiring  = self.combo_wiring.currentText().lower()
        room    = self.chk_room_gain.isChecked()
        box     = st.box_type
        n_ports = int(self.spin_port_count.value())

        if st.port.shape == "round":
            single_area = math.pi * (st.port.diameter_mm / 2000.0) ** 2
        else:
            single_area = slot_port_area(
                st.port.slot_w_mm / 1000.0,
                st.port.slot_h_mm / 1000.0,
            )

        pr_fs  = self.spin_pr_fs.value()
        pr_vas = self.spin_pr_vas.value() / 1000.0   # litres → m³
        pr_qms = self.spin_pr_qms.value()
        pr_sd  = self.spin_pr_sd.value() / 10000.0   # cm² → m²

        worker = _SimWorker(
            self._run_sim,
            driver, vb, vb_rear, fb, power,
            n_drv, wiring, room, box,
            single_area, n_ports,
            pr_fs, pr_vas, pr_qms, pr_sd,
        )
        worker.result_ready.connect(self._on_result)
        worker.error.connect(lambda msg: print(f"[sim error] {msg}"))
        self._workers.append(worker)
        worker.finished.connect(
            lambda: self._workers.remove(worker) if worker in self._workers else None
        )
        worker.start()

    @staticmethod
    def _run_sim(driver, vb, vb_rear, fb, power,
                 n_drv, wiring, room, box,
                 single_area, n_ports,
                 pr_fs, pr_vas, pr_qms, pr_sd):
        freqs = np.logspace(np.log10(FREQ_MIN), np.log10(FREQ_MAX), 300)

        # Build effective driver (handles multi-driver scaling)
        eff = effective_driver_params(driver, n_drv, wiring)
        total_port_area = single_area * n_ports
        xmax_mm = eff.xmax * 1000.0

        if box == "sealed":
            spl = sealed_spl_array(eff, vb, freqs, input_power=power)
            if room:
                spl = apply_room_gain(freqs, spl)
            exc, _ = cone_excursion_array(eff, vb, None, freqs, input_power=power, box_type="sealed")
            imp = impedance_array(eff, vb, None, freqs, box_type="sealed")
            return ("sealed", freqs, spl, exc, xmax_mm, None, None, None, imp, None, None)

        elif box == "bp4":
            spl = bandpass_4th_spl_array(eff, vb_rear, vb, fb, freqs, input_power=power)
            if room:
                spl = apply_room_gain(freqs, spl)
            port_vel = port_air_velocity_array(
                eff, vb_rear, fb, single_area, n_ports, freqs,
                input_power=power, box_type="bp4", vf=vb,
            )
            exc, _ = cone_excursion_array(
                eff, vb_rear, fb, freqs, input_power=power, box_type="bp4", vf=vb
            )
            imp = impedance_array(eff, vb_rear, fb, freqs, box_type="bp4")
            eq_d = equivalent_diameter(single_area)
            chuff = chuffing_velocity_limit(eq_d, fb)
            comp  = compression_velocity_limit(eq_d, fb)
            return ("bp4", freqs, spl, exc, xmax_mm, port_vel, chuff, comp, imp, fb, None)

        elif box == "pr":
            spl = passive_radiator_spl_array(
                eff, pr_fs, pr_vas, pr_qms, vb, freqs, input_power=power
            )
            if room:
                spl = apply_room_gain(freqs, spl)
            exc, _ = cone_excursion_array(eff, vb, None, freqs, input_power=power, box_type="sealed")
            pr_exc = pr_excursion_array(eff, pr_sd, pr_qms, vb, pr_fs, freqs, exc)
            imp = impedance_array(eff, vb, pr_fs, freqs, box_type="pr")
            fb_eff = pr_fs * math.sqrt(1.0 + pr_vas / vb)
            return ("pr", freqs, spl, exc, xmax_mm, None, None, None, imp, fb_eff, pr_exc)

        else:  # vented
            spl = vented_spl_array(eff, vb, fb, freqs, input_power=power)
            if room:
                spl = apply_room_gain(freqs, spl)
            port_vel = port_air_velocity_array(
                eff, vb, fb, single_area, n_ports, freqs, input_power=power
            )
            exc, _ = cone_excursion_array(eff, vb, fb, freqs, input_power=power, box_type="vented")
            imp = impedance_array(eff, vb, fb, freqs, box_type="vented")
            eq_d  = equivalent_diameter(single_area)
            chuff = chuffing_velocity_limit(eq_d, fb)
            comp  = compression_velocity_limit(eq_d, fb)
            return ("vented", freqs, spl, exc, xmax_mm, port_vel, chuff, comp, imp, fb, None)

    def _on_result(self, result):
        (box_type, freqs, spl, exc, xmax_mm,
         port_vel, chuff, comp, imp, fb, pr_exc) = result

        self.canvas.plot(
            freqs, spl, exc, xmax_mm,
            port_velocity=port_vel,
            chuff_limit=chuff,
            comp_limit=comp,
            impedance=imp,
            fb=fb,
            box_type=box_type,
            pr_excursion=pr_exc,
        )

        # Results panel
        peak_spl    = float(np.nanmax(spl))
        mask_80_200 = (freqs >= 80) & (freqs <= 200)
        avg_spl     = float(np.mean(spl[mask_80_200])) if mask_80_200.any() else float("nan")

        def _f_at(target_db):
            ref = peak_spl + target_db
            below = np.where(spl <= ref)[0]
            if len(below) == 0:
                return None
            i = below[0]
            if i == 0:
                return freqs[0]
            f1, f2 = freqs[i - 1], freqs[i]
            s1, s2 = spl[i - 1],   spl[i]
            if s2 == s1:
                return f1
            return f1 + (ref - s1) * (f2 - f1) / (s2 - s1)

        def _fmt_f(val):
            return f"{val:.1f} Hz" if val is not None else "-"

        self._result_labels["F3"].setText(_fmt_f(_f_at(-3)))
        self._result_labels["F6"].setText(_fmt_f(_f_at(-6)))
        self._result_labels["F10"].setText(_fmt_f(_f_at(-10)))
        self._result_labels["Peak SPL"].setText(f"{peak_spl:.1f} dB")
        self._result_labels["Avg SPL (80-200 Hz)"].setText(f"{avg_spl:.1f} dB")
        self._result_labels["Max excursion"].setText(f"{float(np.nanmax(exc)):.2f} mm")

        if box_type in ("pr", "sealed"):
            suffix = "(PR)" if box_type == "pr" else "(sealed)"
            self._result_labels["Port length"].setText(f"N/A {suffix}")
            self._result_labels["Peak port vel."].setText(f"N/A {suffix}")
            self._result_labels["Chuff limit"].setText(f"N/A {suffix}")
        else:
            self._result_labels["Port length"].setText("-")
            if port_vel is not None:
                self._result_labels["Peak port vel."].setText(
                    f"{float(np.nanmax(port_vel)):.1f} m/s"
                )
            if chuff is not None:
                self._result_labels["Chuff limit"].setText(f"{chuff:.1f} m/s")

        if imp is not None and fb is not None:
            imp_at_fb = float(np.interp(fb, freqs, imp))
            self._result_labels["Impedance @ Fb"].setText(f"{imp_at_fb:.2f} \u03a9")
