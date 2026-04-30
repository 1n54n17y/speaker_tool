"""
Thiele/Small based box acoustics engine.
Supports sealed and vented (bass-reflex) enclosures.
All inputs/outputs in SI unless otherwise noted.
"""
import math
from typing import Dict, List, Optional, Tuple

import numpy as np

from .models import BoxDesign, Driver, PortConfig, PassiveRadiator

# Air properties at 20 °C
RHO = 1.2041  # kg/m³ air density
C = 343.0  # m/s speed of sound


# ---------------------------------------------------------------------------
# Helper: estimate missing T/S parameters
# ---------------------------------------------------------------------------

def estimate_mms(driver: Driver) -> float:
    """Estimate Mms from T/S params if not given."""
    if driver.mms > 0:
        return driver.mms
    cms = driver.vas / (RHO * C**2 * driver.sd**2)
    return 1.0 / ((2 * math.pi * driver.fs) ** 2 * cms)


def estimate_cms(driver: Driver) -> float:
    if driver.cms > 0:
        return driver.cms
    return driver.vas / (RHO * C**2 * driver.sd**2)


def estimate_rms(driver: Driver, mms: float) -> float:
    if driver.rms > 0:
        return driver.rms
    if driver.qms > 0:
        return (2 * math.pi * driver.fs * mms) / driver.qms
    return 0.01


def estimate_bl(driver: Driver, mms: float) -> float:
    if driver.bl > 0:
        return driver.bl
    if driver.qes > 0 and driver.re > 0:
        return math.sqrt(
            driver.re * (2 * math.pi * driver.fs * mms) / driver.qes
        )
    return 1.0


# ---------------------------------------------------------------------------
# Multi-driver / Impedance / Le Correction
# ---------------------------------------------------------------------------

def effective_driver_params(driver: Driver, count: int = 1, wiring: str = "series") -> Driver:
    """
    Calculate effective T/S parameters for multiple drivers.
    Returns a cloned Driver object with modified parameters.
    """
    import copy
    eff = copy.deepcopy(driver)
    
    # Ensure base parameters are estimated if missing
    eff.mms = estimate_mms(eff)
    eff.cms = estimate_cms(eff)
    eff.rms = estimate_rms(eff, eff.mms)
    eff.bl  = estimate_bl(eff, eff.mms)

    if count <= 1:
        return eff

    if wiring == "parallel":
        # N drivers in parallel: Re/N, Le/N, Vas*N, Sd*N, Mms*N, Rms*N, Cms/N? No, Cms/N is stiffer.
        # Actually: Cms_total = Cms_single / N (N springs in parallel)
        # Mms_total = Mms_single * N
        # Bl stays same (Force = Bl * I_total = Bl * N * I_single, but Z_mech also * N)
        eff.re = driver.re / count
        eff.le = driver.le / count
        eff.vas = driver.vas * count
        eff.sd = driver.sd * count
        eff.mms = eff.mms * count
        eff.rms = eff.rms * count
        eff.cms = eff.cms / count
        # Bl of parallel combo is same as single driver for nodal equations
        # because F = Bl * I_total / N ... wait.
        # Let's use the property that Qes stays same.
        # Qes = (Re/N * Mms*N * w) / Bl_eff^2 => Bl_eff = Bl_single. Correct.
        eff.pe = driver.pe * count
        
    elif wiring == "series":
        # N drivers in series: Re*N, Le*N, Vas*N, Sd*N, Mms*N, Rms*N, Cms/N
        # Bl_eff = Bl_single * N
        eff.re = driver.re * count
        eff.le = driver.le * count
        eff.vas = driver.vas * count
        eff.sd = driver.sd * count
        eff.mms = eff.mms * count
        eff.rms = eff.rms * count
        eff.cms = eff.cms / count
        eff.bl = eff.bl * count
        eff.pe = driver.pe * count
        
    elif wiring == "isobaric":
        # Two drivers: Vas/2, Mms*2, Cms/2, Sd same.
        # Wiring of the pair (assume parallel)
        eff.vas = driver.vas / 2
        eff.mms = eff.mms * 2
        eff.cms = eff.cms / 2
        eff.rms = eff.rms * 2
        # Parallel wiring for the pair:
        eff.re = driver.re / 2
        eff.le = driver.le / 2
        # Bl stays same
        eff.pe = driver.pe * 2

    return eff


