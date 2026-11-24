from __future__ import annotations

import base64
import copy
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlsplit

import hub_core as core
from secret_store import (
    SecretStoreUnavailable,
    delete_secret,
    is_supported as secret_store_supported,
    read_secret,
    save_secret,
    store_name as credential_store_name,
)


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
HOST = "127.0.0.1"
PORT = 8765
ALLOWED_ORIGIN = f"http://{HOST}:{PORT}"
MAX_PROMPT_CHARS = 20_000
MAX_CHAT_MESSAGES = 32
MAX_CHAT_CONTEXT_CHARS = 32_000
MAX_MODELS_PER_RUN = 5
MAX_ACTIVE_RUNS = 3
MAX_PARALLEL_MODELS = 3
MAX_EXPLICIT_RETRIES = 2
RUN_TTL_SECONDS = 30 * 60
CLI_NAMES = {"codex": "codex", "claude": "claude", "gemini": "gemini", "antigravity": "agy", "ollama": "ollama"}
RUNS: dict[str, dict[str, Any]] = {}
RUN_LOCK = threading.RLock()
_CREDENTIAL_DIALOG_LOCK = threading.Lock()
_CREDENTIAL_DIALOGS: dict[str, subprocess.Popen[Any]] = {}


def _inline_script_hash() -> str:
    html = (WEB_ROOT / "index.html").read_bytes()
    # HTML parsing normalizes line endings before hashing inline script text.
    html = html.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    scripts = re.findall(rb"<script\b[^>]*>(.*?)</script\s*>", html, flags=re.IGNORECASE | re.DOTALL)
    if len(scripts) != 1:
        raise RuntimeError("The browser UI must contain exactly one inline script for the content security policy.")
    digest = hashlib.sha256(scripts[0]).digest()
    return base64.b64encode(digest).decode("ascii")


INLINE_SCRIPT_HASH = _inline_script_hash()


def installed_clis() -> dict[str, bool]:
    return {name: shutil.which(command) is not None for name, command in CLI_NAMES.items()}


def _connection_check_error(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return "Provider returned HTTP " + str(exc.code) + "."
    if isinstance(exc, URLError):
        return "Could not reach the configured connection."
    if isinstance(exc, TimeoutError):
        return "Connection check timed out."
    if isinstance(exc, RuntimeError):
        return str(exc)
    return "Connection check failed."


def _save_connection_check(connection_id: str, checked_connection: dict[str, Any], result: dict[str, Any]) -> None:
    with core.CATALOG_LOCK:
        catalog = core.load_catalog()
        connection = core.connection_by_id(catalog, connection_id)
        if not connection or any(connection.get(key) != checked_connection.get(key) for key in ("base_url", "protocol")):
            return
        connection["last_connection_check"] = result
        if result.get("ok"):
            connection["last_successful_discovery"] = result["checked_at"]
        core.save_catalog(catalog)


def _normalize_run_parameters(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Run settings must be an object.")
    if set(value) - {"max_output_tokens", "stream"}:
        raise ValueError("A run setting is not supported.")
    parameters: dict[str, Any] = {}
    if "stream" in value:
        if not isinstance(value["stream"], bool):
            raise ValueError("Streaming must be enabled or disabled.")
        parameters["stream"] = value["stream"]
    output_limit = value.get("max_output_tokens")
    if output_limit in (None, ""):
        return parameters
    if not isinstance(output_limit, int) or isinstance(output_limit, bool) or not 1 <= output_limit <= 200_000:
        raise ValueError("Maximum output tokens must be a whole number from 1 to 200,000.")
    parameters["max_output_tokens"] = output_limit
    return parameters


def _normalize_chat_messages(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_CHAT_MESSAGES:
        raise ValueError(f"Chat context must contain between 1 and {MAX_CHAT_MESSAGES} messages.")
    messages: list[dict[str, str]] = []
    total_chars = 0
    for item in value:
        if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
            raise ValueError("Chat messages must use user or assistant roles.")
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Chat messages must contain text.")
        total_chars += len(content)
        if len(content) > MAX_PROMPT_CHARS or total_chars > MAX_CHAT_CONTEXT_CHARS:
            raise ValueError("Chat context is too large. Keep fewer recent messages or shorten the handoff context.")
        messages.append({"role": item["role"], "content": content})
    if messages[-1]["role"] != "user":
        raise ValueError("The latest chat message must be from the user.")
    return messages


def _discover_and_record(
    connection_id: str, connection: dict[str, Any], include_metadata: bool = False,
) -> list[str] | list[dict[str, Any]]:
    try:
        models = core.discover_model_details(connection) if include_metadata else core.discover_models(connection)
    except Exception as exc:
        result = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "message": _connection_check_error(exc),
        }
        try:
            _save_connection_check(connection_id, connection, result)
        except (OSError, RuntimeError):
            pass
        raise
    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": True,
        "model_count": len(models),
    }
    _save_connection_check(connection_id, connection, result)
    return models


def active_credential_dialogs() -> dict[str, bool]:
    with _CREDENTIAL_DIALOG_LOCK:
        active: dict[str, bool] = {}
        for connection_id, process in list(_CREDENTIAL_DIALOGS.items()):
            if process.poll() is None:
                active[connection_id] = True
            else:
                _CREDENTIAL_DIALOGS.pop(connection_id, None)
        return active


def open_credential_dialog(connection_id: str, connection_name: str) -> None:
    if not core.ID_RE.fullmatch(connection_id):
        raise ValueError("Invalid provider connection ID.")
    if not secret_store_supported():
        raise SecretStoreUnavailable("Secure key entry is unavailable on this system. Use an environment-variable fallback.")
    try:
        import tkinter  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("This Python installation is missing Tk support, which the secure key window needs.") from exc

    with _CREDENTIAL_DIALOG_LOCK:
        existing = _CREDENTIAL_DIALOGS.get(connection_id)
        if existing and existing.poll() is None:
            return
        catalog = core.load_catalog()
        if not core.connection_by_id(catalog, connection_id):
            raise ValueError("Connection not found.")
        dialog_environment = os.environ.copy()
        for connection in catalog["connections"]:
            env_name = connection.get("auth_env", "")
            if env_name:
                dialog_environment.pop(env_name, None)
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "credential_dialog.py"), connection_id, connection_name],
            cwd=ROOT,
            env=dialog_environment,
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _CREDENTIAL_DIALOGS[connection_id] = process


