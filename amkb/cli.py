"""amkb – konfiguracja i sterowanie podpowiedziami AI z terminala."""

import argparse
import getpass
import subprocess
import sys

from amkb import __version__, config, providers

ENGINE_SOURCE = ("ibus", "amkb")


def mask(key: str | None) -> str:
    if not key:
        return "(brak)"
    return key[:4] + "…" + key[-4:] if len(key) > 10 else "****"


def cmd_config(a):
    cfg = config.load()
    if a.provider:
        if a.provider not in providers.PROVIDERS:
            sys.exit(f"Nieznany dostawca '{a.provider}'. Lista: amkb providers")
        if a.provider != cfg.get("provider"):
            cfg["model"] = None
            cfg["base_url"] = None
        cfg["provider"] = a.provider
    if a.api_key is not None:
        cfg["api_key"] = a.api_key.strip() or None
    if a.model is not None:
        cfg["model"] = a.model or None
    if a.base_url is not None:
        cfg["base_url"] = a.base_url or None
    for field in ("debounce_ms", "max_words", "min_chars", "display"):
        val = getattr(a, field)
        if val is not None:
            cfg[field] = val
    if a.debug is not None:
        cfg["debug"] = a.debug == "on"

    spec = providers.PROVIDERS.get(cfg.get("provider") or "")
    if spec and spec["needs_key"] and not cfg.get("api_key") and sys.stdin.isatty():
        cfg["api_key"] = getpass.getpass(f"Klucz API dla {spec['label']} (niewidoczny): ").strip() or None

    config.save(cfg)
    print(f"Zapisano {config.CONFIG_FILE}")
    print_status(cfg)


def cmd_setup(_a):
    cfg = config.load()
    names = list(providers.PROVIDERS)
    print("Wybierz dostawcę:")
    for i, n in enumerate(names, 1):
        print(f"  {i}. {n:<11} {providers.PROVIDERS[n]['label']}")
    choice = input("Numer lub nazwa: ").strip()
    name = names[int(choice) - 1] if choice.isdigit() and 0 < int(choice) <= len(names) else choice
    if name not in providers.PROVIDERS:
        sys.exit("Nieznany dostawca.")
    spec = providers.PROVIDERS[name]
    cfg.update(provider=name, model=None, base_url=None)
    if spec["needs_key"] or name == "custom":
        key = getpass.getpass("Klucz API (niewidoczny, Enter = bez klucza): ").strip()
        cfg["api_key"] = key or None
    if name == "custom" or not spec["base_url"] and spec["kind"] == "openai":
        cfg["base_url"] = input("Base URL (np. http://localhost:8080/v1): ").strip() or None
    model = input(f"Model [{spec['model'] or 'wymagany'}]: ").strip()
    cfg["model"] = model or None
    config.save(cfg)
    print("Zapisano. Test połączenia…")
    _run_test(cfg, "Dzień dobry, chciałbym zapytać czy")


def cmd_providers(_a):
    for n, s in providers.PROVIDERS.items():
        print(f"{n:<11} {s['label']:<46} domyślny model: {s['model'] or '-'}")


def print_status(cfg):
    spec = providers.PROVIDERS.get(cfg.get("provider") or "")
    print(f"  dostawca : {cfg.get('provider') or '(brak)'}")
    print(f"  model    : {cfg.get('model') or (spec and spec['model']) or '-'}")
    if cfg.get("base_url") or (spec and spec["base_url"]):
        print(f"  base url : {cfg.get('base_url') or spec['base_url']}")
    print(f"  klucz    : {mask(cfg.get('api_key'))}")
    print(f"  włączone : {'tak' if cfg.get('enabled') else 'nie'}")
    print(f"  wygląd   : {cfg.get('display')}, opóźnienie {cfg.get('debounce_ms')} ms, max {cfg.get('max_words')} słów")


def cmd_status(_a):
    cfg = config.load()
    print(f"amkb {__version__}")
    print_status(cfg)
    try:
        engines = subprocess.run(["ibus", "list-engine", "--name-only"], capture_output=True, text=True, timeout=5).stdout
        registered = "amkb" in engines.split()
    except (OSError, subprocess.SubprocessError):
        registered = False
    print(f"  silnik IBus zarejestrowany : {'tak' if registered else 'NIE (uruchom ./install.sh)'}")
    print(f"  źródło wprowadzania GNOME  : {'tak' if ENGINE_SOURCE in _get_sources() else 'nie (amkb activate)'}")
    try:
        cur = subprocess.run(["ibus", "engine"], capture_output=True, text=True, timeout=5).stdout.strip()
        print(f"  aktywny silnik             : {cur}")
    except (OSError, subprocess.SubprocessError):
        pass