def impedance_array(
    driver: Driver,
    vb: float,
    fb: Optional[float],
    freqs: np.ndarray,
    box_type: str = "vented",
) -> np.ndarray:
    """
    Compute electrical impedance magnitude vs frequency (Ohms).
    Uses a robust complex acoustic nodal model including box losses.
    """
    mms = driver.mms if driver.mms > 0 else estimate_mms(driver)
    cms = driver.cms if driver.cms > 0 else estimate_cms(driver)
    bl = driver.bl if driver.bl > 0 else estimate_bl(driver, mms)
    rms_val = driver.rms if driver.rms > 0 else estimate_rms(driver, mms)
    re = driver.re if driver.re > 0 else 8.0
    le = driver.le if driver.le > 0 else 0.0

    kms = 1.0 / cms
    # Mechanical stiffness of air in box: rho * c^2 * Sd^2 / Vb
    kbox = RHO * C**2 * driver.sd**2 / vb
    ql = 7.0 # typical box loss

    z_elec = np.zeros(len(freqs), dtype=complex)

    for i, f in enumerate(freqs):
        omega = 2 * math.pi * f
        if omega == 0: 
            z_elec[i] = re
            continue
            
        # Electrical part: Re + j*omega*Le
        ze = complex(re, omega * le)

        # Motional part: Bl^2 / Zmech
        if box_type == "sealed":
            # Zm = Rms + j(w*Mms - (Kms + Kbox)/w)
            zm = complex(rms_val, omega * mms - (kms + kbox) / omega)
        elif box_type == "bp4":
            fb_use = fb if fb and fb > 0 else driver.fs
            k_rear = kbox # Vr
            v_front = vb # Front chamber Vf
            k_front = RHO * C**2 * driver.sd**2 / v_front
            
            zm_rear = complex(0, -k_rear / omega)
            zm_front = complex(0, -k_front / omega)
            m_port = k_front / (2 * math.pi * fb_use)**2
            zm_port = complex(0, omega * m_port)
            
            # Loss damping for front chamber
            r_front = ql * (2 * math.pi * fb_use) * m_port
            zm_front_loss = 1.0 / (1.0/zm_front + 1.0/r_front)
            
            zm_encl = (zm_front_loss * zm_port) / (zm_front_loss + zm_port)
            zm = complex(rms_val, omega * mms - kms / omega) + zm_rear + zm_encl
        else:
            # Vented or PR
            fb_use = fb if fb and fb > 0 else driver.fs
            m_port = kbox / (2 * math.pi * fb_use)**2
            zm_port = complex(0, omega * m_port)
            zm_box = complex(0, -kbox / omega)
            
            # Box losses
            r_box = ql * (2 * math.pi * fb_use) * m_port
            zm_box_loss = 1.0 / (1.0/zm_box + 1.0/r_box)
            
            zm_encl = (zm_box_loss * zm_port) / (zm_box_loss + zm_port)
            zm = complex(rms_val, omega * mms - kms / omega) + zm_encl

        z_motional = (bl**2 / zm) if abs(zm) > 0 else 0
        z_elec[i] = ze + z_motional

    return np.abs(z_elec)


def apply_le_correction(freqs: np.ndarray, spl: np.ndarray, le: float, re: float) -> np.ndarray:
    """Apply high-frequency rolloff due to voice coil inductance (Le)."""
    if le <= 0:
        return spl
    # 1st-order low-pass filter: H(s) = Re / (Re + s*Le)
    omega = 2 * math.pi * freqs
    tf_le = re / np.sqrt(re**2 + (omega * le)**2)
    return spl + 20 * np.log10(np.maximum(tf_le, 1e-12))


def apply_room_gain(freqs: np.ndarray, spl: np.ndarray, corner_freq: float = 40.0) -> np.ndarray:
    """
    Simulate room/cabin gain (approx +12 dB/oct below corner_freq).

    FIX (Bug 4): replaced the previous discontinuous step function with a
    smooth 4th-order shelving function:
        gain_dB = -10 * log10(1 + (fc/f)^4)
    which gives the correct +12 dB/oct asymptote at low frequencies
    and rolls off smoothly to 0 dB above corner_freq.
    """
    ratio = (corner_freq / np.maximum(freqs, 1e-6)) ** 4
    gain  = -10.0 * np.log10(1.0 + ratio)
    # gain is negative above corner, so subtracting it adds boost below corner
    return spl - gain


