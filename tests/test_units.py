"""Tests for unit conversion helpers."""
import math

from nordbass.core.units import (
    cm2_to_m2,
    cm_to_m,
    inch_to_m,
    litre_to_m3,
    m3_to_litre,
    m_to_mm,
    mh_to_h,
    mm_to_m,
)


def test_mm_roundtrip():
    assert abs(m_to_mm(mm_to_m(100.0)) - 100.0) < 1e-10


def test_litre_roundtrip():
    assert abs(m3_to_litre(litre_to_m3(50.0)) - 50.0) < 1e-10


def test_inch_to_m():
    assert abs(inch_to_m(1.0) - 0.0254) < 1e-10


def test_cm2_to_m2():
    assert abs(cm2_to_m2(531.0) - 0.0531) < 1e-10


def test_mh_to_h():
    assert abs(mh_to_h(2.0) - 0.002) < 1e-10