def _prune_runs() -> None:
    cutoff = time.time() - RUN_TTL_SECONDS
    def settled(run: dict[str, Any]) -> bool:
        return run.get("status") in ("completed", "failed", "cancelled") and run.get("pending_calls", 0) == 0

    for run_id, run in list(RUNS.items()):
        if settled(run) and run.get("created_at", 0) < cutoff:
            del RUNS[run_id]
    if len(RUNS) > 100:
        oldest_first = sorted(RUNS.items(), key=lambda item: item[1].get("created_at", 0))
        for run_id, run_data in oldest_first:
            if settled(run_data):
                del RUNS[run_id]
                if len(RUNS) <= 50:
                    break


def _public_run(run: dict[str, Any]) -> dict[str, Any]:
    public = {key: copy.deepcopy(value) for key, value in run.items()
              if key not in ("prompt", "cancel_event", "created_at") and not key.startswith("_")}
    for model in public.get("models", []):
        if isinstance(model.get("result"), dict):
            model["result"].pop("history_record_id", None)
    return public


def _release_retry_parent_locked(run: dict[str, Any]) -> None:
    if run.get("status") not in ("completed", "failed", "cancelled") or run.get("pending_calls", 0) > 0:
        return
    parent = run.get("_retry_parent")
    if not isinstance(parent, dict):
        return
    source = RUNS.get(parent.get("run_id"))
    if not source:
        return
    row = next((item for item in source.get("models", []) if item.get("model_entry_id") == parent.get("model_entry_id")), None)
    if row:
        row["retry_in_progress"] = False


def _future_finished(run_id: str, future: Any) -> None:
    with RUN_LOCK:
        run = RUNS.get(run_id)
        if run:
            run["pending_calls"] = max(0, run.get("pending_calls", 0) - 1)
            _release_retry_parent_locked(run)


def _append_run_stream(run_id: str, model_entry_id: str, fragment: str, parameters: dict[str, Any]) -> None:
    with RUN_LOCK:
        run = RUNS.get(run_id)
        if not run or run["cancel_event"].is_set():
            return
        row = next((item for item in run["models"] if item["model_entry_id"] == model_entry_id), None)
        if row is None:
            return
        result = row.get("result")
        if not result or not result.get("streaming"):
            result = {"ok": True, "text": "", "usage": {}, "parameters": dict(parameters), "streaming": True}
            row["result"] = result
        result["text"] += fragment


def _persist_result(run_id: str, prompt: str, connection: dict[str, Any], model: dict[str, Any],
                    result: dict[str, Any], benchmark: dict[str, Any] | None,
                    run_kind: str = "comparison") -> tuple[str | None, str | None]:
    try:
        usage = result.get("usage") or {}
        record = {
            "record_id": uuid.uuid4().hex,
            "run_id": run_id,
            "run_kind": "benchmark" if benchmark else run_kind,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt_set_id": (benchmark or {}).get("prompt_set_id"),
            "prompt_set_name": (benchmark or {}).get("prompt_set_name"),
            "prompt_id": (benchmark or {}).get("prompt_id"),
            "category": (benchmark or {}).get("category"),
            "prompt_text": prompt,
            "connection_id": connection["id"],
            "connection_name": connection["name"],
            "protocol": connection["protocol"],
            "destination": connection["destination"],
            "model_entry_id": model["id"],
            "model_id": model["model_id"],
            "model_name": model["name"],
            "parameters": result.get("parameters") or {},
            "latency_ms": result.get("latency_ms"),
            "time_to_first_token_ms": result.get("time_to_first_token_ms"),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "finish_status": "success" if result.get("ok") else "error",
            "error": result.get("error"),
            "response_text": result.get("text") or result.get("partial_text"),
            "cost": core.estimate_cost(model, usage, connection["destination"]) if result.get("ok") else None,
        }
        with core.HISTORY_LOCK:
            catalog = core.load_catalog()
            if not catalog.get("history_enabled"):
                return None, None
            core.append_history(record)
        return record["record_id"], None
    except RuntimeError as exc:
        message = str(exc)
        if message.startswith("Local history ends with an incomplete record."):
            return None, message
        return None, "Local history could not be saved. Check the history file and available disk space."
    except Exception:
        return None, "Local history could not be saved. Check the history file and available disk space."

