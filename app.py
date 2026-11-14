from __future__ import annotations

import copy
import csv
import io
import json
import os
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
)


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
HOST = "127.0.0.1"
PORT = 8765
ALLOWED_ORIGIN = f"http://{HOST}:{PORT}"
MAX_PROMPT_CHARS = 20_000
MAX_MODELS_PER_RUN = 5
MAX_ACTIVE_RUNS = 3
MAX_PARALLEL_MODELS = 3
RUN_TTL_SECONDS = 30 * 60
CLI_NAMES = {"codex": "codex", "claude": "claude", "gemini": "gemini", "antigravity": "agy", "ollama": "ollama"}
RUNS: dict[str, dict[str, Any]] = {}
RUN_LOCK = threading.RLock()
_CREDENTIAL_DIALOG_LOCK = threading.Lock()
_CREDENTIAL_DIALOGS: dict[str, subprocess.Popen[Any]] = {}


def installed_clis() -> dict[str, bool]:
    return {name: shutil.which(command) is not None for name, command in CLI_NAMES.items()}


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
        raise SecretStoreUnavailable("Native secure key entry is currently supported on Windows only.")
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
    for run_id in list(RUNS):
        if RUNS[run_id]["created_at"] < cutoff:
            del RUNS[run_id]
    if len(RUNS) > 100:
        oldest_first = sorted(RUNS.items(), key=lambda item: item[1].get("created_at", 0))
        for run_id, run_data in oldest_first[:-50]:
            if run_data.get("status") in ("completed", "failed", "cancelled"):
                del RUNS[run_id]


def _public_run(run: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in run.items() if key not in ("prompt", "cancel_event", "created_at")}


def _future_finished(run_id: str, future: Any) -> None:
    with RUN_LOCK:
        run = RUNS.get(run_id)
        if run:
            run["pending_calls"] = max(0, run.get("pending_calls", 0) - 1)


def _persist_result(run_id: str, prompt: str, connection: dict[str, Any], model: dict[str, Any],
                    result: dict[str, Any], benchmark: dict[str, Any] | None) -> bool:
    try:
        usage = result.get("usage") or {}
        record = {
            "record_id": uuid.uuid4().hex,
            "run_id": run_id,
            "run_kind": "benchmark" if benchmark else "comparison",
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
            "parameters": {},
            "latency_ms": result.get("latency_ms"),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "finish_status": "success" if result.get("ok") else "error",
            "error": result.get("error"),
            "response_text": result.get("text"),
            "cost": core.estimate_cost(model, usage, connection["destination"]) if result.get("ok") else None,
        }
        with core.HISTORY_LOCK:
            catalog = core.load_catalog()
            if not catalog.get("history_enabled"):
                return False
            core.append_history(record)
        return True
    except Exception:
        return False

def _run_worker(run_id: str, prompt: str, selections: list[tuple[dict[str, Any], dict[str, Any]]]) -> None:
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
                    result = {"ok": False, "error": "The request failed unexpectedly.", "latency_ms": 0}
                with RUN_LOCK:
                    run = RUNS.get(run_id)
                    if not run or run["cancel_event"].is_set():
                        continue
                    row = next((item for item in run["models"] if item["model_entry_id"] == model["id"]), None)
                    if row is None:
                        continue
                    row["status"] = "complete" if result.get("ok") else "failed"
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
                if should_save:
                    saved = _persist_result(run_id, prompt, connection, model, result, benchmark)
                    with RUN_LOCK:
                        current = RUNS.get(run_id)
                        row = next((item for item in current["models"] if item["model_entry_id"] == model["id"]), None) if current else None
                        if row and row.get("result"):
                            row["result"]["history_saved"] = saved
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
                run.pop("prompt", None)
    except Exception:
        pool.shutdown(wait=False, cancel_futures=True)
        with RUN_LOCK:
            run = RUNS.get(run_id)
            if run and not run["cancel_event"].is_set():
                run["status"] = "failed"
                run.pop("prompt", None)


