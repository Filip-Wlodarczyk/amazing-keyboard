"""AI model providers. Each returns a short continuation of the text before the cursor."""

import json
import re
import urllib.error
import urllib.request

PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "kind": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "needs_key": True,
    },
    "anthropic": {
        "label": "Anthropic (Claude)",
        "kind": "anthropic",
        "base_url": None,
        "model": "claude-opus-5-5",
        "needs_key": True,
    },
    "gemini": {
        "label": "Google Gemini",
        "kind": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "gemini-2.5-flash",
        "needs_key": True,
    },
    "groq": {
        "label": "Groq",
        "kind": "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.1-8b-instant",
        "needs_key": True,
    },
    "openrouter": {
        "label": "OpenRouter",
        "kind": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4.1-mini",
        "needs_key": True,
    },
    "mistral": {
        "label": "Mistral",
        "kind": "openai",
        "base_url": "https://api.mistral.ai/v1",
        "model": "mistral-small-latest",
        "needs_key": True,
    },
    "deepseek": {
        "label": "DeepSeek",
        "kind": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "needs_key": True,
    },
    "ollama": {
        "label": "Ollama (local, no key)",
        "kind": "openai",
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.2",
        "needs_key": False,
    },
    "custom": {
        "label": "Custom OpenAI-compatible endpoint (--base-url)",
        "kind": "openai",
        "base_url": None,
        "model": None,
        "needs_key": False,
    },
    "mock": {
        "label": "Test provider (offline, always suggests the same text)",
        "kind": "mock",
        "base_url": None,
        "model": "mock",
        "needs_key": False,
    },
}

# Anthropic models that support server-side fallback after a refusal.
_ANTHROPIC_FALLBACK_MODELS = {
    "claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5",
}

SYSTEM_PROMPT = (
    "You are an inline autocomplete engine, like predictive text on a phone keyboard. "
    "You get the text a user is typing in some text field; the cursor position is marked with <CURSOR>. "
    "Predict what the user will most likely type next at the cursor.\n"
    "Rules:\n"
    "- Output ONLY the continuation text. No quotes, no explanations, no markdown.\n"
    "- At most {max_words} words, on a single line.\n"
    "- Use the same language, tone and style as the existing text.\n"
    "- If the last word is unfinished, finish it without repeating the letters already typed.\n"
    "- Begin with a space if the continuation starts a new word after a complete word.\n"
    "- If there is no sensible continuation, output nothing."
)


class ProviderError(Exception):
    pass


def resolve(cfg: dict) -> tuple[dict, str, str | None]:
    name = cfg.get("provider")
    if name not in PROVIDERS:
        raise ProviderError("No provider set. Set one with: amkb config -p <provider> -k <key>")
    spec = PROVIDERS[name]
    model = cfg.get("model") or spec["model"]
    base_url = cfg.get("base_url") or spec["base_url"]
    if not model:
        raise ProviderError(f"Provider '{name}' requires --model")
    if spec["kind"] == "openai" and not base_url:
        raise ProviderError(f"Provider '{name}' requires --base-url")
    if spec["needs_key"] and not cfg.get("api_key"):
        raise ProviderError(f"Provider '{name}' requires an API key (-k)")
    return spec, model, base_url


def build_user_message(before: str, after: str) -> str:
    return "Text in the field:\n<<<\n" + before + "<CURSOR>" + after + "\n>>>"


def complete(cfg: dict, before: str, after: str = "") -> str:
    """Returns a cleaned-up continuation (may be empty)."""
    spec, model, base_url = resolve(cfg)
    system = SYSTEM_PROMPT.format(max_words=int(cfg.get("max_words") or 8))
    user = build_user_message(before, after)
    timeout = float(cfg.get("timeout_s") or 15)
    kind = spec["kind"]
    if kind == "openai":
        raw = _openai(base_url, cfg.get("api_key"), model, system, user, timeout)
    elif kind == "anthropic":
        raw = _anthropic(cfg["api_key"], model, system, user, timeout)
    elif kind == "gemini":
        raw = _gemini(base_url, cfg["api_key"], model, system, user, timeout)
    elif kind == "mock":
        raw = " this is a test suggestion"
    else:
        raise ProviderError(f"Unknown provider type: {kind}")
    return clean_completion(before, raw, int(cfg.get("max_words") or 8))


