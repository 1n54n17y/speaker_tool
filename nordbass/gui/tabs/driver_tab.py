"""
Driver management tab — table + full Add/Edit dialog.
Double-click a row to edit. Add button opens a blank form.
"""
import math

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QDoubleSpinBox, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from ...core.models import Driver
from ..scale import s, font_size
from ...data.database import delete_driver, list_drivers, save_driver
from ...data.importer import import_csv


# ---------------------------------------------------------------------------
# Add / Edit dialog
# ---------------------------------------------------------------------------

def _dspin(lo, hi, val, dec, suffix=""):
    """Helper: create a configured QDoubleSpinBox."""
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setValue(val)
    sb.setDecimals(dec)
    sb.setSuffix(f"  {suffix}" if suffix else "")
    sb.setMinimumWidth(120)
    return sb


class DriverDialog(QDialog):
    """
    Modal dialog for adding or editing a driver.
    All T/S parameters are shown with their units and a short tooltip.
    """

    def __init__(self, parent=None, driver: Driver = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Driver" if driver else "Add Driver")
        self.setMinimumWidth(480)
        self.setModal(True)

        outer = QVBoxLayout(self)

        # Scroll area so the form fits on small screens
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        container = QWidget()
        scroll.setWidget(container)
        form_layout = QVBoxLayout(container)
        form_layout.setSpacing(8)
        outer.addWidget(scroll)

        # ── Identity ──────────────────────────────────────────────────────
        id_group = QGroupBox("Identity")
        id_form  = QFormLayout(id_group)
        self.edit_name  = QLineEdit()
        self.edit_mfr   = QLineEdit()
        self.edit_notes = QLineEdit()
        self.edit_name.setPlaceholderText("e.g. RSS315HF-4")
        self.edit_mfr.setPlaceholderText("e.g. Dayton Audio")
        id_form.addRow("Model name *:", self.edit_name)
        id_form.addRow("Manufacturer:",  self.edit_mfr)
        id_form.addRow("Notes:",         self.edit_notes)
        form_layout.addWidget(id_group)

        # ── Required T/S parameters ───────────────────────────────────────
        req_group = QGroupBox("Required T/S Parameters")
        req_form  = QFormLayout(req_group)

        self.spin_fs   = _dspin(1,    500,  30.0,  2, "Hz")
        self.spin_qts  = _dspin(0.01, 5.0,  0.35,  3)
        self.spin_qes  = _dspin(0.01, 5.0,  0.40,  3)
        self.spin_qms  = _dspin(0.1,  50.0, 4.0,   2)
        self.spin_vas  = _dspin(0.1,  2000, 80.0,  1, "L")
        self.spin_re   = _dspin(0.1,  32.0, 4.0,   2, "Ω")
        self.spin_sd   = _dspin(1,    2000, 200.0, 1, "cm²")
        self.spin_xmax = _dspin(0.1,  100,  12.0,  1, "mm")
        self.spin_pe   = _dspin(1,    5000, 200.0, 0, "W")

        rows_req = [
            ("Fs *",       self.spin_fs,   "Resonant frequency"),
            ("Qts *",      self.spin_qts,  "Total Q factor"),
            ("Qes *",      self.spin_qes,  "Electrical Q factor"),
            ("Qms *",      self.spin_qms,  "Mechanical Q factor"),
            ("Vas *",      self.spin_vas,  "Equivalent air volume (enter in litres)"),
            ("Re *",       self.spin_re,   "DC voice coil resistance"),
            ("Sd *",       self.spin_sd,   "Effective cone area (enter in cm²)"),
            ("Xmax *",     self.spin_xmax, "One-way linear excursion (enter in mm)"),
            ("Pe *",       self.spin_pe,   "Thermal power handling (RMS)"),
        ]
        for label, widget, tip in rows_req:
            lbl = QLabel(label)
            lbl.setToolTip(tip)
            widget.setToolTip(tip)
            req_form.addRow(lbl, widget)
        form_layout.addWidget(req_group)

        # Connect Q-signals for auto-calculation
        self._updating_q = False
        self.spin_qts.valueChanged.connect(lambda: self._on_q_changed("qts"))
        self.spin_qes.valueChanged.connect(lambda: self._on_q_changed("qes"))
        self.spin_qms.valueChanged.connect(lambda: self._on_q_changed("qms"))

        # ── Physical dimensions ───────────────────────────────────────────
        phys_group = QGroupBox("Physical Dimensions  (* Required for geometry fit check)")
        phys_form  = QFormLayout(phys_group)

        self.spin_cutout   = _dspin(0, 1000, 0.0, 1, "mm")
        self.spin_mnt_depth= _dspin(0, 1000, 0.0, 1, "mm")
        self.spin_mag_diam = _dspin(0, 1000, 0.0, 1, "mm")
        self.spin_mag_h    = _dspin(0, 1000, 0.0, 1, "mm")

        rows_phys = [
            ("Cutout diam *",   self.spin_cutout,    "Diameter of the hole to cut in the front baffle"),
            ("Mounting depth *",self.spin_mnt_depth,  "How deep the driver sits behind the baffle face"),
            ("Magnet diameter", self.spin_mag_diam,   "Outer diameter of the magnet assembly"),
            ("Magnet height",   self.spin_mag_h,      "Height of the magnet assembly"),
        ]
        for label, widget, tip in rows_phys:
            lbl = QLabel(label)
            lbl.setToolTip(tip)
            widget.setToolTip(tip)
            phys_form.addRow(lbl, widget)
        form_layout.addWidget(phys_group)

        # ── Optional T/S parameters ───────────────────────────────────────
        opt_group = QGroupBox("Optional T/S Parameters  (enter 0 if unknown)")
        opt_form  = QFormLayout(opt_group)

        self.spin_le          = _dspin(0, 100,  0.0,  2, "mH")
        self.spin_bl          = _dspin(0, 100,  0.0,  2, "T·m")
        self.spin_mms         = _dspin(0, 2.0,  0.0,  4, "kg")
        self.spin_sensitivity = _dspin(0, 120,  0.0,  1, "dB")

        rows_opt = [
            ("Le",          self.spin_le,          "Voice coil inductance (mH)"),
            ("Bl",          self.spin_bl,          "Force factor"),
            ("Mms",         self.spin_mms,         "Moving mass (cone + coil + air load)"),
            ("Sensitivity", self.spin_sensitivity, "1W / 1m sensitivity"),
        ]
        for label, widget, tip in rows_opt:
            lbl = QLabel(label)
            lbl.setToolTip(tip)
            widget.setToolTip(tip)
            opt_form.addRow(lbl, widget)
        form_layout.addWidget(opt_group)

        # Required field note
        note = QLabel("  * Required fields")
        note.setStyleSheet(f"color: gray; font-size: {font_size(11)};")
        form_layout.addWidget(note)
        form_layout.addStretch()

        # ── Buttons ───────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        # Pre-fill if editing existing driver
        if driver:
            self._fill(driver)
        self._driver_id = driver.id if driver else None

    # ── Fill form from existing Driver ────────────────────────────────────

    def _fill(self, d: Driver):
        self.edit_name.setText(d.name)
        self.edit_mfr.setText(d.manufacturer)
        self.edit_notes.setText(d.notes)
        self.spin_fs.setValue(d.fs)
        self.spin_qts.setValue(d.qts)
        self.spin_qes.setValue(d.qes)
        self.spin_qms.setValue(d.qms)
        self.spin_vas.setValue(d.vas * 1000)         # m³ → L
        self.spin_re.setValue(d.re)
        self.spin_sd.setValue(d.sd * 1e4)            # m² → cm²
        self.spin_xmax.setValue(d.xmax * 1000)       # m → mm
        self.spin_pe.setValue(d.pe)
        self.spin_le.setValue(d.le * 1000)           # H → mH
        self.spin_bl.setValue(d.bl)
        self.spin_mms.setValue(d.mms)
        self.spin_sensitivity.setValue(d.sensitivity)
        # Physical dims mm → stored as m
        self.spin_cutout.setValue(d.cutout_diameter * 1000)
        self.spin_mnt_depth.setValue(d.mounting_depth * 1000)
        self.spin_mag_diam.setValue(d.magnet_diameter * 1000)
        self.spin_mag_h.setValue(d.magnet_height * 1000)

    # ── Q Calculation ─────────────────────────────────────────────────────

    def _on_q_changed(self, source: str):
        if self._updating_q:
            return
        self._updating_q = True
        try:
            qts = self.spin_qts.value()
            qes = self.spin_qes.value()
            qms = self.spin_qms.value()

            if source == "qes" or source == "qms":
                # Calculate Qts = (Qes * Qms) / (Qes + Qms)
                if qes > 0 and qms > 0:
                    self.spin_qts.setValue((qes * qms) / (qes + qms))
            elif source == "qts":
                # If Qms is available, update Qes. Standard practice: Qts and Qes are given.
                if qts > 0 and qms > 0 and qms > qts:
                    # Qes = (Qts * Qms) / (Qms - qts)
                    self.spin_qes.setValue((qts * qms) / (qms - qts))
        finally:
            self._updating_q = False

    # ── Validate + accept ─────────────────────────────────────────────────

    def _on_ok(self):
        name = self.edit_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing field", "Model name is required.")
            return
        self.accept()

    # ── Build Driver model from form ──────────────────────────────────────

    def get_driver(self) -> Driver:
        import uuid
        d = Driver(
            id           = self._driver_id or str(uuid.uuid4()),
            name         = self.edit_name.text().strip(),
            manufacturer = self.edit_mfr.text().strip(),
            notes        = self.edit_notes.text().strip(),
            fs           = self.spin_fs.value(),
            qts          = self.spin_qts.value(),
            qes          = self.spin_qes.value(),
            qms          = self.spin_qms.value(),
            vas          = self.spin_vas.value() / 1000,      # L → m³
            re           = self.spin_re.value(),
            sd           = self.spin_sd.value() / 1e4,        # cm² → m²
            xmax         = self.spin_xmax.value() / 1000,     # mm → m
            pe           = self.spin_pe.value(),
            le           = self.spin_le.value() / 1000,       # mH → H
            bl           = self.spin_bl.value(),
            mms          = self.spin_mms.value(),
            sensitivity  = self.spin_sensitivity.value(),
            cutout_diameter = self.spin_cutout.value() / 1000,    # mm → m
            mounting_depth  = self.spin_mnt_depth.value() / 1000,
            magnet_diameter = self.spin_mag_diam.value() / 1000,
            magnet_height   = self.spin_mag_h.value() / 1000,
        )
        return d


# ---------------------------------------------------------------------------
# Driver tab
# ---------------------------------------------------------------------------

class DriverTab(QWidget):
    COLUMNS = ["Name", "Manufacturer", "Fs (Hz)", "Qts", "Vas (L)",
               "Sd (cm²)", "Xmax (mm)", "Pe (W)", "Re (Ω)",
               "Cutout (mm)", "Mnt depth (mm)"]

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # Table — multi-selection enabled
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection)   # ← multi-select
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_edit)
        layout.addWidget(self.table)

        # Hint label
        hint = QLabel("Double-click a row to edit.  Ctrl+click or Shift+click to select multiple rows for deletion.")
        hint.setStyleSheet(f"color: gray; font-size: {font_size(11)};")
        layout.addWidget(hint)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_add    = QPushButton("  Add driver")
        self.btn_edit   = QPushButton("  Edit selected")
        self.btn_delete = QPushButton("  Delete selected")
        self.btn_import = QPushButton("  Import CSV / XLSX")
        self.btn_refresh= QPushButton("Refresh")

        self.btn_add.setMinimumHeight(s(32))
        self.btn_edit.setMinimumHeight(s(32))
        self.btn_delete.setMinimumHeight(s(32))
        self.btn_add.setStyleSheet("font-weight: bold;")
        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_delete.clicked.connect(self._on_delete)
        self.btn_import.clicked.connect(self._on_import)
        self.btn_refresh.clicked.connect(self.refresh)

        for btn in (self.btn_add, self.btn_edit, self.btn_delete,
                    self.btn_import, self.btn_refresh):
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        self._drivers = []
        self.refresh()

    # ── Table refresh ──────────────────────────────────────────────────────

    def refresh(self):
        self._drivers = list_drivers()
        self.table.setRowCount(len(self._drivers))
        for row, d in enumerate(self._drivers):
            vals = [
                d.name,
                d.manufacturer,
                f"{d.fs:.1f}",
                f"{d.qts:.3f}",
                f"{d.vas * 1000:.1f}",
                f"{d.sd * 1e4:.1f}",
                f"{d.xmax * 1000:.1f}",
                f"{d.pe:.0f}",
                f"{d.re:.2f}",
                f"{d.cutout_diameter * 1000:.1f}" if d.cutout_diameter else "—",
                f"{d.mounting_depth * 1000:.1f}"  if d.mounting_depth  else "—",
            ]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    if col >= 2 else
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, item)

    def _selected_rows(self):
        """Return list of (row_index, Driver) for all selected rows, sorted descending."""
        rows = sorted(
            {idx.row() for idx in self.table.selectedIndexes()},
            reverse=True)
        return [(r, self._drivers[r]) for r in rows if r < len(self._drivers)]

    def _selected_driver(self):
        """Return the single currently focused driver (for edit)."""
        row = self.table.currentRow()
        if row < 0 or row >= len(self._drivers):
            return None
        return self._drivers[row]

    # ── Add ────────────────────────────────────────────────────────────────

    def _on_add(self):
        dlg = DriverDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            save_driver(dlg.get_driver())
            self.refresh()

    # ── Edit ───────────────────────────────────────────────────────────────

    def _on_edit(self):
        d = self._selected_driver()
        if not d:
            QMessageBox.information(self, "Edit", "Select a driver row first.")
            return
        dlg = DriverDialog(self, driver=d)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            save_driver(dlg.get_driver())
            self.refresh()

    # ── Delete ─────────────────────────────────────────────────────────────

    def _on_delete(self):
        selected = self._selected_rows()
        if not selected:
            QMessageBox.information(self, "Delete", "Select one or more driver rows first.")
            return

        if len(selected) == 1:
            msg = f"Delete  {selected[0][1].name}?\nThis cannot be undone."
        else:
            names = ", ".join(d.name for _, d in selected)
            msg = f"Delete {len(selected)} drivers?\n{names}\n\nThis cannot be undone."

        reply = QMessageBox.question(
            self, "Confirm delete", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            for _, d in selected:
                delete_driver(d.id)
            self.refresh()

    # ── Import ─────────────────────────────────────────────────────────────

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import drivers",
            "", "Spreadsheets (*.csv *.xlsx *.ods)")
        if not path:
            return
        try:
            imported = import_csv(path)
            for d in imported:
                save_driver(d)
            self.refresh()
            QMessageBox.information(
                self, "Import complete",
                f"Imported {len(imported)} driver(s) successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))
