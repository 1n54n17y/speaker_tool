"""Tests for flare analysis."""
import numpy as np
import pytest

from nordbass.core.flares import cruise_control, full_mode, simple_mode
from nordbass.core.ports import (
    chuffing_velocity_limit,
    compression_velocity_limit,
    port_mach_number,
    port_reynolds,
    round_port_area,
    equivalent_diameter,
    port_displacement_volume,
)


class TestPorts:
    def test_chuffing_limit_increases_with_diameter(self):
        """Larger port should have a higher chuffing velocity limit."""
        v_small = chuffing_velocity_limit(0.050, 40.0)
        v_large = chuffing_velocity_limit(0.100, 40.0)
        assert v_large > v_small

    def test_compression_limit_roughly_17ms(self):
        """Compression limit should be approximately C/20 ≈ 17.15 m/s."""
        v = compression_velocity_limit(0.075, 40.0)
        assert 15 < v < 20

    def test_mach_number(self):
        m = port_mach_number(17.0)
        assert 0.04 < m < 0.06

    def test_reynolds_positive(self):
        re = port_reynolds(10.0, 0.075)
        assert re > 0

    def test_round_port_area(self):
        a = round_port_area(0.1)  # 100 mm
        expected = np.pi * 0.05 ** 2
        assert abs(a - expected) < 1e-10

    def test_equivalent_diameter(self):
        a = 0.01  # m²
        d = equivalent_diameter(a)
        assert abs(round_port_area(d) - a) < 1e-10

    def test_port_displacement_volume(self):
        vol = port_displacement_volume("round", 0.075, 0, 0, 0.3, 0.003, 1)
        assert vol > 0

    def test_slot_displacement(self):
        vol = port_displacement_volume("slot", 0, 0.1, 0.05, 0.3, 0.003, 1)
        assert vol > 0.0


class TestFlares:
    def test_simple_mode_returns_verdict(self):
        freqs = np.array([20, 40, 60, 80, 100], dtype=float)
        result = simple_mode(0.075, 0.0, freqs, masking=0.15)
        assert result["verdict"] in ("OK", "marginal", "chuffing risk")

    def test_flare_increases_effective_diameter(self):
        freqs = np.array([40], dtype=float)
        r1 = simple_mode(0.075, 0.0, freqs)
        r2 = simple_mode(0.075, 0.020, freqs)
        assert r2["effective_diameter"] > r1["effective_diameter"]

    def test_full_mode_returns_positive_radius(self):
        # Give a high velocity that requires a flare
        vels = [(40.0, 20.0), (60.0, 15.0)]
        result = full_mode(0.050, vels, masking=0.15)
        assert result["min_flare_radius"] >= 0

    def test_full_mode_high_velocity_needs_flare(self):
        vels = [(40.0, 50.0)]  # extremely high velocity
        result = full_mode(0.050, vels, masking=0.0)
        assert result["min_flare_radius"] > 0

    def test_cruise_control_larger_port_lower_velocity(self):
        """Larger port with same volume flow → lower velocity."""
        v_new = cruise_control(0.075, 15.0, 0.100)
        assert v_new < 15.0

    def test_cruise_control_conservation(self):
        """Volume flow should be conserved."""
        orig_d = 0.075
        new_d = 0.100
        orig_v = 15.0
        new_v = cruise_control(orig_d, orig_v, new_d)
        a_orig = round_port_area(orig_d)
        a_new = round_port_area(new_d)
        assert abs(orig_v * a_orig - new_v * a_new) < 1e-10
