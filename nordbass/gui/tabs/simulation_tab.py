"""
Simulation tab - driver selector, box params, calculate button,
results panel, and embedded matplotlib frequency-response charts.
Supports both round and slot (rectangular) ports.
"""
import math
import numpy as np

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QFrame,
)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QCursor

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.ticker as ticker

from ..theme import get_theme
from ..project_state import get_state
from ..scale import s, sf, font_size
from ..collapsible import CollapsibleSection
from ...core.ts_box import (
    cone_excursion_array,
    port_air_velocity_array,
    port_length_for_tuning,
    sealed_alignment_volume,
    sealed_params,
    sealed_spl_array,
    vented_alignment,
    vented_params,
    vented_spl_array,
    bandpass_4th_spl_array,
    passive_radiator_spl_array,
    effective_driver_params,
    impedance_array,
    apply_room_gain,
    find_f3,
)
from ...core.ports import (
    round_port_area,
    slot_port_area,
    chuffing_velocity_limit,
    compression_velocity_limit,
    equivalent_diameter,
)
from ...core.units import litre_to_m3, m3_to_litre
from ...data.database import list_drivers

FREQ_MIN   = 10.0
FREQ_MAX   = 500.0
FREQ_POINTS = 600

FREQ_TICKS = [10, 15, 20, 30, 40, 50, 60, 80, 100, 150, 200, 300, 400, 500]

# Whether the auto-fill warning dialog has been shown this session
_autofill_warned: bool = False


def _logfreqs():
    return np.logspace(math.log10(FREQ_MIN), math.log10(FREQ_MAX), FREQ_POINTS)


# ---------------------------------------------------------------------------
# Auto-fill warning dialog
# ---------------------------------------------------------------------------