def _start_run(prompt: str, selections: list[tuple[dict[str, Any], dict[str, Any]]], benchmark: dict[str, Any] | None = None, history_enabled: bool = False) -> str:
    run_id = uuid.uuid4().hex
    event = threading.Event()
    models = []
    for connection, model in selections:
        models.append({
            "model_entry_id": model["id"],
            "model_id": model["model_id"],
            "model_name": model["name"],
            "connection_name": connection["name"],
            "destination": connection["destination"],
            "status": "queued",
        })
    with RUN_LOCK:
        _prune_runs()
        active = sum(1 for item in RUNS.values() if item["status"] in ("queued", "running") or item.get("pending_calls", 0) > 0)
        if active >= MAX_ACTIVE_RUNS:
            raise ValueError("The app is already handling the maximum number of comparisons. Wait for one to finish.")
        RUNS[run_id] = {
            "id": run_id, "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
            "models": models, "preferred_model_entry_id": None, "cancel_event": event,
            "created_at": time.time(), "prompt": prompt, "pending_calls": 0, "benchmark": benchmark, "history_enabled": history_enabled,
        }
    threading.Thread(target=_run_worker, args=(run_id, prompt, selections), daemon=True).start()
    return run_id


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
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")

    def origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin == ALLOWED_ORIGIN

    def send_json(self, status: int, value: Any) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
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

    def _guard(self) -> bool:
        expected_host = f"{HOST}:{self.server.server_port}".lower()
        host = (self.headers.get("Host") or "").lower()
        if host != expected_host or not self.origin_allowed():
            self.send_json(403, {"error": "Local request not allowed."})
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
                self.send_json(200, snapshot)
            except RuntimeError as exc:
                self.send_json(500, {"error": str(exc)})
            return
        if path == "/api/status":
            self.send_json(200, {"cli_detection": installed_clis(), "cli_note": "Detected, not connected. Coding-agent CLIs are not launched."})
            return
        if path == "/api/history":
            try:
                catalog = core.load_catalog()
                records = core.read_history()
                self.send_json(200, {"enabled": catalog.get("history_enabled", False), "count": len(records)})
            except (OSError, ValueError, RuntimeError):
                self.send_json(500, {"error": "Local history could not be read."})
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
                          "latency_ms", "input_tokens", "output_tokens", "finish_status", "error",
                          "response_text", "cost"]
                safe_rows = [{field: row.get(field) for field in fields} for row in records]
                if export_format == "jsonl":
                    content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in safe_rows).encode("utf-8")
                    self.send_download(content, "application/x-ndjson; charset=utf-8", "poly-llm-hub-history.jsonl")
                else:
                    output = io.StringIO(newline="")
                    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
                    writer.writeheader()
                    for row in safe_rows:
                        sanitized = {}
                        for key, value in row.items():
                            if isinstance(value, (dict, list)):
                                sanitized[key] = json.dumps(value, ensure_ascii=False)
                            elif isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
                                sanitized[key] = "'" + value
                            elif isinstance(value, str) and value.startswith(("\t", "\r", "\n")):
                                sanitized[key] = "'" + value
                            else:
                                sanitized[key] = value
                        writer.writerow(sanitized)
                    self.send_download(output.getvalue().encode("utf-8"), "text/csv; charset=utf-8", "poly-llm-hub-history.csv")
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
        if not self._guard():
            return
        path = urlsplit(self.path).path
        try:
            data = self.body_json(max_bytes=2_100_000 if path == "/api/prompt-sets" or path.startswith("/api/prompt-sets/") else 150_000)
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
                models = core.discover_models(connection)
                connection["last_successful_discovery"] = datetime.now(timezone.utc).isoformat()
                core.save_catalog(catalog)
                self.send_json(200, {"ok": True, "model_count": len(models)})
                return
            if path.startswith("/api/connections/") and path.endswith("/discover"):
                ident = unquote(path[len("/api/connections/"):-len("/discover")].strip("/"))
                catalog = core.load_catalog()
                connection = core.connection_by_id(catalog, ident)
                if not connection:
                    self.send_json(404, {"error": "Connection not found."})
                    return
                models = core.discover_models(connection)
                connection["last_successful_discovery"] = datetime.now(timezone.utc).isoformat()
                core.save_catalog(catalog)
                self.send_json(200, {"models": models, "connection_id": ident})
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
            if path == "/api/runs":
                benchmark_data = data.get("benchmark")
                benchmark = None
                catalog = core.load_catalog()
                if benchmark_data is not None:
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
                model_ids = data.get("model_entry_ids", [])
                if not isinstance(prompt, str) or not prompt.strip():
                    raise ValueError("Enter a prompt first.")
                if len(prompt) > MAX_PROMPT_CHARS:
                    raise ValueError(f"Prompts must be {MAX_PROMPT_CHARS:,} characters or fewer.")
                if not isinstance(model_ids, list) or not 1 <= len(model_ids) <= MAX_MODELS_PER_RUN:
                    raise ValueError(f"Select between 1 and {MAX_MODELS_PER_RUN} models.")
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
                run_id = _start_run(prompt, selections, benchmark, catalog.get("history_enabled", False))
                self.send_json(202, {"run_id": run_id})
                return
            if path.endswith("/preferred") and path.startswith("/api/runs/"):
                run_id = unquote(path[len("/api/runs/"):-len("/preferred")].strip("/"))
                model_entry_id = data.get("model_entry_id")
                with RUN_LOCK:
                    run = RUNS.get(run_id)
                    if not run:
                        self.send_json(404, {"error": "Comparison run not found or expired."})
                        return
                    if model_entry_id is not None:
                        row = next((item for item in run["models"] if item["model_entry_id"] == model_entry_id), None)
                        if not row or row["status"] != "complete":
                            raise ValueError("Choose a completed response to mark as preferred.")
                    run["preferred_model_entry_id"] = model_entry_id
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
        if not self._guard():
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
                        connection["last_successful_discovery"] = old.get("last_successful_discovery")
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
        if not self._guard():
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
                self.send_json(500, {"error": "Windows Credential Manager could not remove this key."})
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
                            self.send_json(500, {"error": "The connection could not be removed, and its key could not be restored. Check Windows Credential Manager."})
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
