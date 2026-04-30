"""
DPI-aware scaling helpers.

Usage:
    from .scale import s, sf, font_size, init_scale, screen_fraction

    widget.setFixedSize(s(120), s(32))   # integer pixel sizes
    Figure(figsize=(sf(5), sf(4)))        # float inch sizes
    label.setStyleSheet(f"font-size:{font_size(11)}")
"""
import sys

# ── Internal state ─────────────────────────────────────────────────
_SCALE: float = 1.0
_SCREEN_W: int = 1920
_SCREEN_H: int = 1080


# ── Initialiser (call once after QApplication is created) ─────────────────
def init_scale(app) -> None:
    """Read DPI ratio and screen geometry from the live QApplication."""
    global _SCALE, _SCREEN_W, _SCREEN_H
    try:
        screen = app.primaryScreen()
        if screen is not None:
            _SCALE = screen.devicePixelRatio()
            geom = screen.availableGeometry()
            _SCREEN_W = geom.width()
            _SCREEN_H = geom.height()
    except Exception:
        pass


# ── Scale helpers ─────────────────────────────────────────────────
def s(px: int) -> int:
    """Scale an integer pixel value by the UI scale factor."""
    return max(1, int(round(px * _SCALE)))


def sf(inches: float) -> float:
    """Scale a matplotlib figure size (in inches) by the UI scale factor."""
    return inches * _SCALE


def font_size(pt: int) -> str:
    """Return a CSS font-size string scaled for the current DPI, e.g. '11px'."""
    return f"{s(pt)}px"


def screen_fraction(w_frac: float, h_frac: float) -> tuple[int, int]:
    """Return (width, height) as fractions of the available screen area."""
    return int(_SCREEN_W * w_frac), int(_SCREEN_H * h_frac)
