from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import stat
import threading
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from provider_metadata import provider_metadata
from history_crypto import decrypt_record, encrypt_record, encryption_available, is_envelope, migrate_file
from secret_store import SecretStoreUnavailable, read_secret, store_name


REQUEST_TIMEOUT_SECONDS = 90
MAX_RESPONSE_BYTES = 2_000_000
PRICING_STALE_AFTER_DAYS = 90
MAX_DISCOVERED_MODELS = 500
MODEL_DISCOVERY_PAGE_SIZE = 100
MODEL_DISCOVERY_MAX_PAGES = 5
CATALOG_LOCK = threading.RLock()
HISTORY_LOCK = threading.RLock()
DATA_ROOT = Path(os.environ.get("APPDATA") or (Path.home() / ".local" / "share")) / "Poly-LLM-Hub"
CATALOG_PATH = DATA_ROOT / "catalog.json"
HISTORY_PATH = DATA_ROOT / "history.jsonl"
PROTOCOLS = {"openai_compatible", "anthropic_messages", "gemini_generate", "ollama_chat"}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
CATALOG_EXPORT_FORMAT = "poly-llm-hub-catalog"
DIRECT_BROWSER_CONNECTIONS = {"anthropic"}


def _prepare_private_data_root() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        os.chmod(DATA_ROOT, 0o700)


def _sync_data_directory() -> None:
    if os.name != "posix":
        return
    try:
        directory_fd = os.open(DATA_ROOT, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        pass


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
        "seed_catalog_initialized": False,
        "prompt_sets": [],
        "history_enabled": False,
        "history_encrypted": False,
    }


def _is_loopback_host(hostname: str) -> bool:
    hostname = hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


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
    hostname = parsed.hostname
    if parsed.scheme == "http" and not _is_loopback_host(hostname):
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


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError):
        return False


def normalize_connection(data: dict[str, Any], existing_id: str | None = None) -> dict[str, Any]:
    ident = _clean_text(existing_id or data.get("id", ""), "Connection ID", 64, True)
    if not ID_RE.fullmatch(ident):
        raise ValueError("Connection ID may contain letters, numbers, dots, underscores, and hyphens.")
    if ident == "poly-hub-history-key-v1":
        raise ValueError("This connection ID is reserved for the local history key.")
    protocol = data.get("protocol")
    if not isinstance(protocol, str) or protocol not in PROTOCOLS:
        raise ValueError("Choose a supported API protocol.")
    request_mode = data.get("request_mode", "local_proxy")
    if request_mode not in ("local_proxy", "direct"):
        raise ValueError("Choose Local Proxy or Direct Connection.")
    if request_mode == "direct" and (
        ident not in DIRECT_BROWSER_CONNECTIONS
        or protocol != "anthropic_messages"
        or validate_base_url(data.get("base_url", "")) != "https://api.anthropic.com/v1"
    ):
        raise ValueError("Direct Connection is available only for the built-in Anthropic Messages connection.")
    base_url = validate_base_url(data.get("base_url", ""))
    hostname = urllib.parse.urlsplit(base_url).hostname or ""
    destination = "local" if _is_loopback_host(hostname) else "remote"

    auth_env = _clean_text(data.get("auth_env", ""), "Credential environment variable", 120)
    if auth_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", auth_env):
        raise ValueError("Credential reference must be an environment-variable name.")
    return {
        "id": ident, "name": _clean_text(data.get("name", ""), "Connection name", 100, True),
        "protocol": protocol, "base_url": base_url, "auth_env": auth_env,
        "request_mode": request_mode,
        "destination": destination, "notes": _clean_text(data.get("notes", ""), "Notes", 1000),
        "source": _clean_text(data.get("source", ""), "Source", 300),
    }


def normalize_pricing(value: Any) -> dict[str, Any] | None:
    if value in (None, {}):
        return None
    if not isinstance(value, dict):
        raise ValueError("Pricing must be an object.")
    inp, out = value.get("input_per_million"), value.get("output_per_million")
    if not isinstance(inp, (int, float)) or isinstance(inp, bool) or not _is_finite_number(inp) or inp < 0:
        raise ValueError("Input price must be a non-negative number per million tokens.")
    if not isinstance(out, (int, float)) or isinstance(out, bool) or not _is_finite_number(out) or out < 0:
        raise ValueError("Output price must be a non-negative number per million tokens.")
    source = _clean_text(value.get("source_url", ""), "Pricing source URL", 500, True)
    parsed = urllib.parse.urlsplit(source)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Pricing source must be an HTTPS URL.")
    checked_on = _clean_text(value.get("checked_on", ""), "Pricing checked date", 10, True)
    try:
        checked_date = date.fromisoformat(checked_on)
    except ValueError as exc:
        raise ValueError("Pricing date must use YYYY-MM-DD.") from exc
    if checked_date > date.today():
        raise ValueError("Pricing checked date cannot be in the future.")
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
    benchmark_scores = data.get("benchmark_scores", [])
    if not isinstance(benchmark_scores, list) or len(benchmark_scores) > 8:
        raise ValueError("Benchmark scores must be a list of at most eight sourced results.")
    clean_benchmarks = []
    for item in benchmark_scores:
        if not isinstance(item, dict):
            raise ValueError("Each benchmark score must be an object.")
        score = item.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not _is_finite_number(score):
            raise ValueError("Benchmark scores must be finite numbers.")
        source_url = _clean_text(item.get("source_url", ""), "Benchmark source URL", 500, True)
        parsed_source = urllib.parse.urlsplit(source_url)
        if parsed_source.scheme != "https" or not parsed_source.hostname:
            raise ValueError("Benchmark sources must be HTTPS URLs.")
        checked_on = _clean_text(item.get("checked_on", ""), "Benchmark date", 10, True)
        try:
            checked_date = date.fromisoformat(checked_on)
        except ValueError as exc:
            raise ValueError("Benchmark date must use YYYY-MM-DD.") from exc
        if checked_date > date.today():
            raise ValueError("Benchmark date cannot be in the future.")
        clean_benchmarks.append({
            "name": _clean_text(item.get("name", ""), "Benchmark name", 80, True),
            "score": float(score),
            "unit": _clean_text(item.get("unit", ""), "Benchmark unit", 40, True),
            "variant": _clean_text(item.get("variant", ""), "Benchmark variant", 160, True),
            "source_url": source_url,
            "checked_on": checked_on,
        })
    return {
        "id": ident, "connection_id": _clean_text(data.get("connection_id", ""), "Connection", 64, True),
        "model_id": _clean_text(data.get("model_id", ""), "Exact model ID", 200, True),
        "name": _clean_text(data.get("name", ""), "Display name", 100, True),
        "description": _clean_text(data.get("description", ""), "Description", 1000),
        "favorite": favorite, "tags": clean_tags, "capabilities": clean_caps,
        "context_limit": limits["context_limit"], "output_limit": limits["output_limit"],
        "metadata_source": _clean_text(data.get("metadata_source", ""), "Metadata source", 500),
        "metadata_checked_on": _clean_text(data.get("metadata_checked_on", ""), "Metadata date", 10),
        "catalog_source": _clean_text(data.get("catalog_source", "local"), "Catalog source", 20),
        "provider_discovered": data.get("provider_discovered", False) if isinstance(data.get("provider_discovered", False), bool) else False,
        "discovered_checked_on": _clean_text(data.get("discovered_checked_on", ""), "Discovery date", 10),
        "rank_score": data.get("rank_score") if isinstance(data.get("rank_score"), (int, float)) and not isinstance(data.get("rank_score"), bool) and math.isfinite(data.get("rank_score")) and data.get("rank_score") >= 0 else None,
        "rank_source": _clean_text(data.get("rank_source", ""), "Rank source", 500),
        "benchmark_scores": clean_benchmarks,
        "pricing": normalize_pricing(data.get("pricing")),
    }


