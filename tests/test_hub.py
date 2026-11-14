import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app
import hub_core as core


class LocalProviderMock(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, fmt, *args):
        return

    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/models":
            self._send(200, {"data": [{"id": "mock-model"}]})
        elif self.path == "/api/tags":
            self._send(200, {"models": [{"name": "mock-local:latest"}]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).requests.append((self.path, body, dict(self.headers)))
        if self.path.endswith("/chat/completions"):
            self._send(200, {"choices": [{"message": {"content": "mock answer"}}],
                             "usage": {"prompt_tokens": 12, "completion_tokens": 4}})
        elif self.path.endswith("/messages"):
            self._send(200, {"content": [{"type": "text", "text": "mock answer"}],
                             "usage": {"input_tokens": 12, "output_tokens": 4}})
        elif self.path.endswith(":generateContent"):
            self._send(200, {"candidates": [{"content": {"parts": [{"text": "mock answer"}]}}],
                             "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 4}})
        elif self.path.endswith("/api/chat"):
            self._send(200, {"message": {"content": "mock answer"},
                             "prompt_eval_count": 12, "eval_count": 4})
        else:
            self._send(404, {"error": "not found"})


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        LocalProviderMock.requests = []
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), LocalProviderMock)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_all_response_parsers(self):
        self.assertEqual(core.extract_openai({"choices": [{"message": {"content": "A"}}], "usage": {"prompt_tokens": 2, "completion_tokens": 3}}), ("A", {"input_tokens": 2, "output_tokens": 3}))
        self.assertEqual(core.extract_anthropic({"content": [{"type": "text", "text": "B"}], "usage": {"input_tokens": 4, "output_tokens": 5}}), ("B", {"input_tokens": 4, "output_tokens": 5}))
        self.assertEqual(core.extract_gemini({"candidates": [{"content": {"parts": [{"text": "C"}]}}], "usageMetadata": {"promptTokenCount": 6, "candidatesTokenCount": 7}}), ("C", {"input_tokens": 6, "output_tokens": 7}))
        self.assertEqual(core.extract_ollama({"message": {"content": "D"}, "prompt_eval_count": 8, "eval_count": 9}), ("D", {"input_tokens": 8, "output_tokens": 9}))

    def test_all_protocol_adapters_use_local_mock_server(self):
        cases = [
            ("openai_compatible", "/v1", "mock-model"),
            ("anthropic_messages", "/v1", "mock-model"),
            ("gemini_generate", "/v1beta", "mock-model"),
            ("ollama_chat", "", "mock-local:latest"),
        ]
        for protocol, prefix, model_id in cases:
            with self.subTest(protocol=protocol):
                connection = {"id": "mock", "name": "Local mock", "protocol": protocol,
                              "base_url": self.base + prefix, "auth_env": "", "destination": "local"}
                model = {"id": "m", "model_id": model_id, "name": model_id, "pricing": None}
                result = core.call_model(connection, model, "hello mock")
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["text"], "mock answer")
                self.assertEqual(result["usage"]["input_tokens"], 12)

    def test_discovery_and_unavailable_discovery(self):
        connection = {"id": "mock", "protocol": "openai_compatible", "base_url": self.base, "auth_env": ""}
        self.assertEqual(core.discover_models(connection), ["mock-model"])
        ollama = {"id": "ollama", "protocol": "ollama_chat", "base_url": self.base, "auth_env": ""}
        self.assertEqual(core.discover_models(ollama), ["mock-local:latest"])
        with mock.patch.object(core, "request_json", side_effect=URLError("offline")):
            with self.assertRaises(URLError):
                core.discover_models(connection)

    def test_manual_model_normalization_and_invalid_discovery_shape(self):
        model = core.normalize_model({"id": "m1", "connection_id": "c1", "model_id": "vendor/exact-id", "name": "Friendly"})
        self.assertEqual(model["model_id"], "vendor/exact-id")
        self.assertIsNone(model["capabilities"]["vision"])
        with mock.patch.object(core, "request_json", return_value={"unexpected": []}):
            with self.assertRaisesRegex(RuntimeError, "Add the exact model ID manually"):
                core.discover_models({"protocol": "openai_compatible", "base_url": "https://example.test", "auth_env": ""})

    def test_endpoint_validation(self):
        self.assertEqual(core.validate_base_url("https://example.com/v1/"), "https://example.com/v1")
        self.assertEqual(core.validate_base_url("http://127.0.0.1:11434"), "http://127.0.0.1:11434")
        self.assertEqual(core.validate_base_url("http://localhost:9000"), "http://localhost:9000")
        remote_ollama = core.normalize_connection({"id": "remote-ollama", "name": "Remote Ollama", "protocol": "ollama_chat", "base_url": "https://models.example.test"})
        self.assertEqual(remote_ollama["destination"], "remote")
        for url in ("http://example.com", "http://192.168.1.5:8000", "https://user:pass@example.com", "https://example.com/?key=x", "file:///tmp/x"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                core.validate_base_url(url)

    def test_missing_credentials_and_safe_http_errors(self):
        connection = {"protocol": "openai_compatible", "base_url": self.base, "auth_env": "POLY_HUB_TEST_KEY_UNSET"}
        model = {"model_id": "m", "pricing": None}
        with mock.patch.dict(os.environ, {}, clear=True):
            result = core.call_model(connection, model, "hello")
        self.assertFalse(result["ok"])
        self.assertIn("POLY_HUB_TEST_KEY_UNSET", result["error"])
        for code, expected in ((401, "Authentication failed"), (429, "Rate limit")):
            error = HTTPError(self.base, code, "provider error", {}, None)
            with mock.patch.object(core, "request_json", side_effect=error):
                result = core.call_model({**connection, "auth_env": ""}, model, "hello")
            self.assertIn(expected, result["error"])
            self.assertNotIn("provider error", result["error"])
        with mock.patch.object(core, "request_json", side_effect=TimeoutError()):
            self.assertEqual(core.call_model({**connection, "auth_env": ""}, model, "x")["error"], "Request timed out.")
        with mock.patch.object(core, "request_json", side_effect=RuntimeError("The provider returned invalid JSON.")):
            self.assertEqual(core.call_model({**connection, "auth_env": ""}, model, "x")["error"], "The provider returned invalid JSON.")

    def test_cost_estimates_and_unknowns(self):
        model = {"pricing": {"input_per_million": 2, "output_per_million": 8, "source_url": "https://provider.test/pricing", "checked_on": "2026-11-14"}}
        cost = core.estimate_cost(model, {"input_tokens": 1000, "output_tokens": 500}, "cloud")
        self.assertEqual(cost["status"], "estimated")
        self.assertAlmostEqual(cost["amount_usd"], .006)
        self.assertEqual(core.estimate_cost(model, {"input_tokens": None, "output_tokens": 4}, "cloud")["status"], "unknown")
        self.assertEqual(core.estimate_cost({}, {"input_tokens": 1, "output_tokens": 2}, "cloud")["label"], "Cost unknown")
        self.assertEqual(core.estimate_cost(model, {"input_tokens": 2, "output_tokens": 1}, "local")["status"], "not_estimated_local")

    def test_anthropic_custom_output_limit(self):
        connection = {"id": "anth", "protocol": "anthropic_messages", "base_url": self.base + "/v1", "auth_env": ""}
        model = {"id": "m", "model_id": "claude-test", "output_limit": 4096}
        result = core.call_model(connection, model, "prompt")
        self.assertTrue(result["ok"])
        last_req = LocalProviderMock.requests[-1]
        self.assertEqual(last_req[1]["max_tokens"], 4096)


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_catalog_path, self.old_data_root, self.old_history_path = core.CATALOG_PATH, core.DATA_ROOT, core.HISTORY_PATH
        self.old_origin = app.ALLOWED_ORIGIN
        core.DATA_ROOT = Path(self.temp.name)
        core.CATALOG_PATH = Path(self.temp.name) / "catalog.json"
        core.HISTORY_PATH = Path(self.temp.name) / "history.jsonl"
        with app.RUN_LOCK:
            app.RUNS.clear()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        app.ALLOWED_ORIGIN = "http://127.0.0.1:" + str(self.server.server_port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        core.CATALOG_PATH, core.DATA_ROOT, core.HISTORY_PATH = self.old_catalog_path, self.old_data_root, self.old_history_path
        app.ALLOWED_ORIGIN = self.old_origin
        with app.RUN_LOCK:
            app.RUNS.clear()
        self.temp.cleanup()

    def request(self, path, method="GET", body=None, origin=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if origin is not None:
            headers["Origin"] = origin
        request = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            response = urlopen(request, timeout=2)
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())
        return response.status, json.loads(response.read())

    def seed_model(self):
        catalog = core.default_catalog()
        catalog["models"].append(core.normalize_model({
            "id": "m-test", "connection_id": "openai", "model_id": "mock-model", "name": "Mock model",
        }))
        core.save_catalog(catalog)

    def test_origin_checks_and_catalog_initialization(self):
        status, data = self.request("/api/catalog", origin=app.ALLOWED_ORIGIN)
        self.assertEqual(status, 200)
        self.assertEqual(len(data["connections"]), 6)
        self.assertEqual(data["models"], [])
        status, data = self.request("/api/catalog", origin="http://evil.example")
        self.assertEqual(status, 403)
        self.assertEqual(data["error"], "Origin not allowed.")

    def test_connection_model_crud_and_durable_nonsecret_catalog(self):
        status, _ = self.request("/api/connections", "POST", {
            "id": "test-custom", "name": "Mock endpoint", "protocol": "openai_compatible",
            "base_url": "http://127.0.0.1:9999/v1", "auth_env": "MOCK_ONLY_KEY",
        })
        self.assertEqual(status, 201)
        status, _ = self.request("/api/models", "POST", {
            "id": "manual-test", "connection_id": "test-custom", "model_id": "exact-user-id", "name": "Manual",
        })
        self.assertEqual(status, 201)
        stored = core.CATALOG_PATH.read_text(encoding="utf-8")
        self.assertIn("MOCK_ONLY_KEY", stored)
        self.assertNotIn("mock-secret-value", stored)
        status, _ = self.request("/api/connections/test-custom", "DELETE")
        self.assertEqual(status, 409)
        status, _ = self.request("/api/models/manual-test", "DELETE")
        self.assertEqual(status, 200)
        status, _ = self.request("/api/connections/test-custom", "DELETE")
        self.assertEqual(status, 200)

    def test_duplicate_and_over_limit_selections_rejected(self):
        self.seed_model()
        for ids in (["m-test", "m-test"], ["m-test"] * 6):
            status, data = self.request("/api/runs", "POST", {"prompt": "hello", "model_entry_ids": ids})
            self.assertEqual(status, 400)
            self.assertIn("error", data)

    def test_comparison_preference_adds_no_provider_call(self):
        self.seed_model()
        calls = []
        def fake_call(connection, model, prompt):
            calls.append((model["id"], prompt))
            return {"ok": True, "text": "mock response", "usage": {"input_tokens": 1, "output_tokens": 2}, "latency_ms": 3}
        with mock.patch.object(core, "call_model", side_effect=fake_call):
            status, data = self.request("/api/runs", "POST", {"prompt": "temporary prompt", "model_entry_ids": ["m-test"]})
            self.assertEqual(status, 202)
            run_id = data["run_id"]
            deadline = time.time() + 3
            while time.time() < deadline:
                status, run = self.request("/api/runs/" + run_id)
                if run["status"] == "completed":
                    break
                time.sleep(.03)
            self.assertEqual(run["status"], "completed")
            self.assertNotIn("prompt", run)
            status, preferred = self.request("/api/runs/" + run_id + "/preferred", "POST", {"model_entry_id": "m-test"})
            self.assertEqual(status, 200)
            self.assertEqual(preferred["preferred_model_entry_id"], "m-test")
            self.assertEqual(len(calls), 1)

    def test_cancel_during_slow_mock_keeps_cancelled_status(self):
        self.seed_model()
        started, release = threading.Event(), threading.Event()
        def slow_call(connection, model, prompt):
            started.set()
            release.wait(2)
            return {"ok": True, "text": "late answer", "usage": {}, "latency_ms": 1}
        with mock.patch.object(core, "call_model", side_effect=slow_call):
            status, data = self.request("/api/runs", "POST", {"prompt": "hello", "model_entry_ids": ["m-test"]})
            self.assertEqual(status, 202)
            run_id = data["run_id"]
            self.assertTrue(started.wait(1))
            status, run = self.request("/api/runs/" + run_id, "DELETE")
            self.assertEqual(status, 200)
            self.assertEqual(run["status"], "cancelled")
            release.set()
            time.sleep(.1)
            status, run = self.request("/api/runs/" + run_id)
            self.assertEqual(run["status"], "cancelled")
            self.assertNotIn("result", run["models"][0])

    def test_prework_cancellation_and_localstorage_privacy(self):
        event = threading.Event()
        with app.RUN_LOCK:
            app.RUNS["queued-test"] = {"id": "queued-test", "status": "queued", "created_at": time.time(),
                "models": [{"model_entry_id": "m", "status": "queued"}], "cancel_event": event}
        self.assertTrue(app._cancel_run("queued-test"))
        self.assertEqual(app.RUNS["queued-test"]["models"][0]["status"], "cancelled")
        html = (Path(app.ROOT) / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('localStorage.setItem("poly-llm-hub:selected-model-ids",JSON.stringify([...selected]))', html)
        self.assertNotIn("localStorage.setItem(\"prompt\"", html)
        self.assertNotIn("localStorage.setItem(\"responses\"", html)


    def test_prompt_set_crud_and_benchmark_uses_saved_prompt(self):
        self.seed_model()
        payload = {"id": "starter", "name": "Starter examples", "description": "Original tasks",
                   "prompts": [{"id": "p-one", "category": "translation", "text": "Translate hello into French."}]}
        status, data = self.request("/api/prompt-sets", "POST", payload)
        self.assertEqual(status, 201)
        self.assertEqual(data["prompt_set"]["prompts"][0]["category"], "translation")
        status, updated = self.request("/api/prompt-sets/starter", "PUT", {
            "name": "Edited examples", "prompts": [{"id": "p-one", "category": "translation", "text": "Translate goodbye into French."}],
        })
        self.assertEqual(status, 200)
        self.assertEqual(updated["prompt_set"]["name"], "Edited examples")
        status, _ = self.request("/api/prompt-sets/starter", "DELETE")
        self.assertEqual(status, 200)
        self.request("/api/prompt-sets", "POST", payload)
        calls = []
        def fake_call(connection, model, prompt):
            calls.append(prompt)
            return {"ok": True, "text": "bonjour", "usage": {"input_tokens": 3, "output_tokens": 1}, "latency_ms": 2}
        with mock.patch.object(core, "call_model", side_effect=fake_call):
            status, data = self.request("/api/runs", "POST", {
                "benchmark": {"prompt_set_id": "starter", "prompt_id": "p-one"},
                "model_entry_ids": ["m-test"],
            })
            self.assertEqual(status, 202)
            deadline = time.time() + 3
            while time.time() < deadline:
                _, run = self.request("/api/runs/" + data["run_id"])
                if run["status"] == "completed":
                    break
                time.sleep(.03)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(calls, ["Translate hello into French."])
        self.assertFalse(core.HISTORY_PATH.exists())

    def test_opt_in_history_and_credential_free_jsonl_csv_export(self):
        self.seed_model()
        status, data = self.request("/api/history")
        self.assertEqual(status, 200)
        self.assertFalse(data["enabled"])
        self.assertEqual(data["count"], 0)
        status, _ = self.request("/api/history/settings", "POST", {"enabled": True})
        self.assertEqual(status, 200)
        def fake_call(connection, model, prompt):
            return {"ok": True, "text": "stored mock response", "usage": {"input_tokens": 2, "output_tokens": 3}, "latency_ms": 4}
        with mock.patch.object(core, "call_model", side_effect=fake_call):
            status, data = self.request("/api/runs", "POST", {"prompt": "explicitly opt-in prompt", "model_entry_ids": ["m-test"]})
            self.assertEqual(status, 202)
            deadline = time.time() + 3
            while time.time() < deadline:
                _, run = self.request("/api/runs/" + data["run_id"])
                if run["status"] == "completed":
                    break
                time.sleep(.03)
        self.assertEqual(run["status"], "completed")
        records = core.read_history()
        self.assertEqual(len(records), 1)
        self.assertTrue(run["models"][0]["result"]["history_saved"])
        self.assertEqual(records[0]["prompt_text"], "explicitly opt-in prompt")
        self.assertEqual(records[0]["response_text"], "stored mock response")
        self.assertNotIn("auth_env", records[0])
        self.assertNotIn("credential", json.dumps(records[0]).lower())
        response = urlopen(self.base + "/api/history/export?format=jsonl", timeout=2)
        exported = response.read().decode("utf-8")
        self.assertIn("stored mock response", exported)
        self.assertNotIn("auth_env", exported)
        response = urlopen(self.base + "/api/history/export?format=csv", timeout=2)
        exported_csv = response.read().decode("utf-8")
        self.assertIn("prompt_text", exported_csv.splitlines()[0])
        self.assertIn("stored mock response", exported_csv)
        self.assertNotIn("auth_env", exported_csv)
        status, _ = self.request("/api/history", "DELETE")
        self.assertEqual(status, 200)
        self.assertFalse(core.HISTORY_PATH.exists())
        _, after_clear = self.request("/api/history")
        self.assertFalse(after_clear["enabled"])

    def test_history_stays_off_unless_explicitly_enabled(self):
        self.seed_model()
        with mock.patch.object(core, "call_model", return_value={"ok": True, "text": "ephemeral", "usage": {}, "latency_ms": 1}):
            status, data = self.request("/api/runs", "POST", {"prompt": "do not persist me", "model_entry_ids": ["m-test"]})
            self.assertEqual(status, 202)
            deadline = time.time() + 3
            while time.time() < deadline:
                _, run = self.request("/api/runs/" + data["run_id"])
                if run["status"] == "completed":
                    break
                time.sleep(.03)
        self.assertEqual(run["status"], "completed")
        self.assertFalse(core.HISTORY_PATH.exists())

    def test_turning_history_off_during_run_prevents_write(self):
        self.seed_model()
        self.request("/api/history/settings", "POST", {"enabled": True})
        started, release = threading.Event(), threading.Event()
        def slow_call(connection, model, prompt):
            started.set()
            release.wait(2)
            return {"ok": True, "text": "should stay ephemeral", "usage": {}, "latency_ms": 2}
        with mock.patch.object(core, "call_model", side_effect=slow_call):
            status, data = self.request("/api/runs", "POST", {"prompt": "private until opt-in persists", "model_entry_ids": ["m-test"]})
            self.assertEqual(status, 202)
            self.assertTrue(started.wait(1))
            self.request("/api/history/settings", "POST", {"enabled": False})
            release.set()
            deadline = time.time() + 3
            while time.time() < deadline:
                _, run = self.request("/api/runs/" + data["run_id"])
                if run["status"] == "completed":
                    break
                time.sleep(.03)
        self.assertEqual(run["status"], "completed")
        self.assertFalse(core.HISTORY_PATH.exists())

    def test_export_format_validation(self):
        status, data = self.request("/api/history/export?format=xml")
        self.assertEqual(status, 400)
        self.assertIn("jsonl or csv", data["error"])

    def test_csv_formula_injection_sanitization(self):
        self.seed_model()
        self.request("/api/history/settings", "POST", {"enabled": True})
        def fake_call(connection, model, prompt):
            return {"ok": True, "text": "=1+1 dangerous formula", "usage": {"input_tokens": 1, "output_tokens": 1}, "latency_ms": 1}
        with mock.patch.object(core, "call_model", side_effect=fake_call):
            status, data = self.request("/api/runs", "POST", {"prompt": "-cmd|' /C calc'!A0", "model_entry_ids": ["m-test"]})
            self.assertEqual(status, 202)
            deadline = time.time() + 3
            while time.time() < deadline:
                _, run = self.request("/api/runs/" + data["run_id"])
                if run["status"] == "completed":
                    break
                time.sleep(.03)
        response = urlopen(self.base + "/api/history/export?format=csv", timeout=2)
        exported_csv = response.read().decode("utf-8")
        self.assertIn("'-cmd|' /C calc'!A0", exported_csv)
        self.assertIn("'=1+1 dangerous formula", exported_csv)

    def test_runs_memory_pruning_cap(self):
        with app.RUN_LOCK:
            app.RUNS.clear()
            for i in range(120):
                app.RUNS[f"run-{i}"] = {
                    "id": f"run-{i}",
                    "status": "completed",
                    "created_at": time.time() - (120 - i),
                    "models": [],
                }
            app._prune_runs()
            self.assertLessEqual(len(app.RUNS), 70)


if __name__ == "__main__":
    unittest.main()