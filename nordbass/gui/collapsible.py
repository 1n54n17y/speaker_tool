"""
CollapsibleSection — a QWidget that shows/hides its content when the
header button is clicked.  Used throughout the left-panel forms.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QSizePolicy,
)
from PySide6.QtCore import Qt


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
        self._toggle.setStyleSheet(
            "QPushButton {"
            "  text-align: left;"
            "  font-weight: bold;"
            "  padding: 4px 6px;"
            "  border: none;"
            "  border-bottom: 1px solid palette(mid);"
            "}"
            "QPushButton:checked { color: palette(highlight); }"
        )
        self._set_title(title)
        self._toggle.clicked.connect(self._on_toggle)
        self._layout.addWidget(self._toggle)

        # Content container
        self._content: QWidget | None = None

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
        self._set_title(self._toggle.text().lstrip("▼ ").lstrip("▶ "))

    # ── Internals ──────────────────────────────────────────────────────────

    def _set_title(self, title: str) -> None:
        arrow = "▼" if self._expanded else "▶"
        self._toggle.setText(f"{arrow}  {title}")

    def _on_toggle(self, checked: bool) -> None:
        self._expanded = checked
        if self._content:
            self._content.setVisible(checked)
        # Update arrow
        raw = self._toggle.text().lstrip("▼ ").lstrip("▶ ")
        self._set_title(raw)
