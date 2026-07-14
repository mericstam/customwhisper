#!/usr/bin/env bash
# CustomWhisper installer for Linux (Ubuntu 22.04+).
#
# Creates a Python venv, installs the Linux requirements, and prints the system
# packages and permission steps you still need to do by hand. Re-runnable.
#
# Usage:  ./install.sh            # CPU/GPU auto (whatever ctranslate2 finds)
#         ./install.sh --help
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PYTHON="${PYTHON:-python3}"
VENV="$HERE/venv"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    sed -n '2,12p' "$0"
    exit 0
fi

echo "==> Creating virtualenv at $VENV"
if [[ ! -d "$VENV" ]]; then
    "$PYTHON" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "==> Upgrading pip and installing requirements-linux.txt"
python -m pip install --upgrade pip
python -m pip install -r "$HERE/requirements-linux.txt"

cat <<'NOTES'

==> Python packages installed.

System packages still needed (install with apt, once):

    sudo apt update
    sudo apt install -y \
        libportaudio2 libsndfile1 ffmpeg \
        libxcb-xinerama0 libxcb-cursor0 \
        gstreamer1.0-plugins-good     # optional: for the completion beep

  X11 session (simplest):     sudo apt install -y xclip
  Wayland session:            sudo apt install -y wl-clipboard ydotool

GPU (NVIDIA/CUDA) — ctranslate2 4.2.1 needs cuBLAS + cuDNN 8:

    pip install nvidia-cublas-cu12 'nvidia-cudnn-cu12==8.*'
    # then add their lib dirs to LD_LIBRARY_PATH (or use a system CUDA install)

Choosing the input path (Settings > recording_options.input_backend):

  * Xorg session ("Ubuntu on Xorg" at login):  input_backend=pynput,
    input_method=clipboard (needs xclip). No extra permissions.
  * Wayland session:  input_backend=evdev  ->  add yourself to the input group
    and re-login:   sudo usermod -aG input "$USER"
    Typing: set post_processing.input_method=ydotool and run ydotoold with
    access to /dev/uinput. Use the wake listener's default --trigger auto so it
    pokes the app over IPC instead of faking a keystroke.

Run it:

    ./start-customwhisper.sh      # app only (hotkey activation)
    ./start-hands-free.sh         # app + "Hey Jarvis" wake listener
    ./stop-customwhisper.sh       # stop everything

NOTES
echo "==> Done."
