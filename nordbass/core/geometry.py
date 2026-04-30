"""
Box geometry solver and cutting list generator.
Matches Boxnotes behaviour: net working volume -> gross volume -> dimensions -> cutting list.
"""
import math
from typing import Dict, List, Optional, Tuple

from .models import PortConfig, Driver

C = 343.0  # m/s


def solve_wedge_dimensions(
    gross_vol: float,
    panel_thickness: float,
    fixed_width: float,
    fixed_height: float,
    fixed_depth_top: Optional[float] = None,
    fixed_depth_bottom: Optional[float] = None,
) -> Tuple[float, float, float, float]:
    """
    Solve for wedge (angled back) enclosure dimensions.
    Returns (height, width, depth_top, depth_bottom) — INTERNAL.

    If one depth is missing, it solves for it to match gross_vol.
    Formula: Vol = W * H * (D_top + D_bottom) / 2
    """
    w = fixed_width
    h = fixed_height
    dt = fixed_depth_top
    db = fixed_depth_bottom

    if dt is not None and db is not None:
        # All given, return as-is
        return (h, w, dt, db)

    if dt is not None:
        # Solve for db: db = 2 * Vol / (W * H) - dt
        db = (2 * gross_vol) / (w * h) - dt
        return (h, w, dt, max(0.01, db))

    if db is not None:
        # Solve for dt: dt = 2 * Vol / (W * H) - db
        dt = (2 * gross_vol) / (w * h) - db
        return (h, w, max(0.01, dt), db)

    # Neither depth given: assume D_bottom = 1.5 * D_top (typical wedge)
    # Vol = W * H * (D_top + 1.5*D_top) / 2 = W * H * 1.25 * D_top
    dt = gross_vol / (w * h * 1.25)
    db = 1.5 * dt
    return (h, w, dt, db)


def bracing_displacement(
    num_braces: int,
    thickness: float,
    width: float,
    height: float,
    window_cutout_percent: float = 40.0,
) -> float:
    """
    Calculate volume displacement of shelf/window bracing.
    Args:
        window_cutout_percent: percentage of the shelf area removed for airflow.
    Returns: volume in m³.
    """
    area = width * height
    net_area = area * (1.0 - window_cutout_percent / 100.0)
    return num_braces * net_area * thickness


def gross_volume(
    net_working_volume: float,
    driver_displacement: float,
    bracing_volume: float,
    port_configs: List[PortConfig],
    extra_volume: float = 0.0,
) -> float:
    """
    Gross internal volume = net + all displacements.
    This is the raw internal box volume before anything is placed inside.
    """
    port_disp = sum(p.displacement_volume for p in port_configs)
    return net_working_volume + driver_displacement + bracing_volume + port_disp + extra_volume


def solve_dimensions(
    gross_vol: float,
    panel_thickness: float,
    double_front: bool,
    fixed_width: Optional[float] = None,
    fixed_depth: Optional[float] = None,
    fixed_height: Optional[float] = None,
    external_dims: bool = False,
) -> Tuple[float, float, float]:
    """
    Solve for H, W, D given gross volume and constraints.

    If external_dims is True, the fixed values are external and we
    subtract panel thickness to get internal.

    Returns (height, width, depth) in metres — INTERNAL dimensions.
    """
    t = panel_thickness
    front_t = 2 * t if double_front else t

    def ext_to_int_h(h_ext: float) -> float:
        """Top + bottom panels."""
        return h_ext - 2 * t

    def ext_to_int_w(w_ext: float) -> float:
        """Left + right panels."""
        return w_ext - 2 * t

    def ext_to_int_d(d_ext: float) -> float:
        """Front + back panels."""
        return d_ext - front_t - t

    # Convert external fixed dims to internal
    fw = fixed_width
    fd = fixed_depth
    fh = fixed_height

    if external_dims:
        if fw is not None:
            fw = ext_to_int_w(fw)
        if fd is not None:
            fd = ext_to_int_d(fd)
        if fh is not None:
            fh = ext_to_int_h(fh)

    # Count how many are fixed
    fixed = [(fh, "h"), (fw, "w"), (fd, "d")]
    known = [(v, name) for v, name in fixed if v is not None]

    if len(known) == 3:
        # All three given; return as-is (volume may not match exactly)
        return (fh, fw, fd)  # type: ignore[return-value]

    if len(known) == 2:
        # Solve for the free dimension
        k1 = known[0][0]
        k2 = known[1][0]
        free_name = [name for v, name in fixed if v is None][0]
        free_val = gross_vol / (k1 * k2) if k1 * k2 > 0 else 0.3

        result = {"h": fh, "w": fw, "d": fd}
        result[free_name] = free_val
        return (result["h"], result["w"], result["d"])  # type: ignore[return-value]

    if len(known) == 1:
        # One fixed: solve the other two assuming golden ratio (1 : 1.618)
        k = known[0][0]
        name_k = known[0][1]
        remaining_area = gross_vol / k if k > 0 else 0.09
        # a * b = remaining_area, b/a = 1.618
        a = math.sqrt(remaining_area / 1.618)
        b = 1.618 * a

        free_names = [name for v, name in fixed if v is None]
        result = {"h": fh, "w": fw, "d": fd}
        result[free_names[0]] = a
        result[free_names[1]] = b
        return (result["h"], result["w"], result["d"])  # type: ignore[return-value]

    # No fixed dimensions: use golden ratio proportions h : w : d = 1.618 : 1 : 0.618
    # V = h * w * d = 1.618 * k * k * 0.618 * k = k^3
    k = gross_vol ** (1.0 / 3.0)
    h = k * 1.618 ** (1.0 / 3.0)
    w = k
    d = gross_vol / (h * w)
    return (h, w, d)


