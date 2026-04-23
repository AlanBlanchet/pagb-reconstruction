#!/usr/bin/env bash
set -euo pipefail

APP_NAME="PAGB-Reconstruction"
APP_DIR="${APP_NAME}.AppDir"

rm -rf "$APP_DIR" "${APP_NAME}*.AppImage"

mkdir -p "$APP_DIR/usr/bin" "$APP_DIR/usr/share/applications" "$APP_DIR/usr/share/icons/hicolor/256x256/apps"

cp -r dist/pagb-reconstruction/* "$APP_DIR/usr/bin/"

cp packaging/pagb-reconstruction.desktop "$APP_DIR/"
cp packaging/pagb-reconstruction.desktop "$APP_DIR/usr/share/applications/"

# Create a simple icon if none exists
if [ ! -f "$APP_DIR/usr/share/icons/hicolor/256x256/apps/pagb-reconstruction.png" ]; then
    convert -size 256x256 xc:#1e66f5 \
        -font DejaVu-Sans-Bold -pointsize 48 -fill white \
        -gravity center -annotate +0+0 "PAGB" \
        "$APP_DIR/usr/share/icons/hicolor/256x256/apps/pagb-reconstruction.png" 2>/dev/null || true
fi

cat > "$APP_DIR/AppRun" << 'EOF'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
exec "${HERE}/usr/bin/pagb-reconstruction" "$@"
EOF
chmod +x "$APP_DIR/AppRun"

if command -v appimagetool &> /dev/null; then
    ARCH=x86_64 appimagetool "$APP_DIR"
else
    echo "appimagetool not found — download from https://github.com/AppImage/appimagetool/releases"
    echo "AppDir created at $APP_DIR"
fi
