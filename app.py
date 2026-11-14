from __future__ import annotations

import json
import os
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
HOST = "127.0.0.1"
PORT = 8765
MAX_PROMPT_CHARS = 20_000
MAX_PROVIDERS = 5
REQUEST_TIMEOUT_SECONDS = 90
OLLAMA_CACHE_SECONDS = 3
MAX_ERROR_MESSAGE_CHARS = 300
ALLOWED_ORIGIN = f"http://{HOST}:{PORT}"

PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "kind": "cloud",
        "key_env": "OPENAI_API_KEY",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "placeholder": "Enter an API model ID",
        "help": "Uses the OpenAI Chat Completions API.",
    },
    "anthropic": {
        "label": "Anthropic",
        "kind": "cloud",
        "key_env": "ANTHROPIC_API_KEY",
        "endpoint": "https://api.anthropic.com/v1/messages",
        "placeholder": "Enter a Claude model ID",
        "help": "Uses the Anthropic Messages API.",
    },
    "gemini": {
        "label": "Google Gemini",
        "kind": "cloud",
        "key_env": "GEMINI_API_KEY",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/",
        "placeholder": "Enter a Gemini model ID",
        "help": "Uses the Gemini generateContent API.",
    },
    "xai": {
        "label": "xAI",
        "kind": "cloud",
        "key_env": "XAI_API_KEY",
        "endpoint": "https://api.x.ai/v1/chat/completions",
        "placeholder": "Enter a Grok model ID",
        "help": "Uses xAI's OpenAI-compatible Chat Completions API.",
    },
    "deepseek": {
        "label": "DeepSeek",
        "kind": "cloud",
        "key_env": "DEEPSEEK_API_KEY",
        "endpoint": "https://api.deepseek.com/chat/completions",
        "placeholder": "Enter a DeepSeek model ID",
        "help": "Uses DeepSeek's OpenAI-compatible Chat Completions API.",
    },
    "ollama": {
        "label": "Ollama (local)",
        "kind": "local",
        "endpoint": "http://127.0.0.1:11434",
        "placeholder": "Select or enter an installed model",
        "help": "Connects to the Ollama server on this computer.",
    },
}

