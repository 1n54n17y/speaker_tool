"""
PySide6 main window — tabs, menu bar, theme, and project file management.

Project file format: .nordproj  (ZIP + project.json)
Auto-save: every 5 minutes when a project path is set.
"""
import sys
from pathlib import Path

try:
    from PySide6.QtWidgets import (
        QApplication, QFileDialog, QInputDialog,
        QMainWindow, QMessageBox, QStatusBar, QTabWidget,
    )
    from PySide6.QtCore import Qt, QTimer

    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False

AUTOSAVE_INTERVAL_MS = 5 * 60 * 1000   # 5 minutes


# ---------------------------------------------------------------------------
# Theme persistence helpers
# ---------------------------------------------------------------------------

def _load_saved_theme() -> str:
    try:
        import sqlite3
        from ..data import DB_PATH
        if not DB_PATH.exists():
            return "light"
        con = sqlite3.connect(DB_PATH)
        con.execute("CREATE TABLE IF NOT EXISTS preferences "
                    "(key TEXT PRIMARY KEY, value TEXT)")
        row = con.execute(
            "SELECT value FROM preferences WHERE key='theme'").fetchone()
        con.close()
        return row[0] if row else "light"
    except Exception:
        return "light"


def _save_theme(name: str):
    try:
        import sqlite3
        from ..data import DB_PATH
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(DB_PATH)
        con.execute("CREATE TABLE IF NOT EXISTS preferences "
                    "(key TEXT PRIMARY KEY, value TEXT)")
        con.execute("INSERT OR REPLACE INTO preferences (key, value) VALUES ('theme', ?)",
                    (name,))
        con.commit()
        con.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Window builder
# ---------------------------------------------------------------------------

