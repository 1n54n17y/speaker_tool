"""
Shared in-memory project state.

Holds everything the user has entered across all tabs.
Serialised to / deserialised from .nordproj files by nordbass/data/project_file.py.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PortState:
    shape:       str   = "round"   # "round" | "slot"
    diameter_mm: float = 75.0
    slot_w_mm:   float = 100.0
    slot_h_mm:   float = 50.0
    count:       int   = 1
    length_m:    float = 0.0       # calculated by simulation
    eq_diam_m:   float = 0.075


@dataclass
class GeometryState:
    volume_l:         float = 100.0
    thickness_mm:     float = 18.0
    double_front:     bool  = True
    is_wedge:         bool  = False
    fixed_width_mm:   float = 0.0   # 0 = auto
    fixed_depth_mm:   float = 0.0
    fixed_depth_top_mm: float = 0.0
    fixed_height_mm:  float = 0.0
    # Bracing
    num_braces:       int   = 0
    brace_thickness_mm: float = 18.0
    brace_window_percent: float = 40.0
    # Port placement
    port_face:        str   = "back"
    port_position:    str   = "bottom-left"


@dataclass
class FlareState:
    port_shape:   str   = "round"
    diameter_mm:  float = 75.0
    slot_w_mm:    float = 100.0
    slot_h_mm:    float = 50.0
    flare_mm:     float = 0.0
    masking:      float = 0.15
    target_vel:   float = 17.0


@dataclass
class ProjectState:
    # ── Identity ──────────────────────────────────────────────────────────
    project_name:   str = "Untitled Project"
    author:         str = ""
    description:    str = ""

    # ── Driver ────────────────────────────────────────────────────────────
    driver_id:   Optional[str] = None
    driver_name: str = ""

    # ── Simulation ────────────────────────────────────────────────────────
    box_type:   str   = "vented"
    volume_l:   float = 100.0
    fb_hz:      float = 30.0
    alignment:  str   = "QB3"
    input_power_w: float = 100.0
    panel_thickness_mm: float = 18.0
    
    # New Multi-driver support
    driver_count:  int  = 1
    driver_wiring: str  = "series"
    room_gain:     bool = False

    # ── Port ──────────────────────────────────────────────────────────────
    port: PortState = field(default_factory=PortState)

    # ── Geometry ──────────────────────────────────────────────────────────
    geometry: GeometryState = field(default_factory=GeometryState)

    # ── Flare ─────────────────────────────────────────────────────────────
    flare: FlareState = field(default_factory=FlareState)

    # ── Settings ──────────────────────────────────────────────────────────
    theme:     str  = "light"
    auto_save: bool = True

    # ── Callbacks (not serialised) ────────────────────────────────────────
    _callbacks: list = field(default_factory=list, repr=False)

    def notify(self):
        for cb in list(self._callbacks):
            try:
                cb()
            except Exception:
                pass

    def register(self, callback):
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister(self, callback):
        self._callbacks = [c for c in self._callbacks if c is not callback]

    def to_dict(self) -> dict:
        """Serialise to a plain dict (for JSON)."""
        import dataclasses
        def _asdict(obj):
            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                return {
                    k: _asdict(v)
                    for k, v in dataclasses.asdict(obj).items()
                    if not k.startswith("_")
                }
            return obj
        d = _asdict(self)
        # Remove non-serialisable callback list
        d.pop("_callbacks", None)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectState":
        """Deserialise from a plain dict."""
        port_d    = d.pop("port",     {})
        geom_d    = d.pop("geometry", {})
        flare_d   = d.pop("flare",    {})
        d.pop("_callbacks", None)

        state = cls(**{k: v for k, v in d.items()
                       if k in cls.__dataclass_fields__
                       and not k.startswith("_")
                       and k not in ("port", "geometry", "flare")})
        state.port     = PortState(**{k: v for k, v in port_d.items()
                                      if k in PortState.__dataclass_fields__})
        state.geometry = GeometryState(**{k: v for k, v in geom_d.items()
                                          if k in GeometryState.__dataclass_fields__})
        state.flare    = FlareState(**{k: v for k, v in flare_d.items()
                                       if k in FlareState.__dataclass_fields__})
        return state


# ── Singleton ─────────────────────────────────────────────────────────────────

_state: Optional[ProjectState] = None


def get_state() -> ProjectState:
    global _state
    if _state is None:
        _state = ProjectState()
    return _state


def reset_state() -> ProjectState:
    """Replace singleton with a fresh state (for New Project)."""
    global _state
    callbacks = _state._callbacks if _state else []
    _state = ProjectState()
    _state._callbacks = callbacks
    return _state
