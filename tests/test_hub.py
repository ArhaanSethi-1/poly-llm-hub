import base64
import csv
import ctypes
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app
import hub_core as core
import history_crypto
import secret_store as store
from scripts.build_source_archive import _validate_source_content, build_archive_bytes


class SecretStoreTests(unittest.TestCase):
    def test_windows_credential_manager_adapter_round_trip(self):
        class FakeWindowsApi:
            def __init__(self):
                self.blob = b""
                self.target = None
                self.credential = None
                self.buffer = None
                self.freed = False

            def CredWriteW(self, credential_pointer, _flags):
                credential = ctypes.cast(credential_pointer, ctypes.POINTER(store._Credential)).contents
                self.target = credential.TargetName
                self.blob = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
                return 1

            def CredReadW(self, target, _type, _flags, output_pointer):
                if target != self.target:
                    return 0
                self.credential = store._Credential()
                self.buffer = (ctypes.c_ubyte * len(self.blob)).from_buffer_copy(self.blob)
                self.credential.CredentialBlobSize = len(self.blob)
                self.credential.CredentialBlob = ctypes.cast(self.buffer, ctypes.POINTER(ctypes.c_ubyte))
                pointer = ctypes.pointer(self.credential)
                ctypes.cast(output_pointer, ctypes.POINTER(ctypes.POINTER(store._Credential)))[0] = pointer
                return 1

            def CredDeleteW(self, target, _type, _flags):
                return int(target == self.target)

            def CredFree(self, _pointer):
                self.freed = True

        api = FakeWindowsApi()
        connection_id, secret = "windows-connection", "win-secret-🔑"
        with mock.patch.object(store, "sys", SimpleNamespace(platform="win32")), \
                mock.patch.object(store, "_windows_api", return_value=api):
            store.save_secret(connection_id, secret)
            self.assertEqual(api.target, store._target(connection_id))
            self.assertNotIn(connection_id, api.target)
            self.assertEqual(store.read_secret(connection_id), secret)
            self.assertTrue(api.freed)
            self.assertTrue(store.delete_secret(connection_id))

    def test_linux_secret_tool_keeps_key_out_of_process_arguments(self):
        connection_id, secret = "linux-connection", "linux-secret-value"
        calls = []

        def fake_run(arguments, **options):
            calls.append((arguments, options))
            output = secret + "\n" if "lookup" in arguments else ""
            return SimpleNamespace(returncode=0, stdout=output, stderr="")

        with mock.patch.object(store, "sys", SimpleNamespace(platform="linux")), \
                mock.patch.object(store.shutil, "which", return_value="/usr/bin/secret-tool"), \
                mock.patch.object(store.subprocess, "run", side_effect=fake_run):
            store.save_secret(connection_id, secret)
            self.assertEqual(store.read_secret(connection_id), secret)
            self.assertTrue(store.delete_secret(connection_id))

        save_arguments, save_options = calls[0]
        self.assertEqual(save_options["input"], secret)
        for arguments, _options in calls:
            self.assertNotIn(secret, arguments)
            self.assertIn(store._target(connection_id), arguments)

    def test_macos_keychain_sends_secret_via_interactive_stdin(self):
        connection_id, secret = "mac-connection", "mac-secret-value"
        calls = []

        def fake_run(arguments, **options):
            calls.append((arguments, options))
            output = secret + "\n" if "find-generic-password" in arguments else ""
            return SimpleNamespace(returncode=0, stdout=output, stderr="")

        with mock.patch.object(store, "sys", SimpleNamespace(platform="darwin")), \
                mock.patch.object(store.os.path, "isfile", return_value=True), \
                mock.patch.object(store.subprocess, "run", side_effect=fake_run):
            store.save_secret(connection_id, secret)
            self.assertEqual(store.read_secret(connection_id), secret)
            self.assertTrue(store.delete_secret(connection_id))

        save_arguments, save_options = calls[0]
        self.assertEqual(save_arguments, [store.MACOS_SECURITY_PATH, "-i"])
        self.assertNotIn(secret, save_options["input"])
        self.assertIn(secret.encode("utf-8").hex(), save_options["input"])
        for arguments, options in calls:
            self.assertNotIn(secret, arguments)
            target = options["input"] if "-i" in arguments else " ".join(arguments)
            self.assertIn(store._target(connection_id), target)


class ReleaseArchiveTests(unittest.TestCase):
    def test_source_scanner_rejects_machine_paths_and_credential_signatures(self):
        separator = chr(92).encode("ascii")
        absolute_path = b"C:" + separator + b"Users" + separator + b"tester" + separator + b"catalog.json"
        with self.assertRaisesRegex(ValueError, "Machine-specific absolute path"):
            _validate_source_content("README.md", absolute_path)

        credential = b"sk-" + b"A" * 28
        with self.assertRaisesRegex(ValueError, "Credential-like material"):
            _validate_source_content("README.md", credential)

    def test_source_archive_is_deterministic_and_excludes_local_artifacts(self):
        first = build_archive_bytes(ROOT_DIR)
        second = build_archive_bytes(ROOT_DIR)
        self.assertEqual(first, second)
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            names = archive.namelist()
            self.assertIn("Poly-LLM-Hub-0.2.0/README.md", names)
            self.assertIn("Poly-LLM-Hub-0.2.0/app.py", names)
            self.assertIn("Poly-LLM-Hub-0.2.0/docs/SECURITY_REVIEW.md", names)
            self.assertFalse(any("PROJECT_LOG" in name or "local-client-inventory" in name for name in names))
            self.assertFalse(any(name.startswith(".git/") or "/.git/" in name for name in names))
            for name in names:
                self.assertFalse(name.endswith(("catalog.json", "history.jsonl", ".pyc", ".gguf", ".log")), name)


