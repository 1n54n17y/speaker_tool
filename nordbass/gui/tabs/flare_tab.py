"""
Flare analysis tab - supports both round and slot (rectangular) ports.
Uses equivalent diameter for chuffing/compression limit calculations.
"""
import math
import numpy as np

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtCore import Qt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.ticker as ticker

from ...core.flares import simple_mode, cruise_control
from ...core.ports import (
    round_port_area,
    slot_port_area,
    equivalent_diameter,
)
from ...core.units import mm_to_m, m_to_mm
from ..theme import get_theme
from ..scale import s, sf, font_size
from ..collapsible import CollapsibleSection


def _spinbox(min_val, max_val, default, suffix, decimals=0, step=None):
    sb = QDoubleSpinBox()
    sb.setRange(min_val, max_val)
    sb.setValue(default)
    sb.setSuffix(suffix)
    sb.setDecimals(decimals)
    if step is not None:
        sb.setSingleStep(step)
    return sb


class FlareCanvas(FigureCanvas):
    """Two-panel plot: chuffing limit and compression limit vs frequency."""

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(sf(6), sf(4)), tight_layout=True)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._last_plot_args = None
        self._apply_mpl_theme()
        self._build_axes()
        get_theme().register(self._on_theme_changed)

    def _apply_mpl_theme(self):
        p = get_theme().palette
        self.fig.set_facecolor(p["mpl_bg"])

    def _on_theme_changed(self, _name):
        self._apply_mpl_theme()
        if self._last_plot_args:
            # _last_plot_args may have 5 or 6 elements depending on version
            self.plot(*self._last_plot_args)
        else:
            self._build_axes()
            self.draw()

    def _build_axes(self):
        p = get_theme().palette
        self.fig.clear()
        self.fig.set_facecolor(p["mpl_bg"])
        self.ax = self.fig.subplots(1, 1)
        self.ax.set_facecolor(p["mpl_axes_bg"])
        self.ax.set_xscale("log")
        self.ax.xaxis.set_major_formatter(
            ticker.FuncFormatter(lambda x, _: f"{int(x)}"))
        self.ax.xaxis.set_minor_formatter(ticker.NullFormatter())
        self.ax.grid(True, which="both", linestyle="--", alpha=0.4,
                     color=p["mpl_grid"])
        self.ax.set_xlabel("Frequency (Hz)", color=p["mpl_text"])
        self.ax.set_ylabel("Velocity limit (m/s)", color=p["mpl_text"])
        self.ax.set_title("Port Velocity Limits vs Frequency", color=p["mpl_text"])
        self.ax.tick_params(colors=p["mpl_text"])
        for spine in self.ax.spines.values():
            spine.set_edgecolor(p["mpl_spine"])
        self.fig.canvas.draw()

    def plot(self, freqs, chuff, comp, eq_diam_mm, flare_mm,
             new_velocity=None):
        self._last_plot_args = (freqs, chuff, comp, eq_diam_mm,
                                flare_mm, new_velocity)
        p = get_theme().palette
        self._build_axes()
        self.ax.plot(freqs, chuff, color="#FF5722", linewidth=1.8,
                     label=f"Chuffing limit (eq. {eq_diam_mm:.1f} mm, flare {flare_mm:.0f} mm)")
        self.ax.plot(freqs, comp, color="#F44336", linewidth=1.8,
                     linestyle="--", label="Compression limit")

        # New velocity line from Cruise Control
        if new_velocity is not None and new_velocity > 0:
            # Colour-code: green if below chuffing at Fb, orange/red if above
            min_chuff = float(chuff.min())
            line_color = (
                "#4CAF50" if new_velocity < min_chuff * 0.8
                else "#FF9800" if new_velocity < min_chuff
                else "#E53935"
            )
            self.ax.axhline(
                y=new_velocity, color=line_color,
                linewidth=1.6, linestyle="-.",
                label=f"New velocity ({new_velocity:.2f} m/s)")

        self.ax.legend(fontsize=8, facecolor=p["mpl_axes_bg"],
                       labelcolor=p["mpl_text"], edgecolor=p["mpl_spine"])
        self.ax.set_xlim(freqs[0], freqs[-1])
        self.ax.set_ylim(bottom=0)
        self.fig.canvas.draw()


