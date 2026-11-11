#!/bin/sh
# Builds dist/grove_<version>_all.deb. Needs only dpkg-deb.
#
#   /usr/share/grove/grove/   the Python package
#   /usr/bin/grove             launcher
#   /usr/share/applications, /usr/share/icons   apps-menu entry and icon
set -e

APP_ID=io.github.webhookstudios.Grove
ROOT="$(cd "$(dirname "$0")" && pwd)"
VERSION="$(sed -n "s/^__version__ = '\(.*\)'/\1/p" "$ROOT/grove/__init__.py")"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

SHARE="$STAGE/usr/share/grove"
install -d "$SHARE/grove" "$STAGE/DEBIAN" "$STAGE/usr/bin" \
    "$STAGE/usr/share/applications" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps" \
    "$STAGE/usr/share/doc/grove"

install -m 644 "$ROOT"/grove/*.py "$ROOT/grove/style.css" "$SHARE/grove/"
cp -r "$ROOT/grove/sedge" "$SHARE/grove/"
find "$SHARE/grove/sedge" -type f -exec chmod 644 {} +
install -m 755 "$ROOT/bin/grove" "$STAGE/usr/bin/grove"
install -m 644 "$ROOT/data/$APP_ID.svg" "$STAGE/usr/share/icons/hicolor/scalable/apps/"
sed -e 's|@EXEC@|grove|' -e "s|@ICON@|$APP_ID|" "$ROOT/data/$APP_ID.desktop.in" \
    > "$STAGE/usr/share/applications/$APP_ID.desktop"
chmod 644 "$STAGE/usr/share/applications/$APP_ID.desktop"

cat > "$STAGE/usr/share/doc/grove/copyright" <<EOT
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: Grove (formerly Spool)
Source: https://github.com/webhookstudios/grove

Files: *
Copyright: $(date +%Y) webhookstudios
License: GPL-2+
 On Debian systems, the full text of the GNU General Public License
 version 2 can be found in /usr/share/common-licenses/GPL-2.

Files: usr/share/grove/grove/sedge/fonts/*
Copyright: 2023 The Young Serif Project Authors; 2015 The Public Sans Project Authors
License: OFL-1.1
 The full license texts are in usr/share/grove/grove/sedge/fonts/.
EOT
chmod 644 "$STAGE/usr/share/doc/grove/copyright"

# Replaces/Breaks take over from this app's old package name, spool.
cat > "$STAGE/DEBIAN/control" <<EOT
Package: grove
Version: $VERSION
Architecture: all
Maintainer: webhookstudios <354619278+webhookstudios@users.noreply.github.com>
Installed-Size: $(du -sk "$STAGE/usr" | cut -f1)
Depends: python3, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1 (>= 1.5), apt, dpkg, pkexec | policykit-1
Replaces: spool (<< 2~)
Breaks: spool (<< 2~)
Section: utils
Priority: optional
Homepage: https://github.com/webhookstudios/grove
Description: Grove, one library for all webhookstudios apps
 Grove (formerly Spool) lists every app published by webhookstudios on GitHub, installs and
 removes them with one click, and checks for new versions each time it
 opens. Installing and removing asks for your password once, through the
 normal system prompt.
EOT

find "$STAGE" -type d -exec chmod 755 {} +

mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build "$STAGE" "$ROOT/dist/grove_${VERSION}_all.deb"