# ---------------------------------------------------------------------------
# Sealed box
# ---------------------------------------------------------------------------

def sealed_params(driver: Driver, vb: float) -> Dict:
    """
    Calculate sealed box parameters.

    Args:
        driver: Driver model
        vb: Box net volume m³

    Returns dict with qtc, fc, f3, alpha, vb_litres, ebp, box_type.
    """
    alpha = driver.vas / vb
    qtc = driver.qts * math.sqrt(1 + alpha)
    fc = driver.fs * math.sqrt(1 + alpha)

    # -3 dB frequency for 2nd-order high-pass
    x = 1.0 / qtc**2 - 2.0
    discriminant = x**2 + 4.0
    f3_norm = math.sqrt((x + math.sqrt(discriminant)) / 2.0)
    f3 = fc * f3_norm

    ebp = driver.fs / driver.qes if driver.qes > 0 else 0.0

    return {
        "qtc": qtc,
        "fc": fc,
        "f3": f3,
        "alpha": alpha,
        "vb_litres": vb * 1000,
        "ebp": ebp,
        "box_type": "sealed",
    }


def sealed_alignment_volume(driver: Driver, target_qtc: float = 0.707) -> float:
    """
    Solve for Vb that achieves *target_qtc* in a sealed box.
    Default 0.707 = Butterworth (maximally flat).
    Returns Vb in m³.
    """
    alpha = (target_qtc / driver.qts) ** 2 - 1
    if alpha <= 0:
        raise ValueError(
            f"Target Qtc={target_qtc} unreachable with Qts={driver.qts}"
        )
    return driver.vas / alpha


def sealed_spl_array(
    driver: Driver,
    vb: float,
    freqs: np.ndarray,
    input_power: float = 1.0,
) -> np.ndarray:
    """SPL vs frequency for sealed box (dB, 1 m)."""
    params = sealed_params(driver, vb)
    qtc = params["qtc"]
    fc = params["fc"]

    if driver.qes > 0:
        eta_0 = (
            4 * math.pi**2 * driver.fs**3 * driver.vas
        ) / (C**3 * driver.qes)
    else:
        eta_0 = 1e-10
    spl_ref = 10 * math.log10(max(eta_0 * input_power, 1e-30)) + 112.1

    # Vectorised 2nd-order high-pass
    wn = 1j * freqs / fc
    tf = np.abs(wn**2 / (wn**2 + wn / qtc + 1.0))
    spl_db = spl_ref + 20 * np.log10(np.maximum(tf, 1e-12))
    return apply_le_correction(freqs, spl_db, driver.le, driver.re)


# ---------------------------------------------------------------------------
# Vented box
# ---------------------------------------------------------------------------

def vented_params(driver: Driver, vb: float, fb: float) -> Dict:
    """
    Calculate vented (bass-reflex) box parameters.

    Returns dict with box_type, vb_litres, fb, alpha, h, efficiency,
    spl_1w1m, f3.
    """
    alpha = driver.vas / vb
    h = fb / driver.fs

    if driver.qes > 0:
        eff = (9.64e-10 * driver.fs**3 * driver.vas) / driver.qes
    else:
        eff = 0.0
    spl_1w1m = 10 * math.log10(max(eff, 1e-30)) + 112.1

    # f3: find from response array using our helper
    freqs_sim = np.logspace(0.5, 3, 500) # 3Hz to 1000Hz
    spl = vented_spl_array(driver, vb, fb, freqs_sim, input_power=1.0)
    f3 = find_f3(freqs_sim, spl)

    return {
        "box_type": "vented",
        "vb_litres": vb * 1000,
        "fb": fb,
        "alpha": alpha,
        "h": h,
        "efficiency": eff,
        "spl_1w1m": spl_1w1m,
        "f3": f3,
    }