def standing_wave_resonances(
    H: float, W: float, D: float
) -> Dict:
    """
    Compute first 3 standing-wave resonances for each axis.
    f_n = n * c / (2 * L).

    Returns dict with front_back, top_bottom, side_side lists,
    plus warnings for resonances in the 80–300 Hz range.
    """
    def _resonances(length: float, count: int = 3) -> List[float]:
        if length <= 0:
            return [0.0] * count
        return [n * C / (2 * length) for n in range(1, count + 1)]

    fb = _resonances(D)   # front ↔ back
    tb = _resonances(H)   # top ↔ bottom
    ss = _resonances(W)   # side ↔ side

    warnings: List[str] = []
    for label, freqs in [("front-back", fb), ("top-bottom", tb), ("side-side", ss)]:
        for i, f in enumerate(freqs):
            if 80 <= f <= 300:
                warnings.append(
                    f"{label} mode {i+1} at {f:.1f} Hz is in the audible crossover range"
                )

    return {
        "front_back": fb,
        "top_bottom": tb,
        "side_side": ss,
        "warnings": warnings,
    }


def cutting_list(
    height_int: float,
    width_int: float,
    depth_int: float,
    panel_thickness: float,
    double_front: bool,
    ports: Optional[List[PortConfig]] = None,
    trim_allowance: float = 0.0,
) -> List[Dict]:
    """
    Generate cutting list.

    Panel layout (Boxnotes convention):
    - Top/Bottom:   external length along depth × external width
    - Left/Right sides: internal height × external depth
    - Back:         internal height × internal width
    - Front baffle: internal height × internal width  (×2 if double_front)

    All dimensions returned in mm rounded to 1 decimal.
    """
    t = panel_thickness
    front_t = 2 * t if double_front else t

    # External dimensions
    h_ext = height_int + 2 * t
    w_ext = width_int + 2 * t
    d_ext = depth_int + front_t + t  # front + back

    # Apply trim allowance
    h_ext += trim_allowance
    w_ext += trim_allowance
    d_ext += trim_allowance

    to_mm = 1000.0

    panels: List[Dict] = []

    # Top and Bottom: span the full width and depth externally
    panels.append(
        {
            "panel_name": "Top",
            "qty": 1,
            "length_mm": round(d_ext * to_mm, 1),
            "width_mm": round(w_ext * to_mm, 1),
            "notes": "External dimension",
        }
    )
    panels.append(
        {
            "panel_name": "Bottom",
            "qty": 1,
            "length_mm": round(d_ext * to_mm, 1),
            "width_mm": round(w_ext * to_mm, 1),
            "notes": "External dimension",
        }
    )

    # Left and Right sides: internal height × external depth
    panels.append(
        {
            "panel_name": "Left Side",
            "qty": 1,
            "length_mm": round(height_int * to_mm, 1),
            "width_mm": round(d_ext * to_mm, 1),
            "notes": "",
        }
    )
    panels.append(
        {
            "panel_name": "Right Side",
            "qty": 1,
            "length_mm": round(height_int * to_mm, 1),
            "width_mm": round(d_ext * to_mm, 1),
            "notes": "",
        }
    )

    # Back panel: internal height × internal width
    panels.append(
        {
            "panel_name": "Back",
            "qty": 1,
            "length_mm": round(height_int * to_mm, 1),
            "width_mm": round(width_int * to_mm, 1),
            "notes": "",
        }
    )

    # Front baffle: internal height × internal width
    port_notes = ""
    if ports:
        hole_descs = []
        for p in ports:
            if p.shape == "round":
                hole_descs.append(
                    f"{p.count}× ø{p.outer_diameter * to_mm:.1f}mm hole"
                )
            else:
                hole_descs.append(
                    f"{p.count}× {p.width * to_mm:.1f}×{p.height * to_mm:.1f}mm slot"
                )
        port_notes = "Port cutouts: " + ", ".join(hole_descs)

    front_qty = 2 if double_front else 1
    panels.append(
        {
            "panel_name": "Front Baffle",
            "qty": front_qty,
            "length_mm": round(height_int * to_mm, 1),
            "width_mm": round(width_int * to_mm, 1),
            "notes": f"{'Double thickness. ' if double_front else ''}{port_notes}".strip(),
        }
    )

    # Summary entry
    panels.append(
        {
            "panel_name": "EXTERNAL DIMS",
            "qty": 0,
            "length_mm": round(h_ext * to_mm, 1),
            "width_mm": round(w_ext * to_mm, 1),
            "notes": f"H×W×D = {h_ext * to_mm:.1f} × {w_ext * to_mm:.1f} × {d_ext * to_mm:.1f} mm",
        }
    )

    return panels


