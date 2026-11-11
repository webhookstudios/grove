#!/bin/sh
# Installs Grove for the current user, without root, with an apps-menu entry.
set -e

APP_ID=io.github.webhookstudios.Grove
ROOT="$(cd "$(dirname "$0")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
DEST="$DATA/grove"

mkdir -p "$DEST" "$DATA/applications" "$DATA/icons/hicolor/scalable/apps"
rm -rf "$DEST/grove"
cp -r "$ROOT/grove" "$DEST/grove"
find "$DEST/grove" -name __pycache__ -prune -exec rm -rf {} +
cp "$ROOT/bin/grove" "$DEST/grove-launcher"
chmod +x "$DEST/grove-launcher"
cp "$ROOT/data/$APP_ID.svg" "$DATA/icons/hicolor/scalable/apps/"
sed -e "s|@EXEC@|python3 \"$DEST/grove-launcher\"|" -e "s|@ICON@|$DATA/icons/hicolor/scalable/apps/$APP_ID.svg|" \
    "$ROOT/data/$APP_ID.desktop.in" > "$DATA/applications/$APP_ID.desktop"
update-desktop-database "$DATA/applications" 2>/dev/null || true

echo "Grove is installed. Open it from the apps menu."