def vented_alignment(
    driver: Driver, alignment: str = "QB3"
) -> Tuple[float, float]:
    """
    Return (Vb m³, Fb Hz) for a named vented alignment.

    Supported: QB3, SC4, B4, Butterworth / SBB4.
    Uses standard Thiele/Small alignment polynomials.

    FIX (Bug 2): B4 and SBB4 now correctly use h = 1.0 (Fb = Fs),
    per Small (1973). alpha formula corrected to (Qts/k)^2 - 1.
    SC4 uses h = 0.9 per its own polynomial condition.
    """
    qts = driver.qts
    if qts > 0.8:
        # High Qts drivers are generally not suitable for vented boxes.
        # Clamp Qts for alignment formula to prevent astronomical Vb values,
        # but the simulation will still use the real Qts.
        qts_for_formula = 0.8
    else:
        qts_for_formula = qts

    # Alignment polynomials from Thiele/Small (1971-1973) and Keele (1973).
    # alpha = Vas/Vb, h = Fb/Fs
    if alignment == "QB3":
        # Quasi-Butterworth 3rd order — from Keele (1973) Table I
        alpha = 1.0 / (20.0 * qts_for_formula**3.3)
        h = (0.26 * qts_for_formula + 0.86) * qts_for_formula**(-0.35)
    elif alignment == "B4":
        # Butterworth 4th order — Small (1973).
        # h = 1.0 (Fb = Fs always for B4); alpha = (Qts/0.383)^2 - 1
        alpha = max(0.0, (qts_for_formula / 0.383) ** 2 - 1.0)
        h = 1.0
    elif alignment == "SC4":
        # Sub-Chebyshev 4th order (0.1 dB passband ripple).
        alpha = max(0.0, (qts_for_formula / 0.315) ** 2 - 1.0)
        h = 0.9
    elif alignment in ("Butterworth", "SBB4"):
        # Super-Butterworth B4 — flat group delay version.
        # h = 1.0 condition same as B4; alpha from Qts/0.402 polynomial.
        alpha = max(0.0, (qts_for_formula / 0.402) ** 2 - 1.0)
        h = 1.0
    else:
        raise ValueError(f"Unknown alignment: {alignment}")

    # Clamp to physically reasonable values (Vb between 5% and 500% of Vas)
    alpha = max(0.002, min(alpha, 20.0))
    h = max(0.3, min(h, 3.0))

    vb = driver.vas / alpha
    fb = driver.fs * h
    return vb, fb


def vented_spl_array(
    driver: Driver,
    vb: float,
    fb: float,
    freqs: np.ndarray,
    input_power: float = 1.0,
) -> np.ndarray:
    """
    Compute SPL vs frequency for a vented box using the 4th-order
    Thiele/Small high-pass transfer function.

    FIX (Bug 1): w^2 denominator coefficient now includes the missing
    cross-loss term h/(Qts*Ql): h^2 + 1 + alpha + h/(Qts*Ql).

    Returns SPL in dB (at 1 m).
    """
    if driver.qes > 0:
        eta_0 = (
            4 * math.pi**2 * driver.fs**3 * driver.vas
        ) / (C**3 * driver.qes)
    else:
        eta_0 = 1e-10
    spl_ref = 10 * math.log10(max(eta_0 * input_power, 1e-30)) + 112.1

    ql = 7.0  # typical box losses Q
    alpha = driver.vas / vb
    h = fb / driver.fs
    qts = driver.qts

    # Normalised frequency x = f / fs
    x = freqs / driver.fs
    w = 1j * x

    # 4th-order polynomial from Small (1973), including cross-loss term.
    # w^2 coefficient = h^2 + 1 + alpha + h/(Qts*Ql)
    D = (
        w**4
        + w**3 * (h / qts + h / ql)
        + w**2 * (h**2 + 1.0 + alpha + h / (qts * ql))
        + w * (h / qts + h * (1.0 + alpha) / ql)
        + h**2
    )

    tf = np.abs(w**4 / D)

    # Convert to dB relative to spl_ref (at high frequency tf -> 1)
    spl_db = spl_ref + 20 * np.log10(np.maximum(tf, 1e-12))
    return apply_le_correction(freqs, spl_db, driver.le, driver.re)


# ---------------------------------------------------------------------------
# Bandpass 4th Order
# ---------------------------------------------------------------------------

