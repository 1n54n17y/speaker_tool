"""
Port geometry, velocity limits, and flow analysis.
Matches Flare-it boundary-layer and compression models.
"""
import math
from typing import Optional

# Air properties at 20 °C
C_AIR = 343.0  # m/s
RHO_AIR = 1.2041  # kg/m³
KINEMATIC_VISCOSITY = 1.516e-5  # m²/s at 20 °C


def port_mach_number(velocity: float, temp: float = 20.0) -> float:
    """Return Mach number for given port air velocity."""
    c = 331.3 + 0.606 * temp
    return velocity / c


def port_reynolds(velocity: float, diameter: float, temp: float = 20.0) -> float:
    """Return Reynolds number for flow in a round port."""
    # Kinematic viscosity scales roughly with temperature
    nu = KINEMATIC_VISCOSITY * (temp / 20.0) ** 0.7 if temp > 0 else KINEMATIC_VISCOSITY
    return (velocity * diameter) / nu


def chuffing_velocity_limit(
    diameter: float, frequency: float, masking: float = 0.15
) -> float:
    """
    Boundary-layer chuffing velocity limit (m/s).

    Model: v_limit = k1 * sqrt(d * f)
    where k1 ≈ 11.0 (empirical, matches Flare-it).

    masking: 0 = no masking, 0.15 = music, 0.30 = home theatre.
    With masking the effective limit is higher because masking content
    hides the chuffing noise.
    """
    k1 = 11.0
    v_base = k1 * math.sqrt(diameter * frequency)
    if masking >= 1.0:
        return v_base  # avoid division by zero
    return v_base / (1.0 - masking)


def compression_velocity_limit(diameter: float, frequency: float) -> float:
    """
    Compression velocity limit (m/s).

    Approximately C / 20 ≈ 17.15 m/s at 20 °C.
    Frequency-independent at low frequencies (< 200 Hz).
    """
    return C_AIR / 20.0


def round_port_area(diameter: float) -> float:
    """Cross-sectional area of a round port (m²)."""
    return math.pi * (diameter / 2.0) ** 2


def slot_port_area(width: float, height: float) -> float:
    """Cross-sectional area of a rectangular/slot port (m²)."""
    return width * height


def equivalent_diameter(area: float) -> float:
    """Equivalent round-port diameter for a given cross-sectional area (m)."""
    return 2.0 * math.sqrt(area / math.pi)


def port_displacement_volume(
    shape: str,
    diameter: float,
    width: float,
    height: float,
    length: float,
    wall_thickness: float,
    count: int,
) -> float:
    """
    Volume displaced by port tube walls inside the enclosure (m³).

    For round ports: annular ring × length × count.
    For slot ports: outer box - inner box × length × count.
    """
    if shape == "round":
        inner_r = diameter / 2.0
        outer_r = inner_r + wall_thickness
        annular_area = math.pi * (outer_r**2 - inner_r**2)
        return annular_area * length * count
    else:
        # Full 4-wall tube displacement
        outer_w = width + 2 * wall_thickness
        outer_h = height + 2 * wall_thickness
        inner_area = width * height
        outer_area = outer_w * outer_h
        return (outer_area - inner_area) * length * count
