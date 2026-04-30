# NordBass — Installation Guide

**Version:** 0.1.24  
**Platforms:** Linux (Ubuntu / Fedora) · Windows 10 / 11  
**Requirements:** Python 3.11 or 3.12

---

## Table of Contents

1. [What You Need](#1-what-you-need)
2. [Linux — Ubuntu 22.04 / 24.04](#2-linux--ubuntu-2204--2404)
3. [Linux — Fedora 40 / 41 / 42 / 43](#3-linux--fedora-40--41--42--43)
4. [Windows 10 / 11](#4-windows-10--11)
5. [First Launch](#5-first-launch)
6. [Launching Every Time After](#6-launching-every-time-after)
7. [Desktop Shortcut (Linux)](#7-desktop-shortcut-linux)
8. [Troubleshooting](#8-troubleshooting)
9. [Uninstalling](#9-uninstalling)

---

## 1. What You Need

| Item | Details |
|---|---|
| Python | 3.11 or 3.12 (free, open source) |
| Internet connection | Required once during install to download packages (~250 MB) |
| Disk space | ~350 MB after install |
| NordBass project folder | From the zip file you downloaded |

---

## 2. Linux — Ubuntu 22.04 / 24.04

### Step 1 — Install Python and system dependencies

Open a terminal (`Ctrl+Alt+T`) and run:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv xcb-util-cursor -y
```

The `xcb-util-cursor` package is required by the Qt GUI framework on Ubuntu.

Verify Python is installed:

```bash
python3 --version
```

You should see `Python 3.11.x` or `Python 3.12.x`.

---

### Step 2 — Extract the project

Extract the `nordbass_speaker_tool` folder from the zip file to a location of your choice, for example your home folder:

```
/home/yourusername/nordbass_speaker_tool/
```

> **Important:** Do not place the folder on a FAT32 or exFAT USB stick when setting up — create the virtual environment on your local drive. You can copy the whole project including `.venv` to the USB afterwards if needed, but symlinks on exFAT will fail.

---

### Step 3 — Open a terminal in the project folder

```bash
cd ~/nordbass_speaker_tool
```

---

### Step 4 — Create a virtual environment

```bash
python3 -m venv .venv
```

This creates a `.venv` folder inside the project. Takes about 10 seconds.

---

### Step 5 — Activate the virtual environment

```bash
source .venv/bin/activate
```

Your prompt will change to show `(.venv)` at the start. You must do this every time you open a new terminal.

---

### Step 6 — Install NordBass and all dependencies

```bash
pip install -e .
```

This downloads and installs everything: PySide6, numpy, scipy, matplotlib, pydantic, and more. **This takes 3–10 minutes** on the first install. Let it run — it will print a lot of output while downloading.

---

### Step 7 — Launch

```bash
nordbass gui
```

The NordBass window will open.

---

## 3. Linux — Fedora 40 / 41 / 42 / 43

Fedora ships Python 3.13+ which has a known bug with virtual environment symlinks. The workaround is to use `--without-pip` and install pip manually.

### Step 1 — Install system dependencies

```bash
sudo dnf install python3 python3-pip xcb-util-cursor -y
```

Verify:

```bash
python3 --version
```

---

### Step 2 — Extract the project

Extract the zip to your home folder or any location you prefer:

```
/home/yourusername/nordbass_speaker_tool/
```

---

### Step 3 — Open a terminal in the project folder

```bash
cd ~/nordbass_speaker_tool
```

---

### Step 4 — Delete any old virtual environment

If you are reinstalling or upgrading from a previous version, remove the old venv first:

```bash
rm -rf .venv
```

---

### Step 5 — Create a virtual environment (Fedora workaround)

Due to a Python 3.13+ symlink bug on Fedora, use this command instead of the standard one:

```bash
python3 -m venv --without-pip --copies .venv
```

Then install pip manually:

```bash
curl https://bootstrap.pypa.io/get-pip.py | .venv/bin/python3
```

If `curl` is not available, use `wget`:

```bash
wget -O- https://bootstrap.pypa.io/get-pip.py | .venv/bin/python3
```

---

### Step 6 — Activate the virtual environment

```bash
source .venv/bin/activate
```

Your prompt will show `(.venv)` at the start.

---

### Step 7 — Install NordBass and all dependencies

```bash
pip install -e .
```

This takes 3–10 minutes. Let it finish completely.

---

### Step 8 — Launch

```bash
nordbass gui
```

---

## 4. Windows 10 / 11

### Step 1 — Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Click the big **Download Python 3.11.x** button (or 3.12 — either works)
3. Run the downloaded installer
4. **Critical:** Before clicking Install Now, tick the checkbox at the bottom that says **"Add python.exe to PATH"**
5. Click **Install Now** and wait for it to finish

Verify in a new Command Prompt window:

```
python --version
```

You should see `Python 3.11.x`.

---

### Step 2 — Edit the database path file

NordBass needs to know where to store its database on Windows. Open this file in Notepad:

```
nordbass_speaker_tool\nordbass\data\__init__.py
```

Replace the entire contents with:

```python
"""Data persistence layer."""
import sys
from pathlib import Path

if sys.platform == "win32":
    DB_PATH = Path.home() / "AppData" / "Roaming" / "NordBass" / "nordbass.db"
else:
    DB_PATH = Path.home() / ".nordbass" / "nordbass.db"
```

Save the file. This is the only code change needed for Windows.

---

### Step 3 — Extract the project

Extract the zip to a folder on your computer. A good location is your home folder:

```
C:\Users\YourName\nordbass_speaker_tool\
```

> **Do NOT copy the `.venv` folder** if transferring from a Linux machine — virtual environments are not cross-platform. You will create a new one in the next step.

---

### Step 4 — Open Command Prompt in the project folder

The easiest way:

1. Open **File Explorer** and navigate to the `nordbass_speaker_tool` folder
2. Click on the address bar at the top (where the folder path is shown)
3. Type `cmd` and press **Enter**

A Command Prompt window will open already inside the correct folder.

---

### Step 5 — Create a virtual environment

```
python -m venv .venv
```

Takes about 10 seconds.

---

### Step 6 — Activate the virtual environment

```
.venv\Scripts\activate
```

Your prompt will change to show `(.venv)` at the start.

> **If you see an execution policy error**, run this first, then try activating again:
> ```
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

---

### Step 7 — Install NordBass and all dependencies

```
pip install -e .
```

This takes 3–10 minutes. PySide6 alone is around 150 MB. Let it finish completely before continuing.

---

### Step 8 — Launch

```
nordbass gui
```

The NordBass window will open.

---

## 5. First Launch

When NordBass opens for the first time:

- The database is created automatically at:
  - **Linux:** `~/.nordbass/nordbass.db`
  - **Windows:** `C:\Users\YourName\AppData\Roaming\NordBass\nordbass.db`
- All four tabs (Drivers, Simulation, Geometry, Flare) will be empty — this is normal
- Go to **File → New Project** to create your first project file (`.nordproj`)
- Go to the **Drivers** tab and click **Add Driver** to enter your first T/S parameters

---

## 6. Launching Every Time After

The install steps only need to be done once. Every time you want to use NordBass after that:

**Linux:**
```bash
cd ~/nordbass_speaker_tool
source .venv/bin/activate
nordbass gui
```

**Windows:**
```
cd C:\Users\YourName\nordbass_speaker_tool
.venv\Scripts\activate
nordbass gui
```

---

## 7. Desktop Shortcut (Linux)

A one-time installer script is included. Run it once from the project folder:

```bash
bash install_desktop.sh
```

This creates:
- A **NordBass** icon on your Desktop
- An entry in your application menu

After running it, if the desktop icon shows a question mark, right-click it and choose **Allow Launching**.

---

## 8. Troubleshooting

### `python3: command not found` (Linux)

Install Python:
```bash
# Ubuntu
sudo apt install python3 python3-venv python3-pip -y

# Fedora
sudo dnf install python3 python3-pip -y
```

---

### `python: command not found` (Windows)

You forgot to tick **"Add python.exe to PATH"** during install. Reinstall Python and tick that box.

---

### `.venv\Scripts\activate` gives an execution policy error (Windows)

```
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then try activating again.

---

### `Unable to symlink` error when creating venv (Fedora)

Use the Fedora workaround in Step 5 of the Fedora section above (`--without-pip --copies`).

---

### Qt platform plugin error / blank window

**Ubuntu:**
```bash
sudo apt install xcb-util-cursor libxcb-cursor0 -y
```

**Fedora:**
```bash
sudo dnf install xcb-util-cursor -y
```

If you are on Wayland and the window is blank or crashes:
```bash
QT_QPA_PLATFORM=xcb nordbass gui
```

---

### `nordbass: command not found`

The virtual environment is not activated. Run:

```bash
source .venv/bin/activate   # Linux
.venv\Scripts\activate      # Windows
```

Then try `nordbass gui` again.

---

### PySide6 or matplotlib not found

```bash
pip install -e .
```

Make sure the virtual environment is activated first.

---

### Old `.venv` from a different machine or path

Delete it and recreate:

```bash
rm -rf .venv           # Linux
rmdir /s /q .venv      # Windows

python3 -m venv .venv  # Linux
python -m venv .venv   # Windows
```

Then repeat Steps 5–7 (activate + install).

---

## 9. Uninstalling

To fully remove NordBass:

1. Delete the project folder (`nordbass_speaker_tool/`)
2. Delete the database:
   - **Linux:** `rm -rf ~/.nordbass/`
   - **Windows:** Delete `C:\Users\YourName\AppData\Roaming\NordBass\`
3. Remove the desktop shortcut (Linux): `rm ~/Desktop/NordBass.desktop`
4. Remove the app menu entry (Linux): `rm ~/.local/share/applications/NordBass.desktop`

---

*NordBass is open source software — GPL v3 License.*