def _run_test(cfg, text):
    try:
        out = providers.complete(cfg, text)
    except providers.ProviderError as e:
        sys.exit(f"Błąd: {e}")
    print(f"{text}\033[90m{out}\033[0m")
    if not out:
        print("(model nie zwrócił podpowiedzi)")


def cmd_test(a):
    _run_test(config.load(), " ".join(a.text) if a.text else "Dzień dobry, chciałbym zapytać czy")


def cmd_toggle(a):
    cfg = config.load()
    cfg["enabled"] = a.cmd == "on"
    config.save(cfg)
    print("Podpowiedzi " + ("włączone" if cfg["enabled"] else "wyłączone"))


# --- źródła wprowadzania GNOME ---------------------------------------------------

def _settings():
    from gi.repository import Gio
    return Gio.Settings.new("org.gnome.desktop.input-sources")


def _get_sources():
    try:
        return [tuple(x) for x in _settings().get_value("sources").unpack()]
    except Exception:  # noqa: BLE001
        return []


def _set_sources(sources):
    from gi.repository import Gio, GLib
    s = _settings()
    s.set_value("sources", GLib.Variant("a(ss)", sources))
    Gio.Settings.sync()


def cmd_activate(_a):
    sources = [s for s in _get_sources() if s != ENGINE_SOURCE]
    _set_sources([ENGINE_SOURCE] + sources)
    subprocess.run(["ibus", "engine", "amkb"], capture_output=True)
    print("Dodano 'Amazing Keyboard (AI)' do źródeł wprowadzania i ustawiono jako aktywne.")
    print("Przełączanie: Super+Spacja. Wyłączenie podpowiedzi: amkb off")


def cmd_deactivate(_a):
    sources = [s for s in _get_sources() if s != ENGINE_SOURCE]
    if not sources:
        sources = [("xkb", "us")]
    _set_sources(sources)
    print("Usunięto amkb ze źródeł wprowadzania.")


def cmd_log(_a):
    try:
        print(config.LOG_FILE.read_text(encoding="utf-8")[-5000:])
    except FileNotFoundError:
        print("(brak logu)")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="amkb",
        description="Amazing Keyboard – podpowiedzi AI w każdym polu tekstowym (Tab = wstaw).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("config", help="ustaw dostawcę, klucz API, model…")
    c.add_argument("-p", "--provider", help="openai, anthropic, gemini, groq, openrouter, mistral, deepseek, ollama, custom")
    c.add_argument("-k", "--api-key", help="klucz API (pomiń, aby wpisać go niewidocznie)")
    c.add_argument("-m", "--model", help="nazwa modelu (pusty = domyślny)")
    c.add_argument("--base-url", help="adres API zgodnego z OpenAI (dla custom/ollama)")
    c.add_argument("--debounce-ms", type=int)
    c.add_argument("--max-words", type=int)
    c.add_argument("--min-chars", type=int)
    c.add_argument("--display", choices=["inline", "popup"])
    c.add_argument("--debug", choices=["on", "off"])
    c.set_defaults(func=cmd_config)

    sub.add_parser("setup", help="interaktywny kreator").set_defaults(func=cmd_setup)
    sub.add_parser("providers", help="lista dostawców").set_defaults(func=cmd_providers)
    sub.add_parser("status", help="pokaż konfigurację i stan").set_defaults(func=cmd_status)
    t = sub.add_parser("test", help="sprawdź podpowiedź w terminalu")
    t.add_argument("text", nargs="*")
    t.set_defaults(func=cmd_test)
    sub.add_parser("on", help="włącz podpowiedzi").set_defaults(func=cmd_toggle)
    sub.add_parser("off", help="wyłącz podpowiedzi").set_defaults(func=cmd_toggle)
    sub.add_parser("activate", help="dodaj do źródeł wprowadzania GNOME i włącz").set_defaults(func=cmd_activate)
    sub.add_parser("deactivate", help="usuń ze źródeł wprowadzania GNOME").set_defaults(func=cmd_deactivate)
    sub.add_parser("log", help="pokaż log silnika").set_defaults(func=cmd_log)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
