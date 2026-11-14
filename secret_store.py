"""Windows Credential Manager adapter keyed by dynamic connection ID."""

from __future__ import annotations

import ctypes
import hashlib
import re
import sys
from ctypes import wintypes


TARGET_PREFIX = "PolyLLMHub/connection/"
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168
MAX_CREDENTIAL_BYTES = 512
CONNECTION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


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
    return sys.platform == "win32"


def _windows_api():
    if not is_supported():
        raise SecretStoreUnavailable("Secure key entry is currently supported on Windows only.")
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
        raise ValueError("This key is too long for a Windows credential entry.")

    api = _windows_api()
    target = _target(connection_id)
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
    api = _windows_api()
    credential_ptr = ctypes.POINTER(_Credential)()
    if not api.CredReadW(_target(connection_id), CRED_TYPE_GENERIC, 0, ctypes.byref(credential_ptr)):
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
    api = _windows_api()
    target = _target(connection_id)
    if api.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
        return True
    if ctypes.get_last_error() == ERROR_NOT_FOUND:
        return False
    raise OSError("Windows Credential Manager could not remove this connection key.")
