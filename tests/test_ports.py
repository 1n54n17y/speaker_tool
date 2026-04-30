"""Additional port-specific tests."""
import math

from nordbass.core.ports import (
    chuffing_velocity_limit,
    compression_velocity_limit,
    equivalent_diameter,
    port_displacement_volume,
    port_mach_number,
    port_reynolds,
    round_port_area,
    slot_port_area,
)


def test_slot_port_area():
    assert abs(slot_port_area(0.1, 0.05) - 0.005) < 1e-10


def test_round_port_area_matches_formula():
    d = 0.075
    expected = math.pi * (d / 2) ** 2
    assert abs(round_port_area(d) - expected) < 1e-12


def test_mach_at_different_temps():
    m20 = port_mach_number(17.0, temp=20.0)
    m0 = port_mach_number(17.0, temp=0.0)
    # Speed of sound lower at 0°C → higher Mach number
    assert m0 > m20


def test_chuffing_scales_with_sqrt():
    """Chuffing limit should scale with sqrt(d*f)."""
    v1 = chuffing_velocity_limit(0.075, 40, masking=0.0)
    v2 = chuffing_velocity_limit(0.075 * 4, 40, masking=0.0)
    # v2/v1 should ≈ sqrt(4) = 2
    assert abs(v2 / v1 - 2.0) < 0.01


def test_displacement_volume_scales_with_count():
    v1 = port_displacement_volume("round", 0.075, 0, 0, 0.3, 0.003, 1)
    v2 = port_displacement_volume("round", 0.075, 0, 0, 0.3, 0.003, 2)
    assert abs(v2 - 2 * v1) < 1e-12
