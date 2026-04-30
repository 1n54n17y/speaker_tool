"""
Typer CLI application for NordBass Speaker Tool.
"""
import math
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..core import models
from ..core.flares import cruise_control, full_mode, simple_mode
from ..core.geometry import (
    cutting_list,
    gross_volume as calc_gross_volume,
    solve_dimensions,
    standing_wave_resonances,
)
from ..core.ports import chuffing_velocity_limit, compression_velocity_limit
from ..core.ts_box import (
    port_length_for_tuning,
    sealed_alignment_volume,
    sealed_params,
    vented_alignment,
    vented_params,
)
from ..core.units import litre_to_m3, m3_to_litre, m_to_mm, mm_to_m
from ..data.database import (
    delete_driver,
    get_driver,
    list_drivers,
    save_driver,
    save_project,
    list_projects,
    get_project,
)
from ..data.importer import export_csv, import_csv

app = typer.Typer(
    name="nordbass",
    help="NordBass Speaker Tool — professional loudspeaker enclosure design.",
    no_args_is_help=True,
)
driver_app = typer.Typer(help="Manage driver database.")
sim_app = typer.Typer(help="Run simulations.")
project_app = typer.Typer(help="Manage projects.")

app.add_typer(driver_app, name="driver")
app.add_typer(sim_app, name="simulate")
app.add_typer(project_app, name="project")

console = Console()


# ── Driver commands ──────────────────────────────────────────────────────

@driver_app.command("add")
def driver_add() -> None:
    """Interactively add a driver to the database."""
    console.print(Panel("Add New Driver", style="bold cyan"))
    name = typer.prompt("Driver name")
    manufacturer = typer.prompt("Manufacturer", default="")
    fs = typer.prompt("Fs (Hz)", type=float)
    qts = typer.prompt("Qts", type=float)
    qes = typer.prompt("Qes", type=float)
    qms = typer.prompt("Qms", type=float)
    vas_l = typer.prompt("Vas (litres)", type=float)
    re = typer.prompt("Re (Ohm)", type=float)
    sd_cm2 = typer.prompt("Sd (cm²)", type=float)
    xmax_mm = typer.prompt("Xmax (mm, one-way)", type=float)
    pe = typer.prompt("Pe (W)", type=float)
    bl = typer.prompt("BL (T·m)", type=float, default=0.0)
    le_mh = typer.prompt("Le (mH)", type=float, default=0.0)
    mms_g = typer.prompt("Mms (g)", type=float, default=0.0)
    sensitivity = typer.prompt("Sensitivity (dB)", type=float, default=0.0)

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
        bl=bl,
        le=le_mh * 1e-3,
        mms=mms_g * 1e-3,
        sensitivity=sensitivity,
    )
    save_driver(driver)
    console.print(f"[green]Driver saved:[/green] {driver.name} (ID: {driver.id[:8]}…)")


@driver_app.command("list")
def driver_list() -> None:
    """List all drivers in the database."""
    drivers = list_drivers()
    if not drivers:
        console.print("[yellow]No drivers in database. Use 'nordbass driver add' or 'nordbass driver import'.[/yellow]")
        return

    table = Table(title="Driver Library")
    table.add_column("ID", style="dim", max_width=10)
    table.add_column("Name", style="bold")
    table.add_column("Mfr")
    table.add_column("Fs Hz", justify="right")
    table.add_column("Qts", justify="right")
    table.add_column("Vas L", justify="right")
    table.add_column("Sd cm²", justify="right")
    table.add_column("Xmax mm", justify="right")
    table.add_column("Pe W", justify="right")

    for d in drivers:
        table.add_row(
            d.id[:8] + "…",
            d.name,
            d.manufacturer,
            f"{d.fs:.1f}",
            f"{d.qts:.3f}",
            f"{m3_to_litre(d.vas):.1f}",
            f"{d.sd * 1e4:.1f}",
            f"{d.xmax * 1000:.1f}",
            f"{d.pe:.0f}",
        )
    console.print(table)