class _AutoFillInfoDialog(QDialog):
    """One-time informational dialog shown before the first auto-fill."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Auto-fill from Alignment")
        self.setMinimumWidth(s(420))
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        layout = QVBoxLayout(self)
        layout.setSpacing(s(10))

        # Icon + title row
        title_row = QHBoxLayout()
        icon_lbl = QLabel("\u26a0\ufe0f")
        icon_lbl.setStyleSheet(f"font-size: {font_size(22)}; padding-right: 6px;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        title_lbl = QLabel("<b>Auto-fill uses theoretical alignment formulas</b>")
        title_lbl.setWordWrap(True)
        title_row.addWidget(icon_lbl)
        title_row.addWidget(title_lbl, stretch=1)
        layout.addLayout(title_row)

        # Body text
        body = QLabel(
            "This button calculates box volume and tuning frequency using "
            "Small\u2019s classic alignment tables (QB3, B4, SC4, SBB4). "
            "These are mathematically correct starting points \u2014 but they "
            "<b>do not account for</b>:<br><br>"
            "\u2022 &nbsp;Your available box space or port area<br>"
            "\u2022 &nbsp;Manufacturer\u2019s real-world recommendations<br>"
            "\u2022 &nbsp;Car cabin gain and room loading<br>"
            "\u2022 &nbsp;Port chuffing limits at high power<br><br>"
            "<b>For beginners:</b> Use the alignment result as a reference, "
            "then check the port velocity graph \u2014 if the purple line crosses "
            "the orange dashed line, your port is too small.<br><br>"
            "<b>For all users:</b> Always verify against the manufacturer\u2019s "
            "recommended box specifications before building."
        )
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setStyleSheet(f"font-size: {font_size(12)};")
        layout.addWidget(body)

        # "Don't show again" checkbox
        self.chk_hide = QCheckBox("Don\u2019t show this again this session")
        self.chk_hide.setStyleSheet(f"font-size: {font_size(11)}; color: gray;")
        layout.addWidget(self.chk_hide)

        # OK button
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)

    @property
    def suppress_future(self) -> bool:
        return self.chk_hide.isChecked()


# ---------------------------------------------------------------------------
# Plot canvas
# ---------------------------------------------------------------------------

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
        self.line_spl, = self.ax_spl.plot([], [], color="#2196F3", linewidth=1.6)
        self.line_exc, = self.ax_exc.plot([], [], color="#4CAF50", linewidth=1.6, label="Driver Xpeak")
        # PR Xpeak line — no label here; label is added dynamically only when PR mode is active
        self.line_pr_exc, = self.ax_exc.plot([], [], color="#FF9800", linewidth=1.2, linestyle="-.")
        self.line_vel, = self.ax_vel.plot([], [], color="#9C27B0", linewidth=1.6, label="Port Velocity")
        self.line_imp, = self.ax_imp.plot([], [], color="#FFD600", linewidth=1.6, label="Impedance")
        self.line_xmax = self.ax_exc.axhline(0, color="#F44336", linestyle="--", linewidth=1.2, visible=False)
        self.line_chuff, = self.ax_vel.plot([], [], color="#FF5722", linestyle="--", linewidth=1.2)
        self.line_comp, = self.ax_vel.plot([], [], color="#F44336", linestyle=":", linewidth=1.2)
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
        if pr_excursion is not None:
            self.line_pr_exc.set_data(freqs, pr_excursion)
            self.line_pr_exc.set_visible(True)
            self.line_pr_exc.set_label("PR Xpeak")
        else:
            self.line_pr_exc.set_data([], [])
            self.line_pr_exc.set_visible(False)
            self.line_pr_exc.set_label("_nolegend_")
        if port_velocity is not None:
            self.line_vel.set_data(freqs, port_velocity)
            self.line_vel.set_visible(True)
        else:
            self.line_vel.set_visible(False)
        if impedance is not None:
            self.line_imp.set_data(freqs, impedance)
            self.line_imp.set_visible(True)
            self.ax_imp.set_ylim(0, max(np.max(impedance)*1.1, 10))
        else:
            self.line_imp.set_visible(False)
        self.line_xmax.set_ydata([xmax_mm, xmax_mm])
        self.line_xmax.set_visible(True)
        self.line_xmax.set_label(f"Xmax {xmax_mm:.1f} mm")
        if chuff_limit is not None:
            self.line_chuff.set_data(freqs, chuff_limit)
            self.line_chuff.set_visible(True)
        else:
            self.line_chuff.set_visible(False)
        if comp_limit is not None:
            self.line_comp.set_data(freqs, comp_limit)
            self.line_comp.set_visible(True)
        else:
            self.line_comp.set_visible(False)
        for l in self.line_fb:
            l.remove()
        self.line_fb = []
        if fb:
            for ax in (self.ax_spl, self.ax_exc, self.ax_vel, self.ax_imp):
                l = ax.axvline(fb, color="#FF9800", linestyle=":", linewidth=1.2)
                self.line_fb.append(l)
            self.line_spl.set_label(f"SPL (Fb {fb:.1f} Hz)")
        else:
            self.line_spl.set_label("SPL")
        if self._comparison_data:
            cf, cs, ce, cv, ci = self._comparison_data
            self.line_comp_spl.set_data(cf, cs)
            self.line_comp_exc.set_data(cf, ce)
            if cv is not None:
                self.line_comp_vel.set_data(cf, cv)
                self.line_comp_vel.set_visible(True)
            else:
                self.line_comp_vel.set_visible(False)
            if ci is not None:
                self.line_comp_imp.set_data(cf, ci)
                self.line_comp_imp.set_visible(True)
            else:
                self.line_comp_imp.set_visible(False)
        else:
            for l in (self.line_comp_spl, self.line_comp_exc, self.line_comp_vel, self.line_comp_imp):
                l.set_visible(False)
        s_max = np.nanmax(spl)
        self.ax_spl.set_ylim(max(s_max-40, 60), s_max+5)
        e_mask = (freqs >= 20)
        e_max = np.nanmax(excursion[e_mask])
        if pr_excursion is not None:
            e_max = max(e_max, np.nanmax(pr_excursion[e_mask]))
        self.ax_exc.set_ylim(0, max(e_max*1.2, xmax_mm*1.2))
        if port_velocity is not None:
            v_max = np.nanmax(port_velocity[e_mask])
            self.ax_vel.set_ylim(0, max(v_max*1.2, 30))
        self.ax_spl.legend(fontsize=7, loc="lower right")
        self.ax_exc.legend(fontsize=7, loc="upper right")
        if port_velocity is not None:
            self.ax_vel.legend(fontsize=7, loc="upper right")
        if impedance is not None:
            self.ax_imp.legend(fontsize=7, loc="upper right")
        self.draw()


def _spinbox(mn, mx, val, suf, dec=0, step=None):
    sb = QDoubleSpinBox()
    sb.setRange(mn, mx); sb.setValue(val)
    sb.setSuffix(suf); sb.setDecimals(dec)
    if step: sb.setSingleStep(step)
    return sb


class SimulationTab(QWidget):
    def __init__(self):
        super().__init__()
        main_layout = QHBoxLayout(self)

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
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(2)
        left_scroll.setWidget(left)
        left_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        sec_drv   = CollapsibleSection("Driver", expanded=True)
        drv_inner = QWidget()
        drv_form  = QFormLayout(drv_inner)
        drv_form.setContentsMargins(0, 0, 0, 0)
        self.driver_combo = QComboBox()
        self.btn_refresh  = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self._load_drivers)
        self.spin_drv_count = _spinbox(1, 16, 1, "")
        self.combo_wiring   = QComboBox()
        self.combo_wiring.addItems(["Series", "Parallel", "Isobaric"])
        drv_form.addRow("Driver:", self.driver_combo)
        drv_form.addRow("Count:", self.spin_drv_count)
        drv_form.addRow("Wiring:", self.combo_wiring)
        drv_form.addRow(self.btn_refresh)
        sec_drv.set_content(drv_inner)
        left_layout.addWidget(sec_drv)

        sec_type    = CollapsibleSection("Box Type", expanded=True)
        type_inner  = QWidget()
        type_layout = QGridLayout(type_inner)
        type_layout.setContentsMargins(0, 0, 0, 0)
        self.radio_sealed = QRadioButton("Sealed")
        self.radio_vented = QRadioButton("Vented")
        self.radio_bp4    = QRadioButton("BP 4th")
        self.radio_pr     = QRadioButton("PR")
        self.radio_vented.setChecked(True)
        self.radio_sealed.toggled.connect(self._on_box_type_changed)
        self.radio_bp4.toggled.connect(self._on_box_type_changed)
        self.radio_pr.toggled.connect(self._on_box_type_changed)
        type_layout.addWidget(self.radio_sealed, 0, 0)
        type_layout.addWidget(self.radio_vented, 0, 1)
        type_layout.addWidget(self.radio_bp4,    1, 0)
        type_layout.addWidget(self.radio_pr,     1, 1)
        sec_type.set_content(type_inner)
        left_layout.addWidget(sec_type)

        sec_params  = CollapsibleSection("Box Parameters", expanded=True)
        param_inner = QWidget()
        self.param_form = QFormLayout(param_inner)
        self.param_form.setContentsMargins(0, 0, 0, 0)
        self.spin_volume     = _spinbox(1, 5000, 100, " L",  1)
        self.spin_volume_rear = _spinbox(1, 5000, 50, " L (rear)", 1)
        self.spin_fb         = _spinbox(10, 200,  30, " Hz", 1)
        self.spin_power      = _spinbox(0.1, 10000, 100, " W", 0)
        self.chk_room_gain   = QCheckBox("Simulate Room/Cabin Gain (40Hz)")
        self.chk_room_gain.toggled.connect(self._calculate)
        self.pr_widget = QWidget()
        pr_form = QFormLayout(self.pr_widget)
        pr_form.setContentsMargins(0, 0, 0, 0)
        self.spin_pr_fs = _spinbox(1, 100, 20, " Hz (PR Fs)")
        self.spin_pr_vas = _spinbox(1, 2000, 100, " L (PR Vas)")
        self.spin_pr_qms = _spinbox(1, 20, 5, " (PR Qms)")
        pr_form.addRow("PR Fs:", self.spin_pr_fs)
        pr_form.addRow("PR Vas:", self.spin_pr_vas)
        pr_form.addRow("PR Qms:", self.spin_pr_qms)
        self.combo_alignment = QComboBox()
        _alignments = [
            ("QB3",  "QB3 — Quasi-Butterworth 3rd order"),
            ("B4",   "B4 — Butterworth 4th order"),
            ("SC4",  "SC4 — Sub-Chebyshev 4th order"),
            ("SBB4", "SBB4 — Super Butterworth Bass 4th order"),
        ]
        for text, tip in _alignments:
            self.combo_alignment.addItem(text)
            self.combo_alignment.setItemData(
                self.combo_alignment.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        self.param_form.addRow("Net Volume:",    self.spin_volume)
        self.param_form.addRow("Rear Volume:",   self.spin_volume_rear)
        self.param_form.addRow("Tuning Fb:",     self.spin_fb)
        self.param_form.addRow("Alignment:",     self.combo_alignment)
        self.param_form.addRow(self.pr_widget)
        self.param_form.addRow("Input power:",   self.spin_power)
        self.param_form.addRow(self.chk_room_gain)
        sec_params.set_content(param_inner)
        left_layout.addWidget(sec_params)

        sec_port  = CollapsibleSection("Port Configuration", expanded=True)
        port_inner = QWidget()
        port_form  = QFormLayout(port_inner)
        port_form.setContentsMargins(0, 0, 0, 0)
        self.combo_port_shape = QComboBox()
        self.combo_port_shape.addItems(["Round", "Slot (rectangular)"])
        self.combo_port_shape.currentIndexChanged.connect(self._on_port_shape_changed)
        port_form.addRow("Shape:", self.combo_port_shape)
        self.spin_port_count = _spinbox(1, 8, 1, "")
        port_form.addRow("# Ports:", self.spin_port_count)
        self.round_widget = QWidget()
        rf = QFormLayout(self.round_widget)
        rf.setContentsMargins(0, 0, 0, 0)
        self.spin_port_diam = _spinbox(10, 500, 75, " mm")
        rf.addRow("Diameter:", self.spin_port_diam)
        self.slot_widget = QWidget()
        sf_w = QFormLayout(self.slot_widget)
        sf_w.setContentsMargins(0, 0, 0, 0)
        self.spin_slot_w = _spinbox(10, 800, 100, " mm")
        self.spin_slot_h = _spinbox(10, 800,  50, " mm")
        self.lbl_eq_diam = QLabel("Eq. diam: —")
        self.lbl_eq_diam.setStyleSheet(f"color:gray;font-size:{font_size(11)}")
        self.spin_slot_w.valueChanged.connect(self._update_eq_diam)
        self.spin_slot_h.valueChanged.connect(self._update_eq_diam)
        sf_w.addRow("Width:",  self.spin_slot_w)
        sf_w.addRow("Height:", self.spin_slot_h)
        sf_w.addRow(self.lbl_eq_diam)
        self.port_stack = QStackedWidget()
        self.port_stack.addWidget(self.round_widget)
        self.port_stack.addWidget(self.slot_widget)
        port_form.addRow(self.port_stack)
        sec_port.set_content(port_inner)
        left_layout.addWidget(sec_port)

        # --- Auto-fill button row with compact warning icon ---
        auto_row = QHBoxLayout()
        auto_row.setSpacing(s(4))
        self.btn_auto = QPushButton("\u2728  Auto-fill from alignment")
        self.btn_auto.setToolTip(
            "<b>Auto-fill from Alignment</b><br><br>"
            "Calculates a theoretical starting volume and tuning frequency "
            "using Small\u2019s alignment tables (QB3, B4, SC4, SBB4).<br><br>"
            "<b>\u26a0\ufe0f Important:</b> This is a math-only estimate. "
            "It does <u>not</u> check port area, available space, or "
            "manufacturer recommendations. Real drivers often need a larger "
            "box and lower tuning than the alignment formula suggests.<br><br>"
            "Always verify the port velocity graph and compare against "
            "the driver manufacturer\u2019s box specifications."
        )
        self.btn_auto.clicked.connect(self._auto_fill)

        # Small warning triangle button — hover shows tooltip, click opens full dialog
        self.btn_warn = QPushButton("\u26a0")
        self.btn_warn.setFixedSize(s(26), s(26))
        self.btn_warn.setToolTip(
            "<b>Starting point only</b><br>"
            "Verify port velocity and check manufacturer specs before building.<br>"
            "<i>Click for full details.</i>"
        )
        self.btn_warn.setStyleSheet(
            f"QPushButton {{ "
            f"  color: #B8860B; font-size: {font_size(14)}; "
            f"  background: transparent; border: none; padding: 0; "
            f"}} "
            f"QPushButton:hover {{ color: #DAA520; }}"
        )
        self.btn_warn.setVisible(False)  # shown after first auto-fill use
        self.btn_warn.clicked.connect(self._show_warn_dialog)

        auto_row.addWidget(self.btn_auto, stretch=1)
        auto_row.addWidget(self.btn_warn)

        self.btn_calc = QPushButton("  Calculate")
        self.btn_calc.setStyleSheet(f"font-weight:bold;padding:{s(6)}px")
        self.btn_calc.clicked.connect(self._calculate)
        left_layout.addLayout(auto_row)
        left_layout.addWidget(self.btn_calc)

        sec_results = CollapsibleSection("Results", expanded=True)
        res_inner   = QWidget()
        res_layout  = QGridLayout(res_inner)
        res_layout.setContentsMargins(0, 0, 0, 0)
        self._result_labels = {}
        for i, key in enumerate(["F3", "Fb / Fc", "Qtc", "SPL 1W/1m", "EBP", "Port length"]):
            lbl = QLabel("-")
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            res_layout.addWidget(QLabel(key + ":"), i, 0)
            res_layout.addWidget(lbl, i, 1)
            self._result_labels[key] = lbl
        sec_results.set_content(res_inner)
        left_layout.addWidget(sec_results)

        comp_box = QHBoxLayout()
        self.btn_pin = QPushButton("Pin Comparison")
        self.btn_clear_comp = QPushButton("Clear")
        self.btn_pin.clicked.connect(self._pin_comparison)
        self.btn_clear_comp.clicked.connect(self._clear_comparison)
        comp_box.addWidget(self.btn_pin)
        comp_box.addWidget(self.btn_clear_comp)
        left_layout.addLayout(comp_box)
        left_layout.addStretch()
        main_layout.addWidget(left_scroll)

        # --- Right panel: hamburger toggle + graph toolbar + canvas ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.canvas = PlotCanvas()
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.toolbar.setStyleSheet("background-color: transparent; border: none;")

        # Hamburger button row — sits in the same position as the toolbar
        toolbar_row = QHBoxLayout()
        toolbar_row.setContentsMargins(s(2), 0, s(2), 0)
        toolbar_row.setSpacing(0)

        self.btn_hamburger = QPushButton("\u2630")  # ☰
        self.btn_hamburger.setFixedSize(s(28), s(28))
        self.btn_hamburger.setToolTip("Show / hide graph tools")
        self.btn_hamburger.setStyleSheet(
            f"QPushButton {{ "
            f"  font-size: {font_size(14)}; background: transparent; "
            f"  border: 1px solid transparent; border-radius: {s(4)}px; padding: 0; "
            f"}} "
            f"QPushButton:hover {{ border-color: gray; }}"
        )
        self.btn_hamburger.clicked.connect(self._toggle_toolbar)
        toolbar_row.addWidget(self.btn_hamburger)
        toolbar_row.addStretch()

        # Toolbar starts hidden; hamburger reveals it
        self.toolbar.setVisible(False)

        right_layout.addLayout(toolbar_row)
        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas, stretch=1)
        main_layout.addWidget(right_panel, stretch=1)

        for w in (self.spin_drv_count, self.spin_volume, self.spin_volume_rear,
                  self.spin_fb, self.spin_power, self.spin_port_count,
                  self.spin_port_diam, self.spin_slot_w, self.spin_slot_h,
                  self.spin_pr_fs, self.spin_pr_vas, self.spin_pr_qms):
            w.valueChanged.connect(self._calculate)
        for w in (self.driver_combo, self.combo_wiring, self.combo_alignment, self.combo_port_shape):
            w.currentIndexChanged.connect(self._calculate)
        self.radio_sealed.toggled.connect(self._calculate)
        self.radio_bp4.toggled.connect(self._calculate)
        self.radio_pr.toggled.connect(self._calculate)

        self._drivers = []
        self._load_drivers()
        self._on_box_type_changed()
        self._on_port_shape_changed(0)

    # ── Hamburger toggle ──────────────────────────────────────────────────

    def _toggle_toolbar(self):
        visible = not self.toolbar.isVisible()
        self.toolbar.setVisible(visible)

    # ── Warning icon helpers ──────────────────────────────────────────────

    def _show_warn_dialog(self):
        dlg = _AutoFillInfoDialog(self)
        dlg.exec()

    # ── State helpers ─────────────────────────────────────────────────────

    def collect_state(self):
        st = get_state()
        if self.radio_sealed.isChecked(): st.box_type = "sealed"
        elif self.radio_bp4.isChecked():  st.box_type = "bp4"
        elif self.radio_pr.isChecked():   st.box_type = "pr"
        else:                             st.box_type = "vented"
        st.volume_l      = self.spin_volume.value()
        st.volume_rear   = self.spin_volume_rear.value()
        st.fb_hz         = self.spin_fb.value()
        st.input_power_w = self.spin_power.value()
        st.alignment     = self.combo_alignment.currentText()
        st.driver_count  = int(self.spin_drv_count.value())
        st.driver_wiring = self.combo_wiring.currentText().lower()
        st.room_gain     = self.chk_room_gain.isChecked()
        st.flare.pr_fs = self.spin_pr_fs.value()
        st.flare.pr_vas = self.spin_pr_vas.value()
        st.flare.pr_qms = self.spin_pr_qms.value()
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
        self.spin_volume_rear.setValue(getattr(st, "volume_rear", 50.0))
        self.spin_fb.setValue(st.fb_hz)
        self.spin_power.setValue(st.input_power_w)
        self.spin_drv_count.setValue(st.driver_count)
        self.chk_room_gain.setChecked(st.room_gain)
        self.spin_pr_fs.setValue(getattr(st.flare, "pr_fs", 20.0))
        self.spin_pr_vas.setValue(getattr(st.flare, "pr_vas", 100.0))
        self.spin_pr_qms.setValue(getattr(st.flare, "pr_qms", 5.0))
        idx_wiring = self.combo_wiring.findText(st.driver_wiring.capitalize())
        if idx_wiring >= 0:
            self.combo_wiring.setCurrentIndex(idx_wiring)
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
        self.btn_auto.setEnabled(vented)
        self.spin_volume_rear.setVisible(bp4)
        if self.param_form:
            lbl = self.param_form.labelForField(self.spin_volume_rear)
            if lbl: lbl.setVisible(bp4)
        self.pr_widget.setVisible(pr)
        for w in (self.spin_port_count, self.combo_port_shape,
                  self.round_widget, self.slot_widget):
            w.setEnabled(vented or bp4)
        self._calculate()

    def _load_drivers(self):
        self._drivers = list_drivers()
        self.driver_combo.clear()
        for d in self._drivers:
            self.driver_combo.addItem(
                f"{d.name} ({d.manufacturer})" if d.manufacturer else d.name)
        if not self._drivers:
            self.driver_combo.addItem("- no drivers in database -")
        st = get_state()
        if st.driver_id:
            for i, d in enumerate(self._drivers):
                if d.id == st.driver_id:
                    self.driver_combo.setCurrentIndex(i)
                    break

    def _get_driver(self):
        idx = self.driver_combo.currentIndex()
        if idx < 0 or idx >= len(self._drivers):
            return None
        return self._drivers[idx]

    def _auto_fill(self):
        global _autofill_warned
        driver = self._get_driver()
        if not driver:
            return

        # Show one-time info dialog if not yet suppressed this session
        if not _autofill_warned:
            dlg = _AutoFillInfoDialog(self)
            dlg.exec()
            if dlg.suppress_future:
                _autofill_warned = True

        vb, fb = vented_alignment(driver, self.combo_alignment.currentText())
        self.spin_volume.setValue(m3_to_litre(vb))
        self.spin_fb.setValue(round(fb, 1))

        # Reveal warning icon after first use
        self.btn_warn.setVisible(True)

    def _get_port_area_and_eq_diam(self):
        if self.combo_port_shape.currentIndex() == 0:
            d    = self.spin_port_diam.value() / 1000.0
            area = round_port_area(d)
            eq_d = d
        else:
            w    = self.spin_slot_w.value() / 1000.0
            h    = self.spin_slot_h.value() / 1000.0
            area = slot_port_area(w, h)
            eq_d = equivalent_diameter(area)
        return area, eq_d

    def _pin_comparison(self):
        if hasattr(self, "_last_run_data"):
            self.canvas.set_comparison(*self._last_run_data)
            self._calculate()

    def _clear_comparison(self):
        self.canvas.clear_comparison()
        self._calculate()

    def _calculate(self):
        base_driver = self._get_driver()
        if not base_driver:
            return
        driver = effective_driver_params(
            base_driver,
            count=int(self.spin_drv_count.value()),
            wiring=self.combo_wiring.currentText().lower()
        )
        freqs     = _logfreqs()
        vb        = litre_to_m3(self.spin_volume.value())
        power     = self.spin_power.value()
        num_ports = int(self.spin_port_count.value())
        port_area, eq_diam = self._get_port_area_and_eq_diam()
        st = get_state()
        st.driver_id   = base_driver.id
        st.driver_name = f"{base_driver.name} ({base_driver.manufacturer})" if base_driver.manufacturer else base_driver.name
        st.volume_l    = self.spin_volume.value()
        if self.radio_sealed.isChecked(): st.box_type = "sealed"
        elif self.radio_bp4.isChecked():  st.box_type = "bp4"
        elif self.radio_pr.isChecked():   st.box_type = "pr"
        else:                             st.box_type = "vented"
        st.port.shape  = "round" if self.combo_port_shape.currentIndex() == 0 else "slot"
        st.port.count  = int(self.spin_port_count.value())
        if st.port.shape == "round":
            st.port.diameter_mm = self.spin_port_diam.value()
            st.port.eq_diam_m   = self.spin_port_diam.value() / 1000.0
        else:
            st.port.slot_w_mm = self.spin_slot_w.value()
            st.port.slot_h_mm = self.spin_slot_h.value()
            st.port.eq_diam_m = eq_diam
        ebp = driver.fs / driver.qes if driver.qes else 0
        self._result_labels["EBP"].setText(f"{ebp:.1f}")
        if driver.qes > 0:
            eta_0 = (4 * math.pi**2 * driver.fs**3 * driver.vas) / (343.0**3 * driver.qes)
            spl_1w1m = 10 * math.log10(max(eta_0, 1e-30)) + 112.1
            self._result_labels["SPL 1W/1m"].setText(f"{spl_1w1m:.1f} dB")
        else:
            self._result_labels["SPL 1W/1m"].setText("-")

        if st.box_type == "sealed":
            p   = sealed_params(driver, vb)
            spl = sealed_spl_array(driver, vb, freqs, input_power=power)
            if self.chk_room_gain.isChecked():
                spl = apply_room_gain(freqs, spl, 40.0)
            exc, xmax_mm = cone_excursion_array(driver, vb, None, freqs, power, "sealed")
            imp = impedance_array(driver, vb, None, freqs, "sealed")
            st.port.length_m = 0.0
            st.fb_hz = 0.0
            f3 = find_f3(freqs, spl)
            self._result_labels["F3"].setText(f"{f3:.1f} Hz")
            self._result_labels["Fb / Fc"].setText(f"Fc = {p['fc']:.1f} Hz")
            self._result_labels["Qtc"].setText(f"{p['qtc']:.3f}")
            self._result_labels["Port length"].setText("N/A (sealed)")
            self._last_run_data = (freqs, spl, exc, None, imp)
            self.canvas.plot(freqs, spl, exc, xmax_mm, impedance=imp, box_type="sealed")

        elif st.box_type == "bp4":
            vr = litre_to_m3(self.spin_volume_rear.value())
            vf = vb
            fb = self.spin_fb.value()
            spl = bandpass_4th_spl_array(driver, vr, vf, fb, freqs, input_power=power)
            if self.chk_room_gain.isChecked():
                spl = apply_room_gain(freqs, spl, 40.0)
            exc, xmax_mm = cone_excursion_array(driver, vr, fb, freqs, power, "bp4", vf=vf)
            port_vel = port_air_velocity_array(driver, vf, fb, port_area, num_ports, freqs, power, box_type="bp4")
            imp = impedance_array(driver, vf, fb, freqs, "bp4")
            port_len = port_length_for_tuning(fb, vf, port_area, num_ports)
            st.port.length_m = port_len
            st.fb_hz = fb
            f3 = find_f3(freqs, spl)
            self._result_labels["F3"].setText(f"{f3:.1f} Hz")
            self._result_labels["Fb / Fc"].setText(f"Fb = {fb:.1f} Hz")
            self._result_labels["Qtc"].setText("-")
            if self.combo_port_shape.currentIndex() == 0:
                port_desc = f"{port_len*1000:.0f} mm (\u00f8{eq_diam*1000:.0f} \u00d7 {num_ports})"
            else:
                port_desc = f"{port_len*1000:.0f} mm ({self.spin_slot_w.value():.0f}\u00d7{self.spin_slot_h.value():.0f} \u00d7 {num_ports})"
            self._result_labels["Port length"].setText(port_desc)
            self._last_run_data = (freqs, spl, exc, port_vel, imp)
            self.canvas.plot(freqs, spl, exc, xmax_mm, port_velocity=port_vel, impedance=imp, fb=fb, box_type="bp4")

        elif st.box_type == "pr":
            pr_fs = self.spin_pr_fs.value()
            pr_vas = litre_to_m3(self.spin_pr_vas.value())
            pr_qms = self.spin_pr_qms.value()
            spl = passive_radiator_spl_array(driver, pr_fs, pr_vas, pr_qms, vb, freqs, input_power=power)
            if self.chk_room_gain.isChecked():
                spl = apply_room_gain(freqs, spl, 40.0)
            fb_eff = pr_fs * math.sqrt(1 + pr_vas / vb)
            exc, xmax_mm = cone_excursion_array(driver, vb, fb_eff, freqs, power, "pr")
            imp = impedance_array(driver, vb, fb_eff, freqs, "pr")
            from ...core.ts_box import pr_excursion_array
            pr_exc = pr_excursion_array(driver, driver.sd, vb, fb_eff, freqs, exc)
            f3 = find_f3(freqs, spl)
            self._result_labels["F3"].setText(f"{f3:.1f} Hz")
            self._result_labels["Fb / Fc"].setText(f"Fb = {fb_eff:.1f} Hz")
            self._result_labels["Qtc"].setText("-")
            self._result_labels["Port length"].setText("N/A (PR)")
            self._last_run_data = (freqs, spl, exc, None, imp)
            self.canvas.plot(freqs, spl, exc, xmax_mm, impedance=imp, fb=fb_eff, box_type="pr", pr_excursion=pr_exc)

        else:  # vented
            fb  = self.spin_fb.value()
            spl = vented_spl_array(driver, vb, fb, freqs, input_power=power)
            if self.chk_room_gain.isChecked():
                spl = apply_room_gain(freqs, spl, 40.0)
            exc, xmax_mm = cone_excursion_array(driver, vb, fb, freqs, power, "vented")
            port_vel = port_air_velocity_array(
                driver, vb, fb, port_area, num_ports, freqs, input_power=power, box_type="vented")
            imp = impedance_array(driver, vb, fb, freqs, "vented")
            chuff = np.array([chuffing_velocity_limit(eq_diam, f, masking=0.15) for f in freqs])
            comp  = np.array([compression_velocity_limit(eq_diam, f) for f in freqs])
            port_len = port_length_for_tuning(fb, vb, port_area, num_ports)
            st.port.length_m = port_len
            st.fb_hz         = fb
            st.alignment     = self.combo_alignment.currentText()
            f3 = find_f3(freqs, spl)
            self._result_labels["F3"].setText(f"{f3:.1f} Hz")
            self._result_labels["Fb / Fc"].setText(f"Fb = {fb:.1f} Hz")
            self._result_labels["Qtc"].setText("-")
            if self.combo_port_shape.currentIndex() == 0:
                port_desc = (f"{port_len*1000:.0f} mm  (\u00f8{eq_diam*1000:.0f} \u00d7 {num_ports})")
            else:
                port_desc = (f"{port_len*1000:.0f} mm  ({self.spin_slot_w.value():.0f}\u00d7"
                             f"{self.spin_slot_h.value():.0f} mm \u00d7 {num_ports})")
            self._result_labels["Port length"].setText(port_desc)
            self._last_run_data = (freqs, spl, exc, port_vel, imp)
            self.canvas.plot(
                freqs, spl, exc, xmax_mm,
                port_velocity=port_vel,
                chuff_limit=chuff,
                comp_limit=comp,
                impedance=imp,
                fb=fb,
                box_type="vented",
            )

        st.notify()
