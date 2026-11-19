# Amazing Keyboard (amkb)

AI suggestions in **every text field** on Ubuntu: as you type, a predicted continuation appears
right after the cursor. **Tab** inserts it, **Ctrl+→** inserts a single word, **Esc** hides it.

It works as an IBus input method engine, so it covers GTK/Qt apps, browsers, Electron apps,
terminals and more – anything that supports input methods (on GNOME/Wayland that is almost everything).

## Installation

```bash
chmod +x install.sh uninstall.sh
./install.sh
```

The installer asks for your sudo password only to copy `amkb.xml` to `/usr/share/ibus/component`
(IBus does not load engines from the home directory).

## Configuration from the terminal

```bash
amkb config -p openai -k sk-...          # provider + API key
amkb config -p anthropic                 # type the key hidden (it won't end up in bash history)
amkb config -p gemini -m gemini-2.5-flash
amkb config -p ollama -m llama3.2        # local, no key needed
amkb config -p custom --base-url http://localhost:8080/v1 -m my-model
amkb setup                               # or use the interactive wizard
```

Then:

```bash
amkb test "Good morning, I would like"   # preview a suggestion in the terminal
amkb activate                            # adds "Amazing Keyboard (AI)" to input sources
```

Switch between your regular keyboard and the AI one with **Super+Space**.

## Other commands

| Command | Description |
|---|---|
| `amkb providers` | list providers and their default models |
| `amkb status` | show configuration and engine state |
| `amkb on` / `amkb off` | enable/disable suggestions without switching input source |
| `amkb config --debounce-ms 300 --max-words 5` | suggestion speed and length |
| `amkb config --display popup` | show the suggestion in a popup near the cursor instead of inline |
| `amkb log` | engine log (`~/.cache/amkb/engine.log`) |
| `amkb deactivate` | remove from input sources |

Configuration changes take effect immediately – the engine reloads `~/.config/amkb/config.json` on its own.

## Providers

`openai`, `anthropic`, `gemini`, `groq`, `openrouter`, `mistral`, `deepseek`, `ollama`,
`custom` (any OpenAI-compatible API) and `mock` (offline test provider).

For `anthropic` the default model is `claude-opus-5-5`. For autocomplete, `claude-haiku-5-5` is faster
and much cheaper: `amkb config -p anthropic -m claude-haiku-5-5`.

## Privacy

- Text before the cursor (up to 1500 characters) is sent to the selected provider.
- Password and PIN fields are skipped (the app has to mark them as such – most do).
- The API key is stored in `~/.config/amkb/config.json` with `600` permissions.
- Typed text is written to the log only with `amkb config --debug on`.

## Limitations

- **Gray color**: the engine requests gray text, but on GNOME/Wayland the input method protocol
  does not pass colors through – the suggestion is then shown in the app's own preedit style
  (usually underlined). If you prefer a clearly separated suggestion: `amkb config --display popup`.
- Suggestions appear only at the end of a line (when there is nothing after the cursor).
- In a terminal, Tab without a visible suggestion works as usual (shell completion).

## Uninstall

```bash
./uninstall.sh
```