def bandpass_4th_spl_array(
    driver: Driver,
    vr: float,
    vf: float,
    fb: float,
    freqs: np.ndarray,
    input_power: float = 1.0,
) -> np.ndarray:
    """
    Compute SPL vs frequency for a 4th-order bandpass enclosure.
    Vr = Rear sealed chamber volume, Vf = Front vented chamber volume.

    FIX (Bug 8): w^2 coefficient now includes the h/(Qts*Ql) cross-loss
    term, consistent with the vented_spl_array fix (Bug 1).
    """
    if driver.qes > 0:
        eta_0 = (4 * math.pi**2 * driver.fs**3 * driver.vas) / (C**3 * driver.qes)
    else:
        eta_0 = 1e-10
    spl_ref = 10 * math.log10(max(eta_0 * input_power, 1e-30)) + 112.1

    alpha_r = driver.vas / vr
    alpha_f = driver.vas / vf
    h = fb / driver.fs
    qts = driver.qts
    ql = 7.0

    wn = 1j * freqs / driver.fs

    # BP4 denominator with corrected w^2 cross-loss term
    D = (
        wn**4
        + wn**3 * (h / qts + h / ql)
        + wn**2 * (h**2 + 1.0 + alpha_r + alpha_f + h / (qts * ql))
        + wn * (h * (1.0 + alpha_r) / qts + h * (1.0 + alpha_r + alpha_f) / ql)
        + h**2 * (1.0 + alpha_r)
    )

    # Numerator for BP4: s^2 * alpha_f * h (output from front port)
    tf = np.abs((wn**2 * alpha_f * h) / D)

    spl_db = spl_ref + 20 * np.log10(np.maximum(tf, 1e-12))
    return apply_le_correction(freqs, spl_db, driver.le, driver.re)


def passive_radiator_spl_array(
    driver: Driver,
    pr_fs: float,
    pr_vas: float,
    pr_qms: float,
    vb: float,
    freqs: np.ndarray,
    input_power: float = 1.0,
) -> np.ndarray:
    """
    Compute SPL for a Passive Radiator enclosure.

    FIX (Bug 7 — three sub-fixes):
      1. Numerator corrected from wn^2*(wn^2+hp^2) to wn^4.
         The artificial notch was an excursion artefact, not a far-field
         SPL feature. Correct far-field SPL numerator is wn^4.
      2. w^2 denominator term now includes alpha_pr (was missing).
      3. w^1 denominator term now includes alpha_pr contribution.
    """
    if driver.qes > 0:
        eta_0 = (4 * math.pi**2 * driver.fs**3 * driver.vas) / (C**3 * driver.qes)
    else:
        eta_0 = 1e-10
    spl_ref = 10 * math.log10(max(eta_0 * input_power, 1e-30)) + 112.1

    alpha = driver.vas / vb
    alpha_pr = pr_vas / vb
    
    # Tuning frequency
    fb = pr_fs * math.sqrt(1 + pr_vas / vb)
    h = fb / driver.fs

    qts = driver.qts
    
    wn = 1j * freqs / driver.fs

    # Corrected 4th-order PR denominator with all alpha_pr terms present
    D = (
        wn**4
        + wn**3 * (h / qts + h / pr_qms)
        + wn**2 * (h**2 + 1.0 + alpha + alpha_pr + h / (qts * pr_qms))
        + wn * (h / qts + h * (1.0 + alpha + alpha_pr) / pr_qms)
        + h**2
    )

    # Correct far-field SPL numerator: wn^4
    tf = np.abs(wn**4 / D)
    
    spl_db = spl_ref + 20 * np.log10(np.maximum(tf, 1e-12))
    return apply_le_correction(freqs, spl_db, driver.le, driver.re)

# ---------------------------------------------------------------------------
# Cone excursion
# ---------------------------------------------------------------------------

