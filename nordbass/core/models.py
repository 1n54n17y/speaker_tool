"""
Pydantic v2 data models for NordBass.
All dimensional fields stored in SI units internally.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Driver(BaseModel):
    """Loudspeaker driver with Thiele/Small parameters (all SI)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    manufacturer: str = ""
    # Thiele/Small parameters (SI)
    fs: float = Field(..., description="Resonant frequency Hz")
    qts: float = Field(..., description="Total Q")
    qes: float = Field(..., description="Electrical Q")
    qms: float = Field(..., description="Mechanical Q")
    vas: float = Field(..., description="Equivalent air volume m³")
    re: float = Field(..., description="DC resistance Ohm")
    le: float = Field(default=0.0, description="Voice coil inductance H")
    bl: float = Field(default=0.0, description="Force factor T·m")
    sd: float = Field(..., description="Effective cone area m²")
    xmax: float = Field(default=0.005, description="Max linear excursion m (one-way)")
    pe: float = Field(default=100.0, description="Thermal power handling W")
    mms: float = Field(default=0.0, description="Moving mass kg")
    cms: float = Field(default=0.0, description="Compliance m/N")
    rms: float = Field(default=0.0, description="Mechanical resistance kg/s")
    sensitivity: float = Field(default=0.0, description="1W/1m sensitivity dB")
    # Physical / mechanical dimensions (SI — metres)
    cutout_diameter: float = Field(default=0.0, description="Front baffle cutout diameter m")
    mounting_depth:  float = Field(default=0.0, description="Depth behind baffle required m")
    magnet_diameter: float = Field(default=0.0, description="Magnet outer diameter m")
    magnet_height:   float = Field(default=0.0, description="Magnet assembly height m")
    notes: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class PassiveRadiator(BaseModel):
    """Passive Radiator parameters."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "New PR"
    fs: float = Field(..., description="PR resonant frequency Hz")
    vas: float = Field(..., description="PR equivalent volume m³")
    qms: float = Field(..., description="PR mechanical Q")
    sd: float = Field(..., description="PR effective area m²")
    xmax: float = Field(default=0.0, description="PR max linear excursion m")
    added_mass: float = Field(default=0.0, description="Mass added to PR kg")


class PortConfig(BaseModel):
    """Single port definition."""

    shape: str = Field(default="round", description="round or slot")
    count: int = Field(default=1, ge=1)
    # For round ports
    diameter: float = Field(default=0.075, description="Inner diameter m")
    # For slot ports
    width: float = Field(default=0.0, description="Slot width m")
    height: float = Field(default=0.0, description="Slot height m")
    # Common
    length: float = Field(default=0.10, description="Port tube length m")
    wall_thickness: float = Field(
        default=0.003, description="Port tube wall thickness m"
    )
    flare_radius: float = Field(default=0.0, description="Flare radius at port exit m")

    @property
    def area(self) -> float:
        """Cross-sectional area m²."""
        if self.shape == "round":
            return math.pi * (self.diameter / 2) ** 2
        else:
            return self.width * self.height

    @property
    def outer_diameter(self) -> float:
        return self.diameter + 2 * self.wall_thickness

    @property
    def displacement_volume(self) -> float:
        """Volume occupied by port tube walls (not air) m³."""
        if self.shape == "round":
            inner_r = self.diameter / 2
            outer_r = inner_r + self.wall_thickness
            return math.pi * (outer_r**2 - inner_r**2) * self.length * self.count
        else:
            # Slot port walls: outer box minus inner box
            outer_w = self.width + 2 * self.wall_thickness
            outer_h = self.height + 2 * self.wall_thickness
            inner_area = self.width * self.height
            outer_area = outer_w * outer_h
            return (outer_area - inner_area) * self.length * self.count


class BoxDesign(BaseModel):
    """Enclosure design parameters."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled Design"
    driver_id: str = ""
    box_type: str = Field(default="vented", description="sealed, vented, bp4, or pr")
    # Volumes in m³
    net_volume: float = Field(..., description="Net working volume m³ (Vb or Front chamber Vf)")
    rear_volume: Optional[float] = Field(default=None, description="Rear chamber volume Vr (BP4 only)")
    tuning_freq: Optional[float] = Field(
        default=None, description="Box tuning Fb Hz (vented/bp4/pr only)"
    )
    # Passive Radiators
    passive_radiators: List[PassiveRadiator] = Field(default_factory=list)
    # Alignment info
    alignment: str = Field(
        default="manual", description="QB3, SC4, B4, Butterworth, manual"
    )
    system_q: Optional[float] = None
    f3: Optional[float] = None
    # Ports
    ports: List[PortConfig] = Field(default_factory=list)
    # Driver configuration
    driver_count: int = Field(default=1, ge=1)
    driver_wiring: str = Field(default="series", description="series, parallel, or isobaric")
    # Input power for excursion / velocity plots
    input_power: float = Field(default=100.0, description="Input power W for plots")
    notes: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class GeometryConfig(BaseModel):
    """Inputs for the box geometry / cutting list module."""

    net_working_volume: float = Field(..., description="Net volume m³")
    panel_thickness: float = Field(
        default=0.018, description="Panel thickness m (e.g. 18mm MDF)"
    )
    double_front: bool = Field(
        default=True, description="Front baffle is double thickness"
    )
    external_dims: bool = Field(
        default=False,
        description="True if W/D are external, False if internal",
    )
    is_wedge: bool = Field(default=False)
    # Wedge depths
    fixed_depth_top: Optional[float] = None
    fixed_depth_bottom: Optional[float] = None
    # Fixed dimensions (set to None to solve for that dimension)
    fixed_width: Optional[float] = None  # m
    fixed_depth: Optional[float] = None  # m
    fixed_height: Optional[float] = None  # m
    # Bracing detail
    num_braces: int = Field(default=0)
    brace_thickness: float = Field(default=0.018)
    brace_window_percent: float = Field(default=40.0)
    # Driver/bracing displacement
    driver_displacement: float = Field(
        default=0.0005, description="Driver magnet/basket displacement m³"
    )
    bracing_volume: float = Field(
        default=0.0, description="Volume of internal bracing m³"
    )
    extra_volume: float = Field(default=0.0, description="Other internal objects m³")
    # Ports
    ports: List[PortConfig] = Field(default_factory=list)
    # Trim allowance added to EXTERNAL dimensions
    trim_allowance: float = Field(
        default=0.0, description="Extra trim on external dims m"
    )


class FlareConfig(BaseModel):
    """Flare-it style configuration."""

    port_diameter: float = Field(..., description="Port inner diameter m")
    flare_radius: float = Field(default=0.0, description="Flare radius m")
    num_ports: int = Field(default=1, ge=1)
    # Music content masking allowance for boundary layer chuffing
    masking_allowance: float = Field(
        default=0.15, description="0=none, 0.15=music, 0.30=HT"
    )


class Project(BaseModel):
    """Complete project encapsulating all design data."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "New Project"
    driver: Optional[Driver] = None
    box_design: Optional[BoxDesign] = None
    geometry: Optional[GeometryConfig] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    notes: str = ""
