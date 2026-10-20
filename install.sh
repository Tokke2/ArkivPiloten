#!/usr/bin/env bash
# ==========================================================================
# ArkivPiloten - installation för macOS och Linux
# ==========================================================================
# Skapar en isolerad Python-miljö (.venv) i appmappen, installerar de
# pinnade paketen från requirements.txt, kontrollerar Tesseract/Tkinter
# och kan slå på autostart. Inget installeras systembrett och inga
# sudo-kommandon körs utan att du själv klistrar in dem.
#
#   ./install.sh                  frågar om autostart
#   ./install.sh --autostart      slår på autostart
#   ./install.sh --no-autostart   rör inte autostart
#   ./install.sh --uninstall      tar bort autostart + genvägar (data kvar)
#
# Windows: använd "ArkivPiloten - Installera senaste Python och starta.bat".
# ==========================================================================
set -euo pipefail

APPDIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
PYTHON="${PYTHON:-python3}"
AUTOSTART="ask"
MAKE_BUNDLE=1
MAKE_SHORTCUT=1
UNINSTALL=0
WITH_DEPS=1

usage() {
    cat <<'EOF'
ArkivPiloten - installation för macOS och Linux

Skapar en isolerad Python-miljö (.venv), installerar requirements.txt,
kontrollerar Tesseract/Tkinter och kan slå på autostart. Inget installeras
systembrett och inga sudo-kommandon körs.

  ./install.sh                  frågar om autostart
  ./install.sh --autostart      slår på autostart
  ./install.sh --no-autostart   rör inte autostart
  ./install.sh --uninstall      tar bort autostart + genvägar (data kvar)
EOF
    echo
    echo "Flaggor:"
    echo "  --autostart / --no-autostart   slå på/av autostart (annars frågas du)"
    echo "  --no-app-bundle                skapa ingen .app på macOS"
    echo "  --no-shortcut                  skapa inga skrivbords-/menyikoner"
    echo "  --no-deps                      hoppa över pip-installationen"
    echo "  --uninstall                    ta bort autostart och genvägar"
    echo "  -h, --help                     visa den här texten"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --autostart) AUTOSTART="yes" ;;
        --no-autostart) AUTOSTART="no" ;;
        --no-app-bundle) MAKE_BUNDLE=0 ;;
        --no-shortcut) MAKE_SHORTCUT=0 ;;
        --no-deps) WITH_DEPS=0 ;;
        --uninstall) UNINSTALL=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Okänt argument: $1" >&2; usage; exit 2 ;;
    esac
    shift
done

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
die()  { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

case "$(uname -s)" in
    Darwin) OS="macos" ;;
    Linux)  OS="linux" ;;
    *) die "Det här skriptet stöder macOS och Linux. På Windows: använd .bat-filen." ;;
esac

command -v "$PYTHON" >/dev/null 2>&1 || die "Hittar ingen '$PYTHON'. Installera Python 3.10+ och kör igen (eller sätt PYTHON=/sökväg/till/python3)."

"$PYTHON" - <<'PY' || die "Python 3.10 eller nyare krävs."
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY

# -- avinstallation --------------------------------------------------------
if [ "$UNINSTALL" = 1 ]; then
    say "Tar bort autostart och genvägar (dina regler och loggar rörs inte) ..."
    if [ -x "$APPDIR/.venv/bin/python" ]; then
        "$APPDIR/.venv/bin/python" "$APPDIR/pdfsorter.py" --remove-autostart || true
    else
        "$PYTHON" "$APPDIR/pdfsorter.py" --remove-autostart || true
    fi
    rm -rf "$HOME/Applications/ArkivPiloten.app"
    rm -f "$HOME/.local/share/applications/arkivpiloten.desktop"
    rm -f "$HOME/Desktop/arkivpiloten.desktop" "$HOME/Skrivbord/arkivpiloten.desktop"
    rm -f "$HOME/Desktop/Starta ArkivPiloten.command" "$HOME/Skrivbord/Starta ArkivPiloten.command"
    say "Klart. Appmappen och dess data är kvar."
    exit 0
fi

say "ArkivPiloten installeras från: $APPDIR"

# -- venv ------------------------------------------------------------------
if [ -w "$APPDIR" ]; then
    VENV="$APPDIR/.venv"
    PYBIN="$VENV/bin/python"
else
    DATA_BASE="${XDG_DATA_HOME:-$HOME/.local/share}/arkivpiloten"
    VENV="$DATA_BASE/venv"
    PYBIN="$VENV/bin/python"
    warn "Appmappen är skrivskyddad - Python-miljön läggs i $VENV."
fi

if [ ! -x "$PYBIN" ]; then
    say "Skapar virtuell Python-miljö: $VENV"
    if ! "$PYTHON" -m venv "$VENV"; then
        die "Kunde inte skapa venv. Debian/Ubuntu: sudo apt install python3-venv. Fedora: sudo dnf install python3."
    fi
fi

if [ "$WITH_DEPS" = 1 ]; then
    say "Installerar Python-paketen från requirements.txt (kan ta några minuter) ..."
    "$PYBIN" -m pip install --upgrade --disable-pip-version-check pip >/dev/null
    "$PYBIN" -m pip install --prefer-binary --disable-pip-version-check \
        -r "$APPDIR/requirements.txt" || die "pip-installationen misslyckades. Kör om med --no-deps för att hoppa över."
fi