def cone_excursion_array(
    driver: Driver,
    vb: float,
    fb: Optional[float],
    freqs: np.ndarray,
    input_power: float = 1.0,
    box_type: str = "vented",
    vf: Optional[float] = None, # Used for BP4
) -> Tuple[np.ndarray, float]:
    """
    Compute cone excursion vs frequency.
    Returns (excursion_mm array, xmax_mm).
    """
    re = driver.re if driver.re > 0 else 8.0
    # V_peak = sqrt(2 * P * Re) for peak excursion
    v_peak = math.sqrt(2.0 * input_power * re)

    mms = driver.mms if driver.mms > 0 else estimate_mms(driver)
    cms = driver.cms if driver.cms > 0 else estimate_cms(driver)
    rms_val = driver.rms if driver.rms > 0 else estimate_rms(driver, mms)
    bl = driver.bl if driver.bl > 0 else estimate_bl(driver, mms)

    kms = 1.0 / cms
    # Acoustic stiffness of the box: K_ab = rho * c^2 / Vb
    # Mechanical equivalent: K_mb = K_ab * Sd^2
    kbox = RHO * C**2 * driver.sd**2 / vb
    
    # Enclosure losses Ql (standard default is 7)
    ql = 7.0

    excursion = np.zeros(len(freqs))

    for i, f in enumerate(freqs):
        omega = 2 * math.pi * f
        if omega == 0: continue

        # Mechanical impedance of the driver itself
        # Z_m = Rms + j(w*Mms - Kms/w)
        zm_driver = complex(rms_val, omega * mms - kms / omega)
        
        # Electromagnetic damping (back-EMF)
        zm_em = (bl**2) / re

        if box_type == "sealed":
            zm_box = complex(0, -kbox / omega)
            z_total = zm_driver + zm_em + zm_box
        elif box_type == "bp4":
            fb_use = fb if fb and fb > 0 else driver.fs
            k_rear = kbox # Vr
            v_front = vf if vf else 0.1
            k_front = RHO * C**2 * driver.sd**2 / v_front
            
            # Enclosure mechanical impedance (Front chamber + Port)
            m_port = k_front / (2 * math.pi * fb_use)**2
            zm_port = complex(0, omega * m_port)
            zm_front = complex(0, -k_front / omega)
            
            # Add Ql damping to front chamber: R_ml = Ql * w_b * M_mp
            r_front = ql * (2 * math.pi * fb_use) * (k_front / (2 * math.pi * fb_use)**2)
            zm_front_loss = 1.0 / (1.0/zm_front + 1.0/r_front)
            
            # Port and Front chamber are in parallel mechanically
            zm_encl = (zm_front_loss * zm_port) / (zm_front_loss + zm_port)
            z_total = zm_driver + zm_em + complex(0, -k_rear / omega) + zm_encl
        else:
            # Vented or PR
            fb_use = fb if fb and fb > 0 else driver.fs
            m_port = kbox / (2 * math.pi * fb_use)**2
            zm_port = complex(0, omega * m_port)
            zm_box = complex(0, -kbox / omega)
            
            # Add Ql damping: R_ml = Ql * w_b * M_mp
            r_box = ql * (2 * math.pi * fb_use) * m_port
            zm_box_loss = 1.0 / (1.0/zm_box + 1.0/r_box)
            
            zm_encl = (zm_box_loss * zm_port) / (zm_box_loss + zm_port)
            z_total = zm_driver + zm_em + zm_encl

        # Velocity v = F / Z = (V * Bl / Re) / Z_total_m
        vel = (v_peak * bl) / (re * abs(z_total))
        xpeak = vel / omega
        excursion[i] = xpeak * 1000

    return excursion, driver.xmax * 1000

# ---------------------------------------------------------------------------
# Group delay
# ---------------------------------------------------------------------------