class HistoryCryptoTests(unittest.TestCase):
    def test_encryption_migration_round_trip_and_plaintext_export_data(self):
        if not history_crypto.encryption_available():
            self.skipTest("optional cryptography package is not installed")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.jsonl"
            records = [{"record_id": "a", "prompt": "private prompt", "response": "private answer"}, {"record_type": "rating", "rating": 5}]
            path.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
            vault = {}
            with mock.patch.object(history_crypto, "read_secret", side_effect=lambda ident: vault.get(ident)), \
                    mock.patch.object(history_crypto, "save_secret", side_effect=lambda ident, value: vault.__setitem__(ident, value)):
                self.assertEqual(history_crypto.migrate_file(path, True), 2)
                encrypted_text = path.read_text(encoding="utf-8")
                self.assertNotIn("private prompt", encrypted_text)
                envelopes = [json.loads(line) for line in encrypted_text.splitlines()]
                self.assertTrue(all(history_crypto.is_envelope(row) for row in envelopes))
                self.assertEqual([history_crypto.decrypt_record(row) for row in envelopes], records)
                self.assertEqual(history_crypto.migrate_file(path, False), 2)
                self.assertEqual([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()], records)

    def test_corrupt_encrypted_history_is_not_replaced_during_migration(self):
        if not history_crypto.encryption_available():
            self.skipTest("optional cryptography package is not installed")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.jsonl"
            original = '{"_poly_llm_history":"poly-llm-history-aesgcm-v1","nonce":"bad","ciphertext":"bad"}\n'
            path.write_text(original, encoding="utf-8")
            with mock.patch.object(history_crypto, "read_secret", return_value="00" * 32):
                with self.assertRaises(RuntimeError):
                    history_crypto.migrate_file(path, False)
            self.assertEqual(path.read_text(encoding="utf-8"), original)


class LocalProviderMock(BaseHTTPRequestHandler):
    requests = []
    redirect_target = ""

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
        if self.path == "/same-origin-redirect":
            self.send_response(302)
            self.send_header("Location", "/models")
            self.end_headers()
        elif self.path == "/cross-origin-redirect":
            self.send_response(302)
            self.send_header("Location", type(self).redirect_target)
            self.end_headers()
        elif self.path == "/models":
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


