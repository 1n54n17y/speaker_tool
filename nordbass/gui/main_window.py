"""
Main application window — tabbed interface hosting all feature tabs.
"""
import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QLabel, QStatusBar, QToolBar, QSizePolicy,
)
from PySide6.QtGui import QAction, QIcon
from PySide6.QtCore import Qt

from .theme import get_theme
from .project_state import get_state
from .tabs.driver_tab import DriverTab
from .tabs.simulation_tab import SimulationTab
from .tabs.geometry_tab import GeometryTab
from .tabs.flare_tab import FlareTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NordBass Speaker Tool")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)

        # ── Central widget: tab bar ───────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self.setCentralWidget(self._tabs)

        # ── Instantiate tabs ───────────────────────────────────────────────
        self._tab_driver     = DriverTab()
        self._tab_simulation = SimulationTab()
        self._tab_geometry   = GeometryTab()
        self._tab_flare      = FlareTab()

        self._tabs.addTab(self._tab_driver,     "Drivers")
        self._tabs.addTab(self._tab_simulation, "Simulation")
        self._tabs.addTab(self._tab_geometry,   "Geometry")
        self._tabs.addTab(self._tab_flare,      "Flare / Port")

        # ── Status bar ──────────────────────────────────────────────────────────
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready")

        # ── Theme toggle in toolbar ───────────────────────────────────────────────
        toolbar = QToolBar("Main toolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        self._act_theme = QAction("☀ Light", self)
        self._act_theme.setToolTip("Toggle dark / light theme")
        self._act_theme.triggered.connect(self._toggle_theme)
        toolbar.addAction(self._act_theme)

        # Apply initial theme stylesheet
        self._apply_theme()

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _toggle_theme(self):
        get_theme().toggle()
        self._apply_theme()

    def _apply_theme(self):
        dark = get_theme().is_dark()
        p    = get_theme().palette
        self._act_theme.setText("☀ Light" if dark else "🌙 Dark")
        self.setStyleSheet(
            f"""
            QMainWindow, QWidget {{
                background-color: {p['qt_bg']};
                color: {p['qt_text']};
            }}
            QTabBar::tab {{
                padding: 6px 18px;
                border: 1px solid transparent;
            }}
            QTabBar::tab:selected {{
                border-bottom: 2px solid {p['qt_accent']};
                color: {p['qt_accent']};
            }}
            QPushButton {{
                border: 1px solid {p['qt_accent']};
                border-radius: 4px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                background-color: {p['qt_accent']};
                color: {p['qt_bg']};
            }}
            QScrollBar:vertical {{ width: 8px; }}
            QScrollBar::handle:vertical {{ border-radius: 4px;
                background: {p['mpl_spine']}; }}
            """
        )


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("NordBass Speaker Tool")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


# Alias so cli/app.py can call: from ..gui.main_window import main
main = run
