"""
DPI-aware scaling helpers.

Usage:
    from .scale import s, sf, font_size

    widget.setFixedSize(s(120), s(32))   # integer pixel sizes
    Figure(figsize=(sf(5), sf(4)))        # float inch sizes
    label.setStyleSheet(f"font-size:{font_size(11)}")
"""
import sys

# ── Detect system DPI scale factor ─────────────────────────────────────────
def _detect_scale() -> float:
    """Best-effort detection of the OS UI scale factor (1.0 on 96 DPI, 2.0 on 192 DPI)."""
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            screen = app.primaryScreen()
            if screen is not None:
                return screen.devicePixelRatio()
    except Exception:
        pass
    # Fallback
    if sys.platform == "darwin":
        return 2.0  # most Macs are HiDPI
    return 1.0


_SCALE: float = 1.0  # initialised on first use
_SCALE_READY: bool = False


def _get_scale() -> float:
    global _SCALE, _SCALE_READY
    if not _SCALE_READY:
        _SCALE = _detect_scale()
        _SCALE_READY = True
    return _SCALE


def s(px: int) -> int:
    """Scale an integer pixel value by the UI scale factor."""
    return max(1, int(round(px * _get_scale())))


def sf(inches: float) -> float:
    """Scale a matplotlib figure size (in inches) by the UI scale factor."""
    return inches * _get_scale()


def font_size(pt: int) -> str:
    """Return a CSS font-size string scaled for the current DPI, e.g. '11px'."""
    return f"{s(pt)}px"
