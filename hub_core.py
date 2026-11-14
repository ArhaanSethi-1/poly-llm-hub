from __future__ import annotations

import ipaddress
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

from provider_metadata import provider_metadata
from secret_store import SecretStoreUnavailable, read_secret


REQUEST_TIMEOUT_SECONDS = 90
MAX_RESPONSE_BYTES = 2_000_000
CATALOG_LOCK = threading.RLock()
HISTORY_LOCK = threading.RLock()
DATA_ROOT = Path(os.environ.get("APPDATA") or (Path.home() / ".local" / "share")) / "Poly-LLM-Hub"
CATALOG_PATH = DATA_ROOT / "catalog.json"
HISTORY_PATH = DATA_ROOT / "history.jsonl"
PROTOCOLS = {"openai_compatible", "anthropic_messages", "gemini_generate", "ollama_chat"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def default_catalog() -> dict[str, Any]:
    rows = [
        ("openai", "OpenAI", "openai_compatible", "https://api.openai.com/v1", "OPENAI_API_KEY", "remote"),
        ("anthropic", "Anthropic", "anthropic_messages", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY", "remote"),
        ("gemini", "Google Gemini", "gemini_generate", "https://generativelanguage.googleapis.com/v1beta", "GEMINI_API_KEY", "remote"),
        ("xai", "xAI", "openai_compatible", "https://api.x.ai/v1", "XAI_API_KEY", "remote"),
        ("deepseek", "DeepSeek", "openai_compatible", "https://api.deepseek.com", "DEEPSEEK_API_KEY", "remote"),
        ("ollama", "Ollama (local)", "ollama_chat", "http://127.0.0.1:11434", "", "local"),
    ]
    return {
        "version": 1,
        "connections": [
            {"id": ident, "name": name, "protocol": protocol, "base_url": base,
             "auth_env": auth, "destination": destination, "notes": "", "source": "built-in starter connection"}
            for ident, name, protocol, base, auth, destination in rows
        ],
        "models": [],
        "prompt_sets": [],
        "history_enabled": False,
    }


def validate_base_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ValueError("Enter a valid base URL.")
    value = value.strip().rstrip("/")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("The base URL is malformed.") from exc
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise ValueError("Use a complete HTTPS URL for remote services.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Base URLs cannot contain credentials, query strings, or fragments.")
    hostname = parsed.hostname.lower()
    if parsed.scheme == "http":
        is_loopback = hostname == "localhost" or hostname.endswith(".localhost")
        try:
            is_loopback = is_loopback or ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            pass
        if not is_loopback:
            raise ValueError("HTTP is allowed only for loopback services. Use HTTPS for remote endpoints.")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("The URL port is invalid.")
    return value


def _clean_text(value: Any, field: str, limit: int, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(field + " must be text.")
    value = value.strip()
    if required and not value:
        raise ValueError(field + " is required.")
    if len(value) > limit:
        raise ValueError(field + " is too long.")
    return value


def normalize_connection(data: dict[str, Any], existing_id: str | None = None) -> dict[str, Any]:
    ident = _clean_text(existing_id or data.get("id", ""), "Connection ID", 64, True)
    if not ID_RE.fullmatch(ident):
        raise ValueError("Connection ID may contain letters, numbers, dots, underscores, and hyphens.")
    protocol = data.get("protocol")
    if not isinstance(protocol, str) or protocol not in PROTOCOLS:
        raise ValueError("Choose a supported API protocol.")
    base_url = validate_base_url(data.get("base_url", ""))
    hostname = urllib.parse.urlsplit(base_url).hostname or ""
    destination = "local" if hostname.lower() == "localhost" or hostname.lower().endswith(".localhost") or hostname in ("127.0.0.1", "::1") else "remote"

    auth_env = _clean_text(data.get("auth_env", ""), "Credential environment variable", 120)
    if auth_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", auth_env):
        raise ValueError("Credential reference must be an environment-variable name.")
    return {
        "id": ident, "name": _clean_text(data.get("name", ""), "Connection name", 100, True),
        "protocol": protocol, "base_url": base_url, "auth_env": auth_env,
        "destination": destination, "notes": _clean_text(data.get("notes", ""), "Notes", 1000),
        "source": _clean_text(data.get("source", ""), "Source", 300),
    }


def normalize_pricing(value: Any) -> dict[str, Any] | None:
    if value in (None, {}):
        return None
    if not isinstance(value, dict):
        raise ValueError("Pricing must be an object.")
    inp, out = value.get("input_per_million"), value.get("output_per_million")
    if not isinstance(inp, (int, float)) or isinstance(inp, bool) or inp < 0:
        raise ValueError("Input price must be a non-negative number per million tokens.")
    if not isinstance(out, (int, float)) or isinstance(out, bool) or out < 0:
        raise ValueError("Output price must be a non-negative number per million tokens.")
    source = _clean_text(value.get("source_url", ""), "Pricing source URL", 500, True)
    parsed = urllib.parse.urlsplit(source)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Pricing source must be an HTTPS URL.")
    checked_on = _clean_text(value.get("checked_on", ""), "Pricing checked date", 10, True)
    try:
        date.fromisoformat(checked_on)
    except ValueError as exc:
        raise ValueError("Pricing date must use YYYY-MM-DD.") from exc
    return {"input_per_million": float(inp), "output_per_million": float(out),
            "source_url": source, "checked_on": checked_on, "currency": "USD"}


def normalize_prompt_set(data: dict[str, Any], existing_id: str | None = None) -> dict[str, Any]:
    ident = _clean_text(existing_id or data.get("id", ""), "Prompt set ID", 64, True)
    if not ID_RE.fullmatch(ident):
        raise ValueError("Prompt set ID may contain letters, numbers, dots, underscores, and hyphens.")
    prompts = data.get("prompts")
    if not isinstance(prompts, list) or not 1 <= len(prompts) <= 100:
        raise ValueError("A prompt set must contain between 1 and 100 prompts.")
    clean_prompts = []
    seen = set()
    for item in prompts:
        if not isinstance(item, dict):
            raise ValueError("Each prompt must be an object.")
        prompt_id = _clean_text(item.get("id", ""), "Prompt ID", 64, True)
        if not ID_RE.fullmatch(prompt_id) or prompt_id in seen:
            raise ValueError("Prompt IDs must be unique and use letters, numbers, dots, underscores, or hyphens.")
        seen.add(prompt_id)
        clean_prompts.append({
            "id": prompt_id,
            "category": _clean_text(item.get("category", ""), "Prompt category", 80, True),
            "text": _clean_text(item.get("text", ""), "Prompt text", 20_000, True),
        })
    return {
        "id": ident,
        "name": _clean_text(data.get("name", ""), "Prompt set name", 100, True),
        "description": _clean_text(data.get("description", ""), "Prompt set description", 1000),
        "prompts": clean_prompts,
        "updated_at": data.get("updated_at") or date.today().isoformat(),
    }


def normalize_model(data: dict[str, Any], existing_id: str | None = None) -> dict[str, Any]:
    ident = _clean_text(existing_id or data.get("id", ""), "Model entry ID", 64, True)
    if not ID_RE.fullmatch(ident):
        raise ValueError("Model entry ID may contain letters, numbers, dots, underscores, and hyphens.")
    capabilities = data.get("capabilities", {})
    if not isinstance(capabilities, dict):
        raise ValueError("Capabilities must be an object.")
    clean_caps = {}
    for key in ("vision", "tools", "reasoning", "streaming"):
        val = capabilities.get(key)
        if val not in (True, False, None):
            raise ValueError("Each capability must be supported, unsupported, or unknown.")
        clean_caps[key] = val
    limits = {}
    for key in ("context_limit", "output_limit"):
        val = data.get(key)
        if val in (None, ""):
            limits[key] = None
        elif isinstance(val, int) and not isinstance(val, bool) and 0 < val <= 10_000_000:
            limits[key] = val
        else:
            raise ValueError(key.replace("_", " ") + " must be a positive integer or blank.")
    favorite = data.get("favorite", False)
    if not isinstance(favorite, bool):
        raise ValueError("Favorite must be true or false.")
    tags = data.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 30:
        raise ValueError("Tags must be a list of at most 30 items.")
    clean_tags = [_clean_text(tag, "Tag", 40, True) for tag in tags]
    return {
        "id": ident, "connection_id": _clean_text(data.get("connection_id", ""), "Connection", 64, True),
        "model_id": _clean_text(data.get("model_id", ""), "Exact model ID", 200, True),
        "name": _clean_text(data.get("name", ""), "Display name", 100, True),
        "description": _clean_text(data.get("description", ""), "Description", 1000),
        "favorite": favorite, "tags": clean_tags, "capabilities": clean_caps,
        "context_limit": limits["context_limit"], "output_limit": limits["output_limit"],
        "metadata_source": _clean_text(data.get("metadata_source", ""), "Metadata source", 500),
        "metadata_checked_on": _clean_text(data.get("metadata_checked_on", ""), "Metadata date", 10),
        "pricing": normalize_pricing(data.get("pricing")),
    }


def load_catalog() -> dict[str, Any]:
    with CATALOG_LOCK:
        if not CATALOG_PATH.exists():
            catalog = default_catalog()
            save_catalog(catalog)
            return catalog
        try:
            catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("The local catalog is unreadable. Preserve the file and repair its JSON before editing the catalog.") from exc
        if not isinstance(catalog, dict) or catalog.get("version") != 1 or not isinstance(catalog.get("connections"), list) or not isinstance(catalog.get("models"), list):
            raise RuntimeError("The local catalog has an unsupported format.")
        catalog.setdefault("prompt_sets", [])
        catalog.setdefault("history_enabled", False)
        if not isinstance(catalog["prompt_sets"], list) or not isinstance(catalog["history_enabled"], bool):
            raise RuntimeError("The local catalog has an unsupported format.")
        return catalog


def save_catalog(catalog: dict[str, Any]) -> None:
    with CATALOG_LOCK:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        temp = CATALOG_PATH.with_suffix(".tmp")
        temp.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, CATALOG_PATH)


def connection_by_id(catalog: dict[str, Any], ident: str) -> dict[str, Any] | None:
    return next((row for row in catalog["connections"] if row.get("id") == ident), None)


def model_by_id(catalog: dict[str, Any], ident: str) -> dict[str, Any] | None:
    return next((row for row in catalog["models"] if row.get("id") == ident), None)


def public_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    connections = []
    for row in catalog["connections"]:
        conn = dict(row)
        try:
            saved_key = read_secret(conn["id"])
        except (OSError, SecretStoreUnavailable, UnicodeDecodeError):
            saved_key = None
        env_name = conn.get("auth_env", "")
        env_key = os.environ.get(env_name, "").strip() if env_name else ""
        conn["credential_set"] = bool(saved_key or env_key)
        conn["credential_saved"] = bool(saved_key)
        conn["credential_source"] = (
            "Windows Credential Manager" if saved_key else ("environment variable" if env_key else "")
        )
        conn.update(provider_metadata(conn["id"]))
        connections.append(conn)
    models = []
    for row in catalog["models"]:
        model = dict(row)
        conn = connection_by_id(catalog, model.get("connection_id", ""))
        model["destination"] = conn.get("destination", "unknown") if conn else "unknown"
        model["connection_name"] = conn.get("name", "Missing connection") if conn else "Missing connection"
        models.append(model)
    return {"connections": connections, "models": models, "prompt_sets": catalog.get("prompt_sets", []), "history_enabled": catalog.get("history_enabled", False)}


def request_json(url: str, method: str = "GET", body: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise RuntimeError("Provider response exceeded the 2 MB limit.")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("The provider returned invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError("The provider returned an unexpected response format.")
    return decoded


def auth_headers(connection: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    env_name = connection.get("auth_env", "")
    try:
        key = read_secret(connection["id"])
    except SecretStoreUnavailable:
        key = None
    except OSError as exc:
        raise RuntimeError("Windows Credential Manager could not read this connection key.") from None
    except UnicodeDecodeError:
        raise RuntimeError("The saved connection key is invalid. Remove it and connect the key again.") from None
    if not key:
        key = os.environ.get(env_name, "").strip() if env_name else ""
    if env_name and not key:
        raise RuntimeError("No key is available. Connect a saved key or set " + env_name + " in the environment.")
    if not key:
        return headers
    if connection["protocol"] == "anthropic_messages":
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
    elif connection["protocol"] == "gemini_generate":
        headers["x-goog-api-key"] = key
    else:
        headers["Authorization"] = "Bearer " + key
    return headers


def extract_openai(result: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError("The provider response did not contain a text choice.")
    content = (choices[0].get("message") or {}).get("content", "")
    if isinstance(content, list):
        content = "\n".join(item.get("text", "") for item in content if isinstance(item, dict))
    usage = result.get("usage") or {}
    return str(content), {"input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens")}


def extract_anthropic(result: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    blocks = result.get("content") or []
    answer = "\n".join(item.get("text", "") for item in blocks if isinstance(item, dict) and item.get("type") == "text")
    usage = result.get("usage") or {}
    return answer, {"input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens")}


def extract_gemini(result: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    candidates = result.get("candidates") or []
    parts = (candidates[0].get("content") or {}).get("parts", []) if candidates else []
    answer = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str))
    usage = result.get("usageMetadata") or {}
    return answer, {"input_tokens": usage.get("promptTokenCount"), "output_tokens": usage.get("candidatesTokenCount")}


def extract_ollama(result: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    answer = (result.get("message") or {}).get("content", "")
    return str(answer), {"input_tokens": result.get("prompt_eval_count"), "output_tokens": result.get("eval_count")}


def call_model(connection: dict[str, Any], model: dict[str, Any], prompt: str) -> dict[str, Any]:
    started = time.perf_counter()
    protocol = connection["protocol"]
    model_id = model["model_id"]
    base = connection["base_url"]
    try:
        headers = auth_headers(connection)
        if protocol in ("openai_compatible", "anthropic_messages", "ollama_chat"):
            path = {"openai_compatible": "/chat/completions", "anthropic_messages": "/messages", "ollama_chat": "/api/chat"}[protocol]
            if protocol == "anthropic_messages":
                body = {"model": model_id, "max_tokens": model.get("output_limit") or 2048, "messages": [{"role": "user", "content": prompt}]}
            elif protocol == "ollama_chat":
                body = {"model": model_id, "messages": [{"role": "user", "content": prompt}], "stream": False}
            else:
                body = {"model": model_id, "messages": [{"role": "user", "content": prompt}], "stream": False}
            result = request_json(base + path, "POST", body, headers)
            answer, usage = {
                "openai_compatible": extract_openai, "anthropic_messages": extract_anthropic,
                "ollama_chat": extract_ollama,
            }[protocol](result)
        elif protocol == "gemini_generate":
            path = "/models/" + urllib.parse.quote(model_id, safe=".-_") + ":generateContent"
            result = request_json(base + path, "POST", {"contents": [{"parts": [{"text": prompt}]}]}, headers)
            answer, usage = extract_gemini(result)
        else:
            raise RuntimeError("This API protocol is not supported.")
        if not answer:
            raise RuntimeError("The provider returned an empty response.")
        return {"ok": True, "text": answer, "usage": usage, "latency_ms": round((time.perf_counter() - started) * 1000)}
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            message = "Authentication failed. Check or reconnect this provider's API key."
        elif exc.code == 429:
            message = "Rate limit or quota reached. Wait and retry, or choose another model."
        else:
            message = "Provider returned HTTP " + str(exc.code) + "."
    except urllib.error.URLError:
        message = "Could not reach the provider. Check the endpoint or local server."
    except TimeoutError:
        message = "Request timed out."
    except RuntimeError as exc:
        message = str(exc)
    except (IndexError, KeyError, AttributeError, TypeError):
        message = "The provider returned an unexpected response structure."
    except Exception:
        message = "The request failed unexpectedly. Check the connection and try again."
    return {"ok": False, "error": message, "latency_ms": round((time.perf_counter() - started) * 1000)}


def discover_models(connection: dict[str, Any]) -> list[str]:
    protocol = connection["protocol"]
    base = connection["base_url"]
    headers = auth_headers(connection)
    if protocol == "ollama_chat":
        result = request_json(base + "/api/tags", headers=headers)
        rows, field = result.get("models"), "name"
    elif protocol == "gemini_generate":
        result = request_json(base + "/models", headers=headers)
        rows, field = result.get("models"), "name"
    else:
        result = request_json(base + "/models", headers=headers)
        rows, field = result.get("data"), "id"
    if not isinstance(rows, list):
        raise RuntimeError("This endpoint returned an unsupported model-list response. Add the exact model ID manually.")
    raw = [row.get(field) for row in rows if isinstance(row, dict)]
    return sorted({item.strip().removeprefix("models/") for item in raw if isinstance(item, str) and item.strip()})[:500]


def append_history(record: dict[str, Any]) -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with HISTORY_LOCK:
        with HISTORY_PATH.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)


def read_history() -> list[dict[str, Any]]:
    rows = []
    with HISTORY_LOCK:
        if not HISTORY_PATH.exists():
            return rows
        with HISTORY_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    value = json.loads(line)
                    if isinstance(value, dict):
                        rows.append(value)
    return rows


def clear_history() -> None:
    with HISTORY_LOCK:
        if HISTORY_PATH.exists():
            HISTORY_PATH.unlink()


def estimate_cost(model: dict[str, Any], usage: dict[str, Any], destination: str) -> dict[str, Any]:
    if destination == "local":
        return {"status": "not_estimated_local", "label": "Not estimated for local run"}
    price = model.get("pricing")
    inp, out = usage.get("input_tokens"), usage.get("output_tokens")
    if not isinstance(price, dict) or not isinstance(inp, int) or not isinstance(out, int):
        return {"status": "unknown", "label": "Cost unknown"}
    if not isinstance(price.get("input_per_million"), (int, float)) or not isinstance(price.get("output_per_million"), (int, float)):
        return {"status": "unknown", "label": "Cost unknown"}
    amount = (inp * price["input_per_million"] + out * price["output_per_million"]) / 1_000_000
    return {
        "status": "estimated", "amount_usd": amount, "label": "Estimated $" + format(amount, ".8g"),
        "assumptions": "Provider-reported tokens × dated USD price per million; excludes unreported cache or tier adjustments.",
        "source_url": price.get("source_url"), "checked_on": price.get("checked_on"),
    }
