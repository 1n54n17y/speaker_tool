"""
NordBass theme manager.

Light / Dark palettes + Qt stylesheet generator.
A singleton ThemeManager holds the current theme and notifies
listeners (matplotlib canvases, widgets) via a simple callback list.
"""

from __future__ import annotations

# ── Palettes ────────────────────────────────────────────────────────────────

LIGHT = {
    "name": "light",

    # Qt widget colours
    "window":          "#F5F5F5",
    "window_text":     "#1A1A1A",
    "base":            "#FFFFFF",
    "alt_base":        "#EFF0F1",
    "button":          "#E0E0E0",
    "button_text":     "#1A1A1A",
    "highlight":       "#2196F3",
    "highlight_text":  "#FFFFFF",
    "border":          "#CCCCCC",
    "group_title":     "#333333",
    "disabled_text":   "#999999",
    "tooltip_bg":      "#FFFFC0",
    "tooltip_text":    "#000000",

    # matplotlib
    "mpl_bg":          "#FFFFFF",
    "mpl_axes_bg":     "#F8F8F8",
    "mpl_text":        "#1A1A1A",
    "mpl_grid":        "#CCCCCC",
    "mpl_spine":       "#AAAAAA",
}

DARK = {
    "name": "dark",

    # Qt widget colours
    "window":          "#1E1E1E",
    "window_text":     "#D4D4D4",
    "base":            "#252525",
    "alt_base":        "#2A2A2A",
    "button":          "#3A3A3A",
    "button_text":     "#D4D4D4",
    "highlight":       "#2196F3",
    "highlight_text":  "#FFFFFF",
    "border":          "#444444",
    "group_title":     "#AAAAAA",
    "disabled_text":   "#666666",
    "tooltip_bg":      "#3A3A3A",
    "tooltip_text":    "#D4D4D4",

    # matplotlib — slightly lighter than the Qt background so charts
    # stand out against the panel
    "mpl_bg":          "#2D2D2D",
    "mpl_axes_bg":     "#333333",
    "mpl_text":        "#CCCCCC",
    "mpl_grid":        "#444444",
    "mpl_spine":       "#555555",
}

PALETTES = {"light": LIGHT, "dark": DARK}