def complex_transfer_function(
    driver: Driver,
    vb: float,
    fb: Optional[float],
    freqs: np.ndarray,
    box_type: str = "vented",
    vf: Optional[float] = None,
    pr_fs: Optional[float] = None,
    pr_vas: Optional[float] = None,
    pr_qms: Optional[float] = None,
) -> np.ndarray:
    """
    Returns the complex transfer function H(s) for the given enclosure.

    FIX (Bug 3): All vented/BP4/PR denominators now include the
    h/(Qts*Ql) cross-loss term in the w^2 coefficient, matching
    the vented_spl_array correction (Bug 1).
    """
    wn = 1j * freqs / driver.fs
    ql = 7.0
    
    if box_type == "sealed":
        params = sealed_params(driver, vb)
        qtc, fc = params["qtc"], params["fc"]
        # Rescale wn for fc
        wn_c = 1j * freqs / fc
        return wn_c**2 / (wn_c**2 + wn_c / qtc + 1.0)
    
    elif box_type == "bp4":
        vr = vb
        v_front = vf if vf else 0.1
        alpha_r = driver.vas / vr
        alpha_f = driver.vas / v_front
        h = (fb if fb else 40.0) / driver.fs
        qts = driver.qts
        D = (
            wn**4
            + wn**3 * (h / qts + h / ql)
            + wn**2 * (h**2 + 1.0 + alpha_r + alpha_f + h / (qts * ql))
            + wn * (h * (1.0 + alpha_r) / qts + h * (1.0 + alpha_r + alpha_f) / ql)
            + h**2 * (1.0 + alpha_r)
        )
        return (wn**2 * alpha_f * h) / D

    elif box_type == "pr":
        alpha    = driver.vas / vb
        alpha_pr = (pr_vas if pr_vas else driver.vas) / vb
        f_tuning = fb if fb else 40.0
        h        = f_tuning / driver.fs
        qts      = driver.qts
        q_pr     = pr_qms if pr_qms else 5.0
        D = (
            wn**4
            + wn**3 * (h / qts + h / q_pr)
            + wn**2 * (h**2 + 1.0 + alpha + alpha_pr + h / (qts * q_pr))
            + wn    * (h / qts + h * (1.0 + alpha + alpha_pr) / q_pr)
            + h**2
        )
        return wn**4 / D

    else:  # vented
        alpha = driver.vas / vb
        h = (fb if fb else 40.0) / driver.fs
        qts = driver.qts
        D = (
            wn**4
            + wn**3 * (h / qts + h / ql)
            + wn**2 * (h**2 + 1.0 + alpha + h / (qts * ql))
            + wn * (h / qts + h * (1.0 + alpha) / ql)
            + h**2
        )
        return wn**4 / D


def group_delay_array(
    driver: Driver,
    vb: float,
    fb: Optional[float],
    freqs: np.ndarray,
    box_type: str = "vented",
    vf: Optional[float] = None,
    pr_fs: Optional[float] = None,
    pr_vas: Optional[float] = None,
    pr_qms: Optional[float] = None,
) -> np.ndarray:
    """
    Compute group delay vs frequency in milliseconds.
    Uses numerical differentiation of the phase response.
    """
    df = 0.1

    tf1 = complex_transfer_function(driver, vb, fb, freqs,      box_type, vf, pr_fs, pr_vas, pr_qms)
    tf2 = complex_transfer_function(driver, vb, fb, freqs + df, box_type, vf, pr_fs, pr_vas, pr_qms)

    phase1 = np.angle(tf1)
    phase2 = np.angle(tf2)

    dphi   = np.unwrap(phase2 - phase1)
    domega = 2 * math.pi * df
    gd_s   = -dphi / domega
    return gd_s * 1000  # ms


# ---------------------------------------------------------------------------
# Port length / velocity
# ---------------------------------------------------------------------------

def port_length_for_tuning(
    fb: float,
    vb: float,
    port_area: float,
    num_ports: int = 1,
    end_correction: float = 0.732,
) -> float:
    """
    Calculate port length for target tuning frequency using the
    Helmholtz resonator formula with end correction.

    Returns port length in metres.
    """
    total_area = port_area * num_ports
    l_eff = (C**2 * total_area) / (4 * math.pi**2 * fb**2 * vb)
    l_phys = l_eff - end_correction * math.sqrt(port_area / math.pi)
    return max(0.01, l_phys)


def find_f3(freqs: np.ndarray, spl: np.ndarray) -> float:
    """
    Find the -3 dB frequency relative to the passband average.
    """
    if len(spl) == 0:
        return 0.0
    mask = (freqs >= 150) & (freqs <= 250)
    if np.any(mask):
        ref = np.mean(spl[mask])
    else:
        ref = np.max(spl)

    target = ref - 3.0
    for i in range(len(spl) - 1):
        if spl[i] < target <= spl[i + 1]:
            f1, f2 = freqs[i], freqs[i + 1]
            s1, s2 = spl[i],   spl[i + 1]
            return f1 + (f2 - f1) * (target - s1) / (s2 - s1)
    return 0.0


