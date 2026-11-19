#!/usr/bin/env bash
# Instalacja Amazing Keyboard (amkb). Jedyny krok z sudo: skopiowanie pliku komponentu IBus.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
PREFIX="$HOME/.local/share/amkb"
BIN="$HOME/.local/bin"
COMPONENT_DIR="/usr/share/ibus/component"

echo "==> Kopiuję pliki do $PREFIX"
mkdir -p "$PREFIX/bin" "$BIN"
rm -rf "$PREFIX/amkb"
cp -r "$SRC/amkb" "$PREFIX/amkb"
find "$PREFIX/amkb" -name '__pycache__' -prune -exec rm -rf {} +

echo "==> Tworzę środowisko Pythona (z dostępem do systemowego gi/IBus)"
if [ ! -x "$PREFIX/venv/bin/python" ]; then
    python3 -m venv --system-site-packages "$PREFIX/venv"
fi
"$PREFIX/venv/bin/pip" install --quiet --upgrade anthropic

cat > "$PREFIX/bin/amkb-engine" <<EOF
#!/bin/sh
export PYTHONPATH="$PREFIX\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$PREFIX/venv/bin/python" -m amkb.engine "\$@"
EOF
cat > "$BIN/amkb" <<EOF
#!/bin/sh
export PYTHONPATH="$PREFIX\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$PREFIX/venv/bin/python" -m amkb.cli "\$@"
EOF
chmod +x "$PREFIX/bin/amkb-engine" "$BIN/amkb"

# Układ klawiatury = pierwszy układ xkb z GNOME (np. 'pl'), żeby litery się nie zmieniły.
LAYOUT="$(python3 - <<'PY'
import ast, subprocess
try:
    out = subprocess.run(["gsettings", "get", "org.gnome.desktop.input-sources", "sources"],
                         capture_output=True, text=True).stdout.strip()
    out = out.removeprefix("@a(ss) ")
    for kind, name in ast.literal_eval(out or "[]"):
        if kind == "xkb":
            print(name); break
    else:
        print("us")
except Exception:
    print("us")
PY
)"
LAYOUT_NAME="${LAYOUT%%+*}"
VARIANT=""
[[ "$LAYOUT" == *+* ]] && VARIANT="${LAYOUT#*+}"
echo "==> Układ klawiatury: $LAYOUT_NAME ${VARIANT:+(wariant $VARIANT)}"

sed -e "s|@EXEC@|$PREFIX/bin/amkb-engine --ibus|" \
    -e "s|@LAYOUT@|$LAYOUT_NAME|" \
    -e "s|@VARIANT@|$VARIANT|" \
    "$SRC/data/amkb.xml.in" > "$PREFIX/amkb.xml"

if [ "${AMKB_SKIP_SYSTEM:-0}" = "1" ]; then
    echo "==> Pomijam krok systemowy. Wykonaj jako root:"
    echo "    install -m 644 $PREFIX/amkb.xml $COMPONENT_DIR/amkb.xml && ibus restart"
    exit 0
fi
echo "==> Rejestruję silnik w IBus (wymaga sudo)"
sudo install -m 644 "$PREFIX/amkb.xml" "$COMPONENT_DIR/amkb.xml"

echo "==> Restart IBus"
ibus restart >/dev/null 2>&1 || true
sleep 2

case ":$PATH:" in
    *":$BIN:"*) ;;
    *) echo "UWAGA: dodaj $BIN do PATH (np. otwórz nowy terminal)";;
esac

cat <<EOF

Gotowe! Dalej:
  amkb config -p openai            # wybierz dostawcę, klucz wpiszesz niewidocznie
  amkb test                        # sprawdź czy działa
  amkb activate                    # włącz w systemie (Super+Spacja przełącza)
EOF
