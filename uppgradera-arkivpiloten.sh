#!/usr/bin/env bash
# ---------------------------------------------------------------------
#  Engångsuppgradering till den version som autouppdaterar sig.
#
#  Ligger ArkivPiloten 1.0.0/1.1.0 kvar på datorn hittar den aldrig de
#  nya releaserna (den letade i main-grenen). Kör det här skriptet en
#  gång: det hämtar senaste versionen, kontrollerar summan och lägger
#  filerna på plats. Regler, inställningar och historik rörs aldrig.
#
#    bash uppgradera-arkivpiloten.sh
#    bash uppgradera-arkivpiloten.sh --root /sökväg/till/appmappen
# ---------------------------------------------------------------------
set -u

SCRIPT_URL="https://github.com/Tokke2/ArkivPiloten/releases/latest/download/install_latest.py"
HÄR="$(cd "$(dirname "$0")" && pwd)"
TMPPY="$(mktemp "${TMPDIR:-/tmp}/arkivpiloten-uppg.XXXXXX.py")"
trap 'rm -f "$TMPPY"' EXIT

echo
echo "  ArkivPiloten – uppgradering till senaste versionen"
echo "  ================================================="
echo

PY=""
for kandidat in python3 python; do
    if command -v "$kandidat" >/dev/null 2>&1; then
        PY="$kandidat"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "  Hittar ingen Python 3. Installera det och kör igen."
    exit 1
fi
echo "  Python: $PY"

echo "  Hämtar hjälpskriptet ..."
if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$SCRIPT_URL" -o "$TMPPY" || { echo "  Kunde inte hämta skriptet."; exit 1; }
elif command -v wget >/dev/null 2>&1; then
    wget -q "$SCRIPT_URL" -O "$TMPPY" || { echo "  Kunde inte hämta skriptet."; exit 1; }
else
    echo "  Behöver curl eller wget."
    exit 1
fi

echo
echo "  Stäng ArkivPiloten om den är igång."
echo
"$PY" "$TMPPY" --root "$HÄR" "$@"
RC=$?

echo
if [ "$RC" = "0" ]; then
    echo "  Klart. Starta ArkivPiloten igen."
elif [ "$RC" = "2" ]; then
    echo "  Appen är redan uppdaterad – inget gjordes."
else
    echo "  Uppgraderingen gick inte igenom. Appmappen är orörd."
    echo "  Kör igen och läs felmeddelandet ovan."
fi
exit "$RC"
