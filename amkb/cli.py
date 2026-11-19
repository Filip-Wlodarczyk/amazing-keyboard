"""amkb – configure and control AI suggestions from the terminal."""

import argparse
import getpass
import subprocess
import sys

from amkb import __version__, config, providers

ENGINE_SOURCE = ("ibus", "amkb")


def mask(key: str | None) -> str:
    if not key:
        return "(none)"
    return key[:4] + "…" + key[-4:] if len(key) > 10 else "****"


def cmd_config(a):
    cfg = config.load()
    if a.provider:
        if a.provider not in providers.PROVIDERS:
            sys.exit(f"Unknown provider '{a.provider}'. List: amkb providers")
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
        cfg["api_key"] = getpass.getpass(f"API key for {spec['label']} (hidden): ").strip() or None

    config.save(cfg)
    print(f"Saved {config.CONFIG_FILE}")
    print_status(cfg)


def cmd_setup(_a):
    cfg = config.load()
    names = list(providers.PROVIDERS)
    print("Choose a provider:")
    for i, n in enumerate(names, 1):
        print(f"  {i}. {n:<11} {providers.PROVIDERS[n]['label']}")
    choice = input("Number or name: ").strip()
    name = names[int(choice) - 1] if choice.isdigit() and 0 < int(choice) <= len(names) else choice
    if name not in providers.PROVIDERS:
        sys.exit("Unknown provider.")
    spec = providers.PROVIDERS[name]
    cfg.update(provider=name, model=None, base_url=None)
    if spec["needs_key"] or name == "custom":
        key = getpass.getpass("API key (hidden, Enter = no key): ").strip()
        cfg["api_key"] = key or None
    if name == "custom" or not spec["base_url"] and spec["kind"] == "openai":
        cfg["base_url"] = input("Base URL (e.g. http://localhost:8080/v1): ").strip() or None
    model = input(f"Model [{spec['model'] or 'required'}]: ").strip()
    cfg["model"] = model or None
    config.save(cfg)
    print("Saved. Testing connection…")
    _run_test(cfg, "Good morning, I would like to ask whether")


def cmd_providers(_a):
    for n, s in providers.PROVIDERS.items():
        print(f"{n:<11} {s['label']:<46} default model: {s['model'] or '-'}")


def print_status(cfg):
    spec = providers.PROVIDERS.get(cfg.get("provider") or "")
    print(f"  provider : {cfg.get('provider') or '(none)'}")
    print(f"  model    : {cfg.get('model') or (spec and spec['model']) or '-'}")
    if cfg.get("base_url") or (spec and spec["base_url"]):
        print(f"  base url : {cfg.get('base_url') or spec['base_url']}")
    print(f"  api key  : {mask(cfg.get('api_key'))}")
    print(f"  enabled  : {'yes' if cfg.get('enabled') else 'no'}")
    print(f"  display  : {cfg.get('display')}, delay {cfg.get('debounce_ms')} ms, max {cfg.get('max_words')} words")


def cmd_status(_a):
    cfg = config.load()
    print(f"amkb {__version__}")
    print_status(cfg)
    try:
        engines = subprocess.run(["ibus", "list-engine", "--name-only"], capture_output=True, text=True, timeout=5).stdout
        registered = "amkb" in engines.split()
    except (OSError, subprocess.SubprocessError):
        registered = False
    print(f"  IBus engine registered : {'yes' if registered else 'NO (run ./install.sh)'}")
    print(f"  GNOME input source     : {'yes' if ENGINE_SOURCE in _get_sources() else 'no (amkb activate)'}")
    try:
        cur = subprocess.run(["ibus", "engine"], capture_output=True, text=True, timeout=5).stdout.strip()
        print(f"  active engine          : {cur}")
    except (OSError, subprocess.SubprocessError):
        pass


def _run_test(cfg, text):
    try:
        out = providers.complete(cfg, text)
    except providers.ProviderError as e:
        sys.exit(f"Error: {e}")
    print(f"{text}\033[90m{out}\033[0m")
    if not out:
        print("(the model returned no suggestion)")


def cmd_test(a):
    _run_test(config.load(), " ".join(a.text) if a.text else "Good morning, I would like to ask whether")


def cmd_toggle(a):
    cfg = config.load()
    cfg["enabled"] = a.cmd == "on"
    config.save(cfg)
    print("Suggestions " + ("enabled" if cfg["enabled"] else "disabled"))


# --- GNOME input sources ---------------------------------------------------

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
    print("Added 'Amazing Keyboard (AI)' to input sources and made it active.")
    print("Switch with Super+Space. Turn suggestions off with: amkb off")


def cmd_deactivate(_a):
    sources = [s for s in _get_sources() if s != ENGINE_SOURCE]
    if not sources:
        sources = [("xkb", "us")]
    _set_sources(sources)
    print("Removed amkb from input sources.")


def cmd_log(_a):
    try:
        print(config.LOG_FILE.read_text(encoding="utf-8")[-5000:])
    except FileNotFoundError:
        print("(no log)")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="amkb",
        description="Amazing Keyboard – AI suggestions in every text field (Tab = insert).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("config", help="set provider, API key, model…")
    c.add_argument("-p", "--provider", help="openai, anthropic, gemini, groq, openrouter, mistral, deepseek, ollama, custom")
    c.add_argument("-k", "--api-key", help="API key (omit to type it hidden)")
    c.add_argument("-m", "--model", help="model name (empty = default)")
    c.add_argument("--base-url", help="OpenAI-compatible API URL (for custom/ollama)")
    c.add_argument("--debounce-ms", type=int)
    c.add_argument("--max-words", type=int)
    c.add_argument("--min-chars", type=int)
    c.add_argument("--display", choices=["inline", "popup"])
    c.add_argument("--debug", choices=["on", "off"])
    c.set_defaults(func=cmd_config)

    sub.add_parser("setup", help="interactive wizard").set_defaults(func=cmd_setup)
    sub.add_parser("providers", help="list providers").set_defaults(func=cmd_providers)
    sub.add_parser("status", help="show configuration and state").set_defaults(func=cmd_status)
    t = sub.add_parser("test", help="try a suggestion in the terminal")
    t.add_argument("text", nargs="*")
    t.set_defaults(func=cmd_test)
    sub.add_parser("on", help="enable suggestions").set_defaults(func=cmd_toggle)
    sub.add_parser("off", help="disable suggestions").set_defaults(func=cmd_toggle)
    sub.add_parser("activate", help="add to GNOME input sources and activate").set_defaults(func=cmd_activate)
    sub.add_parser("deactivate", help="remove from GNOME input sources").set_defaults(func=cmd_deactivate)
    sub.add_parser("log", help="show the engine log").set_defaults(func=cmd_log)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
