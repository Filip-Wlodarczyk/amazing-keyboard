#!/usr/bin/env bash
set -euo pipefail
"$HOME/.local/bin/amkb" deactivate 2>/dev/null || true
sudo rm -f /usr/share/ibus/component/amkb.xml
rm -rf "$HOME/.local/share/amkb" "$HOME/.local/bin/amkb"
ibus restart >/dev/null 2>&1 || true
echo "Odinstalowano. Konfiguracja (z kluczem API) zostaje w ~/.config/amkb – usuń ją ręcznie, jeśli chcesz."
