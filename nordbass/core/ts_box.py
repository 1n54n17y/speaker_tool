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
    
    eff.mms = estimate_mms(eff)
    eff.cms = estimate_cms(eff)
    eff.rms = estimate_rms(eff, eff.mms)
    eff.bl  = estimate_bl(eff, eff.mms)

    if count <= 1:
        return eff

    if wiring == "parallel":
        eff.re = driver.re / count
        eff.le = driver.le / count
        eff.vas = driver.vas * count
        eff.sd = driver.sd * count
        eff.mms = eff.mms * count
        eff.rms = eff.rms * count
        eff.cms = eff.cms / count
        eff.pe = driver.pe * count
        
    elif wiring == "series":
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
        eff.vas = driver.vas / 2
        eff.mms = eff.mms * 2
        eff.cms = eff.cms / 2
        eff.rms = eff.rms * 2
        eff.re = driver.re / 2
        eff.le = driver.le / 2
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
    """
    mms = driver.mms if driver.mms > 0 else estimate_mms(driver)
    cms = driver.cms if driver.cms > 0 else estimate_cms(driver)
    bl = driver.bl if driver.bl > 0 else estimate_bl(driver, mms)
    rms_val = driver.rms if driver.rms > 0 else estimate_rms(driver, mms)
    re = driver.re if driver.re > 0 else 8.0
    le = driver.le if driver.le > 0 else 0.0

    kms = 1.0 / cms
    kbox = RHO * C**2 * driver.sd**2 / vb
    ql = 7.0

    z_elec = np.zeros(len(freqs), dtype=complex)

    for i, f in enumerate(freqs):
        omega = 2 * math.pi * f
        if omega == 0: 
            z_elec[i] = re
            continue
            
        ze = complex(re, omega * le)

        if box_type == "sealed":
            zm = complex(rms_val, omega * mms - (kms + kbox) / omega)
        elif box_type == "bp4":
            fb_use = fb if fb and fb > 0 else driver.fs
            k_rear = kbox
            v_front = vb
            k_front = RHO * C**2 * driver.sd**2 / v_front
            zm_rear = complex(0, -k_rear / omega)
            zm_front = complex(0, -k_front / omega)
            m_port = k_front / (2 * math.pi * fb_use)**2
            zm_port = complex(0, omega * m_port)
            r_front = ql * (2 * math.pi * fb_use) * m_port
            zm_front_loss = 1.0 / (1.0/zm_front + 1.0/r_front)
            zm_encl = (zm_front_loss * zm_port) / (zm_front_loss + zm_port)
            zm = complex(rms_val, omega * mms - kms / omega) + zm_rear + zm_encl
        else:
            fb_use = fb if fb and fb > 0 else driver.fs
            m_port = kbox / (2 * math.pi * fb_use)**2
            zm_port = complex(0, omega * m_port)
            zm_box = complex(0, -kbox / omega)
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
    omega = 2 * math.pi * freqs
    tf_le = re / np.sqrt(re**2 + (omega * le)**2)
    return spl + 20 * np.log10(np.maximum(tf_le, 1e-12))


def apply_room_gain(freqs: np.ndarray, spl: np.ndarray, corner_freq: float = 40.0) -> np.ndarray:
    """
    Simulate room/cabin gain (approx +12 dB/oct below corner_freq).
    """
    ratio = (corner_freq / np.maximum(freqs, 1e-6)) ** 4
    gain  = -10.0 * np.log10(1.0 + ratio)
    return spl - gain


# ---------------------------------------------------------------------------
# Sealed box
# ---------------------------------------------------------------------------

def sealed_params(driver: Driver, vb: float) -> Dict:
    alpha = driver.vas / vb
    qtc = driver.qts * math.sqrt(1 + alpha)
    fc = driver.fs * math.sqrt(1 + alpha)

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

    wn = 1j * freqs / fc
    tf = np.abs(wn**2 / (wn**2 + wn / qtc + 1.0))
    spl_db = spl_ref + 20 * np.log10(np.maximum(tf, 1e-12))
    return apply_le_correction(freqs, spl_db, driver.le, driver.re)


# ---------------------------------------------------------------------------
# Vented box
# ---------------------------------------------------------------------------

def vented_params(driver: Driver, vb: float, fb: float) -> Dict:
    alpha = driver.vas / vb
    h = fb / driver.fs

    if driver.qes > 0:
        eff = (9.64e-10 * driver.fs**3 * driver.vas) / driver.qes
    else:
        eff = 0.0
    spl_1w1m = 10 * math.log10(max(eff, 1e-30)) + 112.1

    freqs_sim = np.logspace(0.5, 3, 500)
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
    qts = driver.qts
    if qts > 0.8:
        qts_for_formula = 0.8
    else:
        qts_for_formula = qts

    if alignment == "QB3":
        alpha = 1.0 / (20.0 * qts_for_formula**3.3)
        h = (0.26 * qts_for_formula + 0.86) * qts_for_formula**(-0.35)
    elif alignment == "B4":
        alpha = max(0.0, (qts_for_formula / 0.383) ** 2 - 1.0)
        h = 1.0
    elif alignment == "SC4":
        alpha = max(0.0, (qts_for_formula / 0.315) ** 2 - 1.0)
        h = 0.9
    elif alignment in ("Butterworth", "SBB4"):
        alpha = max(0.0, (qts_for_formula / 0.402) ** 2 - 1.0)
        h = 1.0
    else:
        raise ValueError(f"Unknown alignment: {alignment}")

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
    if driver.qes > 0:
        eta_0 = (
            4 * math.pi**2 * driver.fs**3 * driver.vas
        ) / (C**3 * driver.qes)
    else:
        eta_0 = 1e-10
    spl_ref = 10 * math.log10(max(eta_0 * input_power, 1e-30)) + 112.1

    ql = 7.0
    alpha = driver.vas / vb
    h = fb / driver.fs
    qts = driver.qts

    x = freqs / driver.fs
    w = 1j * x

    D = (
        w**4
        + w**3 * (h / qts + h / ql)
        + w**2 * (h**2 + 1.0 + alpha + h / (qts * ql))
        + w * (h / qts + h * (1.0 + alpha) / ql)
        + h**2
    )

    tf = np.abs(w**4 / D)
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

    D = (
        wn**4
        + wn**3 * (h / qts + h / ql)
        + wn**2 * (h**2 + 1.0 + alpha_r + alpha_f + h / (qts * ql))
        + wn * (h * (1.0 + alpha_r) / qts + h * (1.0 + alpha_r + alpha_f) / ql)
        + h**2 * (1.0 + alpha_r)
    )

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
    if driver.qes > 0:
        eta_0 = (4 * math.pi**2 * driver.fs**3 * driver.vas) / (C**3 * driver.qes)
    else:
        eta_0 = 1e-10
    spl_ref = 10 * math.log10(max(eta_0 * input_power, 1e-30)) + 112.1

    alpha = driver.vas / vb
    alpha_pr = pr_vas / vb
    fb = pr_fs * math.sqrt(1 + pr_vas / vb)
    h = fb / driver.fs
    qts = driver.qts
    wn = 1j * freqs / driver.fs

    D = (
        wn**4
        + wn**3 * (h / qts + h / pr_qms)
        + wn**2 * (h**2 + 1.0 + alpha + alpha_pr + h / (qts * pr_qms))
        + wn * (h / qts + h * (1.0 + alpha + alpha_pr) / pr_qms)
        + h**2
    )

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
    vf: Optional[float] = None,
) -> Tuple[np.ndarray, float]:
    re = driver.re if driver.re > 0 else 8.0
    v_peak = math.sqrt(2.0 * input_power * re)

    mms = driver.mms if driver.mms > 0 else estimate_mms(driver)
    cms = driver.cms if driver.cms > 0 else estimate_cms(driver)
    rms_val = driver.rms if driver.rms > 0 else estimate_rms(driver, mms)
    bl = driver.bl if driver.bl > 0 else estimate_bl(driver, mms)

    kms = 1.0 / cms
    kbox = RHO * C**2 * driver.sd**2 / vb
    ql = 7.0

    excursion = np.zeros(len(freqs))

    for i, f in enumerate(freqs):
        omega = 2 * math.pi * f
        if omega == 0: continue

        zm_driver = complex(rms_val, omega * mms - kms / omega)
        zm_em = (bl**2) / re

        if box_type == "sealed":
            zm_box = complex(0, -kbox / omega)
            z_total = zm_driver + zm_em + zm_box
        elif box_type == "bp4":
            fb_use = fb if fb and fb > 0 else driver.fs
            k_rear = kbox
            v_front = vf if vf else 0.1
            k_front = RHO * C**2 * driver.sd**2 / v_front
            m_port = k_front / (2 * math.pi * fb_use)**2
            zm_port = complex(0, omega * m_port)
            zm_front = complex(0, -k_front / omega)
            r_front = ql * (2 * math.pi * fb_use) * (k_front / (2 * math.pi * fb_use)**2)
            zm_front_loss = 1.0 / (1.0/zm_front + 1.0/r_front)
            zm_encl = (zm_front_loss * zm_port) / (zm_front_loss + zm_port)
            z_total = zm_driver + zm_em + complex(0, -k_rear / omega) + zm_encl
        else:
            fb_use = fb if fb and fb > 0 else driver.fs
            m_port = kbox / (2 * math.pi * fb_use)**2
            zm_port = complex(0, omega * m_port)
            zm_box = complex(0, -kbox / omega)
            r_box = ql * (2 * math.pi * fb_use) * m_port
            zm_box_loss = 1.0 / (1.0/zm_box + 1.0/r_box)
            zm_encl = (zm_box_loss * zm_port) / (zm_box_loss + zm_port)
            z_total = zm_driver + zm_em + zm_encl

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
    wn = 1j * freqs / driver.fs
    ql = 7.0
    
    if box_type == "sealed":
        params = sealed_params(driver, vb)
        qtc, fc = params["qtc"], params["fc"]
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
    df = 0.1
    tf1 = complex_transfer_function(driver, vb, fb, freqs,      box_type, vf, pr_fs, pr_vas, pr_qms)
    tf2 = complex_transfer_function(driver, vb, fb, freqs + df, box_type, vf, pr_fs, pr_vas, pr_qms)
    phase1 = np.angle(tf1)
    phase2 = np.angle(tf2)
    dphi   = np.unwrap(phase2 - phase1)
    domega = 2 * math.pi * df
    gd_s   = -dphi / domega
    return gd_s * 1000


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
    total_area = port_area * num_ports
    l_eff = (C**2 * total_area) / (4 * math.pi**2 * fb**2 * vb)
    l_phys = l_eff - end_correction * math.sqrt(port_area / math.pi)
    return max(0.01, l_phys)


def find_f3(freqs: np.ndarray, spl: np.ndarray) -> float:
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
    pr_qms: float,
    vb: float,
    fb: float,
    freqs: np.ndarray,
    cone_excursion: np.ndarray,
) -> np.ndarray:
    """
    Compute Passive Radiator excursion (mm) from driver cone excursion.

    FIX: Previous formula used an undamped resonance denominator
    (1 - (f/fb)^2) which blew up to infinity at f=fb, causing the
    huge excursion spike visible in the graph. Replaced with a
    proper damped second-order transfer function that includes pr_qms
    as the Q term, preventing the singularity.
    """
    ratio_sd = driver.sd / pr_sd
    fn = freqs / fb  # normalised frequency
    # Damped 2nd-order resonance: H = fn^2 / sqrt((1-fn^2)^2 + (fn/pr_qms)^2)
    denom = np.sqrt((1.0 - fn**2)**2 + (fn / pr_qms)**2)
    transfer = fn**2 / np.maximum(denom, 1e-9)
    return cone_excursion * ratio_sd * transfer


# ---------------------------------------------------------------------------
# Recommendation helper
# ---------------------------------------------------------------------------

def recommended_vb_range(driver: Driver) -> Dict:
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