# -- kontroller ------------------------------------------------------------
say "Kontrollerar installationen ..."
if ! "$PYBIN" -c 'import tkinter' >/dev/null 2>&1; then
    warn "Tkinter saknas - det grafiska gränssnittet kan inte startas."
    case "$OS" in
        linux) warn "  Debian/Ubuntu: sudo apt install python3-tk"
               warn "  Fedora:        sudo dnf install python3-tkinter"
               warn "  Arch:          sudo pacman -S tk" ;;
        macos) warn "  Homebrew: brew install python-tk  (python.org-versionen har Tk inbyggt)" ;;
    esac
fi

if command -v tesseract >/dev/null 2>&1; then
    if tesseract --list-langs 2>/dev/null | grep -qx "swe"; then
        say "Tesseract OCR: hittad med svenska + engelska."
    else
        warn "Tesseract finns men det svenska språkpaketet (swe) saknas."
        case "$OS" in
            linux) warn "  Debian/Ubuntu: sudo apt install tesseract-ocr-swe"
                   warn "  Fedora:        sudo dnf install tesseract-langpack-swe"
                   warn "  Arch:          sudo pacman -S tesseract-data-swe" ;;
            macos) warn "  brew install tesseract-lang" ;;
        esac
    fi
else
    warn "Tesseract saknas - skannade PDF:er kan inte OCR-läsas."
    case "$OS" in
        linux) warn "  Debian/Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-swe"
               warn "  Fedora:        sudo dnf install tesseract tesseract-langpack-swe"
               warn "  Arch:          sudo pacman -S tesseract tesseract-data-swe" ;;
        macos) warn "  brew install tesseract tesseract-lang" ;;
    esac
    warn "Appen fungerar ändå - den läser vanliga PDF:er utan OCR."
fi

"$PYBIN" "$APPDIR/pdfsorter.py" --status || true

# -- genvägar --------------------------------------------------------------
if [ "$MAKE_SHORTCUT" = 1 ]; then
    say "Skapar genvägar ..."
    "$PYBIN" "$APPDIR/pdfsorter.py" --make-shortcut || warn "Kunde inte skapa genväg (det går att göra senare i appen)."
fi

# -- macOS: riktig .app med Dock-ikon --------------------------------------
make_app_bundle() {
    [ "$OS" = "macos" ] || return 0
    [ "$MAKE_BUNDLE" = 1 ] || return 0
    local app="$HOME/Applications/ArkivPiloten.app"
    local version
    version="$(sed -n 's/^APP_VERSION = "\([^"]*\)".*/\1/p' "$APPDIR/pdfsorter.py" | head -1)"
    [ -n "$version" ] || version="1.1.0"
    say "Bygger $app ..."
    mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
    cat > "$app/Contents/MacOS/ArkivPiloten" <<EOF
#!/bin/sh
exec "$PYBIN" "$APPDIR/pdfsorter.py" "\$@"
EOF
    chmod 755 "$app/Contents/MacOS/ArkivPiloten"
    cat > "$app/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key><string>sv</string>
    <key>CFBundleDisplayName</key><string>ArkivPiloten</string>
    <key>CFBundleExecutable</key><string>ArkivPiloten</string>
    <key>CFBundleIconFile</key><string>ArkivPiloten</string>
    <key>CFBundleIdentifier</key><string>com.arkivpiloten.app</string>
    <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
    <key>CFBundleName</key><string>ArkivPiloten</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>$version</string>
    <key>CFBundleVersion</key><string>$version</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
EOF
    "$PYBIN" - "$APPDIR/ArkivPiloten.png" "$app/Contents/Resources/ArkivPiloten.icns" <<'PY' || warn "Kunde inte skapa .icns (Pillow saknas) - appen får standardikon."
import sys
from PIL import Image
Image.open(sys.argv[1]).save(sys.argv[2], format="ICNS")
PY
    if command -v codesign >/dev/null 2>&1; then
        codesign --force --deep --sign - "$app" >/dev/null 2>&1 || true
    fi
    say "Klart: $app (öppna med: open \"$app\")"
}
make_app_bundle

# -- autostart -------------------------------------------------------------
if [ "$AUTOSTART" = "ask" ]; then
    if [ -t 0 ]; then
        printf 'Starta ArkivPiloten automatiskt vid inloggning? [j/N] '
        read -r svar || svar=""
        case "$svar" in j|J|ja|Ja|JA|y|Y|yes|Yes) AUTOSTART="yes" ;; *) AUTOSTART="no" ;; esac
    else
        AUTOSTART="no"
    fi
fi

if [ "$AUTOSTART" = "yes" ]; then
    say "Slår på autostart ..."
    "$PYBIN" "$APPDIR/pdfsorter.py" --install-autostart || warn "Autostarten kunde inte slås på. Öppna appen och kryssa i Inställningar i stället."
else
    say "Autostart lämnas avstängt (slå på i appen under Inställningar)."
fi

say "Klart!"
echo "  Starta:     $PYBIN \"$APPDIR/pdfsorter.py\""
if [ "$OS" = "macos" ] && [ "$MAKE_BUNDLE" = 1 ]; then
    echo "  App-ikon:   ~/Applications/ArkivPiloten.app"
fi
echo "  Regler:     sparas i appmappen (json/) eller i användarens data-mapp om appmappen är skrivskyddad"
echo "  Diagnostik: $PYBIN \"$APPDIR/pdfsorter.py\" --status"
