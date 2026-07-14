#!/bin/bash
# CustomWhisper installer for macOS (Apple Silicon).
#
# 1. Creates a Python 3.11 virtual environment and installs the Mac deps
#    (mlx-whisper transcription backend + PyQt5 UI).
# 2. Builds a CustomWhisper.app bundle so the app has its OWN identity for macOS
#    privacy permissions — you grant "CustomWhisper" directly instead of your
#    terminal. This is what makes the global hotkey and typing actually work.
#
# Run from the repo root:  ./install-mac.sh
#
set -euo pipefail
cd "$(dirname "$0")"
REPO="$PWD"

echo "== CustomWhisper macOS installer =="

if [ "$(uname)" != "Darwin" ]; then
    echo "This installer is for macOS. On Windows use install.ps1."
    exit 1
fi

# --- locate a Python 3.11 interpreter ---------------------------------------
PYBIN=""
for cand in python3.11 /opt/homebrew/bin/python3.11 /usr/local/bin/python3.11; do
    if command -v "$cand" >/dev/null 2>&1; then
        PYBIN="$cand"; break
    fi
done
if [ -z "$PYBIN" ]; then
    echo "Python 3.11 not found."
    if command -v brew >/dev/null 2>&1; then
        echo "Install it with: brew install python@3.11"
    else
        echo "Install Homebrew (https://brew.sh) then: brew install python@3.11"
    fi
    exit 1
fi
echo "Using $("$PYBIN" --version) at $(command -v "$PYBIN")"

# --- create venv + install deps ---------------------------------------------
if [ ! -d venv ]; then
    echo "Creating virtual environment (venv/)..."
    "$PYBIN" -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
python -m pip install --upgrade pip
echo "Installing dependencies from requirements-mac.txt (downloads PyTorch/MLX; give it a minute)..."
pip install -r requirements-mac.txt

# --- build CustomWhisper.app -------------------------------------------------
echo "Building CustomWhisper.app..."
APP="$REPO/CustomWhisper.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# Launcher: cd into the repo and run the app with the venv's python. Launched via
# LaunchServices (double-click / `open`), this bundle becomes the TCC-responsible
# process, so permissions granted to "CustomWhisper" apply to it.
cat > "$APP/Contents/MacOS/CustomWhisper" <<EOF
#!/bin/bash
cd "$REPO" || exit 1
exec "$REPO/venv/bin/python" run.py >> "$REPO/app_out.txt" 2>&1
EOF
chmod +x "$APP/Contents/MacOS/CustomWhisper"

cat > "$APP/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>            <string>CustomWhisper</string>
    <key>CFBundleDisplayName</key>     <string>CustomWhisper</string>
    <key>CFBundleIdentifier</key>      <string>com.customwhisper.app</string>
    <key>CFBundleExecutable</key>      <string>CustomWhisper</string>
    <key>CFBundleVersion</key>         <string>1.0</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>CFBundlePackageType</key>     <string>APPL</string>
    <key>CFBundleIconFile</key>        <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>  <string>11.0</string>
    <key>LSUIElement</key>             <true/>
    <key>NSHighResolutionCapable</key> <true/>
    <key>NSMicrophoneUsageDescription</key><string>CustomWhisper transcribes your microphone into the active app.</string>
</dict>
</plist>
EOF

# Best-effort app icon from the existing logo (ignored if tools are missing).
if command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1 \
        && [ -f assets/ww-logo-custom.png ]; then
    ICONSET="$(mktemp -d)/AppIcon.iconset"; mkdir -p "$ICONSET"
    for sz in 16 32 64 128 256 512; do
        sips -z $sz $sz assets/ww-logo-custom.png --out "$ICONSET/icon_${sz}x${sz}.png" >/dev/null 2>&1 || true
        sips -z $((sz*2)) $((sz*2)) assets/ww-logo-custom.png --out "$ICONSET/icon_${sz}x${sz}@2x.png" >/dev/null 2>&1 || true
    done
    iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns" >/dev/null 2>&1 || true
fi

# Register the bundle with LaunchServices so `open -a CustomWhisper` and the
# privacy panes recognize it immediately.
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
    -f "$APP" >/dev/null 2>&1 || true

cat <<EOF

== Install complete ==

Built: $APP

CustomWhisper needs THREE macOS privacy permissions. Because it's now its own
app, grant them to "CustomWhisper" itself (not your terminal):

  System Settings > Privacy & Security >
    1. Microphone        -> enable CustomWhisper
    2. Accessibility     -> enable CustomWhisper   (lets it type the text in)
    3. Input Monitoring  -> enable CustomWhisper   (lets it see the hotkey)

How to grant them the first time:
  * Launch the app once:   open "$APP"      (or double-click it in Finder)
  * Trigger a dictation (press Ctrl+Shift+Space). macOS will prompt / add
    "CustomWhisper" to the Accessibility & Input Monitoring lists — switch it ON.
  * If a permission was already listed, toggle it OFF then ON, then relaunch:
        osascript -e 'quit app "CustomWhisper"'   # or use the tray Exit
        open "$APP"

Then: put your cursor in any text field, press Ctrl+Shift+Space, speak, pause —
the transcription is typed into that field. Recording mode / device / paste-vs-type
are all in the tray > Open Settings window.
EOF
