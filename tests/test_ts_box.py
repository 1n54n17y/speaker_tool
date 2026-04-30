"""Tests for the Thiele/Small box acoustics engine."""
import math

import numpy as np
import pytest

from nordbass.core.ts_box import (
    cone_excursion_array,
    group_delay_array,
    port_air_velocity_array,
    port_length_for_tuning,
    sealed_alignment_volume,
    sealed_params,
    sealed_spl_array,
    vented_alignment,
    vented_params,
    vented_spl_array,
)


class TestSealed:
    def test_sealed_qtc_butterworth(self, dayton_rss315):
        """Volume from sealed_alignment_volume(..., 0.707) should give Qtc ≈ 0.707."""
        vb = sealed_alignment_volume(dayton_rss315, target_qtc=0.707)
        p = sealed_params(dayton_rss315, vb)
        assert abs(p["qtc"] - 0.707) < 0.01

    def test_sealed_f3_near_fc_for_qtc_1(self, dayton_rss315):
        """For Qtc = 1.0, f3 should be close to fc (within ~25%).
        Exact: f3 = fc * sqrt((sqrt(5)-1)/2) ≈ 0.786*fc, i.e. ~21.4% below fc."""
        vb = sealed_alignment_volume(dayton_rss315, target_qtc=1.0)
        p = sealed_params(dayton_rss315, vb)
        assert abs(p["f3"] - p["fc"]) / p["fc"] < 0.25

    def test_sealed_qtc_increases_with_smaller_box(self, dayton_rss315):
        """Smaller box → higher Qtc."""
        vb1 = 0.100  # 100 L
        vb2 = 0.050  # 50 L
        p1 = sealed_params(dayton_rss315, vb1)
        p2 = sealed_params(dayton_rss315, vb2)
        assert p2["qtc"] > p1["qtc"]

    def test_sealed_spl_array_shape(self, dayton_rss315):
        """SPL should be higher in passband than at low frequency."""
        vb = sealed_alignment_volume(dayton_rss315, 0.707)
        freqs = np.logspace(0.5, 3, 500)
        spl = sealed_spl_array(dayton_rss315, vb, freqs)
        # SPL at 200 Hz should be higher than at 5 Hz
        idx_200 = np.argmin(np.abs(freqs - 200))
        idx_5 = np.argmin(np.abs(freqs - 5))
        assert spl[idx_200] > spl[idx_5] + 10


class TestVented:
    def test_vented_port_length_reasonable(self, dayton_rss315):
        """Port length should be positive and physically reasonable."""
        port_area = math.pi * (0.075 / 2) ** 2  # 75 mm port
        fb = 25.0
        vb = 0.200  # 200 L
        length = port_length_for_tuning(fb, vb, port_area)
        assert 0.01 < length < 2.0  # between 1 cm and 2 m

    def test_vented_fb_alignment_physically_reasonable(self, dayton_rss315):
        """QB3 alignment should give reasonable Vb and Fb.
        Low-Qts drivers (0.27) produce very small QB3 boxes; threshold 1L."""
        vb, fb = vented_alignment(dayton_rss315, "QB3")
        assert 0.001 < vb < 2.0  # 1 L to 2000 L
        assert 10 < fb < 100

    def test_spl_array_vented_shape(self, dayton_rss315):
        """SPL should be higher at fb + octave than at fb/4."""
        vb, fb = vented_alignment(dayton_rss315, "QB3")
        freqs = np.logspace(0.5, 3, 1000)
        spl = vented_spl_array(dayton_rss315, vb, fb, freqs)
        idx_above = np.argmin(np.abs(freqs - fb * 2))
        idx_below = np.argmin(np.abs(freqs - fb / 4))
        assert spl[idx_above] > spl[idx_below]

    def test_port_velocity_peaks_near_fb(self, dayton_rss315):
        """Port velocity should peak near the tuning frequency."""
        vb, fb = vented_alignment(dayton_rss315, "QB3")
        port_area = math.pi * (0.075 / 2) ** 2
        freqs = np.logspace(math.log10(5), math.log10(200), 500)
        vel = port_air_velocity_array(
            dayton_rss315, vb, fb, port_area, 1, freqs
        )
        peak_idx = np.argmax(vel)
        peak_freq = freqs[peak_idx]
        # Peak should be within an octave of fb
        assert fb / 2 < peak_freq < fb * 2

    def test_vented_params_returns_f3(self, dayton_rss315):
        vb, fb = vented_alignment(dayton_rss315, "QB3")
        p = vented_params(dayton_rss315, vb, fb)
        assert p["f3"] > 0

    def test_all_alignments_succeed(self, dayton_rss315):
        for alignment in ["QB3", "B4", "SC4", "SBB4"]:
            vb, fb = vented_alignment(dayton_rss315, alignment)
            assert vb > 0
            assert fb > 0


class TestExcursion:
    def test_excursion_returns_positive_values(self, dayton_rss315):
        vb, fb = vented_alignment(dayton_rss315, "QB3")
        freqs = np.logspace(1, 2.5, 100)
        exc, xmax_mm = cone_excursion_array(
            dayton_rss315, vb, fb, freqs, input_power=100, box_type="vented"
        )
        assert xmax_mm == 25.0
        assert np.all(exc >= 0)
        assert np.max(exc) > 0


class TestGroupDelay:
    def test_group_delay_not_all_zero(self, dayton_rss315):
        vb, fb = vented_alignment(dayton_rss315, "QB3")
        freqs = np.logspace(1, 2.5, 200)
        gd = group_delay_array(dayton_rss315, vb, fb, freqs, box_type="vented")
        assert not np.all(gd == 0)