def _run_worker(run_id: str, prompt: str, selections: list[tuple[dict[str, Any], dict[str, Any]]],
                parameters: dict[str, Any], messages: list[dict[str, str]] | None = None) -> None:
    with RUN_LOCK:
        run = RUNS.get(run_id)
        if not run:
            return
        cancel_event = run["cancel_event"]
    pool = ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_MODELS, max(1, len(selections))))
    futures = {}
    try:
        for connection, model in selections:
            if cancel_event.is_set():
                break
            with RUN_LOCK:
                current = RUNS.get(run_id)
                if not current or current["cancel_event"].is_set():
                    break
                entry = next((item for item in current["models"] if item["model_entry_id"] == model["id"]), None)
                if entry is None:
                    continue
                entry["status"] = "running"
                current["pending_calls"] = current.get("pending_calls", 0) + 1
            try:
                if parameters.get("stream") and messages is not None:
                    on_delta = lambda fragment, rid=run_id, mid=model["id"], params=parameters: _append_run_stream(rid, mid, fragment, params)
                    future = pool.submit(core.call_model, connection, model, prompt, parameters, on_delta, messages)
                elif messages is not None:
                    future = pool.submit(core.call_model, connection, model, prompt, parameters, messages=messages)
                elif parameters.get("stream"):
                    on_delta = lambda fragment, rid=run_id, mid=model["id"], params=parameters: _append_run_stream(rid, mid, fragment, params)
                    future = pool.submit(core.call_model, connection, model, prompt, parameters, on_delta)
                elif parameters:
                    future = pool.submit(core.call_model, connection, model, prompt, parameters)
                else:
                    future = pool.submit(core.call_model, connection, model, prompt)
            except Exception:
                with RUN_LOCK:
                    current = RUNS.get(run_id)
                    if current:
                        current["pending_calls"] = max(0, current.get("pending_calls", 0) - 1)
                raise
            future.add_done_callback(lambda completed, rid=run_id: _future_finished(rid, completed))
            futures[future] = (connection, model)
        pending = set(futures)
        while pending and not cancel_event.is_set():
            done, pending = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
            for future in done:
                connection, model = futures[future]
                try:
                    result = future.result()
                except Exception:
                    result = {"ok": False, "error": "The request failed unexpectedly.", "latency_ms": 0,
                              "parameters": dict(parameters)}
                with RUN_LOCK:
                    run = RUNS.get(run_id)
                    if not run or run["cancel_event"].is_set():
                        continue
                    row = next((item for item in run["models"] if item["model_entry_id"] == model["id"]), None)
                    if row is None:
                        continue
                    row["status"] = "complete" if result.get("ok") else "failed"
                    previous = row.get("result") or {}
                    if not result.get("ok") and previous.get("streaming") and previous.get("text"):
                        result["partial_text"] = result.get("partial_text") or previous["text"]
                    row["result"] = {
                        **result,
                        "provider": connection["name"],
                        "connection_id": connection["id"],
                        "model_id": model["model_id"],
                        "model_name": model["name"],
                        "destination": connection["destination"],
                        "cost": core.estimate_cost(model, result.get("usage", {}), connection["destination"]) if result.get("ok") else None,
                    }
                    should_save = run.get("history_enabled", False)
                    benchmark = copy.deepcopy(run.get("benchmark"))
                    run_kind = run.get("run_kind", "comparison")
                if should_save:
                    history_record_id, history_save_error = _persist_result(run_id, prompt, connection, model, result, benchmark, run_kind)
                    with RUN_LOCK:
                        current = RUNS.get(run_id)
                        row = next((item for item in current["models"] if item["model_entry_id"] == model["id"]), None) if current else None
                        if row and row.get("result"):
                            row["result"]["history_saved"] = history_record_id is not None
                            if history_save_error:
                                row["result"]["history_save_error"] = history_save_error
                            if history_record_id:
                                row["result"]["history_record_id"] = history_record_id
        if cancel_event.is_set():
            for future in pending:
                future.cancel()
            pool.shutdown(wait=False, cancel_futures=True)
            return
        pool.shutdown(wait=True)
        with RUN_LOCK:
            run = RUNS.get(run_id)
            if run and not run["cancel_event"].is_set():
                run["status"] = "completed"
                _release_retry_parent_locked(run)
    except Exception:
        pool.shutdown(wait=False, cancel_futures=True)
        with RUN_LOCK:
            run = RUNS.get(run_id)
            if run and not run["cancel_event"].is_set():
                run["status"] = "failed"
                _release_retry_parent_locked(run)


def _start_run(prompt: str, selections: list[tuple[dict[str, Any], dict[str, Any]]], benchmark: dict[str, Any] | None = None,
               history_enabled: bool = False, parameters: dict[str, Any] | None = None, retry_depth: int = 0,
               retry_parent: tuple[str, str] | None = None, messages: list[dict[str, str]] | None = None,
               run_kind: str = "comparison") -> str:
    run_id = uuid.uuid4().hex
    event = threading.Event()
    models = []
    for connection, model in selections:
        models.append({
            "model_entry_id": model["id"],
            "model_id": model["model_id"],
            "model_name": model["name"],
            "connection_id": connection["id"],
            "connection_name": connection["name"],
            "destination": connection["destination"],
            "status": "queued",
            "retry_count": 0,
        })
    with RUN_LOCK:
        _prune_runs()
        active = sum(1 for item in RUNS.values() if item["status"] in ("queued", "running") or item.get("pending_calls", 0) > 0)
        if active >= MAX_ACTIVE_RUNS:
            raise ValueError("The app is already handling the maximum number of comparisons. Wait for one to finish.")
        RUNS[run_id] = {
            "id": run_id, "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
            "models": models, "preferred_model_entry_id": None, "cancel_event": event,
            "preferred_saved": False,
            "created_at": time.time(), "prompt": prompt, "pending_calls": 0, "benchmark": benchmark,
            "history_enabled": history_enabled, "parameters": dict(parameters or {}), "retry_depth": retry_depth,
            "run_kind": run_kind,
            "_retry_parent": ({"run_id": retry_parent[0], "model_entry_id": retry_parent[1]} if retry_parent else None),
            "_retry_targets": {
                model["id"]: {"base_url": connection["base_url"], "protocol": connection["protocol"]}
                for connection, model in selections
            },
        }
    worker = threading.Thread(target=_run_worker, args=(run_id, prompt, selections, dict(parameters or {}), messages), daemon=True)
    try:
        worker.start()
    except Exception:
        with RUN_LOCK:
            RUNS.pop(run_id, None)
        raise
    return run_id