def port_air_velocity_array(
    driver: Driver,
    vb: float,
    fb: float,
    port_area: float,
    num_ports: int,
    freqs: np.ndarray,
    input_power: float = 1.0,
    box_type: str = "vented",
    vf: Optional[float] = None,
) -> np.ndarray:
    """
    Compute peak port air velocity vs frequency (m/s).
    """
    re      = driver.re  if driver.re  > 0 else 8.0
    v_peak  = math.sqrt(2.0 * input_power * re)

    mms     = driver.mms if driver.mms > 0 else estimate_mms(driver)
    bl      = driver.bl  if driver.bl  > 0 else estimate_bl(driver, mms)
    rms_val = driver.rms if driver.rms > 0 else estimate_rms(driver, mms)
    cms     = driver.cms if driver.cms > 0 else estimate_cms(driver)

    kms        = 1.0 / cms
    kbox       = RHO * C**2 * driver.sd**2 / vb
    total_area = port_area * num_ports
    ql         = 7.0

    velocities = np.zeros(len(freqs))

    for i, f in enumerate(freqs):
        omega = 2 * math.pi * f
        if omega == 0:
            continue

        zm_driver_em = complex(rms_val + (bl**2 / re), omega * mms - kms / omega)

        if box_type == "bp4":
            k_rear  = kbox
            v_front = vf if vf else 0.1
            k_front = RHO * C**2 * driver.sd**2 / v_front
            m_port  = k_front / (2 * math.pi * fb)**2
            zm_rear = complex(0, -k_rear / omega)
            zm_f_chamber = complex(0, -k_front / omega)
            r_front = ql * (2 * math.pi * fb) * m_port
            zm_f_chamber_loss = 1.0 / (1.0/zm_f_chamber + 1.0/r_front)
            zm_f_port    = complex(0, omega * m_port)
            zm_parallel  = (zm_f_chamber_loss * zm_f_port) / (zm_f_chamber_loss + zm_f_port)
            u_cone = (v_peak * bl / re) / abs(zm_driver_em + zm_rear + zm_parallel)
            u_port = u_cone * abs(zm_f_chamber_loss / (zm_f_chamber_loss + zm_f_port))
        else:
            m_port      = kbox / (2 * math.pi * fb)**2
            zm_box      = complex(0, -kbox / omega)
            r_box       = ql * (2 * math.pi * fb) * m_port
            zm_box_loss = 1.0 / (1.0/zm_box + 1.0/r_box)
            zm_port     = complex(0, omega * m_port)
            zm_parallel = (zm_box_loss * zm_port) / (zm_box_loss + zm_port)
            u_cone = (v_peak * bl / re) / abs(zm_driver_em + zm_parallel)
            u_port = u_cone * abs(zm_box_loss / (zm_box_loss + zm_port))

        velocities[i] = (u_port * driver.sd) / total_area

    return velocities


def pr_excursion_array(
    driver: Driver,
    pr_sd: float,
    vb: float,
    fb: float,
    freqs: np.ndarray,
    cone_excursion: np.ndarray,
) -> np.ndarray:
    """
    Compute Passive Radiator excursion (mm) based on driver excursion.
    """
    ratio_sd      = driver.sd / pr_sd
    freq_ratio_sq = (freqs / fb)**2
    transfer      = 1.0 / np.abs(1.0 - freq_ratio_sq + 1e-6)
    return cone_excursion * ratio_sd * transfer


# ---------------------------------------------------------------------------
# Recommendation helper
# ---------------------------------------------------------------------------

def recommended_vb_range(driver: Driver) -> Dict:
    """
    Suggest reasonable Vb range based on T/S params.
    """
    ebp = driver.fs / driver.qes if driver.qes > 0 else 50.0

    if ebp < 50:
        box_rec = "sealed"
    elif ebp > 100:
        box_rec = "vented"
    else:
        box_rec = "either"

    try:
        vb_sealed_opt = sealed_alignment_volume(driver, target_qtc=0.707)
    except ValueError:
        vb_sealed_opt = driver.vas
    vb_sealed_min = driver.vas * 0.3
    vb_sealed_max = driver.vas * 3.0

    vb_vented_opt, fb_opt = vented_alignment(driver, "QB3")

    return {
        "ebp": ebp,
        "box_type_recommendation": box_rec,
        "sealed": {
            "optimal_litres": vb_sealed_opt * 1000,
            "min_litres":     vb_sealed_min * 1000,
            "max_litres":     vb_sealed_max * 1000,
        },
        "vented": {
            "optimal_litres": vb_vented_opt * 1000,
            "optimal_fb_hz":  fb_opt,
        },
    }
