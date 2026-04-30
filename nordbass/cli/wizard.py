"""
Step-by-step project creation wizard.
"""
import math
from datetime import datetime

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..core import models
from ..core.geometry import (
    cutting_list,
    gross_volume as calc_gross_volume,
    solve_dimensions,
    standing_wave_resonances,
)
from ..core.flares import simple_mode
from ..core.ts_box import (
    port_length_for_tuning,
    sealed_alignment_volume,
    sealed_params,
    vented_alignment,
    vented_params,
)
from ..core.units import litre_to_m3, m3_to_litre, m_to_mm, mm_to_m
from ..data.database import list_drivers, save_driver, save_project

console = Console()


def run_wizard() -> None:
    """Interactive project creation wizard."""
    console.print(Panel("[bold]NordBass Project Wizard[/bold]", style="cyan"))

    project_name = typer.prompt("Project name", default="New Project")

    # ── Step 1: Select or add driver ──────────────────────────────────
    console.print("\n[bold]Step 1: Select Driver[/bold]")
    drivers = list_drivers()
    driver: models.Driver

    if drivers:
        table = Table(title="Available Drivers")
        table.add_column("#", justify="right")
        table.add_column("Name")
        table.add_column("Fs", justify="right")
        table.add_column("Qts", justify="right")
        table.add_column("Vas L", justify="right")
        for i, d in enumerate(drivers, 1):
            table.add_row(str(i), d.name, f"{d.fs:.1f}", f"{d.qts:.3f}", f"{d.vas * 1000:.1f}")
        console.print(table)

        choice = typer.prompt("Enter driver # or 'new' to add", default="1")
        if choice.lower() == "new":
            driver = _add_driver_inline()
        else:
            idx = int(choice) - 1
            driver = drivers[idx]
    else:
        console.print("[yellow]No drivers in database — adding one now.[/yellow]")
        driver = _add_driver_inline()

    console.print(f"Selected: [bold]{driver.name}[/bold]")

    # ── Step 2: Simulation ────────────────────────────────────────────
    console.print("\n[bold]Step 2: Box Simulation[/bold]")
    box_type = typer.prompt("Box type (sealed/vented)", default="vented")

    box_design: models.BoxDesign

    if box_type == "sealed":
        qtc = typer.prompt("Target Qtc", type=float, default=0.707)
        vb = sealed_alignment_volume(driver, target_qtc=qtc)
        console.print(f"Suggested volume: {vb * 1000:.1f} L")
        vol_input = typer.prompt("Accept or enter volume (litres)", default=f"{vb * 1000:.1f}")
        vb = litre_to_m3(float(vol_input))

        p = sealed_params(driver, vb)
        console.print(f"  Qtc = {p['qtc']:.3f}   Fc = {p['fc']:.1f} Hz   F3 = {p['f3']:.1f} Hz")

        box_design = models.BoxDesign(
            name=f"{driver.name} Sealed",
            driver_id=driver.id,
            box_type="sealed",
            net_volume=vb,
            alignment="manual",
            system_q=p["qtc"],
            f3=p["f3"],
        )
    else:
        alignment = typer.prompt("Alignment (QB3/B4/SC4/SBB4)", default="QB3")
        vb_a, fb_a = vented_alignment(driver, alignment)
        console.print(f"Suggested: Vb={vb_a * 1000:.1f} L, Fb={fb_a:.1f} Hz")
        vol_input = typer.prompt("Volume (litres)", default=f"{vb_a * 1000:.1f}")
        fb_input = typer.prompt("Tuning Fb (Hz)", default=f"{fb_a:.1f}")
        vb = litre_to_m3(float(vol_input))
        fb = float(fb_input)

        p = vented_params(driver, vb, fb)
        console.print(f"  F3 = {p['f3']:.1f} Hz   SPL 1W/1m = {p['spl_1w1m']:.1f} dB")

        box_design = models.BoxDesign(
            name=f"{driver.name} Vented ({alignment})",
            driver_id=driver.id,
            box_type="vented",
            net_volume=vb,
            tuning_freq=fb,
            alignment=alignment,
            f3=p["f3"],
        )

    # ── Step 3: Port configuration (vented only) ─────────────────────
    if box_type == "vented":
        console.print("\n[bold]Step 3: Port Configuration[/bold]")
        port_d_mm = typer.prompt("Port diameter (mm)", type=float, default=75.0)
        num_ports = typer.prompt("Number of ports", type=int, default=1)
        port_d = mm_to_m(port_d_mm)
        port_area = math.pi * (port_d / 2) ** 2
        pl = port_length_for_tuning(fb, vb, port_area, num_ports)
        console.print(f"  Port length: {pl * 1000:.1f} mm")

        port_cfg = models.PortConfig(
            shape="round",
            count=num_ports,
            diameter=port_d,
            length=pl,
        )
        box_design.ports = [port_cfg]

        # ── Step 4: Flare sizing ─────────────────────────────────────
        console.print("\n[bold]Step 4: Flare Sizing[/bold]")
        import numpy as np
        freqs = np.array([20, 30, 40, 50, 60, 80, 100], dtype=float)
        result = simple_mode(port_d, 0.0, freqs, masking=0.15)
        console.print(f"  Verdict (no flare): {result['verdict']}")
        if result["verdict"] != "OK":
            flare_mm = typer.prompt("Flare radius (mm)", type=float, default=10.0)
            result2 = simple_mode(port_d, mm_to_m(flare_mm), freqs, masking=0.15)
            console.print(f"  Verdict (with flare): {result2['verdict']}")
    else:
        console.print("\n[dim]Steps 3-4 skipped (sealed box).[/dim]")

    # ── Step 5: Geometry / Cutting list ──────────────────────────────
    console.print("\n[bold]Step 5: Box Geometry[/bold]")
    thickness_mm = typer.prompt("Panel thickness (mm)", type=float, default=18.0)
    double = typer.confirm("Double-thickness front baffle?", default=True)
    width_mm = typer.prompt("Fixed width (mm, 0=auto)", type=float, default=0.0)
    depth_mm = typer.prompt("Fixed depth (mm, 0=auto)", type=float, default=0.0)

    t = mm_to_m(thickness_mm)
    fw = mm_to_m(width_mm) if width_mm > 0 else None
    fd = mm_to_m(depth_mm) if depth_mm > 0 else None

    port_cfgs = box_design.ports if box_design.ports else []
    gv = calc_gross_volume(box_design.net_volume, 0.0005, 0.0, port_cfgs)
    h, w, d = solve_dimensions(gv, t, double, fw, fd, None)

    console.print(f"  Internal: {m_to_mm(h):.1f} × {m_to_mm(w):.1f} × {m_to_mm(d):.1f} mm (H×W×D)")

    res = standing_wave_resonances(h, w, d)
    for warn in res["warnings"]:
        console.print(f"  [yellow]⚠ {warn}[/yellow]")

    panels = cutting_list(h, w, d, t, double, port_cfgs)
    cut_table = Table(title="Cutting List")
    cut_table.add_column("Panel")
    cut_table.add_column("Qty", justify="right")
    cut_table.add_column("L mm", justify="right")
    cut_table.add_column("W mm", justify="right")
    cut_table.add_column("Notes")
    for pa in panels:
        cut_table.add_row(
            pa["panel_name"],
            str(pa["qty"]) if pa["qty"] > 0 else "—",
            f"{pa['length_mm']:.1f}",
            f"{pa['width_mm']:.1f}",
            pa["notes"],
        )
    console.print(cut_table)

    geometry_cfg = models.GeometryConfig(
        net_working_volume=box_design.net_volume,
        panel_thickness=t,
        double_front=double,
        fixed_width=fw,
        fixed_depth=fd,
        ports=port_cfgs,
    )

    # ── Step 6: Save ─────────────────────────────────────────────────
    console.print("\n[bold]Step 6: Save Project[/bold]")
    if typer.confirm("Save this project?", default=True):
        proj = models.Project(
            name=project_name,
            driver=driver,
            box_design=box_design,
            geometry=geometry_cfg,
            updated_at=datetime.now().isoformat(),
        )
        save_project(proj)
        console.print(f"[green]Project saved:[/green] {proj.name} (ID: {proj.id[:8]}…)")
    else:
        console.print("[dim]Project not saved.[/dim]")


def _add_driver_inline() -> models.Driver:
    """Quick inline driver entry."""
    name = typer.prompt("Driver name")
    manufacturer = typer.prompt("Manufacturer", default="")
    fs = typer.prompt("Fs (Hz)", type=float)
    qts = typer.prompt("Qts", type=float)
    qes = typer.prompt("Qes", type=float)
    qms = typer.prompt("Qms", type=float)
    vas_l = typer.prompt("Vas (litres)", type=float)
    re = typer.prompt("Re (Ohm)", type=float)
    sd_cm2 = typer.prompt("Sd (cm²)", type=float)
    xmax_mm = typer.prompt("Xmax (mm)", type=float)
    pe = typer.prompt("Pe (W)", type=float)

    driver = models.Driver(
        name=name,
        manufacturer=manufacturer,
        fs=fs,
        qts=qts,
        qes=qes,
        qms=qms,
        vas=litre_to_m3(vas_l),
        re=re,
        sd=sd_cm2 * 1e-4,
        xmax=mm_to_m(xmax_mm),
        pe=pe,
    )
    save_driver(driver)
    console.print(f"[green]Driver added: {driver.name}[/green]")
    return driver