class RedirectTargetMock(BaseHTTPRequestHandler):
    requests = 0

    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        type(self).requests += 1
        body = json.dumps({"data": [{"id": "should-not-be-reached"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


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

    def test_persian_mizan_scores_are_not_seeded_as_general_ranking(self):
        models = core.seed_models(core.default_catalog())
        mizan_candidates = [row for row in models if row["id"] in ("seed-ollama-gemma3", "seed-ollama-qwen3")]
        self.assertEqual(len(mizan_candidates), 2)
        self.assertTrue(all(row["rank_score"] is None for row in mizan_candidates))
        self.assertTrue(all(row.get("benchmark_scores", []) == [] for row in mizan_candidates))

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

    def test_chat_context_maps_assistant_roles_for_all_protocols(self):
        messages = [
            {"role": "user", "content": "Keep the reply short."},
            {"role": "assistant", "content": "Understood."},
            {"role": "user", "content": "What did I ask you to do?"},
        ]
        cases = [
            ("openai_compatible", "/v1", "mock-model"),
            ("anthropic_messages", "/v1", "mock-model"),
            ("gemini_generate", "/v1beta", "mock-model"),
            ("ollama_chat", "", "mock-local:latest"),
        ]
        for protocol, prefix, model_id in cases:
            with self.subTest(protocol=protocol):
                LocalProviderMock.requests.clear()
                connection = {"id": "mock", "name": "Local mock", "protocol": protocol,
                              "base_url": self.base + prefix, "auth_env": "", "destination": "local"}
                model = {"id": "m", "model_id": model_id, "name": model_id, "pricing": None}
                result = core.call_model(connection, model, messages[-1]["content"], messages=messages)
                self.assertTrue(result["ok"], result)
                body = LocalProviderMock.requests[-1][1]
                if protocol == "gemini_generate":
                    self.assertEqual(body["contents"], [
                        {"role": "user", "parts": [{"text": "Keep the reply short."}]},
                        {"role": "model", "parts": [{"text": "Understood."}]},
                        {"role": "user", "parts": [{"text": "What did I ask you to do?"}]},
                    ])
                else:
                    self.assertEqual(body["messages"], messages)

    def test_discovery_and_unavailable_discovery(self):
        connection = {"id": "mock", "protocol": "openai_compatible", "base_url": self.base, "auth_env": ""}
        self.assertEqual(core.discover_models(connection), ["mock-model"])
        ollama = {"id": "ollama", "protocol": "ollama_chat", "base_url": self.base, "auth_env": ""}
        self.assertEqual(core.discover_models(ollama), ["mock-local:latest"])
        with mock.patch.object(core, "request_json", side_effect=URLError("offline")):
            with self.assertRaises(URLError):
                core.discover_models(connection)

    def test_paginated_discovery_uses_provider_cursors(self):
        cases = [
            ({"id": "openai", "protocol": "openai_compatible", "base_url": "https://example.test", "auth_env": ""},
             [{"data": [{"id": "first"}], "has_more": True, "last_id": "first"},
              {"data": [{"id": "second"}], "has_more": False}], "after=first"),
            ({"id": "gemini", "protocol": "gemini_generate", "base_url": "https://example.test", "auth_env": ""},
             [{"models": [{"name": "models/first"}], "nextPageToken": "next-token"},
              {"models": [{"name": "models/second"}]}], "pageToken=next-token"),
        ]
        for connection, pages, expected_cursor in cases:
            with self.subTest(protocol=connection["protocol"]), mock.patch.object(core, "request_json", side_effect=pages) as request:
                self.assertEqual(core.discover_models(connection), ["first", "second"])
                self.assertIn(expected_cursor, request.call_args_list[1].args[0])

    def test_anthropic_discovery_paginates_and_maps_documented_metadata(self):
        connection = {
            "id": "anthropic", "protocol": "anthropic_messages",
            "base_url": "https://api.anthropic.example/v1", "auth_env": "",
        }
        pages = [
            {
                "data": [{
                    "id": "claude-sonnet-example",
                    "display_name": "Claude Sonnet Example",
                    "max_input_tokens": 200_000,
                    "max_tokens": 8_192,
                    "capabilities": {
                        "image_input": {"supported": True},
                        "thinking": {"supported": True},
                    },
                }],
                "has_more": True,
                "last_id": "claude-sonnet-example",
            },
            {"data": [{"id": "claude-haiku-example", "display_name": "Claude Haiku Example"}], "has_more": False},
        ]
        with mock.patch.object(core, "request_json", side_effect=pages) as request:
            details = core.discover_model_details(connection)

        self.assertEqual([item["model_id"] for item in details], ["claude-haiku-example", "claude-sonnet-example"])
        sonnet = next(item for item in details if item["model_id"] == "claude-sonnet-example")
        self.assertEqual(sonnet["name"], "Claude Sonnet Example")
        self.assertEqual(sonnet["context_limit"], 200_000)
        self.assertEqual(sonnet["output_limit"], 8_192)
        self.assertTrue(sonnet["capabilities"]["vision"])
        self.assertTrue(sonnet["capabilities"]["reasoning"])
        self.assertEqual(sonnet["metadata_source"], "Anthropic Models API")
        self.assertRegex(sonnet["metadata_checked_on"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(request.call_count, 2)
        self.assertIn("after_id=claude-sonnet-example", request.call_args_list[1].args[0])

    def test_json_provider_response_size_is_bounded(self):
        oversized = io.BytesIO(b"x" * (core.MAX_RESPONSE_BYTES + 1))
        with mock.patch.object(core, "_same_origin_opener") as opener:
            opener.return_value.open.return_value = oversized
            with self.assertRaisesRegex(RuntimeError, "2 MB limit"):
                core.request_json("https://provider.example.test/models")

    def test_sse_stream_byte_and_line_limits(self):
        oversized_line = io.BytesIO(b"data: " + b"x" * 65_537 + b"\n")
        with self.assertRaisesRegex(RuntimeError, "stream exceeded the response size limit"):
            list(core._sse_payloads(oversized_line))

        oversized_body = io.BytesIO((b"x" * 60_000 + b"\n") * 34)
        with self.assertRaisesRegex(RuntimeError, "stream exceeded the response size limit"):
            list(core._sse_payloads(oversized_body))

    def test_streamed_output_limit_stops_before_emitting_overflow(self):
        payload = json.dumps({"choices": [{"delta": {"content": "x" * (core.MAX_RESPONSE_BYTES + 1)}}]})
        emitted = []
        with mock.patch.object(core, "_sse_payloads", return_value=iter([payload])):
            with self.assertRaisesRegex(RuntimeError, "Provider response exceeded the 2 MB limit"):
                core._read_stream(io.BytesIO(), "openai_compatible", emitted.append, time.perf_counter())
        self.assertEqual(emitted, [])

    def test_ollama_stream_line_limit(self):
        oversized_line = io.BytesIO(b'{"message":{"content":"' + b"x" * 65_520 + b'"}}\n')
        with self.assertRaisesRegex(RuntimeError, "stream exceeded the response size limit"):
            core._read_stream(oversized_line, "ollama_chat", None, time.perf_counter())

    def test_provider_redirect_must_stay_on_same_origin(self):
        same_origin = core.request_json(self.base + "/same-origin-redirect")
        self.assertEqual(same_origin["data"][0]["id"], "mock-model")

        RedirectTargetMock.requests = 0
        target_server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectTargetMock)
        target_thread = threading.Thread(target=target_server.serve_forever, daemon=True)
        target_thread.start()
        LocalProviderMock.redirect_target = "http://127.0.0.1:" + str(target_server.server_port) + "/models"
        try:
            with self.assertRaises(HTTPError) as raised:
                core.request_json(self.base + "/cross-origin-redirect", headers={"Authorization": "Bearer test"})
            self.assertEqual(raised.exception.code, 302)
            self.assertEqual(RedirectTargetMock.requests, 0)
        finally:
            LocalProviderMock.redirect_target = ""
            target_server.shutdown()
            target_server.server_close()
            target_thread.join(timeout=2)

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
        direct = core.normalize_connection({
            "id": "anthropic", "name": "Anthropic", "protocol": "anthropic_messages",
            "base_url": "https://api.anthropic.com/v1", "request_mode": "direct",
        })
        self.assertEqual(direct["request_mode"], "direct")
        with self.assertRaises(ValueError):
            core.normalize_connection({
                "id": "openai", "name": "OpenAI", "protocol": "openai_compatible",
                "base_url": "https://api.openai.com/v1", "request_mode": "direct",
            })
        with self.assertRaises(ValueError):
            core.normalize_connection({
                "id": "anthropic", "name": "Anthropic", "protocol": "anthropic_messages",
                "base_url": "https://attacker.example/v1", "request_mode": "direct",
            })

    def test_rate_limit_backoff_retries_only_compare_429(self):
        class ImmediateWait:
            def __init__(self): self.delays = []
            def wait(self, delay): self.delays.append(delay); return False
        connection, model = {"id": "openai"}, {"id": "m"}
        throttled = {"ok": False, "http_status": 429, "retry_after_seconds": 0}
        success = {"ok": True, "text": "done"}
        event = ImmediateWait()
        with mock.patch.object(core, "call_model", side_effect=[throttled, success]) as call:
            result = app._call_model_with_rate_limit_backoff(connection, model, "p", {}, event, "comparison")
        self.assertTrue(result["ok"])
        self.assertEqual(result["rate_limit_retries"], 1)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(event.delays, [0.0])
        event = ImmediateWait()
        with mock.patch.object(core, "call_model", return_value=throttled) as call:
            result = app._call_model_with_rate_limit_backoff(connection, model, "p", {}, event, "chat")
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["rate_limit_retries"], 0)
        event = ImmediateWait()
        with mock.patch.object(core, "call_model", return_value={"ok": False, "http_status": 503}) as call:
            result = app._call_model_with_rate_limit_backoff(connection, model, "p", {}, event, "comparison")
        self.assertEqual(call.call_count, 1)
        self.assertEqual(event.delays, [])
        self.assertEqual(result["rate_limit_retries"], 0)

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
        rate_limited = HTTPError(self.base, 429, "provider error", {"Retry-After": "4"}, None)
        with mock.patch.object(core, "request_json", side_effect=rate_limited):
            result = core.call_model({**connection, "auth_env": ""}, model, "hello")
        self.assertEqual(result["http_status"], 429)
        self.assertEqual(result["retry_after_seconds"], 4)
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

    def request(self, path, method="GET", body=None, origin=None, omit_origin=False):
        data = json.dumps(body).encode() if body is not None else None
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if origin is not None:
            headers["Origin"] = origin
        elif method in {"POST", "PUT", "DELETE"} and not omit_origin:
            headers["Origin"] = app.ALLOWED_ORIGIN
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

    def test_html_csp_allows_only_the_hashed_inline_script(self):
        response = urlopen(self.base + "/", timeout=2)
        self.assertEqual(response.status, 200)
        html = response.read().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        scripts = re.findall(rb"<script\b[^>]*>(.*?)</script\s*>", html, flags=re.IGNORECASE | re.DOTALL)
        self.assertEqual(len(scripts), 1)
        script_hash = base64.b64encode(hashlib.sha256(scripts[0]).digest()).decode("ascii")
        self.assertEqual(script_hash, app.INLINE_SCRIPT_HASH)
        policy = response.headers.get("Content-Security-Policy", "")
        self.assertIn("script-src 'sha256-" + script_hash + "'", policy)
        self.assertNotIn("script-src 'unsafe-inline'", policy)
        self.assertIn("object-src 'none'", policy)
        self.assertIn("base-uri 'none'", policy)
        self.assertIn("form-action 'self'", policy)
        self.assertIn("frame-ancestors 'none'", policy)

    def test_catalog_and_downloads_expose_credential_status_without_key(self):
        catalog = core.default_catalog()
        core.save_catalog(catalog)
        sentinel = "NEVER-RETURN-THIS-TEST-KEY"
        with mock.patch.object(core, "read_secret", return_value=sentinel), \
                mock.patch.object(core, "store_name", return_value="Mock credential vault"), \
                mock.patch.dict(os.environ, {"OPENAI_API_KEY": sentinel}):
            status, data = self.request("/api/catalog")
            self.assertEqual(status, 200)
            openai = next(row for row in data["connections"] if row["id"] == "openai")
            self.assertTrue(openai["credential_set"])
            self.assertTrue(openai["credential_saved"])
            self.assertEqual(openai["credential_source"], "Mock credential vault")
            self.assertNotIn(sentinel, json.dumps(data))

            catalog_response = urlopen(self.base + "/api/catalog/export", timeout=2)
            self.assertNotIn(sentinel, catalog_response.read().decode("utf-8"))
            history_jsonl = urlopen(self.base + "/api/history/export?format=jsonl", timeout=2)
            self.assertNotIn(sentinel, history_jsonl.read().decode("utf-8"))
            history_csv = urlopen(self.base + "/api/history/export?format=csv", timeout=2)
            self.assertNotIn(sentinel, history_csv.read().decode("utf-8"))

    def test_origin_checks_and_catalog_initialization(self):
        status, data = self.request("/api/catalog", origin=app.ALLOWED_ORIGIN)
        self.assertEqual(status, 200)
        self.assertEqual(len(data["connections"]), 6)
        self.assertEqual(len(data["models"]), 15)
        self.assertTrue(all(row["catalog_source"] == "seed" for row in data["models"]))
        status, data = self.request("/api/catalog", origin="http://evil.example")
        self.assertEqual(status, 403)
        self.assertEqual(data["error"], "Origin not allowed.")

    def test_bundled_price_refresh_is_manual_and_direct_calls_stay_out_of_run_api(self):
        status, data = self.request("/api/prices/refresh", "POST", {})
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data["updated"], 1)
        self.assertEqual(len(core.load_catalog()["models"]), 15)
        catalog = core.load_catalog()
        customized = catalog["models"][0]
        customized["pricing"] = {
            "input_per_million": 9, "output_per_million": 12,
            "source_url": "https://custom.example/prices", "checked_on": "2026-11-24",
        }
        core.save_catalog(catalog)
        status, data = self.request("/api/prices/refresh", "POST", {})
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data["skipped_custom"], 1)
        self.assertEqual(core.model_by_id(core.load_catalog(), customized["id"])["pricing"]["source_url"], "https://custom.example/prices")

        catalog = core.load_catalog()
        connection = core.connection_by_id(catalog, "anthropic")
        connection["request_mode"] = "direct"
        direct_model = core.normalize_model({
            "id": "anthropic-direct-test", "connection_id": "anthropic", "model_id": "claude-test", "name": "Direct test",
        })
        catalog["models"].append(direct_model)
        core.save_catalog(catalog)
        status, result = self.request("/api/runs", "POST", {
            "prompt": "hello", "model_entry_ids": [direct_model["id"]], "parameters": {"stream": False},
        })
        self.assertEqual(status, 400)
        self.assertIn("Direct Connection", result["error"])

    def test_cancel_closes_tracked_upstream_response(self):
        class TrackedResponse:
            closed = False
            def close(self): self.closed = True
        response = TrackedResponse()
        event = threading.Event()
        with app.RUN_LOCK:
            app.RUNS["upstream-cancel"] = {
                "id": "upstream-cancel", "status": "running", "created_at": time.time(),
                "models": [{"model_entry_id": "m", "status": "running"}], "cancel_event": event,
            }
        app._register_upstream_response("upstream-cancel", "m", event, response)
        self.assertTrue(app._cancel_run("upstream-cancel"))
        self.assertTrue(response.closed)

    def test_seed_catalog_does_not_return_after_user_clears_it(self):
        catalog = core.load_catalog()
        self.assertEqual(len(catalog["models"]), 15)
        catalog["models"].clear()
        core.save_catalog(catalog)
        self.assertEqual(core.load_catalog()["models"], [])

    def test_discovery_merges_models_without_replacing_seed_catalog(self):
        self.request("/api/catalog")
        with mock.patch.object(core, "discover_model_details", return_value=[{
            "model_id": "provider-extra", "name": "Provider extra", "metadata_source": "test endpoint",
        }]):
            status, result = self.request("/api/connections/openai/discover", "POST", {})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["added_count"], 1)
        catalog = core.load_catalog()
        self.assertEqual(len(catalog["models"]), 16)
        discovered = next(row for row in catalog["models"] if row["model_id"] == "provider-extra")
        self.assertEqual(discovered["catalog_source"], "discovered")
        status, data = self.request("/api/history/settings", "POST", {"enabled": True}, omit_origin=True)
        self.assertEqual(status, 403)
        self.assertEqual(data["error"], "Origin not allowed.")

    def test_chat_turn_uses_one_model_and_passes_only_bounded_messages(self):
        self.seed_model()
        messages = [
            {"role": "user", "content": "Remember this detail."},
            {"role": "assistant", "content": "I will."},
            {"role": "user", "content": "Continue from here."},
        ]
        result = {"ok": True, "text": "Continuing.", "usage": {}, "parameters": {"stream": False},
                  "latency_ms": 2, "time_to_first_token_ms": None}
        with mock.patch.object(core, "call_model", return_value=result) as call_model:
            status, data = self.request("/api/runs", "POST", {
                "chat": True, "prompt": messages[-1]["content"], "messages": messages,
                "model_entry_ids": ["m-test"], "parameters": {"stream": False},
            })
            self.assertEqual(status, 202, data)
            deadline = time.time() + 2
            run = None
            while time.time() < deadline:
                status, run = self.request("/api/runs/" + data["run_id"])
                if run["status"] in ("completed", "failed", "cancelled"):
                    break
                time.sleep(0.01)
            self.assertEqual(run["status"], "completed")
            self.assertEqual(run["run_kind"], "chat")
            self.assertEqual(run["models"][0]["status"], "complete")
            call_model.assert_called_once()
            self.assertEqual(call_model.call_args.kwargs["messages"], messages)

        status, data = self.request("/api/runs", "POST", {
            "chat": True, "prompt": "Continue from here.", "messages": messages,
            "model_entry_ids": ["m-test", "another-model"], "parameters": {"stream": False},
        })
        self.assertEqual(status, 400)
        self.assertIn("exactly one model", data["error"])

        status, data = self.request("/api/runs", "POST", {
            "chat": True, "prompt": "A prompt", "messages": [{"role": "system", "content": "not allowed"}],
            "model_entry_ids": ["m-test"], "parameters": {"stream": False},
        })
        self.assertEqual(status, 400)
        self.assertIn("user or assistant", data["error"])

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
        def fake_call(connection, model, prompt, parameters=None, on_delta=None, messages=None, on_response=None):
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

    def test_active_comparison_limit_accounts_for_pending_runs(self):
        self.seed_model()
        release = threading.Event()
        def blocked_call(connection, model, prompt, parameters=None, on_delta=None, messages=None, on_response=None):
            release.wait(5)
            return {"ok": True, "text": "complete", "usage": {}, "latency_ms": 1}
        run_ids = []
        with mock.patch.object(core, "call_model", side_effect=blocked_call):
            try:
                for _ in range(app.MAX_ACTIVE_RUNS):
                    status, data = self.request("/api/runs", "POST", {"prompt": "hello", "model_entry_ids": ["m-test"]})
                    self.assertEqual(status, 202)
                    run_ids.append(data["run_id"])
                status, data = self.request("/api/runs", "POST", {"prompt": "too many", "model_entry_ids": ["m-test"]})
                self.assertEqual(status, 400)
                self.assertIn("maximum number of comparisons", data["error"])
            finally:
                release.set()
            deadline = time.time() + 3
            for run_id in run_ids:
                while time.time() < deadline:
                    _, run = self.request("/api/runs/" + run_id)
                    if run["status"] == "completed":
                        break
                    time.sleep(.03)
                self.assertEqual(run["status"], "completed")

    def test_per_run_model_parallelism_is_capped(self):
        self.seed_model()
        catalog = core.load_catalog()
        model_ids = ["m-test"]
        for index in range(2, app.MAX_MODELS_PER_RUN + 1):
            model_id = "m-test-" + str(index)
            catalog["models"].append(core.normalize_model({
                "id": model_id, "connection_id": "openai", "model_id": "mock-model-" + str(index),
                "name": "Mock model " + str(index),
            }))
            model_ids.append(model_id)
        core.save_catalog(catalog)

        lock = threading.Lock()
        release = threading.Event()
        three_started = threading.Event()
        active = 0
        peak = 0
        call_count = 0

        def concurrent_call(connection, model, prompt, parameters=None, on_delta=None, messages=None, on_response=None):
            nonlocal active, peak, call_count
            with lock:
                active += 1
                call_count += 1
                peak = max(peak, active)
                if active == app.MAX_PARALLEL_MODELS:
                    three_started.set()
            try:
                release.wait(3)
                return {"ok": True, "text": model["model_id"], "usage": {}, "latency_ms": 1}
            finally:
                with lock:
                    active -= 1

        with mock.patch.object(core, "call_model", side_effect=concurrent_call):
            status, data = self.request("/api/runs", "POST", {"prompt": "hello", "model_entry_ids": model_ids})
            self.assertEqual(status, 202)
            run_id = data["run_id"]
            try:
                self.assertTrue(three_started.wait(2), "the run did not start the expected parallel calls")
                with lock:
                    self.assertEqual(active, app.MAX_PARALLEL_MODELS)
                    self.assertEqual(peak, app.MAX_PARALLEL_MODELS)
            finally:
                release.set()
            deadline = time.time() + 5
            while time.time() < deadline:
                _, run = self.request("/api/runs/" + run_id)
                if run["status"] == "completed":
                    break
                time.sleep(.03)
            self.assertEqual(run["status"], "completed")
            self.assertEqual(call_count, len(model_ids))
            self.assertEqual(peak, app.MAX_PARALLEL_MODELS)

    def test_cancel_during_slow_mock_keeps_cancelled_status(self):
        self.seed_model()
        started, release = threading.Event(), threading.Event()
        def slow_call(connection, model, prompt, parameters=None, on_delta=None, messages=None, on_response=None):
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

    def test_stream_callbacks_and_late_results_are_ignored_after_cancel(self):
        self.seed_model()
        catalog = core.load_catalog()
        catalog["models"].append(core.normalize_model({
            "id": "m-test-2", "connection_id": "openai", "model_id": "mock-model-2", "name": "Mock model 2",
        }))
        core.save_catalog(catalog)

        lock = threading.Lock()
        started = threading.Event()
        release = threading.Event()
        calls_started = 0

        def streaming_call(connection, model, prompt, parameters=None, on_delta=None, messages=None, on_response=None):
            nonlocal calls_started
            on_delta("partial-" + model["id"])
            with lock:
                calls_started += 1
                if calls_started == 2:
                    started.set()
            release.wait(5)
            on_delta("late-" + model["id"])
            return {"ok": True, "text": "late result", "usage": {}, "latency_ms": 1}

        with mock.patch.object(core, "call_model", side_effect=streaming_call):
            status, data = self.request("/api/runs", "POST", {
                "prompt": "hello", "model_entry_ids": ["m-test", "m-test-2"],
                "parameters": {"stream": True},
            })
            self.assertEqual(status, 202)
            run_id = data["run_id"]
            self.assertTrue(started.wait(2), "both streaming calls did not start")
            deadline = time.time() + 2
            while time.time() < deadline:
                _, running = self.request("/api/runs/" + run_id)
                if all("partial-" in (model.get("result", {}).get("text") or "") for model in running["models"]):
                    break
                time.sleep(.02)
            self.assertTrue(all("partial-" in (model.get("result", {}).get("text") or "") for model in running["models"]))
            try:
                status, cancelled = self.request("/api/runs/" + run_id, "DELETE")
                self.assertEqual(status, 200)
                self.assertEqual(cancelled["status"], "cancelled")
                self.assertTrue(all(model["status"] == "cancelled" for model in cancelled["models"]))
                self.assertTrue(all("result" not in model for model in cancelled["models"]))
            finally:
                release.set()

            deadline = time.time() + 3
            while time.time() < deadline:
                _, settled = self.request("/api/runs/" + run_id)
                if settled["pending_calls"] == 0:
                    break
                time.sleep(.02)
            self.assertEqual(settled["status"], "cancelled")
            self.assertEqual(settled["pending_calls"], 0)
            self.assertTrue(all(model["status"] == "cancelled" for model in settled["models"]))
            self.assertTrue(all("result" not in model for model in settled["models"]))

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
        def fake_call(connection, model, prompt, parameters=None, on_delta=None, messages=None, on_response=None):
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
        def fake_call(connection, model, prompt, parameters=None, on_delta=None, messages=None, on_response=None):
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

    def test_encrypted_history_is_stored_ciphertext_and_exports_readable_rows(self):
        if not history_crypto.encryption_available():
            self.skipTest("optional cryptography package is not installed")
        catalog = core.load_catalog()
        catalog["history_enabled"] = True
        core.save_catalog(catalog)
        core.append_history({"record_type": "run", "record_id": "encrypted-export", "prompt_text": "hidden in file", "models": []})
        vault = {}
        with mock.patch.object(history_crypto, "read_secret", side_effect=lambda ident: vault.get(ident)), \
                mock.patch.object(history_crypto, "save_secret", side_effect=lambda ident, value: vault.__setitem__(ident, value)):
            self.assertEqual(core.set_history_encryption(True), 1)
            raw = core.HISTORY_PATH.read_text(encoding="utf-8")
            self.assertNotIn("hidden in file", raw)
            response = urlopen(self.base + "/api/history/export?format=jsonl", timeout=2)
            exported = response.read().decode("utf-8")
            self.assertIn("hidden in file", exported)
            exported_row = json.loads(exported)
            self.assertEqual(exported_row["prompt_text"], "hidden in file")
            self.assertNotIn("record_type", exported_row)

    def test_anthropic_direct_connection_can_switch_to_local_proxy(self):
        catalog = core.load_catalog()
        connection = core.connection_by_id(catalog, "anthropic")
        connection["request_mode"] = "direct"
        core.save_catalog(catalog)
        status, result = self.request("/api/connections/anthropic", "PUT", {
            "id": "anthropic", "name": connection["name"], "protocol": connection["protocol"],
            "base_url": connection["base_url"], "auth_env": connection["auth_env"],
            "notes": connection["notes"], "request_mode": "local_proxy",
        })
        self.assertEqual(status, 200, result)
        self.assertEqual(result["connection"]["request_mode"], "local_proxy")
        self.assertEqual(core.connection_by_id(core.load_catalog(), "anthropic")["request_mode"], "local_proxy")

    def test_history_append_failure_keeps_response_and_shows_recovery(self):
        self.seed_model()
        self.request("/api/history/settings", "POST", {"enabled": True})
        response = {"ok": True, "text": "still available", "usage": {}, "latency_ms": 1}
        incomplete = "Local history ends with an incomplete record. Export the readable history, then clear history before saving more runs."
        with mock.patch.object(core, "call_model", return_value=response), \
                mock.patch.object(core, "append_history", side_effect=RuntimeError(incomplete)):
            status, data = self.request("/api/runs", "POST", {"prompt": "keep this result", "model_entry_ids": ["m-test"]})
            self.assertEqual(status, 202)
            deadline = time.time() + 3
            while time.time() < deadline:
                _, run = self.request("/api/runs/" + data["run_id"])
                if run["status"] == "completed":
                    break
                time.sleep(.03)
        result = run["models"][0]["result"]
        self.assertEqual(result["text"], "still available")
        self.assertFalse(result["history_saved"])
        self.assertEqual(result["history_save_error"], incomplete)

    def test_history_rating_and_preference_events_fold_to_latest_state(self):
        records = [
            {"record_id": "record-a", "run_id": "run-pref", "connection_id": "mock", "connection_name": "Mock",
             "model_entry_id": "model-a", "model_id": "a", "model_name": "A", "finish_status": "success", "latency_ms": 10},
            {"record_id": "record-b", "run_id": "run-pref", "connection_id": "mock", "connection_name": "Mock",
             "model_entry_id": "model-b", "model_id": "b", "model_name": "B", "finish_status": "success", "latency_ms": 20},
        ]
        for record in records:
            core.append_history(record)
        core.append_history({"record_type": "rating", "event_id": "rating-1", "target_record_id": "record-a", "rating": 3, "timestamp": "one"})
        core.append_history({"record_type": "rating", "event_id": "rating-2", "target_record_id": "record-a", "rating": 5, "timestamp": "two"})
        core.append_history({"record_type": "preference", "event_id": "pref-1", "target_run_id": "run-pref", "preferred_model_entry_id": "model-a", "timestamp": "one"})
        core.append_history({"record_type": "preference", "event_id": "pref-2", "target_run_id": "run-pref", "preferred_model_entry_id": "model-b", "timestamp": "two"})

        folded = core.read_history()
        self.assertEqual(folded[0]["user_rating"], 5)
        self.assertTrue(folded[0]["has_preference"])
        self.assertFalse(folded[0]["is_preferred"])
        self.assertTrue(folded[1]["is_preferred"])
        summary = core.summarize_history(folded)
        model_a = next(row for row in summary if row["model_entry_id"] == "model-a")
        self.assertEqual(model_a["average_user_rating"], 5)

        jsonl_response = urlopen(self.base + "/api/history/export?format=jsonl", timeout=2)
        exported_jsonl = [json.loads(line) for line in jsonl_response.read().decode("utf-8").splitlines()]
        self.assertEqual(exported_jsonl[0]["user_rating"], 5)
        self.assertFalse(exported_jsonl[0]["is_preferred"])
        self.assertTrue(exported_jsonl[1]["is_preferred"])
        csv_response = urlopen(self.base + "/api/history/export?format=csv", timeout=2)
        exported_csv = list(csv.DictReader(io.StringIO(csv_response.read().decode("utf-8"))))
        self.assertEqual(exported_csv[0]["user_rating"], "5")
        self.assertEqual(exported_csv[0]["is_preferred"], "False")
        self.assertEqual(exported_csv[1]["is_preferred"], "True")

        core.append_history({"record_type": "rating", "event_id": "rating-3", "target_record_id": "record-a", "rating": None, "timestamp": "three"})
        core.append_history({"record_type": "preference", "event_id": "pref-3", "target_run_id": "run-pref", "preferred_model_entry_id": None, "timestamp": "three"})
        cleared = core.read_history()
        self.assertIsNone(cleared[0]["user_rating"])
        self.assertFalse(cleared[0]["has_preference"])
        self.assertFalse(cleared[0]["is_preferred"])
        self.assertFalse(cleared[1]["has_preference"])
        self.assertEqual(sum(row["preference_samples"] for row in core.summarize_history(cleared)), 0)
        response = urlopen(self.base + "/api/history/export?format=jsonl", timeout=2)
        cleared_export = [json.loads(line) for line in response.read().decode("utf-8").splitlines()]
        self.assertIsNone(cleared_export[0]["user_rating"])
        self.assertFalse(cleared_export[0]["has_preference"])


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
        def slow_call(connection, model, prompt, parameters=None, on_delta=None, messages=None, on_response=None):
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
        def fake_call(connection, model, prompt, parameters=None, on_delta=None, messages=None, on_response=None):
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
            app.RUNS["old-active-run"] = {
                "id": "old-active-run", "status": "running", "created_at": time.time() - 3600,
                "pending_calls": 1, "models": [],
            }
            app._prune_runs()
            self.assertLessEqual(len(app.RUNS), 70)
            self.assertIn("old-active-run", app.RUNS)

    def test_settled_runs_expire_after_ttl_but_active_runs_remain(self):
        now = time.time()
        with app.RUN_LOCK:
            app.RUNS.clear()
            app.RUNS["expired-run"] = {
                "id": "expired-run", "status": "completed", "created_at": now - app.RUN_TTL_SECONDS - 1,
                "pending_calls": 0, "models": [],
            }
            app.RUNS["fresh-run"] = {
                "id": "fresh-run", "status": "completed", "created_at": now,
                "pending_calls": 0, "models": [],
            }
            app.RUNS["pending-run"] = {
                "id": "pending-run", "status": "cancelled", "created_at": now - app.RUN_TTL_SECONDS - 1,
                "pending_calls": 1, "models": [],
            }
            app._prune_runs()
            self.assertNotIn("expired-run", app.RUNS)
            self.assertIn("fresh-run", app.RUNS)
            self.assertIn("pending-run", app.RUNS)


if __name__ == "__main__":
    unittest.main()