def _stylesheet(p: dict) -> str:
    """Build a complete Qt stylesheet from a palette dict."""
    try:
        from .scale import s
        fs_base = s(13)
        fs_small = s(11)
    except Exception:
        fs_base = 13
        fs_small = 11
    return f"""
/* ── Global ────────────────────────────────── */
QWidget {{
    background-color: {p['window']};
    color: {p['window_text']};
    font-family: "Segoe UI", "DejaVu Sans", sans-serif;
    font-size: {fs_base}px;
}}

/* ── Main window / central widget ─────────── */
QMainWindow, QDialog {{
    background-color: {p['window']};
}}

/* ── Menu bar ──────────────────────────────── */
QMenuBar {{
    background-color: {p['button']};
    color: {p['window_text']};
    border-bottom: 1px solid {p['border']};
    padding: 2px 4px;
}}
QMenuBar::item:selected {{
    background-color: {p['highlight']};
    color: {p['highlight_text']};
    border-radius: 4px;
}}
QMenu {{
    background-color: {p['base']};
    color: {p['window_text']};
    border: 1px solid {p['border']};
    padding: 4px 0px;
}}
QMenu::item:selected {{
    background-color: {p['highlight']};
    color: {p['highlight_text']};
}}
QMenu::separator {{
    height: 1px;
    background: {p['border']};
    margin: 4px 10px;
}}

/* ── Tabs ──────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {p['border']};
    background-color: {p['window']};
}}
QTabBar::tab {{
    background-color: {p['button']};
    color: {p['window_text']};
    padding: 6px 16px;
    border: 1px solid {p['border']};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {p['window']};
    color: {p['window_text']};
    border-bottom: 2px solid {p['highlight']};
}}
QTabBar::tab:hover:!selected {{
    background-color: {p['alt_base']};
}}

/* ── GroupBox ──────────────────────────────── */
QGroupBox {{
    border: 1px solid {p['border']};
    border-radius: 5px;
    margin-top: 10px;
    padding-top: 6px;
    color: {p['group_title']};
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: {p['group_title']};
}}

/* ── Input widgets ─────────────────────────── */
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
    background-color: {p['base']};
    color: {p['window_text']};
    border: 1px solid {p['border']};
    border-radius: 4px;
    padding: 3px 6px;
    selection-background-color: {p['highlight']};
    selection-color: {p['highlight_text']};
}}
QComboBox::drop-down {{
    border-left: 1px solid {p['border']};
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {p['base']};
    color: {p['window_text']};
    selection-background-color: {p['highlight']};
    selection-color: {p['highlight_text']};
    border: 1px solid {p['border']};
}}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {p['button']};
    border: none;
    width: 16px;
}}

/* ── Buttons ───────────────────────────────── */
QPushButton {{
    background-color: {p['button']};
    color: {p['button_text']};
    border: 1px solid {p['border']};
    border-radius: 4px;
    padding: 5px 12px;
}}
QPushButton:hover {{
    background-color: {p['highlight']};
    color: {p['highlight_text']};
    border-color: {p['highlight']};
}}
QPushButton:pressed {{
    background-color: #1565C0;
    color: #FFFFFF;
}}
QPushButton:disabled {{
    color: {p['disabled_text']};
    border-color: {p['border']};
}}

/* ── Table ─────────────────────────────────── */
QTableWidget {{
    background-color: {p['base']};
    color: {p['window_text']};
    gridline-color: {p['border']};
    border: 1px solid {p['border']};
    alternate-background-color: {p['alt_base']};
}}
QTableWidget::item:selected {{
    background-color: {p['highlight']};
    color: {p['highlight_text']};
}}
QHeaderView::section {{
    background-color: {p['button']};
    color: {p['window_text']};
    border: 1px solid {p['border']};
    padding: 4px;
    font-weight: bold;
}}

/* ── Scrollbars ────────────────────────────── */
QScrollBar:vertical {{
    background: {p['alt_base']};
    width: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {p['button']};
    border-radius: 5px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {p['alt_base']};
    height: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal {{
    background: {p['button']};
    border-radius: 5px;
    min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ── Status bar ────────────────────────────── */
QStatusBar {{
    background-color: {p['button']};
    color: {p['disabled_text']};
    border-top: 1px solid {p['border']};
}}

/* ── Tooltips ──────────────────────────────── */
QToolTip {{
    background-color: {p['tooltip_bg']};
    color: {p['tooltip_text']};
    border: 1px solid {p['border']};
    padding: 4px;
    border-radius: 3px;
}}

/* ── Labels ────────────────────────────────── */
QLabel {{
    background: transparent;
    color: {p['window_text']};
}}

/* ── Radio / Checkbox ──────────────────────── */
QRadioButton, QCheckBox {{
    color: {p['window_text']};
    spacing: 6px;
}}
"""


# ── ThemeManager singleton ───────────────────────────────────────────────────

class ThemeManager:
    _instance: "ThemeManager | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._current = "light"
            cls._instance._callbacks: list = []
            cls._instance._app = None
        return cls._instance

    # ── Public API ──────────────────────────────────────────────────────────

    def set_app(self, app):
        """Register the QApplication so we can apply stylesheets."""
        self._app = app

    @property
    def current(self) -> str:
        return self._current

    @property
    def palette(self) -> dict:
        return PALETTES[self._current]

    def is_dark(self) -> bool:
        return self._current == "dark"

    def set_theme(self, name: str):
        """Switch to 'light' or 'dark' and notify all listeners."""
        if name not in PALETTES:
            raise ValueError(f"Unknown theme: {name}")
        self._current = name
        if self._app:
            self._app.setStyleSheet(_stylesheet(self.palette))
        for cb in self._callbacks:
            try:
                cb(name)
            except Exception:
                pass

    def register(self, callback):
        """Register a callable(theme_name) to be called on theme change."""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister(self, callback):
        self._callbacks = [c for c in self._callbacks if c is not callback]

    def mpl_style(self) -> dict:
        """Return a dict of matplotlib rcParams for the current theme."""
        p = self.palette
        return {
            "figure.facecolor":     p["mpl_bg"],
            "axes.facecolor":       p["mpl_axes_bg"],
            "axes.edgecolor":       p["mpl_spine"],
            "axes.labelcolor":      p["mpl_text"],
            "axes.titlecolor":      p["mpl_text"],
            "xtick.color":          p["mpl_text"],
            "ytick.color":          p["mpl_text"],
            "text.color":           p["mpl_text"],
            "grid.color":           p["mpl_grid"],
            "legend.facecolor":     p["mpl_axes_bg"],
            "legend.edgecolor":     p["mpl_spine"],
            "legend.labelcolor":    p["mpl_text"],
        }


# Module-level convenience accessor
def get_theme() -> ThemeManager:
    return ThemeManager()
