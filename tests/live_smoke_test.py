"""Opt-in live provider smoke check. Never run as part of the regular test suite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import hub_core as core
from secret_store import SecretStoreUnavailable, read_secret


PROMPT = "Reply with the single word OK."
REQUIRED_RESULT_FIELDS = {"ok", "text", "usage", "parameters", "latency_ms"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-costs", action="store_true",
        help="confirm that this sends live provider requests and may incur charges",
    )
    parser.add_argument("--connection", help="test only this saved connection ID")
    parser.add_argument("--include-local", action="store_true", help="also send the prompt to configured local Ollama models")
    args = parser.parse_args()
    if not args.confirm_costs:
        parser.error("Live provider calls can incur charges. Re-run with --confirm-costs to continue.")

    try:
        catalog = core.load_catalog()
    except Exception:
        print("Could not read the local Poly-LLM Hub catalog.")
        return 2

    connections = catalog.get("connections", [])
    models = catalog.get("models", [])
    selected_connections = []
    for connection in connections:
        if args.connection and connection.get("id") != args.connection:
            continue
        if connection.get("destination") == "local":
            if args.include_local:
                selected_connections.append(connection)
            continue
        try:
            saved_key = read_secret(connection.get("id", ""))
        except (OSError, SecretStoreUnavailable, ValueError):
            saved_key = None
        if saved_key:
            selected_connections.append(connection)

    if not selected_connections:
        print("No matching provider connection has a key in the OS credential store. No request was sent.")
        return 0

    failures = 0
    sent = 0
    for connection in selected_connections:
        model = next((row for row in models if row.get("connection_id") == connection.get("id")), None)
        if model is None:
            print(f"{connection.get('name', 'Provider')}: skipped (no model configured)")
            continue
        # call_model reads the OS key itself and returns a normalized result; the
        # raw response text and key are deliberately never printed or persisted.
        result = core.call_model(
            connection, model, PROMPT,
            {"stream": False, "max_output_tokens": 8},
        )
        sent += 1
        shape_ok = isinstance(result, dict) and REQUIRED_RESULT_FIELDS.issubset(result)
        success = bool(shape_ok and result.get("ok") and isinstance(result.get("text"), str) and result["text"].strip())
        if success:
            print(f"{connection.get('name')}/{model.get('model_id')}: PASS · {result.get('latency_ms')} ms")
        else:
            failures += 1
            # `call_model` sanitizes errors and does not include response bodies.
            print(f"{connection.get('name')}/{model.get('model_id')}: FAIL · {result.get('error', 'unexpected response shape')}")

    print(f"Completed {sent} live request(s); {failures} failed. No raw responses or keys were written by this script.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
