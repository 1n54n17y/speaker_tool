"""
CollapsibleSection — a QWidget that shows/hides its content when the
header button is clicked.  Used throughout the left-panel forms.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QSizePolicy,
)


def _toggle_style() -> str:
    """Build the stylesheet for the header toggle button using ThemeManager.
    Falls back to safe defaults if ThemeManager is not yet available.
    """
    try:
        from .theme import get_theme
        p = get_theme().palette
        text_color   = p["window_text"]
        border_color = p["border"]
        hover_bg     = p["alt_base"]
        hover_text   = p["window_text"]
    except Exception:
        text_color   = "#1A1A1A"
        border_color = "#CCCCCC"
        hover_bg     = "#EFF0F1"
        hover_text   = "#1A1A1A"

    return (
        "QPushButton {"
        "  text-align: left;"
        "  font-weight: bold;"
        "  padding: 4px 6px;"
        "  border: none;"
        f" border-bottom: 1px solid {border_color};"
        f" color: {text_color};"
        "  background: transparent;"
        "}"
        "QPushButton:hover {"
        f"  background-color: {hover_bg};"
        f"  color: {hover_text};"
        "}"
        # :checked = expanded state — keep same text colour, no highlight flash
        "QPushButton:checked {"
        f"  color: {text_color};"
        "  background: transparent;"
        "}"
        "QPushButton:checked:hover {"
        f"  background-color: {hover_bg};"
        f"  color: {hover_text};"
        "}"
    )


class CollapsibleSection(QWidget):
    """
    A collapsible panel with a bold header button and a content area.

    Usage::

        sec = CollapsibleSection("Box Parameters", expanded=True)
        inner = QWidget()
        form = QFormLayout(inner)
        # ... populate form ...
        sec.set_content(inner)
        layout.addWidget(sec)
    """

    def __init__(self, title: str = "", expanded: bool = True, parent=None):
        super().__init__(parent)
        self._expanded = expanded
        self._title_text = title

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Header toggle button
        self._toggle = QPushButton()
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setFlat(True)
        self._toggle.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._toggle.setStyleSheet(_toggle_style())
        self._set_title(title)
        self._toggle.clicked.connect(self._on_toggle)
        self._layout.addWidget(self._toggle)

        # Content container
        self._content: QWidget | None = None

        # Register for live theme changes
        try:
            from .theme import get_theme
            get_theme().register(self._on_theme_changed)
        except Exception:
            pass

    # ── Public API ──────────────────────────────────────────────────────────

    def set_content(self, widget: QWidget) -> None:
        """Set (or replace) the content widget."""
        if self._content is not None:
            self._layout.removeWidget(self._content)
            self._content.setParent(None)
        self._content = widget
        self._layout.addWidget(widget)
        widget.setVisible(self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._toggle.setChecked(expanded)
        if self._content:
            self._content.setVisible(expanded)
        self._set_title(self._title_text)

    # ── Internals ──────────────────────────────────────────────────────────

    def _set_title(self, title: str) -> None:
        self._title_text = title
        arrow = "▼" if self._expanded else "▶"
        self._toggle.setText(f"{arrow}  {title}")

    def _on_toggle(self, checked: bool) -> None:
        self._expanded = checked
        if self._content:
            self._content.setVisible(checked)
        self._set_title(self._title_text)

    def _on_theme_changed(self, _name: str) -> None:
        """Re-apply stylesheet when the user switches light ↔ dark."""
        self._toggle.setStyleSheet(_toggle_style())
