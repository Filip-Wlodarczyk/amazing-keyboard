#!/usr/bin/env bash
# Installs Amazing Keyboard (amkb). The only sudo step: copying the IBus component file.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
PREFIX="$HOME/.local/share/amkb"
BIN="$HOME/.local/bin"
COMPONENT_DIR="/usr/share/ibus/component"

echo "==> Copying files to $PREFIX"
mkdir -p "$PREFIX/bin" "$BIN"
rm -rf "$PREFIX/amkb"
cp -r "$SRC/amkb" "$PREFIX/amkb"
find "$PREFIX/amkb" -name '__pycache__' -prune -exec rm -rf {} +

echo "==> Creating Python environment (with access to system gi/IBus)"
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

# Keyboard layout = first xkb layout from GNOME (e.g. 'us'), so your letters stay the same.
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
echo "==> Keyboard layout: $LAYOUT_NAME ${VARIANT:+(variant $VARIANT)}"

sed -e "s|@EXEC@|$PREFIX/bin/amkb-engine --ibus|" \
    -e "s|@LAYOUT@|$LAYOUT_NAME|" \
    -e "s|@VARIANT@|$VARIANT|" \
    "$SRC/data/amkb.xml.in" > "$PREFIX/amkb.xml"

if [ "${AMKB_SKIP_SYSTEM:-0}" = "1" ]; then
    echo "==> Skipping the system step. Run as root:"
    echo "    install -m 644 $PREFIX/amkb.xml $COMPONENT_DIR/amkb.xml && ibus restart"
    exit 0
fi
echo "==> Registering the engine with IBus (needs sudo)"
sudo install -m 644 "$PREFIX/amkb.xml" "$COMPONENT_DIR/amkb.xml"

echo "==> Restarting IBus"
ibus restart >/dev/null 2>&1 || true
sleep 2

case ":$PATH:" in
    *":$BIN:"*) ;;
    *) echo "NOTE: add $BIN to PATH (e.g. open a new terminal)";;
esac

cat <<EOF

Done! Next:
  amkb config -p openai            # choose a provider, type the key hidden
  amkb test                        # check that it works
  amkb activate                    # enable system-wide (Super+Space switches)
EOF