def load_catalog() -> dict[str, Any]:
    with CATALOG_LOCK:
        _prepare_private_data_root()
        if not CATALOG_PATH.exists():
            catalog = default_catalog()
            catalog["models"] = seed_models(catalog)
            catalog["seed_catalog_initialized"] = True
            save_catalog(catalog)
            return catalog
        try:
            catalog_mode = CATALOG_PATH.lstat().st_mode
        except OSError as exc:
            raise RuntimeError("The local catalog file could not be inspected.") from exc
        if not stat.S_ISREG(catalog_mode):
            raise RuntimeError("The local catalog path must be a regular file.")
        if os.name == "posix":
            os.chmod(CATALOG_PATH, 0o600)
        try:
            catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("The local catalog is unreadable. Preserve the file and repair its JSON before editing the catalog.") from exc
        if not isinstance(catalog, dict) or catalog.get("version") != 1 or not isinstance(catalog.get("connections"), list) or not isinstance(catalog.get("models"), list):
            raise RuntimeError("The local catalog has an unsupported format.")
        catalog.setdefault("prompt_sets", [])
        catalog.setdefault("history_enabled", False)
        catalog.setdefault("history_encrypted", False)
        catalog.setdefault("seed_catalog_initialized", bool(catalog["models"]))
        if (not isinstance(catalog["prompt_sets"], list)
                or not isinstance(catalog["history_enabled"], bool)
                or not isinstance(catalog["seed_catalog_initialized"], bool)
                or not isinstance(catalog["history_encrypted"], bool)):
            raise RuntimeError("The local catalog has an unsupported format.")
        if not catalog["seed_catalog_initialized"] and not catalog["models"]:
            catalog["models"] = seed_models(catalog)
            catalog["seed_catalog_initialized"] = True
            save_catalog(catalog)
        elif not catalog["seed_catalog_initialized"]:
            catalog["seed_catalog_initialized"] = True
            save_catalog(catalog)
        return catalog


