"""
.nordproj project file — save and load.

Format: ZIP container with a project.json root file plus sub-folders.

    my_design.nordproj
    ├── project.json          ← main manifest (human-readable)
    ├── drivers/
    │   └── <driver_id>.json  ← full T/S + physical data for each driver used
    └── simulations/
        └── latest.json       ← last simulation results (optional)

The file extension is .nordproj.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

FORMAT_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_project(state, path: Path, driver=None) -> None:
    """
    Serialise ProjectState (and optionally the current Driver) to a .nordproj
    ZIP file at *path*.

    Parameters
    ----------
    state : ProjectState
        The singleton returned by get_state().
    path : Path
        Destination file path (should end in .nordproj).
    driver : Driver | None
        The currently selected driver object (fetched from DB by caller).
    """
    now = datetime.now(timezone.utc).isoformat()

    # ── project.json ──────────────────────────────────────────────────────
    project_json = {
        "formatVersion": FORMAT_VERSION,
        "name":          state.project_name,
        "description":   state.description,
        "author":        state.author,
        "created":       now,   # will be overwritten on re-save if we track it
        "modified":      now,
        "version":       "1.0.0",
        "settings": {
            "theme":    state.theme,
            "autoSave": state.auto_save,
        },
        "simulation": {
            "boxType":   state.box_type,
            "volume":    state.volume_l,
            "fb":        state.fb_hz,
            "alignment": state.alignment,
            "inputPower": state.input_power_w,
        },
        "port": {
            "shape":      state.port.shape,
            "diameterMm": state.port.diameter_mm,
            "slotWMm":    state.port.slot_w_mm,
            "slotHMm":    state.port.slot_h_mm,
            "count":      state.port.count,
            "lengthM":    state.port.length_m,
        },
        "geometry": {
            "path":           "geometry/box_dimensions.json",
            "volumeL":        state.geometry.volume_l,
            "thicknessMm":    state.geometry.thickness_mm,
            "doubleFront":    state.geometry.double_front,
            "fixedWidthMm":   state.geometry.fixed_width_mm,
            "fixedDepthMm":   state.geometry.fixed_depth_mm,
            "fixedHeightMm":  state.geometry.fixed_height_mm,
            "portFace":       state.geometry.port_face,
            "portPosition":   state.geometry.port_position,
            "material":       "MDF",
        },
        "flare": {
            "path":             "flare/analysis.json",
            "portShape":        state.flare.port_shape,
            "diameterMm":       state.flare.diameter_mm,
            "slotWMm":          state.flare.slot_w_mm,
            "slotHMm":          state.flare.slot_h_mm,
            "flareRadiusMm":    state.flare.flare_mm,
            "masking":          state.flare.masking,
            "targetVelocity":   state.flare.target_vel,
        },
        "drivers": [],
        "metadata": {
            "platform":    "desktop",
            "appVersion":  "0.1.17",
        },
    }

    # ── Driver entry ──────────────────────────────────────────────────────
    driver_json_str = None
    if driver:
        driver_path = f"drivers/{driver.id}.json"
        project_json["drivers"].append({
            "id":      driver.id,
            "name":    driver.name,
            "path":    driver_path,
            "savedAt": now,
        })
        driver_json_str = json.dumps(_driver_to_dict(driver), indent=2)

    # ── Pack ZIP ──────────────────────────────────────────────────────────
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", json.dumps(project_json, indent=2))
        if driver_json_str and driver:
            zf.writestr(f"drivers/{driver.id}.json", driver_json_str)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_project(path: Path) -> tuple:
    """
    Load a .nordproj file.

    Returns
    -------
    (state_dict, drivers_list)
        state_dict   : dict suitable for ProjectState.from_dict()
        drivers_list : list of driver dicts (may be empty)
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Project file not found: {path}")

    with zipfile.ZipFile(path, "r") as zf:
        project_json = json.loads(zf.read("project.json"))

        # Load any bundled driver files
        drivers_list = []
        for drv_entry in project_json.get("drivers", []):
            drv_path = drv_entry.get("path", "")
            if drv_path in zf.namelist():
                drv_data = json.loads(zf.read(drv_path))
                drivers_list.append(drv_data)

    state_dict = _project_json_to_state_dict(project_json)
    return state_dict, drivers_list


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _driver_to_dict(d) -> dict:
    """Convert a Driver Pydantic model to a plain dict."""
    if hasattr(d, "model_dump"):
        return d.model_dump()   # Pydantic v2
    return d.__dict__


def _driver_dict_to_model(d: dict):
    """Convert a plain dict back to a Driver Pydantic model."""
    from ..core.models import Driver
    # Pydantic v2: model_fields holds the field names
    known = set(Driver.model_fields.keys())
    return Driver(**{k: v for k, v in d.items() if k in known})


def _project_json_to_state_dict(p: dict) -> dict:
    """Flatten project.json back to a ProjectState-compatible dict."""
    sim   = p.get("simulation", {})
    port  = p.get("port", {})
    geom  = p.get("geometry", {})
    flare = p.get("flare", {})
    sett  = p.get("settings", {})

    return {
        "project_name": p.get("name", "Untitled Project"),
        "description":  p.get("description", ""),
        "author":       p.get("author", ""),
        "theme":        sett.get("theme", "light"),
        "auto_save":    sett.get("autoSave", True),
        # Simulation
        "box_type":       sim.get("boxType",   "vented"),
        "volume_l":       sim.get("volume",    100.0),
        "fb_hz":          sim.get("fb",         30.0),
        "alignment":      sim.get("alignment", "QB3"),
        "input_power_w":  sim.get("inputPower", 100.0),
        # Port
        "port": {
            "shape":       port.get("shape",      "round"),
            "diameter_mm": port.get("diameterMm", 75.0),
            "slot_w_mm":   port.get("slotWMm",   100.0),
            "slot_h_mm":   port.get("slotHMm",    50.0),
            "count":       port.get("count",        1),
            "length_m":    port.get("lengthM",    0.0),
        },
        # Geometry
        "geometry": {
            "volume_l":        geom.get("volumeL",       100.0),
            "thickness_mm":    geom.get("thicknessMm",    18.0),
            "double_front":    geom.get("doubleFront",   True),
            "fixed_width_mm":  geom.get("fixedWidthMm",  0.0),
            "fixed_depth_mm":  geom.get("fixedDepthMm",  0.0),
            "fixed_height_mm": geom.get("fixedHeightMm", 0.0),
            "port_face":       geom.get("portFace",     "back"),
            "port_position":   geom.get("portPosition","bottom-left"),
        },
        # Flare
        "flare": {
            "port_shape":  flare.get("portShape",     "round"),
            "diameter_mm": flare.get("diameterMm",    75.0),
            "slot_w_mm":   flare.get("slotWMm",      100.0),
            "slot_h_mm":   flare.get("slotHMm",       50.0),
            "flare_mm":    flare.get("flareRadiusMm",  0.0),
            "masking":     flare.get("masking",        0.15),
            "target_vel":  flare.get("targetVelocity", 17.0),
        },
    }
