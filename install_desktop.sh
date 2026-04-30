#!/bin/bash
# NordBass — desktop launcher installer
# Run once from the project directory: bash install_desktop.sh

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_FILE="$HOME/Desktop/NordBass.desktop"
APPS_FILE="$HOME/.local/share/applications/NordBass.desktop"

echo "Installing NordBass desktop launcher..."
echo "  Project: $PROJECT_DIR"

# Write the launcher script
cat > "$PROJECT_DIR/nordbass_launcher.sh" << LAUNCHER
#!/bin/bash
cd "$PROJECT_DIR"
source .venv/bin/activate
exec nordbass gui
LAUNCHER
chmod +x "$PROJECT_DIR/nordbass_launcher.sh"

# Write the .desktop file (used for both Desktop and app menu)
DESKTOP_CONTENT="[Desktop Entry]
Version=1.0
Type=Application
Name=NordBass
Comment=Loudspeaker enclosure design tool
Exec=$PROJECT_DIR/nordbass_launcher.sh
Icon=$PROJECT_DIR/nordbass_icon.png
Terminal=false
Categories=AudioVideo;Engineering;
StartupNotify=true"

# Install to Desktop
echo "$DESKTOP_CONTENT" > "$DESKTOP_FILE"
chmod +x "$DESKTOP_FILE"

# Also install to application menu
mkdir -p "$HOME/.local/share/applications"
echo "$DESKTOP_CONTENT" > "$APPS_FILE"

# Mark as trusted (required by Ubuntu/GNOME to show the icon)
if command -v gio &>/dev/null; then
    gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
fi

echo ""
echo "Done! NordBass shortcut installed to:"
echo "  Desktop: $DESKTOP_FILE"
echo "  App menu: $APPS_FILE"
echo ""
echo "If the icon shows a question mark, right-click it → Allow Launching."
