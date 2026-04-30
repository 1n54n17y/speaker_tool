"""
Unit conversion helpers. Internal representation is always SI.
"""
from enum import Enum
from typing import Union


class UnitSystem(str, Enum):
    METRIC = "metric"
    IMPERIAL = "imperial"


# Conversion factors TO SI
MM_TO_M = 1e-3
CM_TO_M = 1e-2
INCH_TO_M = 0.0254
LITRE_TO_M3 = 1e-3
CM3_TO_M3 = 1e-6
INCH3_TO_M3 = 1.6387064e-5
MH_TO_H = 1e-3
CM2_TO_M2 = 1e-4


def mm_to_m(v: float) -> float:
    return v * MM_TO_M


def m_to_mm(v: float) -> float:
    return v / MM_TO_M


def cm_to_m(v: float) -> float:
    return v * CM_TO_M


def m_to_cm(v: float) -> float:
    return v / CM_TO_M


def litre_to_m3(v: float) -> float:
    return v * LITRE_TO_M3


def m3_to_litre(v: float) -> float:
    return v / LITRE_TO_M3


def inch_to_m(v: float) -> float:
    return v * INCH_TO_M


def m_to_inch(v: float) -> float:
    return v / INCH_TO_M


def inch3_to_m3(v: float) -> float:
    return v * INCH3_TO_M3


def m3_to_inch3(v: float) -> float:
    return v / INCH3_TO_M3


def cm3_to_m3(v: float) -> float:
    return v * CM3_TO_M3


def m3_to_cm3(v: float) -> float:
    return v / CM3_TO_M3


def cm2_to_m2(v: float) -> float:
    return v * CM2_TO_M2


def m2_to_cm2(v: float) -> float:
    return v / CM2_TO_M2


def mh_to_h(v: float) -> float:
    return v * MH_TO_H


def h_to_mh(v: float) -> float:
    return v / MH_TO_H
