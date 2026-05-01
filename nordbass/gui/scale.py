"""
DPI-aware scaling helpers.

Usage:
    from .scale import s, sf, font_size, init_scale, screen_fraction

    init_scale(app)                       # call once after QApplication()
    widget.setFixedSize(s(120), s(32))    # integer pixel sizes
    Figure(figsize=(sf(5), sf(4)))        # float inch sizes
    label.setStyleSheet(f"font-size:{font_size(11)}")
    w, h = screen_fraction(0.80, 0.85)    # 80% of screen width, 85% of height
"""
import sys
from typing import Tuple

_SCALE: float = 1.0
_SCALE_READY: bool = False
_SCREEN_W: int = 1280
_SCREEN_H: int = 720


def init_scale(app) -> None:
    """Call once after QApplication() to lock in the DPI scale and screen size."""
    global _SCALE, _SCALE_READY, _SCREEN_W, _SCREEN_H
    try:
        screen = app.primaryScreen()
        if screen is not None:
            _SCALE = screen.devicePixelRatio()
            geo = screen.availableGeometry()
            _SCREEN_W = geo.width()
            _SCREEN_H = geo.height()
    except Exception:
        pass
    _SCALE_READY = True


def _get_scale() -> float:
    global _SCALE, _SCALE_READY
    if not _SCALE_READY:
        # Lazy fallback before init_scale() is called
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                screen = app.primaryScreen()
                if screen is not None:
                    _SCALE = screen.devicePixelRatio()
        except Exception:
            pass
        if sys.platform == "darwin":
            _SCALE = max(_SCALE, 2.0)
        _SCALE_READY = True
    return _SCALE


def s(px: int) -> int:
    """Scale an integer pixel value by the DPI ratio."""
    return max(1, int(round(px * _get_scale())))


def sf(inches: float) -> float:
    """Scale a float inch value (for matplotlib figsize) by the DPI ratio."""
    return inches * _get_scale()


def font_size(pt: int) -> str:
    """Return a scaled CSS font-size string, e.g. '13px'."""
    return f"{s(pt)}px"


def screen_fraction(w_frac: float, h_frac: float) -> Tuple[int, int]:
    """Return (width, height) as fractions of the available screen size."""
    return int(_SCREEN_W * w_frac), int(_SCREEN_H * h_frac)
