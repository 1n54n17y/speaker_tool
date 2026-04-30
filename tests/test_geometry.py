"""Tests for box geometry and cutting list."""
import math

import pytest

from nordbass.core.geometry import (
    cutting_list,
    gross_volume,
    solve_dimensions,
    standing_wave_resonances,
)
from nordbass.core.models import PortConfig


class TestGrossVolume:
    def test_gross_volume_adds_displacements(self):
        """Gross volume should be greater than net volume."""
        net = 0.100  # 100 L
        gv = gross_volume(net, 0.001, 0.0005, [])
        assert gv > net
        assert abs(gv - 0.1015) < 1e-6

    def test_gross_volume_with_port(self):
        port = PortConfig(shape="round", count=1, diameter=0.075, length=0.3, wall_thickness=0.003)
        net = 0.100
        gv = gross_volume(net, 0.0, 0.0, [port])
        assert gv > net


class TestSolveDimensions:
    def test_solve_with_two_fixed(self):
        """With 2 fixed dims, H*W*D should ≈ gross volume."""
        gv = 0.100
        h, w, d = solve_dimensions(gv, 0.018, True, fixed_width=0.4, fixed_depth=0.4)
        vol = h * w * d
        assert abs(vol - gv) / gv < 0.01

    def test_solve_with_no_fixed(self):
        """With no fixed dims, volume should still match."""
        gv = 0.080
        h, w, d = solve_dimensions(gv, 0.018, True)
        vol = h * w * d
        assert abs(vol - gv) / gv < 0.05

    def test_solve_with_one_fixed(self):
        gv = 0.060
        h, w, d = solve_dimensions(gv, 0.018, False, fixed_height=0.5)
        vol = h * w * d
        assert abs(vol - gv) / gv < 0.05


class TestResonances:
    def test_resonances_front_back(self):
        """f1 for D=0.4m should be C/(2*0.4) = 428.75 Hz."""
        res = standing_wave_resonances(0.6, 0.4, 0.4)
        expected = 343.0 / (2 * 0.4)
        assert abs(res["front_back"][0] - expected) < 0.1

    def test_resonances_computed(self):
        res = standing_wave_resonances(0.6, 0.4, 0.4)
        assert len(res["front_back"]) == 3
        assert len(res["top_bottom"]) == 3
        assert len(res["side_side"]) == 3

    def test_warnings_for_audible_range(self):
        """Small box should have resonances in the 80-300 Hz warning zone."""
        res = standing_wave_resonances(0.3, 0.3, 0.3)
        # C/(2*0.3) = 571.7 Hz → mode 1 is above 300 Hz range
        # Actually that's outside the warning zone. Use bigger dims:
        res2 = standing_wave_resonances(0.8, 0.8, 0.8)
        # C/(2*0.8) = 214 Hz — in the 80-300 range
        assert len(res2["warnings"]) > 0


class TestCuttingList:
    def test_panel_count_single_front(self):
        panels = cutting_list(0.5, 0.3, 0.3, 0.018, double_front=False)
        # Top, Bottom, Left, Right, Back, Front, EXTERNAL summary = 7
        assert len(panels) == 7
        front = [p for p in panels if p["panel_name"] == "Front Baffle"][0]
        assert front["qty"] == 1

    def test_panel_count_double_front(self):
        panels = cutting_list(0.5, 0.3, 0.3, 0.018, double_front=True)
        front = [p for p in panels if p["panel_name"] == "Front Baffle"][0]
        assert front["qty"] == 2

    def test_dimensions_positive(self):
        panels = cutting_list(0.5, 0.3, 0.3, 0.018, True)
        for p in panels:
            assert p["length_mm"] > 0
            assert p["width_mm"] > 0
