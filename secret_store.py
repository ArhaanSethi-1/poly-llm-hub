"""OS credential-store adapters keyed by dynamic connection ID."""

from __future__ import annotations

import ctypes
import hashlib
import os
import re
import shutil
import subprocess
import sys
from ctypes import wintypes


TARGET_PREFIX = "PolyLLMHub/connection/"
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168
MAX_CREDENTIAL_BYTES = 512
CONNECTION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MACOS_KEYCHAIN_SERVICE = "com.poly-llm-hub.connection"
MACOS_SECURITY_PATH = "/usr/bin/security"


class SecretStoreUnavailable(RuntimeError):
    """Raised when the current operating system has no implemented vault."""


class _FileTime(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FileTime),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def is_supported() -> bool:
    return (
        sys.platform == "win32"
        or (sys.platform.startswith("linux") and shutil.which("secret-tool") is not None)
        or (sys.platform == "darwin" and os.path.isfile(MACOS_SECURITY_PATH))
    )


def store_name() -> str:
    if sys.platform == "win32":
        return "Windows Credential Manager"
    if sys.platform.startswith("linux") and shutil.which("secret-tool") is not None:
        return "Linux Secret Service"
    if sys.platform == "darwin" and os.path.isfile(MACOS_SECURITY_PATH):
        return "macOS Keychain"
    return ""


def _windows_api():
    if sys.platform != "win32":
        raise SecretStoreUnavailable("The Windows credential store is unavailable on this system.")
    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    advapi32.CredWriteW.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
    advapi32.CredWriteW.restype = wintypes.BOOL
    advapi32.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_Credential)),
    ]
    advapi32.CredReadW.restype = wintypes.BOOL
    advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    advapi32.CredDeleteW.restype = wintypes.BOOL
    advapi32.CredFree.argtypes = [ctypes.c_void_p]
    advapi32.CredFree.restype = None
    return advapi32


def _secret_tool(*arguments: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("secret-tool") if sys.platform.startswith("linux") else None
    if not executable:
        raise SecretStoreUnavailable("Linux Secret Service is unavailable. Install secret-tool and sign in to a desktop session.")
    try:
        result = subprocess.run(
            [executable, *arguments],
            input=input_text,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OSError("Linux Secret Service did not respond in time.") from exc
    except OSError as exc:
        raise OSError("Linux Secret Service could not be reached.") from exc
    return result


def _macos_security(*arguments: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    if sys.platform != "darwin" or not os.path.isfile(MACOS_SECURITY_PATH):
        raise SecretStoreUnavailable("macOS Keychain is unavailable on this system.")
    try:
        return subprocess.run(
            [MACOS_SECURITY_PATH, *arguments],
            input=input_text,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OSError("macOS Keychain did not respond in time.") from exc
    except OSError as exc:
        raise OSError("macOS Keychain could not be reached.") from exc


def _target(connection_id: str) -> str:
    if not isinstance(connection_id, str) or not CONNECTION_ID_RE.fullmatch(connection_id):
        raise ValueError("Invalid provider connection ID.")
    digest = hashlib.sha256(connection_id.encode("utf-8")).hexdigest()
    return TARGET_PREFIX + digest


def save_secret(connection_id: str, value: str) -> None:
    secret = value.strip()
    if not secret:
        raise ValueError("Enter an API key first.")
    encoded = secret.encode("utf-8")
    if len(encoded) > MAX_CREDENTIAL_BYTES:
        raise ValueError("This key is too long for a secure credential entry.")

    target = _target(connection_id)
    if sys.platform.startswith("linux"):
        result = _secret_tool(
            "store", "--label=Poly-LLM Hub connection key",
            "service", "poly-llm-hub", "connection", target,
            input_text=secret,
        )
        if result.returncode != 0:
            raise OSError("Linux Secret Service could not save this key. Check that your desktop keyring is available.")
        return

    if sys.platform == "darwin":
        # The security CLI's -w value is otherwise a process argument. Send
        # hex through its interactive stdin parser to keep key bytes out of
        # argv while storing the original credential bytes in the Keychain.
        encoded_secret = encoded.hex()
        command = (
            f"add-generic-password -U -s {MACOS_KEYCHAIN_SERVICE} "
            f"-a {target} -X {encoded_secret}\n"
        )
        result = _macos_security("-i", input_text=command)
        if result.returncode != 0:
            raise OSError("macOS Keychain could not save this key. Check that your login keychain is available.")
        return

    api = _windows_api()
    buffer = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
    credential = _Credential()
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = target
    credential.CredentialBlobSize = len(encoded)
    credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = "Poly-LLM Hub connection key"
    if not api.CredWriteW(ctypes.byref(credential), 0):
        raise OSError("Windows Credential Manager could not save this key.")


def read_secret(connection_id: str) -> str | None:
    target = _target(connection_id)
    if sys.platform.startswith("linux"):
        result = _secret_tool("lookup", "service", "poly-llm-hub", "connection", target)
        if result.returncode != 0:
            if not result.stdout:
                return None
            raise OSError("Linux Secret Service could not read this connection key.")
        secret = result.stdout
        if secret.endswith("\r\n"):
            secret = secret[:-2]
        elif secret.endswith("\n"):
            secret = secret[:-1]
        if not secret:
            return None
        if len(secret.encode("utf-8")) > MAX_CREDENTIAL_BYTES:
            raise OSError("The saved connection credential has an invalid size.")
        return secret

    if sys.platform == "darwin":
        result = _macos_security(
            "find-generic-password", "-s", MACOS_KEYCHAIN_SERVICE, "-a", target, "-w"
        )
        if result.returncode != 0:
            if not result.stdout:
                return None
            raise OSError("macOS Keychain could not read this connection key.")
        secret = result.stdout.rstrip("\r\n")
        if not secret:
            return None
        try:
            secret_bytes = secret.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise OSError("The saved connection credential has an invalid encoding.") from exc
        if len(secret_bytes) > MAX_CREDENTIAL_BYTES:
            raise OSError("The saved connection credential has an invalid size.")
        return secret

    api = _windows_api()
    credential_ptr = ctypes.POINTER(_Credential)()
    if not api.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(credential_ptr)):
        if ctypes.get_last_error() == ERROR_NOT_FOUND:
            return None
        raise OSError("Windows Credential Manager could not read this connection key.")
    try:
        credential = credential_ptr.contents
        size = int(credential.CredentialBlobSize)
        if size < 1 or size > MAX_CREDENTIAL_BYTES:
            raise OSError("The saved connection credential has an invalid size.")
        return ctypes.string_at(credential.CredentialBlob, size).decode("utf-8")
    finally:
        api.CredFree(credential_ptr)


def delete_secret(connection_id: str) -> bool:
    target = _target(connection_id)
    if sys.platform.startswith("linux"):
        result = _secret_tool("clear", "service", "poly-llm-hub", "connection", target)
        if result.returncode != 0:
            raise OSError("Linux Secret Service could not remove this connection key.")
        return True

    if sys.platform == "darwin":
        result = _macos_security(
            "delete-generic-password", "-s", MACOS_KEYCHAIN_SERVICE, "-a", target
        )
        if result.returncode != 0:
            raise OSError("macOS Keychain could not remove this connection key.")
        return True

    api = _windows_api()
    if api.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
        return True
    if ctypes.get_last_error() == ERROR_NOT_FOUND:
        return False
    raise OSError("Windows Credential Manager could not remove this connection key.")
