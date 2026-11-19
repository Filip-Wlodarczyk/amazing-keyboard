"""IBus engine: shows an AI suggestion as gray text after the cursor, Tab inserts it.

Started by ibus-daemon (with the --ibus flag).
"""

import logging
import re
import sys
import threading
from collections import OrderedDict

import gi

gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus  # noqa: E402

from amkb import config, providers  # noqa: E402

BUS_NAME = "org.freedesktop.IBus.AMKB"
ENGINE_NAME = "amkb"
GHOST_COLOR = 0x8A8A8A

log = logging.getLogger("amkb")

_M = IBus.ModifierType
SHORTCUT_MASK = _M.CONTROL_MASK | _M.MOD1_MASK | _M.SUPER_MASK | _M.MOD4_MASK | _M.HYPER_MASK | _M.META_MASK

MODIFIER_KEYS = {
    IBus.KEY_Shift_L, IBus.KEY_Shift_R, IBus.KEY_Control_L, IBus.KEY_Control_R,
    IBus.KEY_Alt_L, IBus.KEY_Alt_R, IBus.KEY_Super_L, IBus.KEY_Super_R,
    IBus.KEY_Meta_L, IBus.KEY_Meta_R, IBus.KEY_Hyper_L, IBus.KEY_Hyper_R,
    IBus.KEY_ISO_Level3_Shift, IBus.KEY_ISO_Level5_Shift, IBus.KEY_Caps_Lock,
    IBus.KEY_Num_Lock, IBus.KEY_Mode_switch,
}

NAVIGATION_KEYS = {
    IBus.KEY_Left, IBus.KEY_Right, IBus.KEY_Up, IBus.KEY_Down,
    IBus.KEY_Home, IBus.KEY_End, IBus.KEY_Page_Up, IBus.KEY_Page_Down,
    IBus.KEY_KP_Left, IBus.KEY_KP_Right, IBus.KEY_KP_Up, IBus.KEY_KP_Down,
    IBus.KEY_KP_Home, IBus.KEY_KP_End, IBus.KEY_Delete, IBus.KEY_KP_Delete,
    IBus.KEY_Insert,
}

_BLOCKED_PURPOSES = {IBus.InputPurpose.PASSWORD, IBus.InputPurpose.PIN}
_PRIVATE_HINT = getattr(IBus.InputHints, "PRIVATE", 0)


class Settings:
    """Configuration reloaded automatically when the file changes (amkb config ...)."""

    def __init__(self):
        self._mtime = -1.0
        self.cfg = config.DEFAULTS

    def get(self) -> dict:
        m = config.mtime()
        if m != self._mtime:
            self._mtime = m
            self.cfg = config.load()
            log.setLevel(logging.DEBUG if self.cfg.get("debug") else logging.INFO)
        return self.cfg


SETTINGS = Settings()