CLI_NAMES = {
    "codex": ["codex"],
    "claude": ["claude"],
    "gemini": ["gemini"],
    "antigravity": ["agy"],
    "ollama": ["ollama"],
}


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def http_json(
    url: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    data = json_bytes(body) if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read(8_000_000)
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("The provider returned an unreadable response.") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError("The provider returned an unexpected response format.")
    return decoded


def error_from_http(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read(12_000).decode("utf-8", errors="replace")
        parsed = json.loads(body)
        message = parsed.get("error", {})
        if isinstance(message, dict):
            message = message.get("message", "")
        if not message and isinstance(parsed.get("message"), str):
            message = parsed["message"]
    except Exception:
        message = ""
    message = message[:MAX_ERROR_MESSAGE_CHARS] if isinstance(message, str) else ""
    suffix = f": {message}" if message else ""
    if exc.code == 401:
        return "Authentication failed. Check the provider API key environment variable."
    if exc.code == 429:
        return "Rate limit or quota reached. Wait and retry, or choose another provider."
    return f"Provider returned HTTP {exc.code}{suffix}"


def extract_openai(result: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError("The provider response did not contain a text choice.")
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, list):
        content = "\n".join(item.get("text", "") for item in content if isinstance(item, dict))
    usage = result.get("usage") or {}
    return str(content), {
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
    }


def call_provider(provider_id: str, model: str, prompt: str) -> dict[str, Any]:
    config = PROVIDERS[provider_id]
    started = time.perf_counter()
    try:
        if provider_id == "ollama":
            result = http_json(
                config["endpoint"] + "/api/chat",
                {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False},
                {"Content-Type": "application/json"},
            )
            answer = (result.get("message") or {}).get("content", "")
            usage = {
                "input_tokens": result.get("prompt_eval_count"),
                "output_tokens": result.get("eval_count"),
            }
        elif provider_id == "anthropic":
            key = os.environ.get(config["key_env"], "").strip()
            if not key:
                raise RuntimeError(f"Set {config['key_env']} before using this provider.")
            result = http_json(
                config["endpoint"],
                {"model": model, "max_tokens": 2048, "messages": [{"role": "user", "content": prompt}]},
                {
                    "Content-Type": "application/json",
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                },
            )
            answer = "\n".join(block.get("text", "") for block in result.get("content", []) if block.get("type") == "text")
            usage = {
                "input_tokens": (result.get("usage") or {}).get("input_tokens"),
                "output_tokens": (result.get("usage") or {}).get("output_tokens"),
            }
        elif provider_id == "gemini":
            key = os.environ.get(config["key_env"], "").strip()
            if not key:
                raise RuntimeError(f"Set {config['key_env']} before using this provider.")
            model_path = urllib.parse.quote(model, safe=".-_")
            url = f"{config['endpoint']}{model_path}:generateContent?key={urllib.parse.quote(key, safe='')}"
            result = http_json(
                url,
                {"contents": [{"parts": [{"text": prompt}]}]},
                {"Content-Type": "application/json"},
            )
            candidates = result.get("candidates") or []
            parts = (candidates[0].get("content") or {}).get("parts", []) if candidates else []
            answer = "\n".join(part.get("text", "") for part in parts if isinstance(part.get("text"), str))
            meta = result.get("usageMetadata") or {}
            usage = {
                "input_tokens": meta.get("promptTokenCount"),
                "output_tokens": meta.get("candidatesTokenCount"),
            }
        else:
            key = os.environ.get(config["key_env"], "").strip()
            if not key:
                raise RuntimeError(f"Set {config['key_env']} before using this provider.")
            result = http_json(
                config["endpoint"],
                {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False},
                {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            )
            answer, usage = extract_openai(result)
        if not answer:
            raise RuntimeError("The provider returned an empty response.")
        return {
            "provider": provider_id,
            "model": model,
            "ok": True,
            "text": answer,
            "usage": usage,
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }
    except urllib.error.HTTPError as exc:
        message = error_from_http(exc)
    except urllib.error.URLError as exc:
        message = "Could not reach the provider. Check the network or local server."
    except TimeoutError:
        message = "Request timed out."
    except RuntimeError as exc:
        message = str(exc)
    except (IndexError, KeyError, AttributeError, TypeError):
        message = "The provider returned an unexpected response structure."
    except Exception:
        message = "The request failed unexpectedly. Check the provider configuration and try again."
    return {
        "provider": provider_id,
        "model": model,
        "ok": False,
        "error": message,
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }


def installed_clis() -> dict[str, bool]:
    return {name: any(shutil.which(command) for command in commands) for name, commands in CLI_NAMES.items()}


_ollama_cache_lock = threading.Lock()
_ollama_cache: dict[str, Any] = {"at": 0.0, "models": []}


def local_ollama_models() -> list[str]:
    with _ollama_cache_lock:
        if time.monotonic() - _ollama_cache["at"] < OLLAMA_CACHE_SECONDS:
            return list(_ollama_cache["models"])
    try:
        result = http_json("http://127.0.0.1:11434/api/tags", timeout_seconds=2)
        models = [item.get("name", "") for item in result.get("models", []) if item.get("name")]
    except Exception:
        models = []
    with _ollama_cache_lock:
        _ollama_cache["at"] = time.monotonic()
        _ollama_cache["models"] = models
    return models


def provider_state() -> dict[str, Any]:
    items = []
    ollama_models = local_ollama_models()
    for provider_id, config in PROVIDERS.items():
        key_present = bool(os.environ.get(config.get("key_env", ""), "").strip()) if config.get("key_env") else None
        items.append({
            "id": provider_id,
            "label": config["label"],
            "kind": config["kind"],
            "key_env": config.get("key_env"),
            "key_present": key_present,
            "placeholder": config["placeholder"],
            "help": config["help"],
            "available": key_present if config["kind"] == "cloud" else bool(ollama_models),
        })
    return {
        "providers": items,
        "ollama_models": ollama_models,
        "cli_detection": installed_clis(),
        "privacy": "Prompts are sent only after you press Compare. This app does not save prompts or responses.",
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "PolyLLMHub/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        # Avoid logging request bodies, which can contain user prompts.
        return

    def send_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")

    def origin_allowed(self) -> bool:
        # Browsers send Origin on cross-origin and same-origin fetches; non-browser
        # clients (curl, scripts) typically omit it, which we still allow since
        # this server already only binds to loopback.
        origin = self.headers.get("Origin")
        return origin is None or origin == ALLOWED_ORIGIN

    def send_json(self, status: int, value: Any) -> None:
        body = json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        # No cross-origin use is supported; refuse preflights explicitly rather
        # than relying on the default 501 behavior.
        self.send_response(403)
        self.send_security_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if not self.origin_allowed():
            self.send_json(403, {"error": "Origin not allowed."})
            return
        if self.path == "/api/status":
            self.send_json(200, provider_state())
            return
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        file_path = WEB_ROOT / "index.html"
        try:
            body = file_path.read_bytes()
        except OSError:
            self.send_error(500, "Web interface is missing.")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if not self.origin_allowed():
            self.send_json(403, {"error": "Origin not allowed."})
            return
        if self.path != "/api/compare":
            self.send_json(404, {"error": "Not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 150_000:
                self.send_json(413, {"error": "Request is empty or too large."})
                return
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"error": "Invalid JSON request."})
            return
        prompt = data.get("prompt", "")
        selections = data.get("models", [])
        if not isinstance(prompt, str) or not prompt.strip():
            self.send_json(400, {"error": "Enter a prompt first."})
            return
        if len(prompt) > MAX_PROMPT_CHARS:
            self.send_json(400, {"error": f"Prompts must be {MAX_PROMPT_CHARS:,} characters or fewer."})
            return
        if not isinstance(selections, list) or not 1 <= len(selections) <= MAX_PROVIDERS:
            self.send_json(400, {"error": f"Select between 1 and {MAX_PROVIDERS} providers."})
            return
        jobs = []
        seen_providers: set[str] = set()
        for selection in selections:
            if not isinstance(selection, dict):
                self.send_json(400, {"error": "Invalid provider selection."})
                return
            provider_id = selection.get("provider")
            model = selection.get("model", "")
            if provider_id not in PROVIDERS or not isinstance(model, str) or not model.strip():
                self.send_json(400, {"error": "Choose a supported provider and enter its model ID."})
                return
            if provider_id in seen_providers:
                continue  # ignore duplicate provider entries rather than double-calling it
            seen_providers.add(provider_id)
            jobs.append((provider_id, model.strip()[:160], prompt))

        results = []
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = [pool.submit(call_provider, *job) for job in jobs]
            for future in as_completed(futures):
                results.append(future.result())
        order = {selection["provider"]: index for index, selection in enumerate(selections)}
        results.sort(key=lambda item: order.get(item["provider"], 999))
        self.send_json(200, {"results": results})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Poly-LLM Hub is ready at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop. This server accepts local connections only.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Poly-LLM Hub.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
