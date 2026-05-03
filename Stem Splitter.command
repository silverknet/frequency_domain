#!/bin/bash
# Stem Splitter launcher — sets up a virtual environment and installs all dependencies.

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$DIR/stem_splitter.py"
VENV="$DIR/.venv"

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$PATH"

echo "╔══════════════════════════╗"
echo "║      Stem Splitter       ║"
echo "╚══════════════════════════╝"
echo ""

# ── Homebrew ──────────────────────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
    echo "[ Installing Homebrew... ]"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    export PATH="/opt/homebrew/bin:$PATH"
else
    echo "✓  Homebrew"
fi

# ── ffmpeg ────────────────────────────────────────────────────────────────────
if ! command -v ffmpeg &>/dev/null; then
    echo "[ Installing ffmpeg... ]"
    brew install ffmpeg
else
    echo "✓  ffmpeg"
fi

# ── Base Python — must have working Tkinter (not pip-installable) ─────────────
#    python.org Python bundles its own Tcl/Tk. Homebrew python-tk may have
#    binary compatibility issues on macOS 26+.

tk_works() { "$1" -c "import tkinter" &>/dev/null 2>&1; }

find_base_python() {
    local candidates=()

    # python.org — glob all installed versions (bundled Tcl/Tk, most reliable)
    for f in /Library/Frameworks/Python.framework/Versions/*/bin/python3; do
        [ -x "$f" ] && candidates+=("$f")
    done

    # python.org symlinks in /usr/local/bin
    for f in /usr/local/bin/python3 /usr/local/bin/python3.*; do
        [ -x "$f" ] && candidates+=("$f")
    done

    # Homebrew — glob all installed versions
    for f in /opt/homebrew/opt/python@*/bin/python3; do
        [ -x "$f" ] && candidates+=("$f")
    done

    for P in "${candidates[@]}"; do
        if tk_works "$P"; then
            echo "$P"
            return 0
        fi
    done
    return 1
}

BASE_PYTHON=$(find_base_python)

# If nothing works yet, try installing Homebrew python-tk and retest
if [ -z "$BASE_PYTHON" ]; then
    for formula in python@3.13 python@3.12 python@3.11; do
        PREFIX=$(brew --prefix "$formula" 2>/dev/null)
        if [ -n "$PREFIX" ] && [ -x "$PREFIX/bin/python3" ]; then
            VERSION=$("$PREFIX/bin/python3" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
            echo "[ Installing python-tk@${VERSION}... ]"
            brew install "python-tk@${VERSION}" 2>/dev/null
            if tk_works "$PREFIX/bin/python3"; then
                BASE_PYTHON="$PREFIX/bin/python3"
                break
            fi
        fi
    done
fi

if [ -z "$BASE_PYTHON" ]; then
    echo ""
    echo "⚠  No Python with working Tkinter found."
    echo ""
    echo "   Pythons checked:"
    for f in \
        /Library/Frameworks/Python.framework/Versions/*/bin/python3 \
        /usr/local/bin/python3 \
        /opt/homebrew/opt/python@*/bin/python3; do
        [ -x "$f" ] && echo "     $f  $(tk_works "$f" && echo '✓ tkinter ok' || echo '✗ tkinter failed')"
    done
    echo ""
    echo "   If none show '✓ tkinter ok', install Python from python.org:"
    echo "   python.org/downloads  →  download the macOS .pkg  →  run installer"
    echo "   Then relaunch Stem Splitter."
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

echo "✓  Python  ($BASE_PYTHON)"

# ── SSL certificates — python.org Python ships without them configured ────────
#    The installer includes "Install Certificates.command" but many users skip it.
ssl_ok() { "$1" -c "import urllib.request; urllib.request.urlopen('https://example.com')" &>/dev/null 2>&1; }

if ! ssl_ok "$BASE_PYTHON"; then
    CERT_SCRIPT=$(ls "/Applications/Python"*/Install\ Certificates.command 2>/dev/null | tail -1)
    if [ -n "$CERT_SCRIPT" ]; then
        echo "[ Installing SSL certificates... ]"
        bash "$CERT_SCRIPT" &>/dev/null && echo "✓  SSL certificates" || echo "⚠  SSL install had warnings (may still work)"
    fi
fi

# ── Virtual environment ───────────────────────────────────────────────────────
# Recreate the venv if it doesn't exist or its base Python changed
VENV_PYTHON="$VENV/bin/python3"
CURRENT_BASE=$([ -f "$VENV/base_python" ] && cat "$VENV/base_python")

if [ ! -x "$VENV_PYTHON" ] || [ "$CURRENT_BASE" != "$BASE_PYTHON" ]; then
    echo "[ Creating virtual environment... ]"
    "$BASE_PYTHON" -m venv "$VENV"
    echo "$BASE_PYTHON" > "$VENV/base_python"
fi

echo "✓  Virtual environment  ($VENV)"

# ── Demucs + torchcodec (installed into venv) ────────────────────────────────
if ! "$VENV_PYTHON" -c "import demucs" 2>/dev/null; then
    echo "[ Installing demucs into venv... ]"
    "$VENV_PYTHON" -m pip install --quiet demucs
else
    echo "✓  Demucs"
fi

if ! "$VENV_PYTHON" -c "import torchcodec" 2>/dev/null; then
    echo "[ Installing torchcodec into venv... ]"
    "$VENV_PYTHON" -m pip install --quiet torchcodec
else
    echo "✓  torchcodec"
fi

echo ""
echo "Launching..."
echo ""

"$VENV_PYTHON" "$SCRIPT"