# --- implementations -----------------------------------------------------------

def _post_json(url: str, headers: dict, body: dict, timeout: float) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "amkb/0.1")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise ProviderError(f"HTTP {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise ProviderError(f"Connection error: {e.reason}") from None


def _openai(base_url, api_key, model, system, user, timeout) -> str:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 64,
        "temperature": 0.2,
        "stream": False,
    }
    data = _post_json(base_url.rstrip("/") + "/chat/completions", headers, body, timeout)
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise ProviderError(f"Unexpected response: {str(data)[:300]}") from None


_anthropic_clients: dict = {}


def _anthropic(api_key, model, system, user, timeout) -> str:
    try:
        import anthropic
    except ImportError:
        raise ProviderError("Package 'anthropic' missing – re-run ./install.sh") from None

    client = _anthropic_clients.get(api_key)
    if client is None:
        client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=0)
        _anthropic_clients.clear()
        _anthropic_clients[api_key] = client

    kwargs = dict(
        model=model,
        max_tokens=4000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "low"},
    )
    try:
        if model in _ANTHROPIC_FALLBACK_MODELS:
            response = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
            )
        else:
            response = client.messages.create(**kwargs)
    except anthropic.AuthenticationError:
        raise ProviderError("Anthropic: invalid API key") from None
    except anthropic.NotFoundError:
        raise ProviderError(f"Anthropic: model '{model}' not found") from None
    except anthropic.RateLimitError:
        raise ProviderError("Anthropic: rate limit exceeded") from None
    except anthropic.APIStatusError as e:
        raise ProviderError(f"Anthropic HTTP {e.status_code}: {e.message}") from None
    except anthropic.APIConnectionError:
        raise ProviderError("Anthropic: connection error") from None

    if response.stop_reason == "refusal":
        return ""
    return "".join(b.text for b in response.content if b.type == "text")


def _gemini(base_url, api_key, model, system, user, timeout) -> str:
    url = f"{base_url.rstrip('/')}/models/{model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "maxOutputTokens": 64,
            "temperature": 0.2,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    data = _post_json(url, {"x-goog-api-key": api_key}, body, timeout)
    try:
        parts = data["candidates"][0]["content"].get("parts", [])
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        return ""


# --- response cleanup --------------------------------------------------

def clean_completion(before: str, raw: str, max_words: int = 8) -> str:
    if not raw:
        return ""
    text = raw.replace("\r", "").replace("<CURSOR>", "")
    # If the model starts with a newline, suggest nothing; otherwise keep the first line.
    if text.startswith("\n"):
        return ""
    text = text.split("\n", 1)[0]
    # Strip quotes/backticks wrapping the whole text.
    for q in ('"', "'", "`", "„", "”", "«"):
        if len(text) > 2 and text.startswith(q) and text.endswith(q if q != "„" else "”"):
            text = text[1:-1]
    text = text.rstrip()

    # If the model repeated the start of an unfinished word, cut it off.
    m = re.search(r"(\S+)$", before)
    partial = m.group(1) if m else ""
    if partial and len(partial) >= 2 and text.lower().startswith(partial.lower()) and len(text) > len(partial):
        text = text[len(partial):]

    # Avoid a double space at the join.
    if before.endswith((" ", "\t", "\n")) or not before:
        text = text.lstrip()

    # Word limit.
    words = re.findall(r"\s*\S+", text)
    if len(words) > max_words:
        text = "".join(words[:max_words])
    return text if text.strip() else ""
