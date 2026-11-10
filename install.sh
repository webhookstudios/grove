#!/bin/sh
# Installs Spool for the current user, without root, with an apps-menu entry.
set -e

APP_ID=io.github.webhookstudios.Spool
ROOT="$(cd "$(dirname "$0")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
DEST="$DATA/spool"

mkdir -p "$DEST" "$DATA/applications" "$DATA/icons/hicolor/scalable/apps"
rm -rf "$DEST/spool"
cp -r "$ROOT/spool" "$DEST/spool"
find "$DEST/spool" -name __pycache__ -prune -exec rm -rf {} +
cp "$ROOT/bin/spool" "$DEST/spool-launcher"
chmod +x "$DEST/spool-launcher"
cp "$ROOT/data/$APP_ID.svg" "$DATA/icons/hicolor/scalable/apps/"
sed -e "s|@EXEC@|python3 \"$DEST/spool-launcher\"|" -e "s|@ICON@|$DATA/icons/hicolor/scalable/apps/$APP_ID.svg|" \
    "$ROOT/data/$APP_ID.desktop.in" > "$DATA/applications/$APP_ID.desktop"
update-desktop-database "$DATA/applications" 2>/dev/null || true

echo "Spool is installed. Open it from the apps menu."