def _build_window():
    from .tabs.driver_tab     import DriverTab
    from .tabs.simulation_tab import SimulationTab
    from .tabs.geometry_tab   import GeometryTab
    from .tabs.flare_tab      import FlareTab
    from .theme               import get_theme
    from .project_state       import get_state, reset_state
    from ..data.project_file  import save_project, load_project

    class NordBassMainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self._project_path: Path | None = None
            self._unsaved = False

            self.setWindowTitle("NordBass Speaker Tool")
            from .scale import s, screen_fraction
            self.setMinimumSize(s(900), s(600))
            w, h = screen_fraction(0.80, 0.85)
            self.resize(w, h)

            # ── Menu bar ──────────────────────────────────────────────────
            menu = self.menuBar()
            file_menu = menu.addMenu("&File")

            act_new  = file_menu.addAction("New Project")
            act_open = file_menu.addAction("Open Project…")
            act_save = file_menu.addAction("Save Project")
            act_saveas = file_menu.addAction("Save Project As…")
            file_menu.addSeparator()
            act_quit = file_menu.addAction("Quit")

            act_new.setShortcut("Ctrl+N")
            act_open.setShortcut("Ctrl+O")
            act_save.setShortcut("Ctrl+S")
            act_saveas.setShortcut("Ctrl+Shift+S")
            act_quit.setShortcut("Ctrl+Q")

            act_new.triggered.connect(self._on_new)
            act_open.triggered.connect(self._on_open)
            act_save.triggered.connect(self._on_save)
            act_saveas.triggered.connect(self._on_save_as)
            act_quit.triggered.connect(self.close)

            help_menu = menu.addMenu("&Help")

            # Theme sub-menu
            theme_menu = help_menu.addMenu("Theme")
            self._action_light = theme_menu.addAction("Light")
            self._action_light.setCheckable(True)
            self._action_light.triggered.connect(lambda: self._set_theme("light"))
            self._action_dark = theme_menu.addAction("Dark")
            self._action_dark.setCheckable(True)
            self._action_dark.triggered.connect(lambda: self._set_theme("dark"))

            help_menu.addSeparator()
            help_menu.addAction("About").triggered.connect(self._show_about)

            # ── Tabs ──────────────────────────────────────────────────────
            self._tabs = QTabWidget()
            self._tab_drivers    = DriverTab()
            self._tab_simulation = SimulationTab()
            self._tab_geometry   = GeometryTab()
            self._tab_flare      = FlareTab()
            self._tabs.addTab(self._tab_drivers,    "Drivers")
            self._tabs.addTab(self._tab_simulation, "Simulation")
            self._tabs.addTab(self._tab_geometry,   "Geometry")
            self._tabs.addTab(self._tab_flare,      "Flare")
            self.setCentralWidget(self._tabs)

            # ── Status bar ────────────────────────────────────────────────
            self._status = self.statusBar()
            self._status.showMessage("Ready  —  No project open")

            # ── Apply saved theme ─────────────────────────────────────────
            saved = _load_saved_theme()
            self._update_check_marks(saved)

            # ── Autosave timer (every 5 minutes) ─────────────────────────
            self._autosave_timer = QTimer(self)
            self._autosave_timer.setInterval(AUTOSAVE_INTERVAL_MS)
            self._autosave_timer.timeout.connect(self._autosave)
            self._autosave_timer.start()

            # Mark state dirty on any state change
            get_state().register(self._mark_dirty)

        # ── Tab reset ─────────────────────────────────────────────────────

        def _reset_all_tabs(self):
            """Tell every tab to refresh its widgets from the current state."""
            self._tab_simulation.reset_ui()
            self._tab_geometry.reset_ui()
            self._tab_flare.reset_ui()
            self._tab_drivers.refresh()

        # ── Project title helper ──────────────────────────────────────────

        def _set_title(self):
            name = get_state().project_name
            dirty = " •" if self._unsaved else ""
            path_str = f"  [{self._project_path}]" if self._project_path else ""
            self.setWindowTitle(f"NordBass  —  {name}{dirty}{path_str}")

        def _mark_dirty(self):
            self._unsaved = True
            self._set_title()

        # ── New Project ───────────────────────────────────────────────────

        def _on_new(self):
            if self._unsaved:
                reply = QMessageBox.question(
                    self, "Unsaved changes",
                    "You have unsaved changes. Save before creating a new project?",
                    QMessageBox.StandardButton.Save |
                    QMessageBox.StandardButton.Discard |
                    QMessageBox.StandardButton.Cancel)
                if reply == QMessageBox.StandardButton.Cancel:
                    return
                if reply == QMessageBox.StandardButton.Save:
                    if not self._on_save():
                        return

            # Ask for a name and save location
            name, ok = QInputDialog.getText(
                self, "New Project", "Project name:", text="Untitled Project")
            if not ok or not name.strip():
                return

            path, _ = QFileDialog.getSaveFileName(
                self, "Choose location for new project",
                str(Path.home() / f"{name.strip()}.nordproj"),
                "NordBass Project (*.nordproj)")
            if not path:
                return

            state = reset_state()
            state.project_name = name.strip()
            self._project_path = Path(path)
            self._unsaved = False
            self._reset_all_tabs()
            self._save_now()
            self._set_title()
            self._status.showMessage(f"New project created: {self._project_path.name}", 4000)

        # ── Open Project ──────────────────────────────────────────────────

        def _on_open(self):
            if self._unsaved:
                reply = QMessageBox.question(
                    self, "Unsaved changes",
                    "Save current project before opening another?",
                    QMessageBox.StandardButton.Save |
                    QMessageBox.StandardButton.Discard |
                    QMessageBox.StandardButton.Cancel)
                if reply == QMessageBox.StandardButton.Cancel:
                    return
                if reply == QMessageBox.StandardButton.Save:
                    if not self._on_save():
                        return

            path, _ = QFileDialog.getOpenFileName(
                self, "Open NordBass Project",
                str(Path.home()),
                "NordBass Project (*.nordproj);;All files (*)")
            if not path:
                return

            try:
                state_dict, drivers_list = load_project(Path(path))
            except Exception as e:
                QMessageBox.critical(self, "Open failed", str(e))
                return

            # Apply loaded state
            from .project_state import ProjectState, get_state
            from ..data.database import save_driver
            from ..data.project_file import _driver_dict_to_model

            new_state = ProjectState.from_dict(state_dict)
            st = get_state()
            # Copy all fields across
            for f_name in ProjectState.__dataclass_fields__:
                if not f_name.startswith("_"):
                    setattr(st, f_name, getattr(new_state, f_name))

            # Import bundled drivers into DB if not already present
            imported = 0
            for drv_data in drivers_list:
                try:
                    drv = _driver_dict_to_model(drv_data)
                    save_driver(drv)
                    imported += 1
                except Exception:
                    pass

            self._project_path = Path(path)
            self._unsaved = False
            self._reset_all_tabs()
            self._set_title()
            msg = f"Opened: {self._project_path.name}"
            if imported:
                msg += f"  ({imported} driver(s) imported)"
            self._status.showMessage(msg, 5000)

        # ── Save Project ──────────────────────────────────────────────────

        def _on_save(self) -> bool:
            if self._project_path is None:
                return self._on_save_as()
            self._save_now()
            return True

        def _on_save_as(self) -> bool:
            name = get_state().project_name
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Project As",
                str(Path.home() / f"{name}.nordproj"),
                "NordBass Project (*.nordproj)")
            if not path:
                return False
            if not path.endswith(".nordproj"):
                path += ".nordproj"
            self._project_path = Path(path)
            self._save_now()
            return True

        def _save_now(self):
            """Internal: actually write the file."""
            from ..data.database import get_driver
            from .project_state import get_state
            st = get_state()
            driver = None
            if st.driver_id:
                try:
                    driver = get_driver(st.driver_id)
                except Exception:
                    pass
            try:
                save_project(st, self._project_path, driver=driver)
                self._unsaved = False
                self._set_title()
                self._status.showMessage(
                    f"Saved: {self._project_path.name}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Save failed", str(e))

        # ── Autosave ──────────────────────────────────────────────────────

        def _autosave(self):
            if self._project_path and self._unsaved and get_state().auto_save:
                self._save_now()
                self._status.showMessage(
                    f"Auto-saved: {self._project_path.name}", 2000)

        # ── Theme ─────────────────────────────────────────────────────────

        def _set_theme(self, name: str):
            get_theme().set_theme(name)
            _save_theme(name)
            get_state().theme = name
            self._update_check_marks(name)
            self._status.showMessage(
                f"Theme: {'Dark' if name == 'dark' else 'Light'}", 2000)

        def _update_check_marks(self, name: str):
            self._action_light.setChecked(name == "light")
            self._action_dark.setChecked(name == "dark")

        # ── About ─────────────────────────────────────────────────────────

        def _show_about(self):
            QMessageBox.about(
                self, "About NordBass",
                "NordBass Speaker Tool v0.1.17\n\n"
                "Professional loudspeaker enclosure design.\n"
                "GPL v3 License.\n\n"
                "Project files use the .nordproj format\n"
                "(ZIP container with project.json manifest).")

        # ── Close guard ───────────────────────────────────────────────────

        def closeEvent(self, event):
            if self._unsaved:
                reply = QMessageBox.question(
                    self, "Unsaved changes",
                    "Save before quitting?",
                    QMessageBox.StandardButton.Save |
                    QMessageBox.StandardButton.Discard |
                    QMessageBox.StandardButton.Cancel)
                if reply == QMessageBox.StandardButton.Cancel:
                    event.ignore()
                    return
                if reply == QMessageBox.StandardButton.Save:
                    if not self._on_save():
                        event.ignore()
                        return
            event.accept()

    return NordBassMainWindow


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if not HAS_PYSIDE6:
        print("PySide6 is required. Install with: pip install PySide6")
        sys.exit(1)

    from .theme         import get_theme
    from .scale         import init_scale

    app = QApplication(sys.argv)
    init_scale(app)

    tm = get_theme()
    tm.set_app(app)

    saved = _load_saved_theme()
    tm.set_theme(saved)

    window = _build_window()()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
