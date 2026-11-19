"""Configuration stored in ~/.config/amkb/config.json (permissions 600)."""

import json
import os
import tempfile
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "amkb"
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "amkb"
LOG_FILE = CACHE_DIR / "engine.log"

DEFAULTS = {
    "provider": None,
    "api_key": None,
    "model": None,          # None = provider's default model
    "base_url": None,       # None = provider's default URL
    "enabled": True,
    "debounce_ms": 400,     # ms after the last keystroke before sending a request
    "min_chars": 3,         # minimum context length
    "max_words": 8,         # maximum suggestion length
    "context_chars": 1500,  # how many chars before the cursor to send
    "display": "inline",    # inline = gray text in the field, popup = box near the cursor
    "timeout_s": 15,
    "debug": False,         # logs request text – for diagnostics only
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)
    data = {k: cfg.get(k, v) for k, v in DEFAULTS.items()}
    fd, tmp = tempfile.mkstemp(dir=CONFIG_DIR, prefix=".config.", suffix=".json")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, CONFIG_FILE)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def mtime() -> float:
    try:
        return CONFIG_FILE.stat().st_mtime
    except OSError:
        return 0.0
