"""
Theme manager — provides palette colours for matplotlib and Qt widgets.
Supports light and dark mode.  Other modules call get_theme() to get the
current Theme instance and can register callbacks for live updates.
"""
from typing import Callable, List


_LIGHT_PALETTE = {
    "mpl_bg":       "#f7f6f2",
    "mpl_axes_bg":  "#fbfbf9",
    "mpl_text":     "#28251d",
    "mpl_grid":     "#dcd9d5",
    "mpl_spine":    "#d4d1ca",
    "qt_bg":        "#f7f6f2",
    "qt_text":      "#28251d",
    "qt_accent":    "#01696f",
}

_DARK_PALETTE = {
    "mpl_bg":       "#171614",
    "mpl_axes_bg":  "#1c1b19",
    "mpl_text":     "#cdccca",
    "mpl_grid":     "#262523",
    "mpl_spine":    "#393836",
    "qt_bg":        "#171614",
    "qt_text":      "#cdccca",
    "qt_accent":    "#4f98a3",
}


class Theme:
    def __init__(self, dark: bool = False):
        self._dark = dark
        self._callbacks: List[Callable] = []
        self._update_palette()

    def _update_palette(self):
        self.palette = _DARK_PALETTE.copy() if self._dark else _LIGHT_PALETTE.copy()

    def is_dark(self) -> bool:
        return self._dark

    def set_dark(self, dark: bool) -> None:
        if dark != self._dark:
            self._dark = dark
            self._update_palette()
            self._notify("theme")

    def toggle(self) -> None:
        self.set_dark(not self._dark)

    def register(self, callback: Callable) -> None:
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister(self, callback: Callable) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify(self, name: str) -> None:
        for cb in list(self._callbacks):
            try:
                cb(name)
            except TypeError:
                try:
                    cb()
                except Exception:
                    pass
            except Exception:
                pass


_THEME = Theme(dark=False)


def get_theme() -> Theme:
    return _THEME
