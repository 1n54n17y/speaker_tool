"""
Shared test fixtures with golden driver data.
"""
import pytest

from nordbass.core.models import Driver


@pytest.fixture
def dayton_rss315() -> Driver:
    """Dayton Audio RSS315HF-4 — known good T/S parameters."""
    return Driver(
        name="Dayton RSS315HF-4",
        manufacturer="Dayton Audio",
        fs=17.5,
        qts=0.27,
        qes=0.28,
        qms=3.5,
        vas=0.320,       # m³ (320 litres)
        re=3.2,
        le=0.002,         # 2 mH
        sd=0.0531,        # m² (531 cm²)
        xmax=0.025,       # 25 mm one-way
        pe=500,
        mms=0.320,        # kg
        sensitivity=85.0,
    )


@pytest.fixture
def small_driver() -> Driver:
    """A smaller 6.5" driver for variety in tests."""
    return Driver(
        name="Test 6.5 inch",
        manufacturer="Test",
        fs=38.0,
        qts=0.42,
        qes=0.50,
        qms=3.0,
        vas=0.025,        # 25 litres
        re=6.0,
        sd=0.0133,        # ~133 cm²
        xmax=0.006,       # 6 mm
        pe=100,
    )