@driver_app.command("delete")
def driver_delete(driver_id: str = typer.Argument(..., help="Driver ID (prefix ok)")) -> None:
    """Delete a driver from the database."""
    # Support prefix matching
    drivers = list_drivers()
    matches = [d for d in drivers if d.id.startswith(driver_id)]
    if len(matches) == 0:
        console.print(f"[red]No driver found matching '{driver_id}'[/red]")
        raise typer.Exit(1)
    if len(matches) > 1:
        console.print(f"[red]Ambiguous ID prefix '{driver_id}' — matches {len(matches)} drivers[/red]")
        raise typer.Exit(1)
    d = matches[0]
    if typer.confirm(f"Delete '{d.name}'?"):
        delete_driver(d.id)
        console.print(f"[green]Deleted {d.name}[/green]")


@driver_app.command("import")
def driver_import(filepath: str = typer.Argument(..., help="Path to CSV file")) -> None:
    """Import drivers from a CSV file."""
    drivers = import_csv(filepath)
    if not drivers:
        console.print("[yellow]No valid drivers found in file.[/yellow]")
        return
    for d in drivers:
        save_driver(d)
    console.print(f"[green]Imported {len(drivers)} driver(s).[/green]")


@driver_app.command("export")
def driver_export(filepath: str = typer.Argument(..., help="Output CSV path")) -> None:
    """Export all drivers to CSV."""
    drivers = list_drivers()
    export_csv(drivers, filepath)
    console.print(f"[green]Exported {len(drivers)} driver(s) to {filepath}[/green]")


# ── Simulation commands ──────────────────────────────────────────────────

def _resolve_driver(driver_id: str) -> models.Driver:
    """Resolve a driver by ID or prefix."""
    drivers = list_drivers()
    matches = [d for d in drivers if d.id.startswith(driver_id)]
    if len(matches) == 0:
        console.print(f"[red]No driver found matching '{driver_id}'[/red]")
        raise typer.Exit(1)
    if len(matches) > 1:
        console.print(f"[red]Ambiguous ID — matches {len(matches)} drivers[/red]")
        raise typer.Exit(1)
    return matches[0]


