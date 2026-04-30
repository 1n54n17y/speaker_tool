# NordBass Speaker Tool

Professional loudspeaker enclosure design application — a Python-based alternative to WinISD, Boxnotes, and Flare-it.

## Features

- **Thiele/Small acoustics engine**: sealed and vented (bass-reflex) box simulations
- **Named alignments**: QB3, B4, SC4, SBB4 (Butterworth) with automatic Vb/Fb calculation
- **SPL, excursion, port velocity, and group delay** arrays for plotting
- **Port geometry**: Helmholtz tuning, Mach/Reynolds numbers, displacement volume
- **Flare-it analysis**: chuffing limits, compression limits, flare radius sizing, cruise control
- **Box geometry**: dimension solver (golden ratio defaults), standing-wave resonance warnings, CNC-ready cutting list
- **Driver database**: SQLite-backed CRUD with CSV import/export
- **Rich CLI**: interactive wizard and individual commands via Typer + Rich
- **PySide6 GUI**: tabbed interface for Drivers, Simulation, Geometry, Flare analysis
- **Pydantic v2 models**: validated, serialisable data throughout

## Installation

```bash
# Clone and install in development mode
cd nordbass_speaker_tool
pip install -e ".[dev]"

# For GUI support
pip install -e ".[dev,gui]"
```

## Quick Start (CLI)

```bash
# Add a driver interactively
nordbass driver add

# Import drivers from CSV
nordbass driver import drivers.csv

# List drivers in the database
nordbass driver list

# Simulate a sealed box (Butterworth Qtc=0.707)
nordbass simulate sealed <driver_id>

# Simulate a vented box with QB3 alignment
nordbass simulate vented <driver_id> --alignment QB3

# Simulate with manual volume and tuning
nordbass simulate vented <driver_id> --volume 120 --fb 28

# Compute box geometry and cutting list
nordbass geometry --volume 100 --thickness 18 --width 400 --depth 500

# Flare / chuffing analysis
nordbass flare --diameter 75 --flare 10 --masking 0.15

# Full project wizard
nordbass project new

# List and show projects
nordbass project list
nordbass project show <project_id>

# Launch GUI
nordbass gui
```

## Module Overview

| Module | Description |
|---|---|
| `nordbass.core.models` | Pydantic v2 data models (Driver, BoxDesign, PortConfig, etc.) |
| `nordbass.core.ts_box` | Sealed/vented acoustics engine (SPL, excursion, port velocity, group delay) |
| `nordbass.core.ports` | Port geometry, Mach/Reynolds, chuffing/compression limits |
| `nordbass.core.flares` | Flare-it equivalent (simple mode, full mode, cruise control) |
| `nordbass.core.geometry` | Box dimension solver, standing-wave resonances, cutting list |
| `nordbass.core.units` | SI unit conversion helpers |
| `nordbass.data.database` | SQLite CRUD for drivers and projects |
| `nordbass.data.importer` | CSV import/export with flexible column mapping |
| `nordbass.cli.app` | Typer CLI application |
| `nordbass.cli.wizard` | Step-by-step project creation wizard |
| `nordbass.gui` | PySide6 GUI (Drivers, Simulation, Geometry, Flare tabs) |

## Running Tests

```bash
pytest tests/ -v
```

## License

GPL v3. See [LICENSE](LICENSE).
