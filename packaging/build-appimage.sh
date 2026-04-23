#!/usr/bin/env bash
set -euo pipefail

APP_NAME="PAGB-Reconstruction"
APP_DIR="${APP_NAME}.AppDir"

rm -rf "$APP_DIR" "${APP_NAME}*.AppImage"

mkdir -p "$APP_DIR/usr/bin" "$APP_DIR/usr/share/applications" "$APP_DIR/usr/share/icons/hicolor/256x256/apps"

cp -r dist/pagb-reconstruction/* "$APP_DIR/usr/bin/"

cp packaging/pagb-reconstruction.desktop "$APP_DIR/"
cp packaging/pagb-reconstruction.desktop "$APP_DIR/usr/share/applications/"

# Generate icon with Pillow (available via matplotlib dependency)
ICON_PATH="$APP_DIR/usr/share/icons/hicolor/256x256/apps/pagb-reconstruction.png"
if [ ! -f "$ICON_PATH" ]; then
    python3 -c "
from PIL import Image, ImageDraw, ImageFont
import sys
img = Image.new('RGB', (256, 256), (30, 102, 245))
draw = ImageDraw.Draw(img)
try:
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 48)
except OSError:
    font = ImageFont.load_default(size=48)
bbox = draw.textbbox((0, 0), 'PAGB', font=font)
x = (256 - bbox[2] + bbox[0]) // 2
y = (256 - bbox[3] + bbox[1]) // 2
draw.text((x, y), 'PAGB', fill='white', font=font)
img.save(sys.argv[1])
" "$ICON_PATH"
fi
cp "$ICON_PATH" "$APP_DIR/pagb-reconstruction.png"

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