def _retry_failed_model(run_id: str, model_entry_id: Any) -> str:
    if not isinstance(model_entry_id, str):
        raise ValueError("Choose a model result to retry.")
    with RUN_LOCK:
        source = RUNS.get(run_id)
        if not source:
            raise KeyError("Comparison run not found or expired.")
        if source.get("status") not in ("completed", "failed"):
            raise ValueError("Wait for the comparison to finish before retrying a model.")
        row = next((item for item in source["models"] if item["model_entry_id"] == model_entry_id), None)
        if not row or row.get("status") != "failed":
            raise ValueError("Only a failed model result can be retried.")
        if row.get("retry_in_progress"):
            raise ValueError("A retry for this model is already in progress.")
        if source.get("retry_depth", 0) >= MAX_EXPLICIT_RETRIES:
            raise ValueError("This request has reached the maximum of two explicit retries.")
        retry_count = row.get("retry_count", 0)
        if retry_count >= MAX_EXPLICIT_RETRIES:
            raise ValueError("This model has already used its two explicit retries.")
        prompt = source.get("prompt")
        if not isinstance(prompt, str) or not prompt:
            raise ValueError("The original prompt is no longer available for retry.")
        row["retry_count"] = retry_count + 1
        row["retry_in_progress"] = True
        benchmark = copy.deepcopy(source.get("benchmark"))
        parameters = dict(source.get("parameters") or {})
        history_enabled = False
        retry_depth = source.get("retry_depth", 0) + 1
        expected_model_id = row.get("model_id")
        expected_connection_id = row.get("connection_id")
        expected_target = copy.deepcopy((source.get("_retry_targets") or {}).get(model_entry_id))

    try:
        catalog = core.load_catalog()
        model = core.model_by_id(catalog, model_entry_id)
        if not model or model.get("model_id") != expected_model_id or model.get("connection_id") != expected_connection_id:
            raise ValueError("The model configuration changed or was removed. Review it before starting a new comparison.")
        connection = core.connection_by_id(catalog, model["connection_id"])
        if not connection:
            raise ValueError("The model's provider connection was removed.")
        if not expected_target or any(connection.get(key) != expected_target.get(key) for key in ("base_url", "protocol")):
            raise ValueError("The provider endpoint changed since the failed request. Review the connection before starting a new comparison.")
        history_enabled = bool(catalog.get("history_enabled"))
        output_limit = parameters.get("max_output_tokens")
        known_limit = model.get("output_limit")
        if isinstance(output_limit, int) and isinstance(known_limit, int) and output_limit > known_limit:
            raise ValueError("The previous output-token cap exceeds this model's current catalog limit.")
        return _start_run(
            prompt, [(connection, model)], benchmark, history_enabled, parameters, retry_depth,
            retry_parent=(run_id, model_entry_id),
        )
    except Exception:
        with RUN_LOCK:
            source = RUNS.get(run_id)
            row = next((item for item in source["models"] if item["model_entry_id"] == model_entry_id), None) if source else None
            if row:
                row["retry_count"] = max(0, row.get("retry_count", 1) - 1)
                row["retry_in_progress"] = False
        raise


def _cancel_run(run_id: str) -> bool:
    with RUN_LOCK:
        run = RUNS.get(run_id)
        if not run:
            return False
        if run["status"] in ("completed", "failed", "cancelled"):
            return True
        run["cancel_event"].set()
        run["status"] = "cancelled"
        run.pop("prompt", None)
        _release_retry_parent_locked(run)
        for item in run["models"]:
            if item["status"] in ("queued", "running"):
                item["status"] = "cancelled"
                item.pop("result", None)
        return True