def seed_models(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """Load bundled starter models only for a genuinely empty model list."""
    if catalog.get("models"):
        return []
    seed_path = Path(__file__).resolve().parent / "catalog" / "seed_models.json"
    try:
        records = json.loads(seed_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("The bundled model catalog could not be loaded.") from exc
    connections = {row.get("id") for row in catalog.get("connections", [])}
    models = []
    for record in records:
        if record.get("connection_id") not in connections:
            continue
        models.append(normalize_model(record))
    return models


def save_catalog(catalog: dict[str, Any]) -> None:
    with CATALOG_LOCK:
        _prepare_private_data_root()
        payload = json.dumps(catalog, ensure_ascii=True, indent=2)
        descriptor, temp_name = tempfile.mkstemp(prefix=".catalog-", suffix=".tmp", dir=DATA_ROOT)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                if os.name == "posix":
                    os.fchmod(handle.fileno(), 0o600)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, CATALOG_PATH)
            if os.name == "posix":
                os.chmod(CATALOG_PATH, 0o600)
            _sync_data_directory()
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def exportable_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    """Return a versioned, credential-free catalog backup."""
    return {
        "format": CATALOG_EXPORT_FORMAT,
        "version": 1,
        "connections": [normalize_connection(row) for row in catalog["connections"]],
        "models": [normalize_model(row) for row in catalog["models"]],
        "prompt_sets": [normalize_prompt_set(row) for row in catalog.get("prompt_sets", [])],
    }


def merge_catalog_import(catalog: dict[str, Any], payload: Any) -> dict[str, int]:
    """Validate and merge a backup. Existing connection IDs are never overwritten."""
    if not isinstance(payload, dict) or payload.get("format") != CATALOG_EXPORT_FORMAT or payload.get("version") != 1:
        raise ValueError("This is not a supported Poly-LLM Hub catalog backup.")

    imported_rows: dict[str, list[dict[str, Any]]] = {}
    for field, normalizer in (
        ("connections", normalize_connection),
        ("models", normalize_model),
        ("prompt_sets", normalize_prompt_set),
    ):
        rows = payload.get(field)
        if not isinstance(rows, list):
            raise ValueError("The catalog backup is missing a valid " + field.replace("_", " ") + " list.")
        if any(not isinstance(row, dict) for row in rows):
            raise ValueError("Every item in the backup's " + field.replace("_", " ") + " list must be an object.")
        clean_rows = [normalizer(row) for row in rows]
        ids = [row["id"] for row in clean_rows]
        if len(ids) != len(set(ids)):
            raise ValueError("The catalog backup contains duplicate " + field.replace("_", " ") + " IDs.")
        imported_rows[field] = clean_rows

    current_connection_ids = {row["id"] for row in catalog["connections"]}
    connections_added = 0
    for connection in imported_rows["connections"]:
        if connection["id"] == "ollama" and connection["protocol"] != "ollama_chat":
            raise ValueError("The built-in Ollama connection must keep the Ollama protocol.")
        if connection["id"] not in current_connection_ids:
            catalog["connections"].append(connection)
            current_connection_ids.add(connection["id"])
            connections_added += 1

    model_indexes = {row["id"]: index for index, row in enumerate(catalog["models"])}
    models_added = 0
    models_updated = 0
    for model in imported_rows["models"]:
        if model["connection_id"] not in current_connection_ids:
            raise ValueError("A model in the backup refers to a connection that is not available.")
        index = model_indexes.get(model["id"])
        if index is None:
            model_indexes[model["id"]] = len(catalog["models"])
            catalog["models"].append(model)
            models_added += 1
        else:
            catalog["models"][index] = model
            models_updated += 1

    prompt_indexes = {row["id"]: index for index, row in enumerate(catalog.get("prompt_sets", []))}
    prompt_sets_added = 0
    prompt_sets_updated = 0
    for prompt_set in imported_rows["prompt_sets"]:
        index = prompt_indexes.get(prompt_set["id"])
        if index is None:
            prompt_indexes[prompt_set["id"]] = len(catalog["prompt_sets"])
            catalog["prompt_sets"].append(prompt_set)
            prompt_sets_added += 1
        else:
            catalog["prompt_sets"][index] = prompt_set
            prompt_sets_updated += 1

    return {
        "connections_added": connections_added,
        "connections_skipped": len(imported_rows["connections"]) - connections_added,
        "models_added": models_added,
        "models_updated": models_updated,
        "prompt_sets_added": prompt_sets_added,
        "prompt_sets_updated": prompt_sets_updated,
    }


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
            store_name() if saved_key else ("environment variable" if env_key else "")
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
    return {"connections": connections, "models": models, "prompt_sets": catalog.get("prompt_sets", []), "history_enabled": catalog.get("history_enabled", False), "credential_store_name": store_name()}


def request_json(
    url: str, method: str = "GET", body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None, on_response=None,
) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=True).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with _same_origin_opener().open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        if on_response:
            on_response(response)
        try:
            raw = response.read(2_000_001)
        finally:
            if on_response:
                on_response(None)
    if len(raw) > 2_000_000:
        raise RuntimeError("Provider response exceeded the 2 MB limit.")
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("The provider returned invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise RuntimeError("The provider returned an unexpected response format.")
    return decoded


class _SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow provider redirects only when scheme, host, and port stay fixed."""

    # Run before urllib's default redirect handler, which would otherwise
    # follow a cross-origin redirect after this handler declined it.
    handler_order = 400

    @staticmethod
    def _origin(url: str) -> tuple[str, str, int | None]:
        parsed = urllib.parse.urlsplit(url)
        try:
            port = parsed.port
        except ValueError:
            return ("", "", None)
        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").lower()
        if port is None:
            port = 443 if scheme == "https" else (80 if scheme == "http" else None)
        return scheme, hostname, port

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if self._origin(req.full_url) != self._origin(newurl):
            raise urllib.error.HTTPError(newurl, code, "Cross-origin provider redirect blocked.", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _same_origin_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_SameOriginRedirectHandler())


def auth_headers(connection: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    env_name = connection.get("auth_env", "")
    connection_id = connection.get("id")
    if isinstance(connection_id, str) and connection_id:
        try:
            key = read_secret(connection_id)
        except SecretStoreUnavailable:
            key = None
        except OSError:
            raise RuntimeError("The secure credential store could not read this connection key.") from None
        except UnicodeDecodeError:
            raise RuntimeError("The saved connection key is invalid. Remove it and connect the key again.") from None
    else:
        key = None
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


def _sse_payloads(response):
    data_lines = []
    total_bytes = 0
    while True:
        line = response.readline(65_537)
        if not line:
            break
        total_bytes += len(line)
        if total_bytes > MAX_RESPONSE_BYTES or len(line) > 65_536:
            raise RuntimeError("Provider stream exceeded the response size limit.")
        try:
            decoded = line.decode("utf-8").rstrip("\r\n")
        except UnicodeDecodeError as exc:
            raise RuntimeError("The provider stream contained invalid text encoding.") from exc
        if not decoded:
            if data_lines:
                yield "\n".join(data_lines)
                data_lines = []
        elif decoded.startswith("data:"):
            data = decoded[5:]
            data_lines.append(data[1:] if data.startswith(" ") else data)
    if data_lines:
        yield "\n".join(data_lines)


def _read_stream(response, protocol: str, on_delta, started: float) -> tuple[str, dict[str, Any], int | None]:
    text_parts = []
    output_bytes = 0
    usage: dict[str, Any] = {}
    first_token_ms = None

    def emit(fragment: Any) -> None:
        nonlocal output_bytes, first_token_ms
        if not isinstance(fragment, str) or not fragment:
            return
        output_bytes += len(fragment.encode("utf-8"))
        if output_bytes > MAX_RESPONSE_BYTES:
            raise RuntimeError("Provider response exceeded the 2 MB limit.")
        if first_token_ms is None:
            first_token_ms = round((time.perf_counter() - started) * 1000)
        text_parts.append(fragment)
        if on_delta:
            on_delta(fragment)

    if protocol == "ollama_chat":
        total_bytes = 0
        while True:
            line = response.readline(65_537)
            if not line:
                break
            total_bytes += len(line)
            if total_bytes > MAX_RESPONSE_BYTES or len(line) > 65_536:
                raise RuntimeError("Provider stream exceeded the response size limit.")
            if not line.strip():
                continue
            try:
                chunk = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("The provider returned invalid streaming JSON.") from exc
            if not isinstance(chunk, dict):
                raise RuntimeError("The provider returned an unexpected streaming response format.")
            if chunk.get("error"):
                raise RuntimeError("The provider stream returned an error.")
            emit((chunk.get("message") or {}).get("content", ""))
            if isinstance(chunk.get("prompt_eval_count"), int):
                usage["input_tokens"] = chunk["prompt_eval_count"]
            if isinstance(chunk.get("eval_count"), int):
                usage["output_tokens"] = chunk["eval_count"]
    else:
        for raw in _sse_payloads(response):
            if raw == "[DONE]":
                break
            try:
                chunk = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError("The provider returned invalid streaming JSON.") from exc
            if not isinstance(chunk, dict):
                raise RuntimeError("The provider returned an unexpected streaming response format.")
            if protocol == "openai_compatible":
                if chunk.get("error"):
                    raise RuntimeError("The provider stream returned an error.")
                usage_chunk = chunk.get("usage") or {}
                if usage_chunk.get("prompt_tokens") is not None:
                    usage["input_tokens"] = usage_chunk.get("prompt_tokens")
                if usage_chunk.get("completion_tokens") is not None:
                    usage["output_tokens"] = usage_chunk.get("completion_tokens")
                choices = chunk.get("choices") or []
                if choices:
                    delta = (choices[0].get("delta") or {})
                    content = delta.get("content", "")
                    if isinstance(content, list):
                        content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
                    emit(content)
            elif protocol == "anthropic_messages":
                kind = chunk.get("type")
                if kind == "error":
                    raise RuntimeError("The provider stream returned an error.")
                if kind == "message_start":
                    counts = (chunk.get("message") or {}).get("usage") or {}
                    if counts.get("input_tokens") is not None:
                        usage["input_tokens"] = counts.get("input_tokens")
                elif kind == "content_block_delta":
                    delta = chunk.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        emit(delta.get("text", ""))
                elif kind == "message_delta":
                    counts = chunk.get("usage") or {}
                    if counts.get("output_tokens") is not None:
                        usage["output_tokens"] = counts.get("output_tokens")
            elif protocol == "gemini_generate":
                candidates = chunk.get("candidates") or []
                if candidates:
                    parts = (candidates[0].get("content") or {}).get("parts", [])
                    for part in parts:
                        if isinstance(part, dict):
                            emit(part.get("text", ""))
                counts = chunk.get("usageMetadata") or {}
                if counts.get("promptTokenCount") is not None:
                    usage["input_tokens"] = counts.get("promptTokenCount")
                if counts.get("candidatesTokenCount") is not None:
                    usage["output_tokens"] = counts.get("candidatesTokenCount")

    return "".join(text_parts), usage, first_token_ms


def request_stream(
    url: str, body: dict[str, Any], headers: dict[str, str], protocol: str, on_delta, started: float,
    on_response=None,
) -> tuple[str, dict[str, Any], int | None]:
    data = json.dumps(body, ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with _same_origin_opener().open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        if on_response:
            on_response(response)
        try:
            return _read_stream(response, protocol, on_delta, started)
        finally:
            if on_response:
                on_response(None)


def call_model(
    connection: dict[str, Any], model: dict[str, Any], prompt: str, parameters: dict[str, Any] | None = None,
    on_delta=None, messages: list[dict[str, str]] | None = None, on_response=None,
) -> dict[str, Any]:
    started = time.perf_counter()
    protocol = connection["protocol"]
    model_id = model["model_id"]
    base = connection["base_url"]
    parameters = dict(parameters or {})
    effective_parameters = dict(parameters)
    requested_output_limit = parameters.get("max_output_tokens")
    streaming = parameters.get("stream") is True
    effective_parameters["stream"] = streaming
    provider_messages = messages or [{"role": "user", "content": prompt}]
    time_to_first_token_ms = None
    streamed_parts: list[str] = []
    http_status = None
    retry_after_seconds = None

    def stream_delta(fragment: str) -> None:
        nonlocal time_to_first_token_ms
        if time_to_first_token_ms is None:
            time_to_first_token_ms = round((time.perf_counter() - started) * 1000)
        streamed_parts.append(fragment)
        if on_delta:
            on_delta(fragment)

    try:
        headers = auth_headers(connection)
        if protocol in ("openai_compatible", "anthropic_messages", "ollama_chat"):
            path = {"openai_compatible": "/chat/completions", "anthropic_messages": "/messages", "ollama_chat": "/api/chat"}[protocol]
            if protocol == "anthropic_messages":
                effective_parameters["max_output_tokens"] = (
                    requested_output_limit if requested_output_limit is not None else model.get("output_limit") or 2048
                )
                body = {"model": model_id, "max_tokens": effective_parameters["max_output_tokens"], "messages": provider_messages}
                body["stream"] = streaming
            elif protocol == "ollama_chat":
                body = {"model": model_id, "messages": provider_messages, "stream": streaming}
                if requested_output_limit is not None:
                    body["options"] = {"num_predict": requested_output_limit}
            else:
                body = {"model": model_id, "messages": provider_messages, "stream": streaming}
                if requested_output_limit is not None:
                    token_field = "max_completion_tokens" if connection.get("id") == "openai" else "max_tokens"
                    body[token_field] = requested_output_limit
                if streaming and connection.get("id") == "openai":
                    body["stream_options"] = {"include_usage": True}
            if protocol != "anthropic_messages" and requested_output_limit is not None:
                effective_parameters["max_output_tokens"] = requested_output_limit
            if streaming:
                answer, usage, measured_first_token_ms = request_stream(base + path, body, headers, protocol, stream_delta, started, on_response)
                time_to_first_token_ms = measured_first_token_ms
            else:
                result = request_json(base + path, "POST", body, headers, on_response)
                answer, usage = {
                    "openai_compatible": extract_openai, "anthropic_messages": extract_anthropic,
                    "ollama_chat": extract_ollama,
                }[protocol](result)
        elif protocol == "gemini_generate":
            action = ":streamGenerateContent?alt=sse" if streaming else ":generateContent"
            path = "/models/" + urllib.parse.quote(model_id, safe=".-_") + action
            body = {"contents": [
                {"role": "model" if message["role"] == "assistant" else "user", "parts": [{"text": message["content"]}]}
                for message in provider_messages
            ]}
            if requested_output_limit is not None:
                body["generationConfig"] = {"maxOutputTokens": requested_output_limit}
                effective_parameters["max_output_tokens"] = requested_output_limit
            if streaming:
                answer, usage, measured_first_token_ms = request_stream(base + path, body, headers, protocol, stream_delta, started, on_response)
                time_to_first_token_ms = measured_first_token_ms
            else:
                result = request_json(base + path, "POST", body, headers, on_response)
                answer, usage = extract_gemini(result)
        else:
            raise RuntimeError("This API protocol is not supported.")
        if not answer:
            raise RuntimeError("The provider returned an empty response.")
        return {"ok": True, "text": answer, "usage": usage, "parameters": effective_parameters,
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "time_to_first_token_ms": time_to_first_token_ms}
    except urllib.error.HTTPError as exc:
        http_status = exc.code
        if exc.code == 429:
            header = exc.headers.get("Retry-After") if exc.headers else None
            if header:
                try:
                    retry_after_seconds = max(0.0, float(header.strip()))
                except ValueError:
                    try:
                        retry_after_seconds = max(
                            0.0,
                            (parsedate_to_datetime(header).astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds(),
                        )
                    except (TypeError, ValueError, OverflowError):
                        retry_after_seconds = None
        try:
            exc.close()
        except Exception:
            pass
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
    return {"ok": False, "error": message, "parameters": effective_parameters,
            "partial_text": "".join(streamed_parts) or None,
            "time_to_first_token_ms": time_to_first_token_ms,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            **({"http_status": http_status} if http_status is not None else {}),
            **({"retry_after_seconds": retry_after_seconds} if retry_after_seconds is not None else {})}


def _url_with_query(url: str, values: dict[str, str | int]) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.extend((key, str(value)) for key, value in values.items())
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment))


def _discover_model_pages(
    url: str, headers: dict[str, str], protocol: str, rows_key: str, id_field: str,
) -> list[dict[str, Any]]:
    discovered: dict[str, dict[str, Any]] = {}
    cursor = None
    seen_cursors: set[str] = set()
    for page_index in range(MODEL_DISCOVERY_MAX_PAGES):
        query: dict[str, str | int] = {}
        if protocol == "gemini_generate":
            query["pageSize"] = MODEL_DISCOVERY_PAGE_SIZE
            if cursor:
                query["pageToken"] = cursor
        elif protocol == "anthropic_messages":
            query["limit"] = MODEL_DISCOVERY_PAGE_SIZE
            if cursor:
                query["after_id"] = cursor
        elif cursor:
            query.update({"limit": MODEL_DISCOVERY_PAGE_SIZE, "after": cursor})

        result = request_json(_url_with_query(url, query) if query else url, headers=headers)
        rows = result.get(rows_key)
        if not isinstance(rows, list):
            raise RuntimeError("This endpoint returned an unsupported model-list response. Add the exact model ID manually.")
        page_ids = [row.get(id_field) for row in rows if isinstance(row, dict)]
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = row.get(id_field)
            if isinstance(model_id, str) and model_id.strip():
                clean_id = model_id.strip().removeprefix("models/")
                if clean_id and len(clean_id) <= 200:
                    discovered.setdefault(clean_id, row)
        if len(discovered) >= MAX_DISCOVERED_MODELS:
            break

        if protocol == "gemini_generate":
            next_cursor = result.get("nextPageToken")
            has_more = isinstance(next_cursor, str) and bool(next_cursor)
        else:
            has_more = result.get("has_more") is True
            next_cursor = result.get("last_id")
            if not isinstance(next_cursor, str) or not next_cursor:
                next_cursor = next((item for item in reversed(page_ids) if isinstance(item, str) and item), None)
        if not has_more:
            break
        if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen_cursors:
            raise RuntimeError("The provider indicated more model pages but returned no usable next-page cursor.")
        if len(next_cursor) > 4096:
            raise RuntimeError("The provider returned an oversized model-list cursor.")
        if page_index + 1 >= MODEL_DISCOVERY_MAX_PAGES:
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return [discovered[model_id] for model_id in sorted(discovered)[:MAX_DISCOVERED_MODELS]]


def discover_models(connection: dict[str, Any]) -> list[str]:
    return [entry["model_id"] for entry in _discover_model_records(connection)]


def _positive_model_limit(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 10_000_000:
        return value
    return None


def _capability_support(container: Any, field: str) -> bool | None:
    if not isinstance(container, dict):
        return None
    capability = container.get(field)
    if not isinstance(capability, dict) or not isinstance(capability.get("supported"), bool):
        return None
    return capability["supported"]


def _discover_model_records(connection: dict[str, Any]) -> list[dict[str, Any]]:
    protocol = connection["protocol"]
    base = connection["base_url"]
    headers = auth_headers(connection)
    if protocol == "ollama_chat":
        source, rows_key, id_field = "Ollama /api/tags", "models", "name"
        rows = _discover_model_pages(base + "/api/tags", headers, protocol, rows_key, id_field)
    elif protocol == "gemini_generate":
        source, rows_key, id_field = "Gemini Models API", "models", "name"
        rows = _discover_model_pages(base + "/models", headers, protocol, rows_key, id_field)
    else:
        source, rows_key, id_field = (
            ("Anthropic Models API", "data", "id") if protocol == "anthropic_messages"
            else ("OpenAI-compatible model-list endpoint", "data", "id")
        )
        rows = _discover_model_pages(base + "/models", headers, protocol, rows_key, id_field)

    today = date.today().isoformat()
    details: list[dict[str, Any]] = []
    for row in rows:
        raw_id = row.get(id_field)
        if not isinstance(raw_id, str) or not raw_id.strip():
            continue
        model_id = raw_id.strip().removeprefix("models/")
        name = model_id
        description = ""
        context_limit = None
        output_limit = None
        capabilities: dict[str, bool | None] = {
            "vision": None, "tools": None, "reasoning": None, "streaming": None,
        }
        if protocol == "anthropic_messages":
            display_name = row.get("display_name")
            if isinstance(display_name, str) and display_name.strip():
                name = display_name.strip()
            caps = row.get("capabilities")
            capabilities["vision"] = _capability_support(caps, "image_input")
            capabilities["reasoning"] = _capability_support(caps, "thinking")
            context_limit = _positive_model_limit(row.get("max_input_tokens"))
            output_limit = _positive_model_limit(row.get("max_tokens"))
        elif protocol == "gemini_generate":
            display_name = row.get("displayName")
            if isinstance(display_name, str) and display_name.strip():
                name = display_name.strip()
            raw_description = row.get("description")
            if isinstance(raw_description, str):
                description = raw_description.strip()[:1000]
            context_limit = _positive_model_limit(row.get("inputTokenLimit"))
            output_limit = _positive_model_limit(row.get("outputTokenLimit"))
        details.append({
            "model_id": model_id,
            "name": name[:100],
            "description": description,
            "context_limit": context_limit,
            "output_limit": output_limit,
            "capabilities": capabilities,
            "metadata_source": source,
            "metadata_checked_on": today,
        })
    return details


def discover_model_details(connection: dict[str, Any]) -> list[dict[str, Any]]:
    """Return allow-listed model metadata supported by the selected provider's list response."""
    return _discover_model_records(connection)


def _history_cost_was_stale(cost: dict[str, Any], timestamp: Any) -> bool:
    if cost.get("price_stale") is True:
        return True
    try:
        checked_on = date.fromisoformat(cost.get("checked_on"))
    except (TypeError, ValueError):
        return False
    try:
        recorded = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if recorded.tzinfo is None:
            recorded = recorded.replace(tzinfo=timezone.utc)
        run_date = recorded.astimezone(timezone.utc).date()
    except (AttributeError, TypeError, ValueError):
        run_date = date.today()
    return (run_date - checked_on).days > PRICING_STALE_AFTER_DAYS


def append_history(record: dict[str, Any]) -> None:
    _prepare_private_data_root()
    with HISTORY_LOCK:
        catalog = load_catalog()
        encrypted = bool(catalog.get("history_encrypted"))
        if HISTORY_PATH.exists() or HISTORY_PATH.is_symlink():
            try:
                history_stat = HISTORY_PATH.lstat()
            except OSError as exc:
                raise RuntimeError("The local history file could not be inspected.") from exc
            if not stat.S_ISREG(history_stat.st_mode):
                raise RuntimeError("The local history path must be a regular file.")
            if not encrypted and history_stat.st_size:
                try:
                    with HISTORY_PATH.open("rb") as existing:
                        first = existing.readline()
                    encrypted = is_envelope(json.loads(first.decode("utf-8")))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    pass
            if history_stat.st_size:
                with HISTORY_PATH.open("rb") as existing:
                    existing.seek(-1, os.SEEK_END)
                    if existing.read(1) != b"\n":
                        tail = _read_history_final_line()
                        try:
                            tail_value = json.loads(tail.decode("utf-8")) if tail.strip() else {}
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            raise RuntimeError(
                                "Local history ends with an incomplete record. Export the readable history, then clear history before saving more runs."
                            ) from None
                        if not isinstance(tail_value, dict):
                            raise RuntimeError(
                                "Local history ends with an incomplete record. Export the readable history, then clear history before saving more runs."
                            )
                        with HISTORY_PATH.open("ab") as existing:
                            existing.write(b"\n")
                            existing.flush()
                            os.fsync(existing.fileno())
        stored_record = encrypt_record(record, create_key=True) if encrypted else record
        line = json.dumps(stored_record, ensure_ascii=True, separators=(",", ":")) + "\n"
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(HISTORY_PATH, flags, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8", newline="\n") as handle:
            if os.name == "posix":
                os.fchmod(handle.fileno(), 0o600)
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        _sync_data_directory()


def _read_history_final_line() -> bytes:
    chunks = []
    with HISTORY_PATH.open("rb") as handle:
        position = handle.seek(0, os.SEEK_END)
        while position:
            size = min(65536, position)
            position -= size
            handle.seek(position)
            chunk = handle.read(size)
            newline = chunk.rfind(b"\n")
            if newline >= 0:
                chunks.append(chunk[newline + 1:])
                break
            chunks.append(chunk)
    return b"".join(reversed(chunks))


def read_history_report() -> tuple[list[dict[str, Any]], bool]:
    rows = []
    rating_events: dict[str, dict[str, Any]] = {}
    preference_events: dict[str, dict[str, Any]] = {}
    ignored_incomplete_tail = False
    catalog = load_catalog()
    encryption_required = bool(catalog.get("history_encrypted"))
    with HISTORY_LOCK:
        if HISTORY_PATH.is_symlink():
            raise RuntimeError("The local history path must not be a symbolic link.")
        if not HISTORY_PATH.exists():
            return rows, ignored_incomplete_tail
        try:
            history_mode = HISTORY_PATH.lstat().st_mode
        except OSError as exc:
            raise RuntimeError("The local history file could not be inspected.") from exc
        if not stat.S_ISREG(history_mode):
            raise RuntimeError("The local history path must be a regular file.")
        _prepare_private_data_root()
        if os.name == "posix":
            os.chmod(HISTORY_PATH, 0o600)
        with HISTORY_PATH.open("rb") as handle:
            for raw_line in handle:
                is_final_fragment = not raw_line.endswith(b"\n")
                try:
                    line = raw_line.decode("utf-8")
                except UnicodeDecodeError:
                    if is_final_fragment:
                        ignored_incomplete_tail = True
                        break
                    raise ValueError("Local history contains invalid UTF-8 before its final record.") from None
                if line.strip():
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        if is_final_fragment:
                            ignored_incomplete_tail = True
                            break
                        raise
                    if isinstance(value, dict) and is_envelope(value):
                        value = decrypt_record(value)
                    elif encryption_required:
                        raise RuntimeError("History encryption is enabled but an unencrypted record was found.")
                    if isinstance(value, dict):
                        if value.get("record_type") == "rating":
                            target_id = value.get("target_record_id")
                            rating = value.get("rating")
                            if isinstance(target_id, str) and (
                                rating is None or (isinstance(rating, int) and not isinstance(rating, bool) and 1 <= rating <= 5)
                            ):
                                rating_events[target_id] = value
                        elif value.get("record_type") == "preference":
                            target_run_id = value.get("target_run_id")
                            preferred_id = value.get("preferred_model_entry_id")
                            if isinstance(target_run_id, str) and (preferred_id is None or isinstance(preferred_id, str)):
                                preference_events[target_run_id] = value
                        else:
                            rows.append(value)
    for row in rows:
        record_id = row.get("record_id")
        event = rating_events.get(record_id) if isinstance(record_id, str) else None
        if event:
            row["user_rating"] = event.get("rating")
            row["rating_updated_at"] = event.get("timestamp")
        run_id = row.get("run_id")
        preference = preference_events.get(run_id) if isinstance(run_id, str) else None
        if preference:
            preferred_id = preference.get("preferred_model_entry_id")
            row["has_preference"] = bool(preferred_id)
            row["is_preferred"] = bool(preferred_id) and row.get("model_entry_id") == preferred_id
            row["preference_updated_at"] = preference.get("timestamp")
    return rows, ignored_incomplete_tail


def read_history() -> list[dict[str, Any]]:
    """Return complete history rows; see read_history_report for tail warnings."""
    return read_history_report()[0]


def clear_history() -> None:
    with HISTORY_LOCK:
        if HISTORY_PATH.exists():
            HISTORY_PATH.unlink()
            _sync_data_directory()


def set_history_encryption(enabled: bool) -> int:
    """Migrate the existing JSONL atomically, then persist the encryption setting."""
    if not isinstance(enabled, bool):
        raise ValueError("History encryption must be enabled or disabled.")
    with HISTORY_LOCK:
        catalog = load_catalog()
        if bool(catalog.get("history_encrypted")) == enabled:
            return 0
        if enabled and not encryption_available():
            raise RuntimeError(
                "History encryption needs the optional cryptography package. Install requirements-history-encryption.txt and restart the app."
            )
        _prepare_private_data_root()
        migrated = migrate_file(HISTORY_PATH, enabled)
        catalog["history_encrypted"] = enabled
        save_catalog(catalog)
        _sync_data_directory()
        return migrated


def summarize_history(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate saved records by catalog model without treating missing data as zero."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        connection_id = str(record.get("connection_id") or "")
        model_entry_id = str(record.get("model_entry_id") or record.get("model_id") or "unknown")
        key = (connection_id, model_entry_id)
        row = groups.setdefault(key, {
            "connection_id": connection_id,
            "connection_name": str(record.get("connection_name") or "Unknown connection"),
            "model_entry_id": model_entry_id,
            "model_id": str(record.get("model_id") or "Unknown model"),
            "model_name": str(record.get("model_name") or record.get("model_id") or "Unknown model"),
            "records": 0,
            "successes": 0,
            "failures": 0,
            "latency_total_ms": 0,
            "latency_samples": 0,
            "first_token_total_ms": 0,
            "first_token_samples": 0,
            "input_tokens": 0,
            "input_token_samples": 0,
            "output_tokens": 0,
            "output_token_samples": 0,
            "estimated_cost_usd": 0.0,
            "cost_estimate_samples": 0,
            "stale_cost_estimate_samples": 0,
            "local_run_samples": 0,
            "rating_total": 0,
            "rating_samples": 0,
            "preferred_selections": 0,
            "preference_samples": 0,
        })
        row["records"] += 1
        if record.get("finish_status") == "success":
            row["successes"] += 1
        else:
            row["failures"] += 1
        latency = record.get("latency_ms")
        if isinstance(latency, (int, float)) and not isinstance(latency, bool) and latency >= 0:
            row["latency_total_ms"] += latency
            row["latency_samples"] += 1
        first_token = record.get("time_to_first_token_ms")
        if isinstance(first_token, (int, float)) and not isinstance(first_token, bool) and first_token >= 0:
            row["first_token_total_ms"] += first_token
            row["first_token_samples"] += 1
        for field, total_field, sample_field in (
            ("input_tokens", "input_tokens", "input_token_samples"),
            ("output_tokens", "output_tokens", "output_token_samples"),
        ):
            value = record.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                row[total_field] += value
                row[sample_field] += 1
        cost = record.get("cost")
        rating = record.get("user_rating")
        if isinstance(rating, int) and not isinstance(rating, bool) and 1 <= rating <= 5:
            row["rating_total"] += rating
            row["rating_samples"] += 1
        if record.get("is_preferred") is True:
            row["preferred_selections"] += 1
        if record.get("has_preference") is True:
            row["preference_samples"] += 1
        if record.get("destination") == "local":
            row["local_run_samples"] += 1
        if isinstance(cost, dict) and cost.get("status") == "estimated":
            amount = cost.get("amount_usd")
            if isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount >= 0:
                row["estimated_cost_usd"] += amount
                row["cost_estimate_samples"] += 1
                if _history_cost_was_stale(cost, record.get("timestamp")):
                    row["stale_cost_estimate_samples"] += 1

    result = list(groups.values())
    for row in result:
        row["average_latency_ms"] = (
            row["latency_total_ms"] / row["latency_samples"] if row["latency_samples"] else None
        )
        row["average_time_to_first_token_ms"] = (
            row["first_token_total_ms"] / row["first_token_samples"] if row["first_token_samples"] else None
        )
        row["average_user_rating"] = row["rating_total"] / row["rating_samples"] if row["rating_samples"] else None
        del row["rating_total"]
        del row["latency_total_ms"]
        del row["first_token_total_ms"]
    return sorted(result, key=lambda row: (-row["records"], row["connection_name"].casefold(), row["model_name"].casefold()))


def summarize_history_trends(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate saved result counts and success rates by UTC calendar day."""
    groups: dict[str, dict[str, int]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        timestamp = record.get("timestamp")
        if not isinstance(timestamp, str):
            continue
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        day = parsed.astimezone(timezone.utc).date().isoformat()
        row = groups.setdefault(day, {"runs": 0, "successes": 0})
        row["runs"] += 1
        if record.get("finish_status") == "success":
            row["successes"] += 1
    days = sorted(groups)
    if days:
        cutoff = date.fromisoformat(days[-1]) - timedelta(days=364)
        days = [day for day in days if date.fromisoformat(day) >= cutoff]
    return [
        {
            "date": day,
            "runs": values["runs"],
            "successes": values["successes"],
            "success_rate": values["successes"] / values["runs"],
        }
        for day in days
        for values in (groups[day],)
    ]


def summarize_model_history_trends(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate dated history success counts by model entry and UTC day."""
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    latest_day: date | None = None
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("timestamp"), str):
            continue
        try:
            parsed = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        day = parsed.astimezone(timezone.utc).date().isoformat()
        latest_day = max(latest_day, date.fromisoformat(day)) if latest_day else date.fromisoformat(day)
        connection_id = str(record.get("connection_id") or "")
        model_entry_id = str(record.get("model_entry_id") or record.get("model_id") or "unknown")
        key = (day, connection_id, model_entry_id)
        row = groups.setdefault(key, {
            "date": day,
            "connection_id": connection_id,
            "connection_name": str(record.get("connection_name") or "Unknown connection"),
            "model_entry_id": model_entry_id,
            "model_id": str(record.get("model_id") or "Unknown model"),
            "model_name": str(record.get("model_name") or record.get("model_id") or "Unknown model"),
            "runs": 0,
            "successes": 0,
        })
        row["runs"] += 1
        if record.get("finish_status") == "success":
            row["successes"] += 1
    if latest_day is None:
        return []
    cutoff = latest_day - timedelta(days=364)
    result = []
    for (day, _connection_id, _model_entry_id), row in sorted(groups.items()):
        if date.fromisoformat(day) < cutoff:
            continue
        result.append({
            **row,
            "model_key": json.dumps([row["connection_id"], row["model_entry_id"]], separators=(",", ":")),
            "success_rate": row["successes"] / row["runs"],
        })
    recent_days: dict[str, list[str]] = {}
    for row in result:
        dates = recent_days.setdefault(row["model_key"], [])
        if not dates or dates[-1] != row["date"]:
            dates.append(row["date"])
    allowed_days = {key: set(days[-30:]) for key, days in recent_days.items()}
    return [row for row in result if row["date"] in allowed_days[row["model_key"]]]


def summarize_category_history_trends(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate saved prompt-benchmark model results by category and UTC day."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or record.get("run_kind") != "benchmark":
            continue
        category = record.get("category")
        timestamp = record.get("timestamp")
        if not isinstance(category, str) or not category.strip() or not isinstance(timestamp, str):
            continue
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        day = parsed.astimezone(timezone.utc).date().isoformat()
        key = (day, category)
        row = groups.setdefault(key, {"date": day, "category": category, "runs": 0, "successes": 0})
        row["runs"] += 1
        if record.get("finish_status") == "success":
            row["successes"] += 1
    if not groups:
        return []
    latest_day = max(date.fromisoformat(day) for day, _category in groups)
    cutoff = latest_day - timedelta(days=364)
    result = []
    for (day, category), row in sorted(groups.items()):
        if date.fromisoformat(day) < cutoff:
            continue
        result.append({
            **row,
            "category_key": category,
            "success_rate": row["successes"] / row["runs"],
        })
    recent_days: dict[str, list[str]] = {}
    for row in result:
        days = recent_days.setdefault(row["category_key"], [])
        if not days or days[-1] != row["date"]:
            days.append(row["date"])
    allowed_days = {category: set(days[-30:]) for category, days in recent_days.items()}
    return [row for row in result if row["date"] in allowed_days[row["category_key"]]]


def summarize_benchmarks(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare saved prompt-set runs by prompt and model without returning prompt text."""
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or record.get("run_kind") != "benchmark":
            continue
        prompt_set_id = record.get("prompt_set_id")
        prompt_id = record.get("prompt_id")
        if not isinstance(prompt_set_id, str) or not isinstance(prompt_id, str):
            continue
        connection_id = str(record.get("connection_id") or "")
        model_entry_id = str(record.get("model_entry_id") or record.get("model_id") or "unknown")
        key = (prompt_set_id, prompt_id, connection_id, model_entry_id)
        row = groups.setdefault(key, {
            "prompt_set_id": prompt_set_id,
            "prompt_set_name": str(record.get("prompt_set_name") or "Unknown prompt set"),
            "prompt_id": prompt_id,
            "category": str(record.get("category") or "Uncategorized"),
            "connection_id": connection_id,
            "connection_name": str(record.get("connection_name") or "Unknown connection"),
            "model_entry_id": model_entry_id,
            "model_id": str(record.get("model_id") or "Unknown model"),
            "model_name": str(record.get("model_name") or record.get("model_id") or "Unknown model"),
            "runs": 0,
            "successes": 0,
            "latency_total_ms": 0,
            "latency_samples": 0,
            "rating_total": 0,
            "rating_samples": 0,
            "preferred_selections": 0,
            "preference_samples": 0,
            "output_tokens": 0,
            "output_token_samples": 0,
            "estimated_cost_usd": 0.0,
            "cost_samples": 0,
            "stale_cost_samples": 0,
            "local_run_samples": 0,
        })
        row["runs"] += 1
        if record.get("finish_status") == "success":
            row["successes"] += 1
        latency = record.get("latency_ms")
        if isinstance(latency, (int, float)) and not isinstance(latency, bool) and latency >= 0:
            row["latency_total_ms"] += latency
            row["latency_samples"] += 1
        rating = record.get("user_rating")
        if isinstance(rating, int) and not isinstance(rating, bool) and 1 <= rating <= 5:
            row["rating_total"] += rating
            row["rating_samples"] += 1
        if record.get("is_preferred") is True:
            row["preferred_selections"] += 1
        if record.get("has_preference") is True:
            row["preference_samples"] += 1
        if record.get("destination") == "local":
            row["local_run_samples"] += 1
        output_tokens = record.get("output_tokens")
        if isinstance(output_tokens, int) and not isinstance(output_tokens, bool) and output_tokens >= 0:
            row["output_tokens"] += output_tokens
            row["output_token_samples"] += 1
        cost = record.get("cost")
        if isinstance(cost, dict) and cost.get("status") == "estimated":
            amount = cost.get("amount_usd")
            if isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount >= 0:
                row["estimated_cost_usd"] += amount
                row["cost_samples"] += 1
                if _history_cost_was_stale(cost, record.get("timestamp")):
                    row["stale_cost_samples"] += 1

    result = list(groups.values())
    for row in result:
        row["success_rate"] = row["successes"] / row["runs"] if row["runs"] else None
        row["average_latency_ms"] = row["latency_total_ms"] / row["latency_samples"] if row["latency_samples"] else None
        row["average_user_rating"] = row["rating_total"] / row["rating_samples"] if row["rating_samples"] else None
        del row["latency_total_ms"]
        del row["rating_total"]
    return sorted(result, key=lambda row: (
        row["prompt_set_name"].casefold(), row["category"].casefold(), row["prompt_id"].casefold(),
        row["connection_name"].casefold(), row["model_name"].casefold(),
    ))


def estimate_cost(model: dict[str, Any], usage: dict[str, Any], destination: str) -> dict[str, Any]:
    if destination == "local":
        return {"status": "not_estimated_local", "label": "Not estimated for local run"}
    price = model.get("pricing")
    inp, out = usage.get("input_tokens"), usage.get("output_tokens")
    if (not isinstance(price, dict) or not isinstance(inp, int) or isinstance(inp, bool) or inp < 0
            or not isinstance(out, int) or isinstance(out, bool) or out < 0):
        return {"status": "unknown", "label": "Cost unknown"}
    input_price, output_price = price.get("input_per_million"), price.get("output_per_million")
    if (not isinstance(input_price, (int, float)) or isinstance(input_price, bool) or not _is_finite_number(input_price)
            or input_price < 0 or not isinstance(output_price, (int, float)) or isinstance(output_price, bool)
            or not _is_finite_number(output_price) or output_price < 0):
        return {"status": "unknown", "label": "Cost unknown"}
    checked_on = price.get("checked_on")
    try:
        checked_date = date.fromisoformat(checked_on) if isinstance(checked_on, str) else None
    except ValueError:
        checked_date = None
    if checked_date is None:
        return {"status": "unknown", "label": "Cost unknown"}
    age_days = max(0, (date.today() - checked_date).days)
    stale = age_days > PRICING_STALE_AFTER_DAYS
    try:
        amount = (inp * input_price + out * output_price) / 1_000_000
    except OverflowError:
        return {"status": "unknown", "label": "Cost unknown"}
    if not _is_finite_number(amount):
        return {"status": "unknown", "label": "Cost unknown"}
    label = "Estimated $" + format(amount, ".8g")
    if stale:
        label += f" · pricing is {age_days} days old"
    return {
        "status": "estimated", "amount_usd": amount, "label": label,
        "assumptions": "Provider-reported tokens × dated USD price per million; excludes unreported cache or tier adjustments.",
        "source_url": price.get("source_url"), "checked_on": checked_on,
        "price_age_days": age_days, "price_stale": stale,
    }
