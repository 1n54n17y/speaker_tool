"""
Shared application state — single source of truth for all tabs.
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class PortState:
    shape: str = "round"
    count: int = 1
    length_m: float = 0.0
    diameter_mm: float = 75.0
    eq_diam_m: float = 0.075
    slot_w_mm: float = 100.0
    slot_h_mm: float = 50.0


@dataclass
class GeometryState:
    volume_l: float = 100.0
    thickness_mm: float = 18.0
    double_front: bool = True
    is_wedge: bool = False
    fixed_width_mm: float = 0.0
    fixed_depth_mm: float = 0.0
    fixed_depth_top_mm: float = 0.0
    fixed_height_mm: float = 0.0
    num_braces: int = 0
    brace_thickness_mm: float = 18.0
    brace_window_percent: float = 40.0
    port_face: str = "back"
    port_position: str = "bottom-left"


@dataclass
class FlareState:
    """Stores passive radiator and flare-related parameters."""
    pr_fs: float = 20.0
    pr_vas: float = 100.0
    pr_qms: float = 5.0
    flare_radius_mm: float = 20.0
    flare_length_mm: float = 50.0


@dataclass
class ProjectState:
    # Driver
    driver_id: Optional[int] = None
    driver_name: str = ""
    driver_count: int = 1
    driver_wiring: str = "series"

    # Box
    box_type: str = "vented"
    volume_l: float = 100.0
    volume_rear: float = 50.0
    fb_hz: float = 30.0
    alignment: str = "QB3"
    input_power_w: float = 100.0
    room_gain: bool = False

    # Nested states
    port: PortState = field(default_factory=PortState)
    geometry: GeometryState = field(default_factory=GeometryState)
    flare: FlareState = field(default_factory=FlareState)

    # Misc
    panel_thickness_mm: float = 18.0
    data: dict = field(default_factory=dict)

    # Internal — observer callbacks
    _callbacks: List[Callable] = field(default_factory=list)

    def register(self, callback: Callable) -> None:
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister(self, callback: Callable) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def notify(self) -> None:
        for cb in list(self._callbacks):
            try:
                cb()
            except TypeError:
                try:
                    cb(self)
                except Exception:
                    pass
            except Exception:
                pass


_STATE = ProjectState()


def get_state() -> ProjectState:
    return _STATE