class Handler(BaseHTTPRequestHandler):
    server_version = "PolyLLMHub/0.2"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        policy = (
            "default-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; "
            "style-src 'self' 'unsafe-inline'; script-src 'sha256-" + INLINE_SCRIPT_HASH + "'"
        )
        self.send_header("Content-Security-Policy", policy)

    def origin_allowed(self, required: bool = False) -> bool:
        origin = self.headers.get("Origin")
        return origin == ALLOWED_ORIGIN if required else origin is None or origin == ALLOWED_ORIGIN

    def send_json(self, status: int, value: Any) -> None:
        body = json.dumps(value, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self.send_json(500, {"error": "The web interface is missing."})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_download(self, body: bytes, content_type: str, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", "attachment; filename=" + filename)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def body_json(self, max_bytes: int = 150_000) -> dict[str, Any]:
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type != "application/json":
            raise ValueError("Content-Type must be application/json.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid content length.") from exc
        if length < 1 or length > max_bytes:
            raise ValueError("Request is empty or too large.")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid JSON request.") from exc
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object.")
        return value

    def _guard(self, require_origin: bool = False) -> bool:
        expected_host = f"{HOST}:{self.server.server_port}".lower()
        host = (self.headers.get("Host") or "").lower()
        if host != expected_host:
            self.send_json(403, {"error": "Local request not allowed."})
            return False
        if not self.origin_allowed(required=require_origin):
            self.send_json(403, {"error": "Origin not allowed."})
            return False
        return True

    def do_OPTIONS(self) -> None:
        self.send_response(403)
        self.send_security_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if not self._guard():
            return
        path = urlsplit(self.path).path
        if path == "/api/catalog":
            try:
                snapshot = core.public_catalog(core.load_catalog())
                snapshot["credential_dialogs"] = active_credential_dialogs()
                snapshot["credential_store_supported"] = secret_store_supported()
                snapshot["credential_store_name"] = credential_store_name()
                self.send_json(200, snapshot)
            except RuntimeError as exc:
                self.send_json(500, {"error": str(exc)})
            return
        if path == "/api/catalog/export":
            try:
                snapshot = core.exportable_catalog(core.load_catalog())
                self.send_download(
                    json.dumps(snapshot, ensure_ascii=True, indent=2).encode("utf-8"),
                    "application/json; charset=utf-8",
                    "poly-llm-hub-catalog.json",
                )
            except (OSError, RuntimeError, ValueError):
                self.send_json(500, {"error": "The catalog backup could not be created."})
            return
        if path == "/api/status":
            self.send_json(200, {"cli_detection": installed_clis(), "cli_note": "Detected, not connected. Coding-agent CLIs are not launched."})
            return
        if path == "/api/history":
            try:
                catalog = core.load_catalog()
                records, ignored_tail = core.read_history_report()
                self.send_json(200, {
                    "enabled": catalog.get("history_enabled", False),
                    "count": len(records),
                    "ignored_incomplete_tail": ignored_tail,
                })
            except (OSError, ValueError, RuntimeError):
                self.send_json(500, {"error": "Local history could not be read."})
            return
        if path == "/api/history/summary":
            try:
                records, ignored_tail = core.read_history_report()
                self.send_json(200, {
                    "models": core.summarize_history(records),
                    "benchmarks": core.summarize_benchmarks(records),
                    "trends": core.summarize_history_trends(records),
                    "model_trends": core.summarize_model_history_trends(records),
                    "category_trends": core.summarize_category_history_trends(records),
                    "ignored_incomplete_tail": ignored_tail,
                })
            except (OSError, ValueError, RuntimeError):
                self.send_json(500, {"error": "Local history summary could not be read."})
            return
        if path == "/api/history/export":
            try:
                query = parse_qs(urlsplit(self.path).query)
                export_format = query.get("format", ["jsonl"])[0].lower()
                if export_format not in ("jsonl", "csv"):
                    self.send_json(400, {"error": "Choose jsonl or csv export."})
                    return
                records = core.read_history()
                fields = ["record_id", "run_id", "run_kind", "timestamp", "prompt_set_id", "prompt_set_name",
                          "prompt_id", "category", "prompt_text", "connection_id", "connection_name",
                          "protocol", "destination", "model_entry_id", "model_id", "model_name", "parameters",
                          "latency_ms", "time_to_first_token_ms", "input_tokens", "output_tokens", "finish_status", "error",
                          "response_text", "cost", "user_rating", "rating_updated_at", "is_preferred", "has_preference", "preference_updated_at"]
                safe_rows = [{field: row.get(field) for field in fields} for row in records]
                if export_format == "jsonl":
                    content = "".join(json.dumps(row, ensure_ascii=True) + "\n" for row in safe_rows).encode("utf-8")
                    self.send_download(content, "application/x-ndjson; charset=utf-8", "poly-llm-hub-history.jsonl")
                else:
                    output = io.StringIO(newline="")
                    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
                    writer.writeheader()
                    for row in safe_rows:
                        sanitized = {}
                        for key, value in row.items():
                            if isinstance(value, (dict, list)):
                                sanitized[key] = json.dumps(value, ensure_ascii=True)
                            elif isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
                                sanitized[key] = "'" + value
                            elif isinstance(value, str) and value.startswith(("\t", "\r", "\n")):
                                sanitized[key] = "'" + value
                            else:
                                sanitized[key] = value
                        writer.writerow(sanitized)
                    self.send_download(output.getvalue().encode("utf-8", errors="backslashreplace"), "text/csv; charset=utf-8", "poly-llm-hub-history.csv")
            except (OSError, ValueError, RuntimeError):
                self.send_json(500, {"error": "Local history could not be exported."})
            return
        if path.startswith("/api/runs/"):
            run_id = unquote(path.removeprefix("/api/runs/"))
            with RUN_LOCK:
                _prune_runs()
                run = RUNS.get(run_id)
                snapshot = _public_run(run) if run else None
            if snapshot is None:
                self.send_json(404, {"error": "Comparison run not found or expired."})
            else:
                self.send_json(200, snapshot)
            return
        if path in ("/", "/index.html"):
            self.send_file(WEB_ROOT / "index.html")
            return
        self.send_json(404, {"error": "Not found."})

    def do_POST(self) -> None:
        if not self._guard(require_origin=True):
            return
        path = urlsplit(self.path).path
        try:
            data = self.body_json(max_bytes=2_100_000 if path == "/api/catalog/import" or path == "/api/prompt-sets" or path.startswith("/api/prompt-sets/") else 150_000)
            if path == "/api/catalog/import":
                with core.CATALOG_LOCK:
                    catalog = core.load_catalog()
                    summary = core.merge_catalog_import(catalog, data)
                    core.save_catalog(catalog)
                self.send_json(200, summary)
                return
            if path == "/api/prompt-sets":
                catalog = core.load_catalog()
                prompt_set = core.normalize_prompt_set(data)
                if any(row.get("id") == prompt_set["id"] for row in catalog["prompt_sets"]):
                    raise ValueError("That prompt set ID is already in use.")
                catalog["prompt_sets"].append(prompt_set)
                core.save_catalog(catalog)
                self.send_json(201, {"prompt_set": prompt_set})
                return
            if path == "/api/history/settings":
                enabled = data.get("enabled")
                if not isinstance(enabled, bool):
                    raise ValueError("History setting must be true or false.")
                with core.HISTORY_LOCK:
                    catalog = core.load_catalog()
                    catalog["history_enabled"] = enabled
                    core.save_catalog(catalog)
                self.send_json(200, {"enabled": enabled})
                return
            if path == "/api/connections":
                catalog = core.load_catalog()
                connection = core.normalize_connection(data)
                if core.connection_by_id(catalog, connection["id"]):
                    raise ValueError("That connection ID is already in use.")
                catalog["connections"].append(connection)
                core.save_catalog(catalog)
                self.send_json(201, {"connection": connection})
                return
            if path.startswith("/api/connections/") and path.endswith("/credential/open"):
                ident = unquote(path[len("/api/connections/"):-len("/credential/open")].strip("/"))
                catalog = core.load_catalog()
                connection = core.connection_by_id(catalog, ident)
                if not connection:
                    self.send_json(404, {"error": "Connection not found."})
                    return
                try:
                    open_credential_dialog(ident, connection["name"])
                except SecretStoreUnavailable as exc:
                    self.send_json(501, {"error": str(exc)})
                    return
                except (ValueError, RuntimeError) as exc:
                    self.send_json(400, {"error": str(exc)})
                    return
                except OSError:
                    self.send_json(500, {"error": "The secure key-entry window could not be opened."})
                    return
                self.send_json(202, {"ok": True, "dialog_open": ident in active_credential_dialogs()})
                return
            if path.startswith("/api/connections/") and path.endswith("/test"):
                ident = unquote(path[len("/api/connections/"):-len("/test")].strip("/"))
                catalog = core.load_catalog()
                connection = core.connection_by_id(catalog, ident)
                if not connection:
                    self.send_json(404, {"error": "Connection not found."})
                    return
                models = _discover_and_record(ident, connection)
                self.send_json(200, {"ok": True, "model_count": len(models)})
                return
            if path.startswith("/api/connections/") and path.endswith("/discover"):
                ident = unquote(path[len("/api/connections/"):-len("/discover")].strip("/"))
                catalog = core.load_catalog()
                connection = core.connection_by_id(catalog, ident)
                if not connection:
                    self.send_json(404, {"error": "Connection not found."})
                    return
                discovered = _discover_and_record(ident, connection, include_metadata=True)
                self.send_json(200, {
                    "models": [item["model_id"] for item in discovered],
                    "model_metadata": discovered,
                    "connection_id": ident,
                })
                return
            if path == "/api/models":
                catalog = core.load_catalog()
                model = core.normalize_model(data)
                if core.model_by_id(catalog, model["id"]):
                    raise ValueError("That model entry ID is already in use.")
                if not core.connection_by_id(catalog, model["connection_id"]):
                    raise ValueError("Choose an existing provider connection.")
                catalog["models"].append(model)
                core.save_catalog(catalog)
                self.send_json(201, {"model": model})
                return
            if path.startswith("/api/runs/") and path.endswith("/retry"):
                run_id = unquote(path[len("/api/runs/"):-len("/retry")].strip("/"))
                try:
                    retry_id = _retry_failed_model(run_id, data.get("model_entry_id"))
                except KeyError:
                    self.send_json(404, {"error": "Comparison run not found or expired."})
                    return
                self.send_json(202, {"run_id": retry_id})
                return
            if path == "/api/runs":
                chat_mode = data.get("chat", False)
                if not isinstance(chat_mode, bool):
                    raise ValueError("Chat mode must be enabled or disabled.")
                messages = _normalize_chat_messages(data.get("messages")) if chat_mode else None
                if not chat_mode and "messages" in data:
                    raise ValueError("Conversation messages are accepted only for a single-model chat run.")
                benchmark_data = data.get("benchmark")
                benchmark = None
                catalog = core.load_catalog()
                if benchmark_data is not None:
                    if chat_mode:
                        raise ValueError("A chat turn cannot also be a saved benchmark prompt.")
                    if not isinstance(benchmark_data, dict):
                        raise ValueError("Benchmark metadata must be an object.")
                    set_id = benchmark_data.get("prompt_set_id")
                    prompt_id = benchmark_data.get("prompt_id")
                    prompt_set = next((row for row in catalog["prompt_sets"] if row.get("id") == set_id), None)
                    prompt_row = next((row for row in prompt_set.get("prompts", []) if row.get("id") == prompt_id), None) if prompt_set else None
                    if not prompt_row:
                        raise ValueError("The selected saved prompt was not found. Refresh the prompt-set list.")
                    prompt = prompt_row["text"]
                    benchmark = {"prompt_set_id": prompt_set["id"], "prompt_set_name": prompt_set["name"],
                                 "prompt_id": prompt_row["id"], "category": prompt_row["category"]}
                else:
                    prompt = data.get("prompt", "")
                    if chat_mode and messages:
                        if prompt != messages[-1]["content"]:
                            raise ValueError("The prompt must match the latest user chat message.")
                        prompt = messages[-1]["content"]
                model_ids = data.get("model_entry_ids", [])
                if not isinstance(prompt, str) or not prompt.strip():
                    raise ValueError("Enter a prompt first.")
                if len(prompt) > MAX_PROMPT_CHARS:
                    raise ValueError(f"Prompts must be {MAX_PROMPT_CHARS:,} characters or fewer.")
                if not isinstance(model_ids, list) or not 1 <= len(model_ids) <= MAX_MODELS_PER_RUN:
                    raise ValueError(f"Select between 1 and {MAX_MODELS_PER_RUN} models.")
                if chat_mode and len(model_ids) != 1:
                    raise ValueError("Choose exactly one model for a chat turn.")
                if any(not isinstance(item, str) for item in model_ids) or len(set(model_ids)) != len(model_ids):
                    raise ValueError("Choose each catalog model once.")
                selections = []
                for ident in model_ids:
                    model = core.model_by_id(catalog, ident)
                    if not model:
                        raise ValueError("A selected model is no longer in the catalog. Refresh and try again.")
                    connection = core.connection_by_id(catalog, model["connection_id"])
                    if not connection:
                        raise ValueError("A selected model has no provider connection.")
                    selections.append((connection, model))
                parameters = _normalize_run_parameters(data.get("parameters", {}))
                requested_output_limit = parameters.get("max_output_tokens")
                if requested_output_limit is not None:
                    for _connection, model in selections:
                        known_limit = model.get("output_limit")
                        if isinstance(known_limit, int) and requested_output_limit > known_limit:
                            raise ValueError("Maximum output tokens exceeds the catalog output limit for " + model["name"] + ".")
                run_id = _start_run(
                    prompt, selections, benchmark, catalog.get("history_enabled", False), parameters,
                    messages=messages, run_kind="chat" if chat_mode else "comparison",
                )
                self.send_json(202, {"run_id": run_id})
                return
            if path.endswith("/preferred") and path.startswith("/api/runs/"):
                run_id = unquote(path[len("/api/runs/"):-len("/preferred")].strip("/"))
                model_entry_id = data.get("model_entry_id")
                if model_entry_id is not None and not isinstance(model_entry_id, str):
                    raise ValueError("Choose a completed response to mark as preferred.")
                with RUN_LOCK:
                    run = RUNS.get(run_id)
                    if not run:
                        self.send_json(404, {"error": "Comparison run not found or expired."})
                        return
                    if model_entry_id is not None:
                        row = next((item for item in run["models"] if item["model_entry_id"] == model_entry_id), None)
                        if not row or row["status"] != "complete":
                            raise ValueError("Choose a completed response to mark as preferred.")
                    preferred_saved = False
                    if run.get("history_enabled"):
                        with core.HISTORY_LOCK:
                            catalog = core.load_catalog()
                            if catalog.get("history_enabled"):
                                if not any(record.get("run_id") == run_id for record in core.read_history()):
                                    raise ValueError("This comparison was cleared from local history. Run a new comparison to save a preferred choice.")
                                core.append_history({
                                    "record_type": "preference",
                                    "event_id": uuid.uuid4().hex,
                                    "target_run_id": run_id,
                                    "preferred_model_entry_id": model_entry_id,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                })
                                preferred_saved = True
                    run["preferred_model_entry_id"] = model_entry_id
                    run["preferred_saved"] = preferred_saved
                    snapshot = _public_run(run)
                self.send_json(200, snapshot)
                return
            if path.endswith("/rating") and path.startswith("/api/runs/"):
                run_id = unquote(path[len("/api/runs/"):-len("/rating")].strip("/"))
                model_entry_id = data.get("model_entry_id")
                rating = data.get("rating")
                if not isinstance(model_entry_id, str):
                    raise ValueError("Choose a model result to rate.")
                if "rating" not in data:
                    raise ValueError("Choose a quality rating from 1 to 5.")
                if rating is not None and (
                    not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5
                ):
                    raise ValueError("A quality rating must be a whole number from 1 to 5, or empty to clear it.")
                with RUN_LOCK:
                    run = RUNS.get(run_id)
                    if not run:
                        self.send_json(404, {"error": "Comparison run not found or expired."})
                        return
                    row = next((item for item in run["models"] if item["model_entry_id"] == model_entry_id), None)
                    result = row.get("result") if row else None
                    if not row or row.get("status") != "complete" or not result or not result.get("ok"):
                        raise ValueError("Choose a completed response to rate.")
                    history_record_id = result.get("history_record_id")
                    if not history_record_id:
                        raise ValueError("Enable local history before starting a comparison to save a rating.")
                    with core.HISTORY_LOCK:
                        catalog = core.load_catalog()
                        if not catalog.get("history_enabled"):
                            raise ValueError("Enable local history to save ratings.")
                        if not any(
                            record.get("record_id") == history_record_id
                            for record in core.read_history()
                        ):
                            raise ValueError("This saved result was cleared from local history. Run a new comparison to rate it.")
                        core.append_history({
                            "record_type": "rating",
                            "event_id": uuid.uuid4().hex,
                            "target_record_id": history_record_id,
                            "rating": rating,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                    result["user_rating"] = rating
                    snapshot = _public_run(run)
                self.send_json(200, snapshot)
                return
            self.send_json(404, {"error": "Not found."})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            if isinstance(exc, HTTPError):
                message = "Provider returned HTTP " + str(exc.code) + "."
            elif isinstance(exc, URLError):
                message = "Could not reach the configured connection."
            elif isinstance(exc, TimeoutError):
                message = "The configured connection timed out."
            else:
                message = str(exc)
            self.send_json(502, {"error": message})
        except Exception:
            self.send_json(500, {"error": "The request failed unexpectedly."})

    def do_PUT(self) -> None:
        if not self._guard(require_origin=True):
            return
        path = urlsplit(self.path).path
        try:
            data = self.body_json(max_bytes=2_100_000 if path == "/api/prompt-sets" or path.startswith("/api/prompt-sets/") else 150_000)
            if path.startswith("/api/prompt-sets/"):
                ident = unquote(path.removeprefix("/api/prompt-sets/"))
                catalog = core.load_catalog()
                old = next((row for row in catalog["prompt_sets"] if row.get("id") == ident), None)
                if not old:
                    self.send_json(404, {"error": "Prompt set not found."})
                    return
                prompt_set = core.normalize_prompt_set(data, existing_id=ident)
                for row in catalog["prompt_sets"]:
                    if row["id"] == ident:
                        row.update(prompt_set)
                core.save_catalog(catalog)
                self.send_json(200, {"prompt_set": prompt_set})
                return
            if path.startswith("/api/connections/"):
                ident = unquote(path.removeprefix("/api/connections/"))
                catalog = core.load_catalog()
                old = core.connection_by_id(catalog, ident)
                if not old:
                    self.send_json(404, {"error": "Connection not found."})
                    return
                connection = core.normalize_connection(data, existing_id=ident)
                if ident == "ollama" and connection["protocol"] != "ollama_chat":
                    raise ValueError("The built-in Ollama connection must keep the Ollama protocol.")
                for row in catalog["connections"]:
                    if row["id"] == ident:
                        if all(connection.get(key) == old.get(key) for key in ("base_url", "protocol")):
                            for field in ("last_successful_discovery", "last_connection_check"):
                                if field in old:
                                    connection[field] = old[field]
                        row.update(connection)
                core.save_catalog(catalog)
                self.send_json(200, {"connection": connection})
                return
            if path.startswith("/api/models/"):
                ident = unquote(path.removeprefix("/api/models/"))
                catalog = core.load_catalog()
                old = core.model_by_id(catalog, ident)
                if not old:
                    self.send_json(404, {"error": "Model entry not found."})
                    return
                model = core.normalize_model(data, existing_id=ident)
                if not core.connection_by_id(catalog, model["connection_id"]):
                    raise ValueError("Choose an existing provider connection.")
                for row in catalog["models"]:
                    if row["id"] == ident:
                        row.update(model)
                core.save_catalog(catalog)
                self.send_json(200, {"model": model})
                return
            self.send_json(404, {"error": "Not found."})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except RuntimeError as exc:
            self.send_json(500, {"error": str(exc)})
        except Exception:
            self.send_json(500, {"error": "The request failed unexpectedly."})

    def do_DELETE(self) -> None:
        if not self._guard(require_origin=True):
            return
        path = urlsplit(self.path).path
        if path == "/api/history":
            try:
                with core.HISTORY_LOCK:
                    catalog = core.load_catalog()
                    catalog["history_enabled"] = False
                    core.save_catalog(catalog)
                    core.clear_history()
                self.send_json(200, {"ok": True})
            except (OSError, RuntimeError):
                self.send_json(500, {"error": "Local history could not be cleared."})
            return
        if path.startswith("/api/runs/"):
            run_id = unquote(path.removeprefix("/api/runs/"))
            if not _cancel_run(run_id):
                self.send_json(404, {"error": "Comparison run not found or expired."})
            else:
                with RUN_LOCK:
                    snapshot = _public_run(RUNS[run_id])
                self.send_json(200, snapshot)
            return
        if path.startswith("/api/connections/") and path.endswith("/credential"):
            ident = unquote(path[len("/api/connections/"):-len("/credential")].strip("/"))
            try:
                catalog = core.load_catalog()
                if not core.connection_by_id(catalog, ident):
                    self.send_json(404, {"error": "Connection not found."})
                    return
                removed = delete_secret(ident)
            except SecretStoreUnavailable as exc:
                self.send_json(501, {"error": str(exc)})
                return
            except OSError:
                self.send_json(500, {"error": "The secure credential store could not remove this key."})
                return
            self.send_json(200, {"ok": True, "removed": removed})
            return
        try:
            catalog = core.load_catalog()
            if path.startswith("/api/prompt-sets/"):
                ident = unquote(path.removeprefix("/api/prompt-sets/"))
                before = len(catalog["prompt_sets"])
                catalog["prompt_sets"] = [row for row in catalog["prompt_sets"] if row.get("id") != ident]
                if len(catalog["prompt_sets"]) == before:
                    self.send_json(404, {"error": "Prompt set not found."})
                    return
                core.save_catalog(catalog)
                self.send_json(200, {"ok": True})
                return
            if path.startswith("/api/connections/"):
                ident = unquote(path.removeprefix("/api/connections/"))
                if ident in ("openai", "anthropic", "gemini", "xai", "deepseek", "ollama"):
                    self.send_json(400, {"error": "Built-in connections cannot be removed. You can edit them."})
                    return
                if not core.connection_by_id(catalog, ident):
                    self.send_json(404, {"error": "Connection not found."})
                    return
                if any(row.get("connection_id") == ident for row in catalog["models"]):
                    self.send_json(409, {"error": "Remove or reassign this connection's models first."})
                    return
                saved_key = None
                try:
                    saved_key = read_secret(ident)
                    delete_secret(ident)
                except SecretStoreUnavailable:
                    pass
                except OSError:
                    self.send_json(500, {"error": "The saved key could not be removed. The connection was kept."})
                    return
                before = len(catalog["connections"])
                catalog["connections"] = [row for row in catalog["connections"] if row["id"] != ident]
                if len(catalog["connections"]) == before:
                    self.send_json(404, {"error": "Connection not found."})
                    return
                try:
                    core.save_catalog(catalog)
                except (OSError, RuntimeError):
                    if saved_key:
                        try:
                            save_secret(ident, saved_key)
                        except (OSError, RuntimeError, ValueError):
                            self.send_json(500, {"error": "The connection could not be removed, and its key could not be restored. Check the secure credential store."})
                            return
                    self.send_json(500, {"error": "The connection could not be removed. Its saved key was restored if present."})
                    return
                self.send_json(200, {"ok": True})
                return
            if path.startswith("/api/models/"):
                ident = unquote(path.removeprefix("/api/models/"))
                before = len(catalog["models"])
                catalog["models"] = [row for row in catalog["models"] if row["id"] != ident]
                if len(catalog["models"]) == before:
                    self.send_json(404, {"error": "Model entry not found."})
                    return
                core.save_catalog(catalog)
                self.send_json(200, {"ok": True})
                return
            self.send_json(404, {"error": "Not found."})
        except RuntimeError as exc:
            self.send_json(500, {"error": str(exc)})

def _maintenance(stop_event: threading.Event) -> None:
    while not stop_event.wait(60):
        with RUN_LOCK:
            _prune_runs()


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Poly-LLM Hub is ready at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop. The server accepts local connections only.")
    stop_event = threading.Event()
    threading.Thread(target=_maintenance, args=(stop_event,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Poly-LLM Hub.")
    finally:
        stop_event.set()
        server.server_close()
        with _CREDENTIAL_DIALOG_LOCK:
            for process in _CREDENTIAL_DIALOGS.values():
                if process.poll() is None:
                    try:
                        process.terminate()
                    except OSError:
                        pass


if __name__ == "__main__":
    main()