def check_fit(
    driver: Optional[Driver],
    ports: List[PortConfig],
    h_int: float,
    w_int: float,
    d_int: float,
    t: float,
    double_front: bool,
    port_face: str = "back",
) -> Tuple[List[str], List[str]]:
    """
    Check if the driver and ports physically fit in the enclosure.
    Returns (warnings, oks) lists of strings.
    """
    warnings: List[str] = []
    oks: List[str] = []

    ft = 2 * t if double_front else t
    h_ext = h_int + 2 * t
    w_ext = w_int + 2 * t
    d_ext = d_int + ft + t

    if driver:
        if driver.cutout_diameter > 0:
            bw, bh = w_ext, h_ext
            if driver.cutout_diameter > w_ext:
                warnings.append(
                    f"⚠ Cutout ø{driver.cutout_diameter*1000:.0f} mm exceeds baffle width {bw*1000:.0f} mm"
                )
            elif driver.cutout_diameter > h_ext:
                warnings.append(
                    f"⚠ Cutout ø{driver.cutout_diameter*1000:.0f} mm exceeds baffle height {bh*1000:.0f} mm"
                )
            else:
                oks.append(
                    f"✓ Cutout ø{driver.cutout_diameter*1000:.0f} mm fits in baffle {bw*1000:.0f}×{bh*1000:.0f} mm"
                )

        if driver.mounting_depth > 0:
            if driver.mounting_depth > d_int:
                warnings.append(
                    f"⚠ Mounting depth {driver.mounting_depth*1000:.0f} mm > internal depth {d_int*1000:.0f} mm"
                )
            else:
                oks.append(
                    f"✓ Mounting depth {driver.mounting_depth*1000:.0f} mm — {(d_int - driver.mounting_depth)*1000:.0f} mm clearance"
                )

        if driver.magnet_diameter > 0:
            if driver.magnet_diameter > w_int:
                warnings.append(
                    f"⚠ Magnet ø{driver.magnet_diameter*1000:.0f} mm > internal width {w_int*1000:.0f} mm"
                )
            elif driver.magnet_diameter > h_int:
                warnings.append(
                    f"⚠ Magnet ø{driver.magnet_diameter*1000:.0f} mm > internal height {h_int*1000:.0f} mm"
                )
            else:
                oks.append(f"✓ Magnet ø{driver.magnet_diameter*1000:.0f} mm fits inside box")

    for p in ports:
        panel_contrib = ft if port_face == "front" else t
        tube_len = max(0.0, p.length - panel_contrib)

        # Available internal space in that direction
        if port_face in ("front", "back"):
            avail = d_int
            pw_ext, ph_ext = w_ext, h_ext
        else:
            avail = w_int
            pw_ext, ph_ext = d_ext, h_ext

        if p.shape == "round":
            if p.diameter > pw_ext:
                warnings.append(
                    f"⚠ Port ø{p.diameter*1000:.0f} mm is wider than {port_face} panel ({pw_ext*1000:.0f} mm)"
                )
            else:
                oks.append(f"✓ Port ø{p.diameter*1000:.0f} mm fits on {port_face} panel")
        else:
            if p.width > pw_ext:
                warnings.append(
                    f"⚠ Slot width {p.width*1000:.0f} mm exceeds {port_face} panel {pw_ext*1000:.0f} mm"
                )
            else:
                oks.append(
                    f"✓ Slot {p.width*1000:.0f}×{p.height*1000:.0f} mm fits on {port_face} panel"
                )

        if tube_len > avail:
            warnings.append(
                f"⚠ Port tube {tube_len*1000:.0f} mm exceeds internal space {avail*1000:.0f} mm"
            )
        elif p.length > 0:
            oks.append(
                f"✓ Port: {panel_contrib*1000:.0f} mm panel + {tube_len*1000:.0f} mm tube = {p.length*1000:.0f} mm total"
            )

    return warnings, oks
