"""
Flare-it equivalent: port flare sizing and velocity analysis.

Simple mode  – evaluate a single port diameter against chuffing / compression limits.
Full mode    – given actual port velocities, compute minimum flare radius.
Cruise ctrl  – rescale velocity when port geometry changes.
"""
import math
from typing import Dict, List, Tuple

import numpy as np

from .ports import (
    chuffing_velocity_limit,
    compression_velocity_limit,
    round_port_area,
)


def simple_mode(
    diameter: float,
    flare_radius: float,
    freqs: np.ndarray,
    masking: float = 0.15,
) -> Dict:
    """
    Evaluate a port against chuffing and compression limits.

    Returns dict with:
        freqs            – input frequency array
        chuffing_limit   – boundary-layer velocity limit (m/s) per freq
        compression_limit – compression velocity limit (m/s) per freq
        effective_diameter – diameter + 2 * flare_radius (flare enlargement)
        verdict          – 'OK', 'marginal', or 'chuffing risk'
    """
    # Effective diameter at the port mouth with flare
    d_eff = diameter + 2 * flare_radius

    chuff = np.array(
        [chuffing_velocity_limit(d_eff, float(f), masking) for f in freqs]
    )
    comp = np.array(
        [compression_velocity_limit(d_eff, float(f)) for f in freqs]
    )

    # Combined limit is the lower of the two
    combined = np.minimum(chuff, comp)
    min_limit = float(np.min(combined))

    if min_limit > 20:
        verdict = "OK"
    elif min_limit > 12:
        verdict = "marginal"
    else:
        verdict = "chuffing risk"

    return {
        "freqs": freqs,
        "chuffing_limit": chuff,
        "compression_limit": comp,
        "effective_diameter": d_eff,
        "verdict": verdict,
    }


def full_mode(
    diameter: float,
    velocities_at_freqs: List[Tuple[float, float]],
    masking: float = 0.15,
) -> Dict:
    """
    Given required port velocities at specific frequencies, compute the
    minimum flare radius to keep velocity below chuffing limits.

    Returns dict with:
        min_flare_radius – minimum flare radius (m)
        per_freq         – list of dicts per frequency point
    """
    per_freq: List[Dict] = []
    max_flare_needed = 0.0

    for freq, vel in velocities_at_freqs:
        # Find minimum effective diameter such that
        # chuffing_velocity_limit(d_eff, freq, masking) >= vel
        # v_limit = k1 * sqrt(d_eff * freq) / (1 - masking)
        # d_eff >= (vel * (1 - masking) / k1)^2 / freq
        k1 = 11.0
        masking_factor = 1.0 - masking if masking < 1.0 else 1.0
        d_eff_needed = (vel * masking_factor / k1) ** 2 / max(freq, 1.0)

        flare_needed = max(0.0, (d_eff_needed - diameter) / 2.0)
        max_flare_needed = max(max_flare_needed, flare_needed)

        comp_limit = compression_velocity_limit(diameter, freq)

        per_freq.append(
            {
                "freq": freq,
                "velocity": vel,
                "d_eff_needed": d_eff_needed,
                "flare_needed": flare_needed,
                "compression_limit": comp_limit,
                "comp_exceeded": vel > comp_limit,
            }
        )

    return {
        "min_flare_radius": max_flare_needed,
        "per_freq": per_freq,
    }


def cruise_control(
    original_diameter: float,
    original_velocity_at_fb: float,
    new_diameter: float,
    new_num_ports: int = 1,
    original_num_ports: int = 1,
) -> float:
    """
    When port diameter changes but total volume velocity is constant,
    recalculate air velocity for the new port geometry.

    Volume velocity Q = v * A * n  (constant).
    Returns new velocity m/s.
    """
    a_orig = round_port_area(original_diameter) * original_num_ports
    a_new = round_port_area(new_diameter) * new_num_ports
    if a_new <= 0:
        raise ValueError("New port area must be > 0")
    q = original_velocity_at_fb * a_orig
    return q / a_new
