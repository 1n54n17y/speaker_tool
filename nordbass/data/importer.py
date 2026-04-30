"""
CSV import / export for driver databases.
Flexible column-name matching for import; canonical names for export.
"""
import csv
import io
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..core.models import Driver
from ..core.units import cm2_to_m2, litre_to_m3, mh_to_h, mm_to_m

# ── Column name mapping ──────────────────────────────────────────────────

# Maps possible CSV column names (lowercase, stripped) → (model field, converter)
# converter is a callable: raw_string → SI float
_IDENTITY = float
_FROM_LITRES = lambda v: litre_to_m3(float(v))
_FROM_CM2 = lambda v: cm2_to_m2(float(v))
_FROM_MM = lambda v: mm_to_m(float(v))
_FROM_MH = lambda v: mh_to_h(float(v))
_STR = str

_COLUMN_MAP: Dict[str, Tuple[str, object]] = {}

# Name / manufacturer
for alias in ("name", "driver", "model", "driver_name", "model_name"):
    _COLUMN_MAP[alias] = ("name", _STR)
for alias in ("manufacturer", "brand", "make", "mfr"):
    _COLUMN_MAP[alias] = ("manufacturer", _STR)

# TS numeric fields
for alias in ("fs", "fs_hz", "resonant_freq", "resonant_frequency"):
    _COLUMN_MAP[alias] = ("fs", _IDENTITY)
for alias in ("qts", "total_q", "q_ts"):
    _COLUMN_MAP[alias] = ("qts", _IDENTITY)
for alias in ("qes", "electrical_q", "q_es"):
    _COLUMN_MAP[alias] = ("qes", _IDENTITY)
for alias in ("qms", "mechanical_q", "q_ms"):
    _COLUMN_MAP[alias] = ("qms", _IDENTITY)

# Vas – detect unit
for alias in ("vas_l", "vas_litres", "vas_liters"):
    _COLUMN_MAP[alias] = ("vas", _FROM_LITRES)
for alias in ("vas", "vas_m3"):
    # If bare "vas", assume litres (most common in datasheets)
    _COLUMN_MAP[alias] = ("vas", _FROM_LITRES)

# Sd
for alias in ("sd_cm2", "cone_area", "sd_cm"):
    _COLUMN_MAP[alias] = ("sd", _FROM_CM2)
for alias in ("sd", "sd_m2"):
    # bare "sd" – assume cm² (datasheet convention)
    _COLUMN_MAP[alias] = ("sd", _FROM_CM2)

# Xmax
for alias in ("xmax_mm", "xmax"):
    _COLUMN_MAP[alias] = ("xmax", _FROM_MM)

# Re
for alias in ("re", "dc_resistance", "re_ohm"):
    _COLUMN_MAP[alias] = ("re", _IDENTITY)

# Le
for alias in ("le_mh", "le_mh"):
    _COLUMN_MAP[alias] = ("le", _FROM_MH)
for alias in ("le",):
    _COLUMN_MAP[alias] = ("le", _FROM_MH)  # assume mH

# Bl
for alias in ("bl", "force_factor", "bl_tm"):
    _COLUMN_MAP[alias] = ("bl", _IDENTITY)

# Pe
for alias in ("pe", "power", "rms_power", "power_handling"):
    _COLUMN_MAP[alias] = ("pe", _IDENTITY)

# Mms
for alias in ("mms", "mms_g", "moving_mass"):
    _COLUMN_MAP[alias] = ("mms", lambda v: float(v) / 1000.0)  # g → kg

# Sensitivity
for alias in ("sensitivity", "spl_1w1m", "spl"):
    _COLUMN_MAP[alias] = ("sensitivity", _IDENTITY)

# Notes
for alias in ("notes", "comment", "comments"):
    _COLUMN_MAP[alias] = ("notes", _STR)


def _match_column(header: str) -> Optional[Tuple[str, object]]:
    key = header.strip().lower().replace(" ", "_")
    return _COLUMN_MAP.get(key)


# ── Import ───────────────────────────────────────────────────────────────

def import_csv(filepath: str) -> List[Driver]:
    """
    Import drivers from a CSV file.
    Returns list of Driver objects (unsaved).
    Skips rows with missing required fields (fs, qts, qes, qms, vas, sd, xmax, pe, re).
    """
    path = Path(filepath)
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []

        col_mapping: Dict[str, Tuple[str, object]] = {}
        for col in reader.fieldnames:
            match = _match_column(col)
            if match:
                col_mapping[col] = match

        drivers: List[Driver] = []
        required = {"fs", "qts", "qes", "qms", "vas", "sd"}

        for row in reader:
            data: Dict = {}
            for csv_col, (field, converter) in col_mapping.items():
                raw = row.get(csv_col, "").strip()
                if not raw:
                    continue
                try:
                    data[field] = converter(raw)  # type: ignore[operator]
                except (ValueError, TypeError):
                    continue

            # Check required fields present
            if not required.issubset(data.keys()):
                continue
            
            # Default Re if missing
            if "re" not in data:
                data["re"] = 4.0

            if "name" not in data:
                data["name"] = "Unnamed Driver"

            try:
                drivers.append(Driver(**data))
            except Exception:
                continue

        return drivers


# ── Export ───────────────────────────────────────────────────────────────

_EXPORT_COLUMNS = [
    ("name", "Name", lambda d: d.name),
    ("manufacturer", "Manufacturer", lambda d: d.manufacturer),
    ("fs", "Fs (Hz)", lambda d: d.fs),
    ("qts", "Qts", lambda d: d.qts),
    ("qes", "Qes", lambda d: d.qes),
    ("qms", "Qms", lambda d: d.qms),
    ("vas", "Vas (L)", lambda d: d.vas * 1000),
    ("re", "Re (Ohm)", lambda d: d.re),
    ("le", "Le (mH)", lambda d: d.le * 1000),
    ("bl", "BL (T·m)", lambda d: d.bl),
    ("sd", "Sd (cm²)", lambda d: d.sd * 1e4),
    ("xmax", "Xmax (mm)", lambda d: d.xmax * 1000),
    ("pe", "Pe (W)", lambda d: d.pe),
    ("mms", "Mms (g)", lambda d: d.mms * 1000),
    ("sensitivity", "Sensitivity (dB)", lambda d: d.sensitivity),
    ("notes", "Notes", lambda d: d.notes),
]


def export_csv(drivers: List[Driver], filepath: str) -> None:
    """Export list of drivers to CSV with canonical column names."""
    path = Path(filepath)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([col[1] for col in _EXPORT_COLUMNS])
        for d in drivers:
            writer.writerow([col[2](d) for col in _EXPORT_COLUMNS])