@sim_app.command("sealed")
def simulate_sealed(
    driver_id: str = typer.Argument(..., help="Driver ID"),
    volume: Optional[float] = typer.Option(None, "--volume", "-v", help="Box volume in litres"),
    qtc: float = typer.Option(0.707, "--qtc", help="Target Qtc (used if volume not given)"),
) -> None:
    """Simulate a sealed enclosure."""
    driver = _resolve_driver(driver_id)
    console.print(f"[bold]Driver:[/bold] {driver.name}")

    if volume is None:
        vb = sealed_alignment_volume(driver, target_qtc=qtc)
    else:
        vb = litre_to_m3(volume)

    p = sealed_params(driver, vb)

    table = Table(title="Sealed Box Results")
    table.add_column("Parameter", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Volume (Vb)", f"{p['vb_litres']:.2f} L")
    table.add_row("System Q (Qtc)", f"{p['qtc']:.3f}")
    table.add_row("System Resonance (Fc)", f"{p['fc']:.2f} Hz")
    table.add_row("-3 dB Frequency (F3)", f"{p['f3']:.2f} Hz")
    table.add_row("EBP", f"{p['ebp']:.1f}")
    console.print(table)


@sim_app.command("vented")
def simulate_vented(
    driver_id: str = typer.Argument(..., help="Driver ID"),
    volume: Optional[float] = typer.Option(None, "--volume", "-v", help="Box volume litres"),
    fb: Optional[float] = typer.Option(None, "--fb", help="Tuning frequency Hz"),
    alignment: str = typer.Option("QB3", "--alignment", "-a", help="QB3, B4, SC4, SBB4"),
) -> None:
    """Simulate a vented (bass-reflex) enclosure."""
    driver = _resolve_driver(driver_id)
    console.print(f"[bold]Driver:[/bold] {driver.name}")

    if volume is None or fb is None:
        vb_a, fb_a = vented_alignment(driver, alignment)
        if volume is None:
            vb = vb_a
        else:
            vb = litre_to_m3(volume)
        if fb is None:
            fb_use = fb_a
        else:
            fb_use = fb
    else:
        vb = litre_to_m3(volume)
        fb_use = fb

    p = vented_params(driver, vb, fb_use)

    table = Table(title=f"Vented Box Results ({alignment})")
    table.add_column("Parameter", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Volume (Vb)", f"{p['vb_litres']:.2f} L")
    table.add_row("Tuning (Fb)", f"{p['fb']:.2f} Hz")
    table.add_row("-3 dB (F3)", f"{p['f3']:.2f} Hz")
    table.add_row("SPL 1W/1m", f"{p['spl_1w1m']:.1f} dB")
    table.add_row("Efficiency", f"{p['efficiency'] * 100:.4f}%")

    # Port length suggestion
    port_d = 0.075  # default 75 mm
    port_area = math.pi * (port_d / 2) ** 2
    pl = port_length_for_tuning(fb_use, vb, port_area, num_ports=1)
    table.add_row("Port Length (ø75mm)", f"{pl * 1000:.1f} mm")

    console.print(table)


# ── Geometry command ─────────────────────────────────────────────────────

@app.command("geometry")
def geometry_cmd(
    volume: float = typer.Option(..., "--volume", "-v", help="Net working volume (litres)"),
    thickness: float = typer.Option(18.0, "--thickness", "-t", help="Panel thickness mm"),
    width: Optional[float] = typer.Option(None, "--width", "-W", help="Fixed width mm"),
    depth: Optional[float] = typer.Option(None, "--depth", "-D", help="Fixed depth mm"),
    height: Optional[float] = typer.Option(None, "--height", "-H", help="Fixed height mm"),
    double_front: bool = typer.Option(True, "--double-front/--single-front"),
) -> None:
    """Compute box dimensions and cutting list."""
    net_vol = litre_to_m3(volume)
    t = mm_to_m(thickness)
    fw = mm_to_m(width) if width else None
    fd = mm_to_m(depth) if depth else None
    fh = mm_to_m(height) if height else None

    gv = calc_gross_volume(net_vol, 0.0005, 0.0, [])
    h, w, d = solve_dimensions(gv, t, double_front, fw, fd, fh)

    console.print(Panel(f"Internal: {m_to_mm(h):.1f} × {m_to_mm(w):.1f} × {m_to_mm(d):.1f} mm (H×W×D)", title="Dimensions"))
    console.print(f"Gross internal volume: {gv * 1000:.2f} L")

    res = standing_wave_resonances(h, w, d)
    res_table = Table(title="Standing Wave Resonances")
    res_table.add_column("Axis")
    res_table.add_column("Mode 1 Hz", justify="right")
    res_table.add_column("Mode 2 Hz", justify="right")
    res_table.add_column("Mode 3 Hz", justify="right")
    res_table.add_row("Front↔Back", *[f"{f:.1f}" for f in res["front_back"]])
    res_table.add_row("Top↔Bottom", *[f"{f:.1f}" for f in res["top_bottom"]])
    res_table.add_row("Side↔Side", *[f"{f:.1f}" for f in res["side_side"]])
    console.print(res_table)

    for w_msg in res["warnings"]:
        console.print(f"[yellow]⚠ {w_msg}[/yellow]")

    panels = cutting_list(h, w, d, t, double_front)
    cut_table = Table(title="Cutting List")
    cut_table.add_column("Panel")
    cut_table.add_column("Qty", justify="right")
    cut_table.add_column("Length mm", justify="right")
    cut_table.add_column("Width mm", justify="right")
    cut_table.add_column("Notes")
    for p in panels:
        cut_table.add_row(
            p["panel_name"],
            str(p["qty"]) if p["qty"] > 0 else "—",
            f"{p['length_mm']:.1f}",
            f"{p['width_mm']:.1f}",
            p["notes"],
        )
    console.print(cut_table)


# ── Flare command ────────────────────────────────────────────────────────

@app.command("flare")
def flare_cmd(
    diameter: float = typer.Option(..., "--diameter", "-d", help="Port inner diameter mm"),
    flare: float = typer.Option(0.0, "--flare", "-f", help="Flare radius mm"),
    masking: float = typer.Option(0.15, "--masking", "-m", help="Masking allowance (0, 0.15, 0.30)"),
) -> None:
    """Run flare / chuffing analysis for a port."""
    import numpy as np

    d_m = mm_to_m(diameter)
    f_m = mm_to_m(flare)
    freqs = np.array([20, 30, 40, 50, 60, 80, 100, 150, 200], dtype=float)

    result = simple_mode(d_m, f_m, freqs, masking)

    table = Table(title=f"Flare Analysis — ø{diameter:.0f}mm, flare {flare:.0f}mm")
    table.add_column("Freq Hz", justify="right")
    table.add_column("Chuffing Limit m/s", justify="right")
    table.add_column("Compression Limit m/s", justify="right")
    for i, f in enumerate(freqs):
        table.add_row(
            f"{f:.0f}",
            f"{result['chuffing_limit'][i]:.2f}",
            f"{result['compression_limit'][i]:.2f}",
        )
    console.print(table)
    console.print(f"Verdict: [bold]{result['verdict']}[/bold]")
    console.print(f"Effective diameter: {result['effective_diameter'] * 1000:.1f} mm")


# ── Project commands ─────────────────────────────────────────────────────

@project_app.command("new")
def project_new_cmd() -> None:
    """Create a new project (interactive wizard)."""
    from .wizard import run_wizard
    run_wizard()


@project_app.command("list")
def project_list_cmd() -> None:
    """List saved projects."""
    projects = list_projects()
    if not projects:
        console.print("[yellow]No projects saved.[/yellow]")
        return
    table = Table(title="Projects")
    table.add_column("ID", style="dim", max_width=10)
    table.add_column("Name", style="bold")
    table.add_column("Driver")
    table.add_column("Box Type")
    table.add_column("Updated")
    for p in projects:
        drv = p.driver.name if p.driver else "—"
        bt = p.box_design.box_type if p.box_design else "—"
        table.add_row(p.id[:8] + "…", p.name, drv, bt, p.updated_at[:10])
    console.print(table)


@project_app.command("show")
def project_show_cmd(project_id: str = typer.Argument(..., help="Project ID")) -> None:
    """Show full project details."""
    projects = list_projects()
    matches = [p for p in projects if p.id.startswith(project_id)]
    if not matches:
        console.print(f"[red]No project found matching '{project_id}'[/red]")
        raise typer.Exit(1)
    proj = matches[0]
    console.print(Panel(f"[bold]{proj.name}[/bold]\nID: {proj.id}\nCreated: {proj.created_at}\nUpdated: {proj.updated_at}"))

    if proj.driver:
        d = proj.driver
        console.print(f"\n[bold cyan]Driver:[/bold cyan] {d.name} ({d.manufacturer})")
        console.print(f"  Fs={d.fs:.1f} Hz  Qts={d.qts:.3f}  Vas={d.vas * 1000:.1f} L  Sd={d.sd * 1e4:.1f} cm²")

    if proj.box_design:
        b = proj.box_design
        console.print(f"\n[bold cyan]Box Design:[/bold cyan] {b.box_type}")
        console.print(f"  Volume={b.net_volume * 1000:.1f} L  Fb={b.tuning_freq or 0:.1f} Hz  Alignment={b.alignment}")

    if proj.notes:
        console.print(f"\n[bold]Notes:[/bold] {proj.notes}")


# ── GUI launcher ─────────────────────────────────────────────────────────

@app.command("gui")
def gui_cmd() -> None:
    """Launch the PySide6 GUI."""
    try:
        from ..gui.main_window import main as gui_main
        gui_main()
    except ImportError as e:
        console.print(f"[red]GUI requires PySide6: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
