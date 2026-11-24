"""Authenticated history encryption using a random key stored in the OS vault."""

from __future__ import annotations

import base64
import json
import os
import secrets
import stat
import tempfile
from pathlib import Path
from typing import Any

from secret_store import SecretStoreUnavailable, read_secret, save_secret


HISTORY_KEY_ID = "poly-hub-history-key-v1"
HISTORY_ENVELOPE = "poly-llm-history-aesgcm-v1"
HISTORY_AAD = b"Poly-LLM-Hub history record v1"

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # Optional dependency; unencrypted history still works.
    AESGCM = None  # type: ignore[assignment,misc]


def encryption_available() -> bool:
    return AESGCM is not None


def _require_aesgcm():
    if AESGCM is None:
        raise RuntimeError(
            "History encryption needs the optional cryptography package. Install requirements-history-encryption.txt and restart the app."
        )
    return AESGCM


def _key(create: bool = False) -> bytes:
    _require_aesgcm()
    try:
        stored = read_secret(HISTORY_KEY_ID)
    except SecretStoreUnavailable as exc:
        raise RuntimeError("History encryption needs an available operating-system credential store.") from exc
    except OSError as exc:
        raise RuntimeError("The history-encryption key could not be read from the operating-system credential store.") from exc
    if stored is None and create:
        stored = secrets.token_hex(32)
        try:
            save_secret(HISTORY_KEY_ID, stored)
        except (OSError, SecretStoreUnavailable, ValueError) as exc:
            raise RuntimeError("The history-encryption key could not be saved to the operating-system credential store.") from exc
    if stored is None:
        raise RuntimeError("The encrypted history key is missing from the operating-system credential store.")
    try:
        key = bytes.fromhex(stored)
    except ValueError as exc:
        raise RuntimeError("The history-encryption key in the operating-system credential store is invalid.") from exc
    if len(key) != 32:
        raise RuntimeError("The history-encryption key in the operating-system credential store has an invalid size.")
    return key


def is_envelope(value: Any) -> bool:
    return isinstance(value, dict) and value.get("_poly_llm_history") == HISTORY_ENVELOPE


def encrypt_record(record: dict[str, Any], *, create_key: bool = False) -> dict[str, str]:
    aesgcm = _require_aesgcm()
    nonce = os.urandom(12)
    plaintext = json.dumps(record, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ciphertext = aesgcm(_key(create=create_key)).encrypt(nonce, plaintext, HISTORY_AAD)
    return {
        "_poly_llm_history": HISTORY_ENVELOPE,
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }


def decrypt_record(value: dict[str, Any]) -> dict[str, Any]:
    if not is_envelope(value):
        return value
    aesgcm = _require_aesgcm()
    try:
        nonce = base64.b64decode(value["nonce"], validate=True)
        ciphertext = base64.b64decode(value["ciphertext"], validate=True)
        if len(nonce) != 12 or len(ciphertext) < 16:
            raise ValueError("invalid encrypted record size")
        plaintext = aesgcm(_key()).decrypt(nonce, ciphertext, HISTORY_AAD)
        record = json.loads(plaintext.decode("utf-8"))
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "History could not be decrypted. Check that the original OS credential-store key is available and the history file is intact."
        ) from exc
    if not isinstance(record, dict):
        raise RuntimeError("An encrypted history record has an invalid format.")
    return record


def migrate_file(path: Path, enabled: bool) -> int:
    """Atomically re-encrypt/decrypt complete JSONL records, preserving event rows."""
    if enabled:
        _key(create=True)
    try:
        path_status = path.lstat()
    except FileNotFoundError:
        return 0
    except OSError as exc:
        raise RuntimeError("The local history path could not be inspected.") from exc
    if not stat.S_ISREG(path_status.st_mode):
        raise RuntimeError("The local history path must be a regular file.")
    source_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        source_fd = os.open(path, source_flags)
    except OSError as exc:
        raise RuntimeError("The local history path could not be opened safely for migration.") from exc
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".history-", suffix=".tmp", dir=path.parent)
    except OSError:
        os.close(source_fd)
        raise
    count = 0
    try:
        with os.fdopen(source_fd, "rb") as source, os.fdopen(descriptor, "wb") as handle:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise RuntimeError("The local history path must be a regular file.")
            if os.name == "posix":
                os.fchmod(handle.fileno(), 0o600)
            for line_number, raw_line in enumerate(source, start=1):
                if not raw_line.strip():
                    continue
                try:
                    parsed = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise RuntimeError(
                        f"History encryption migration stopped at unreadable record {line_number}; the original file was preserved."
                    ) from exc
                if not isinstance(parsed, dict):
                    raise RuntimeError(
                        f"History encryption migration stopped at invalid record {line_number}; the original file was preserved."
                    )
                record = decrypt_record(parsed)
                stored = encrypt_record(record) if enabled else record
                handle.write(json.dumps(stored, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))
                handle.write(b"\n")
                count += 1
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        if os.name == "posix":
            os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
    return count