class FlareTab(QWidget):
    def __init__(self):
        super().__init__()
        main_layout = QHBoxLayout(self)

        # ── Left panel: scrollable ───────────────────────────────────────
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

        # --- Port shape + dimensions ---
        sec_port  = CollapsibleSection("Port Shape", expanded=True)
        port_inner = QWidget()
        port_form = QFormLayout(port_inner)
        port_form.setContentsMargins(0, 0, 0, 0)

        self.combo_shape = QComboBox()
        self.combo_shape.addItems(["Round", "Slot (rectangular)"])
        self.combo_shape.currentIndexChanged.connect(self._on_shape_changed)
        port_form.addRow("Shape:", self.combo_shape)

        # Round inputs
        self.round_widget = QWidget()
        round_form = QFormLayout(self.round_widget)
        round_form.setContentsMargins(0, 0, 0, 0)
        self.spin_diameter = _spinbox(10, 500, 75, " mm")
        self.spin_diameter.valueChanged.connect(self._update_eq_label)
        round_form.addRow("Diameter:", self.spin_diameter)

        # Slot inputs
        self.slot_widget = QWidget()
        slot_form = QFormLayout(self.slot_widget)
        slot_form.setContentsMargins(0, 0, 0, 0)
        self.spin_slot_w = _spinbox(10, 800, 100, " mm")
        self.spin_slot_h = _spinbox(10, 800,  50, " mm")
        self.spin_slot_w.valueChanged.connect(self._update_eq_label)
        self.spin_slot_h.valueChanged.connect(self._update_eq_label)
        slot_form.addRow("Width:",  self.spin_slot_w)
        slot_form.addRow("Height:", self.spin_slot_h)

        self.lbl_eq = QLabel("Eq. diameter: —")
        self.lbl_eq.setStyleSheet(f"color: gray; font-size: {font_size(11)};")
        slot_form.addRow(self.lbl_eq)

        self.port_stack = QStackedWidget()
        self.port_stack.addWidget(self.round_widget)
        self.port_stack.addWidget(self.slot_widget)
        port_form.addRow(self.port_stack)

        sec_port.set_content(port_inner)
        left_layout.addWidget(sec_port)

        # --- Flare + masking ---
        sec_flare  = CollapsibleSection("Flare Parameters", expanded=True)
        flare_inner = QWidget()
        flare_form = QFormLayout(flare_inner)
        flare_form.setContentsMargins(0, 0, 0, 0)

        self.spin_flare   = _spinbox(0, 300, 0,    " mm")
        self.spin_masking = _spinbox(0, 0.5, 0.15, "",   decimals=2, step=0.05)
        self.spin_num_ports = QSpinBox()
        self.spin_num_ports.setRange(1, 8)
        self.spin_num_ports.setValue(1)
        self.chk_both_sides = QCheckBox("Flare both ends of port")
        self.chk_both_sides.setChecked(False)
        self.chk_both_sides.setToolTip(
            "When ticked, the flare radius is applied to both the inlet "
            "and outlet of the port tube, doubling the effective end correction "
            "and raising the chuffing threshold further.")

        flare_form.addRow("Flare radius:", self.spin_flare)
        flare_form.addRow("",              self.chk_both_sides)
        flare_form.addRow("Masking (0=none, 0.15=music, 0.30=HT):",
                          self.spin_masking)
        flare_form.addRow("# Ports:", self.spin_num_ports)
        sec_flare.set_content(flare_inner)
        left_layout.addWidget(sec_flare)

        # Analyse button + verdict
        self.btn_calc = QPushButton("  Analyse")
        self.btn_calc.setStyleSheet(f"font-weight: bold; padding: {s(6)}px;")
        self.btn_calc.clicked.connect(self._calculate)
        left_layout.addWidget(self.btn_calc)

        self.lbl_verdict = QLabel("")
        self.lbl_verdict.setWordWrap(True)
        left_layout.addWidget(self.lbl_verdict)

        # Results table (collapsible)
        sec_results = CollapsibleSection("Frequency Table", expanded=False)
        self.result_table = QTableWidget(0, 3)
        self.result_table.setHorizontalHeaderLabels(
            ["Freq (Hz)", "Chuffing limit (m/s)", "Compression limit (m/s)"])
        self.result_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        sec_results.set_content(self.result_table)
        left_layout.addWidget(sec_results)

        # --- Cruise control ---
        sec_cc   = CollapsibleSection("Cruise Control — port resize", expanded=True)
        cc_inner = QWidget()
        cc_form  = QFormLayout(cc_inner)
        cc_form.setContentsMargins(0, 0, 0, 0)

        self.spin_orig_d   = _spinbox(10, 500, 75,  " mm")
        self.spin_orig_vel = _spinbox(0, 200,  15,  " m/s", decimals=1)
        self.spin_new_d    = _spinbox(10, 500, 100, " mm")
        self.spin_new_n    = QSpinBox()
        self.spin_new_n.setRange(1, 8)
        self.spin_new_n.setValue(1)
        self.lbl_cruise    = QLabel("—")

        self.btn_cruise = QPushButton("Calculate new velocity")
        self.btn_cruise.clicked.connect(self._cruise)

        cc_form.addRow("Original diameter:", self.spin_orig_d)
        cc_form.addRow("Velocity at Fb:",    self.spin_orig_vel)
        cc_form.addRow("New diameter:",      self.spin_new_d)
        cc_form.addRow("New # ports:",       self.spin_new_n)
        cc_form.addRow(self.btn_cruise)
        cc_form.addRow("New velocity:",      self.lbl_cruise)
        sec_cc.set_content(cc_inner)
        left_layout.addWidget(sec_cc)

        left_layout.addStretch()
        main_layout.addWidget(left_scroll, stretch=40)

        # ── Right panel: chart ────────────────────────────────────────────
        self.canvas = FlareCanvas()
        main_layout.addWidget(self.canvas, stretch=60)

        # Init
        self._on_shape_changed(0)

    # ── Helpers ────────────────────────────────────────────────────────────

    def collect_state(self):
        """Read all widget values into ProjectState (called before every save)."""
        from ..project_state import get_state
        fl = get_state().flare
        fl.port_shape  = "round" if self.combo_shape.currentIndex() == 0 else "slot"
        fl.diameter_mm = self.spin_diameter.value()
        fl.slot_w_mm   = self.spin_slot_w.value()
        fl.slot_h_mm   = self.spin_slot_h.value()
        fl.flare_mm    = self.spin_flare.value()
        fl.masking     = self.spin_masking.value()

    def reset_ui(self):
        """Reset all widgets to defaults (called on New Project / Load Project)."""
        from ..project_state import get_state
        fl = get_state().flare
        shape_idx = 0 if fl.port_shape == "round" else 1
        self.combo_shape.setCurrentIndex(shape_idx)
        self.spin_diameter.setValue(fl.diameter_mm)
        self.spin_slot_w.setValue(fl.slot_w_mm)
        self.spin_slot_h.setValue(fl.slot_h_mm)
        self.spin_flare.setValue(fl.flare_mm)
        self.spin_masking.setValue(fl.masking)
        self.lbl_cruise.setText("—")
        self.lbl_verdict.setText("")
        self.result_table.setRowCount(0)
        self.canvas._build_axes()
        self.canvas.draw()

    def _on_shape_changed(self, index):
        self.port_stack.setCurrentIndex(index)
        self._update_eq_label()

    def _update_eq_label(self):
        if self.combo_shape.currentIndex() == 1:
            w = self.spin_slot_w.value() / 1000.0
            h = self.spin_slot_h.value() / 1000.0
            eq_d = equivalent_diameter(slot_port_area(w, h)) * 1000.0
            self.lbl_eq.setText(f"Eq. diameter: {eq_d:.1f} mm")

    def _get_eq_diam_m(self):
        """Return equivalent round diameter in metres for current shape."""
        if self.combo_shape.currentIndex() == 0:
            return self.spin_diameter.value() / 1000.0
        else:
            w = self.spin_slot_w.value() / 1000.0
            h = self.spin_slot_h.value() / 1000.0
            return equivalent_diameter(slot_port_area(w, h))

    # ── Analyse ────────────────────────────────────────────────────────────

    def _calculate(self):
        eq_diam    = self._get_eq_diam_m()
        flare_r    = self.spin_flare.value() / 1000.0
        # Both-sides: doubles the effective flare contribution
        eff_flare  = flare_r * 2 if self.chk_both_sides.isChecked() else flare_r
        masking    = self.spin_masking.value()

        freqs = np.array([20, 25, 30, 40, 50, 60, 80, 100, 150, 200],
                         dtype=float)
        result = simple_mode(eq_diam, eff_flare, freqs, masking)

        # Verdict label with colour hint
        verdict = result["verdict"]
        if "noise free" in verdict.lower():
            color = "green"
        elif "risk" in verdict.lower():
            color = "orange"
        else:
            color = "red"

        shape_desc = (
            f"Round  {eq_diam*1000:.0f} mm"
            if self.combo_shape.currentIndex() == 0
            else f"Slot  {self.spin_slot_w.value():.0f} x "
                 f"{self.spin_slot_h.value():.0f} mm  "
                 f"(eq. {eq_diam*1000:.1f} mm)"
        )
        self.lbl_verdict.setText(
            f"<b>Port:</b> {shape_desc}<br>"
            f"<b>Verdict:</b> <span style='color:{color}'>{verdict}</span><br>"
            f"<b>Effective diameter (with flare):</b> "
            f"{result['effective_diameter']*1000:.1f} mm"
        )

        # Table
        self.result_table.setRowCount(len(freqs))
        for i, f in enumerate(freqs):
            self.result_table.setItem(
                i, 0, QTableWidgetItem(f"{f:.0f}"))
            self.result_table.setItem(
                i, 1, QTableWidgetItem(f"{result['chuffing_limit'][i]:.2f}"))
            self.result_table.setItem(
                i, 2, QTableWidgetItem(f"{result['compression_limit'][i]:.2f}"))

        # Chart — preserve current cruise velocity line if one exists
        try:
            existing_vel = float(self.lbl_cruise.text().split()[0])
        except (ValueError, IndexError, AttributeError):
            existing_vel = None

        plot_freqs  = np.linspace(10, 250, 300)
        plot_result = simple_mode(eq_diam, eff_flare, plot_freqs, masking)
        self.canvas.plot(
            plot_freqs,
            plot_result["chuffing_limit"],
            plot_result["compression_limit"],
            eq_diam * 1000,
            self.spin_flare.value(),
            new_velocity=existing_vel,
        )

    # ── Cruise control ─────────────────────────────────────────────────────

    def _cruise(self):
        orig_d   = self.spin_orig_d.value() / 1000.0
        new_d    = self.spin_new_d.value() / 1000.0
        orig_vel = self.spin_orig_vel.value()
        new_n    = self.spin_new_n.value()

        new_vel = cruise_control(orig_d, orig_vel, new_d,
                                 new_num_ports=new_n)
        self.lbl_cruise.setText(f"{new_vel:.2f} m/s")

        # Update chart with the new velocity line if a plot already exists
        if self.canvas._last_plot_args:
            args = list(self.canvas._last_plot_args)
            # Replace or append new_velocity (6th arg)
            if len(args) >= 6:
                args[5] = new_vel
            else:
                args.append(new_vel)
            self.canvas.plot(*args)