class AMKBEngine(IBus.Engine):
    __gtype_name__ = "AMKBEngine"

    def __init__(self, bus: IBus.Bus, object_path: str):
        super().__init__(connection=bus.get_connection(), object_path=object_path)
        self._suggestion = ""
        self._buffer = ""          # fallback context when the app provides no surrounding text
        self._timer = 0
        self._req_id = 0
        self._focused = False
        self._blocked = False
        self._caps = 0
        self._cache: OrderedDict[str, str] = OrderedDict()

    # --- lifecycle ------------------------------------------------------------

    def do_enable(self):
        self.get_surrounding_text()  # asks the app to send surrounding text

    def do_disable(self):
        self._dismiss()
        self._buffer = ""

    def do_focus_in(self):
        self._focused = True
        self._buffer = ""
        self.get_surrounding_text()

    def do_focus_out(self):
        self._focused = False
        self._dismiss()
        self._buffer = ""

    def do_reset(self):
        self._dismiss()
        self._buffer = ""

    def do_set_capabilities(self, caps):
        self._caps = caps

    def do_set_content_type(self, purpose, hints):
        self._blocked = purpose in _BLOCKED_PURPOSES or bool(_PRIVATE_HINT and hints & _PRIVATE_HINT)
        if self._blocked:
            self._dismiss()

    # --- keys --------------------------------------------------------------

    def do_process_key_event(self, keyval, keycode, state):
        if state & _M.RELEASE_MASK:
            return False
        self._focused = True  # keys only reach the focused context
        if self._blocked:
            return False

        shortcut = bool(state & SHORTCUT_MASK)

        if self._suggestion:
            if keyval in (IBus.KEY_Tab, IBus.KEY_KP_Tab) and not (shortcut or state & _M.SHIFT_MASK):
                self._accept(self._suggestion)
                return True
            if keyval == IBus.KEY_Right and state & _M.CONTROL_MASK and not state & _M.SHIFT_MASK:
                m = re.match(r"\s*\S+", self._suggestion)
                self._accept(m.group(0) if m else self._suggestion)
                return True
            if keyval == IBus.KEY_Escape and not shortcut:
                self._dismiss()
                return True

        if keyval in MODIFIER_KEYS:
            return False

        if shortcut:
            self._dismiss()
            self._buffer = ""
            return False

        if keyval == IBus.KEY_BackSpace:
            self._dismiss()
            self._buffer = self._buffer[:-1]
            self._schedule()
            return False

        if keyval in (IBus.KEY_Return, IBus.KEY_KP_Enter, IBus.KEY_ISO_Enter):
            self._dismiss()
            self._buffer += "\n"
            return False

        if keyval in NAVIGATION_KEYS or keyval in (IBus.KEY_Tab, IBus.KEY_Escape):
            self._dismiss()
            self._buffer = ""
            return False

        ch = IBus.keyval_to_unicode(keyval)
        if isinstance(ch, int):
            ch = chr(ch) if ch else ""
        if not ch or ord(ch[0]) < 32 or ord(ch[0]) == 127:
            self._dismiss()
            return False
        ch = ch[0]
        self._buffer = (self._buffer + ch)[-4000:]

        # The user types exactly what we suggest – advance the suggestion without a new request.
        if self._suggestion and self._suggestion.startswith(ch):
            rest = self._suggestion[1:]
            self._hide()
            self._suggestion = ""
            if rest.strip():
                req = self._req_id
                GLib.idle_add(self._reshow, req, rest)
            else:
                self._schedule()
            return False

        self._dismiss()
        self._schedule()
        return False

    # --- suggestions -----------------------------------------------------------

    def _accept(self, text: str):
        rest = self._suggestion[len(text):]
        self._hide()
        self._suggestion = ""
        self.commit_text(IBus.Text.new_from_string(text))
        self._buffer = (self._buffer + text)[-4000:]
        if rest.strip():
            GLib.idle_add(self._reshow, self._req_id, rest)
        else:
            self._schedule()

    def _reshow(self, req_id, text):
        if req_id == self._req_id and self._focused and not self._blocked:
            self._show(text)
        return False

    def _show(self, text: str):
        self._suggestion = text
        cfg = SETTINGS.get()
        if cfg.get("display") == "popup":
            self.update_auxiliary_text(IBus.Text.new_from_string("⇥ " + text.strip()), True)
            return
        ibus_text = IBus.Text.new_from_string(text)
        n = len(text)
        attrs = IBus.AttrList()
        attrs.append(IBus.Attribute.new(IBus.AttrType.FOREGROUND, GHOST_COLOR, 0, n))
        attrs.append(IBus.Attribute.new(IBus.AttrType.UNDERLINE, IBus.AttrUnderline.NONE, 0, n))
        ibus_text.set_attributes(attrs)
        # cursor at 0 – the caret stays right after what the user typed
        self.update_preedit_text_with_mode(ibus_text, 0, True, IBus.PreeditFocusMode.CLEAR)

    def _hide(self):
        self.update_preedit_text_with_mode(IBus.Text.new_from_string(""), 0, False, IBus.PreeditFocusMode.CLEAR)
        self.hide_auxiliary_text()

    def _dismiss(self):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        self._req_id += 1
        if self._suggestion:
            self._suggestion = ""
            self._hide()

    def _schedule(self):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        cfg = SETTINGS.get()
        if not cfg.get("enabled") or not cfg.get("provider") or self._blocked:
            return
        self._timer = GLib.timeout_add(int(cfg.get("debounce_ms") or 400), self._fire)

    def _context(self) -> tuple[str, str] | None:
        if self._caps & IBus.Capabilite.SURROUNDING_TEXT:
            try:
                text, cursor, anchor = self.get_surrounding_text()
                s = text.get_text() if text else ""
            except Exception:  # noqa: BLE001
                s, cursor, anchor = "", 0, 0
            if s:
                if anchor != cursor:
                    return None  # selection – no suggestion
                return s[:cursor], s[cursor:]
        return self._buffer, ""

    def _fire(self):
        self._timer = 0
        if not self._focused or self._blocked:
            return False
        cfg = SETTINGS.get()
        ctx = self._context()
        if ctx is None:
            return False
        before, after = ctx
        before = before[-int(cfg.get("context_chars") or 1500):]
        if len(before.strip()) < int(cfg.get("min_chars") or 3):
            return False
        # Suggest only at the end of a line.
        if after.split("\n", 1)[0].strip():
            return False

        key = before
        if key in self._cache:
            self._cache.move_to_end(key)
            if self._cache[key]:
                self._show(self._cache[key])
            return False

        self._req_id += 1
        req_id = self._req_id
        cfg_copy = dict(cfg)
        log.debug("request: %r", before[-200:])
        threading.Thread(target=self._worker, args=(req_id, cfg_copy, before, after), daemon=True).start()
        return False

    def _worker(self, req_id, cfg, before, after):
        try:
            result = providers.complete(cfg, before, after)
        except Exception as e:  # noqa: BLE001
            log.warning("provider error: %s", e)
            result = None
        GLib.idle_add(self._on_result, req_id, before, result)

    def _on_result(self, req_id, before, result):
        if result is not None:
            self._cache[before] = result
            while len(self._cache) > 64:
                self._cache.popitem(last=False)
        if req_id != self._req_id or not self._focused or self._blocked or not result:
            return False
        log.debug("suggestion: %r", result)
        self._show(result)
        return False


class Daemon:
    def __init__(self):
        IBus.init()
        self.bus = IBus.Bus()
        if not self.bus.is_connected():
            sys.exit("Cannot connect to IBus (is ibus-daemon running?)")
        self.mainloop = GLib.MainLoop()
        self.bus.connect("disconnected", lambda *_: self.mainloop.quit())
        self.engines = []
        self.counter = 0
        self.factory = IBus.Factory.new(self.bus.get_connection())
        self.factory.connect("create-engine", self._create_engine)
        # The engine is described in /usr/share/ibus/component/amkb.xml and started by ibus-daemon.
        self.bus.request_name(BUS_NAME, 0)

    def _create_engine(self, factory, engine_name):
        self.counter += 1
        engine = AMKBEngine(self.bus, f"/org/freedesktop/IBus/Engine/AMKB/{self.counter}")
        self.engines.append(engine)
        return engine

    def run(self):
        self.mainloop.run()


def setup_logging():
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def main():
    setup_logging()
    log.info("engine start")
    try:
        Daemon().run()
    except Exception:
        log.exception("engine crashed")
        raise


if __name__ == "__main__":
    main()
