"""Build a deterministic source archive from the reviewed application allowlist."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_FILES = (
    ".gitignore",
    ".github/workflows/checks.yml",
    "LICENSE",
    "README.md",
    "app.py",
    "credential_dialog.py",
    "hub_core.py",
    "provider_metadata.py",
    "pyproject.toml",
    "roadmap.md",
    "secret_store.py",
    "start.ps1",
    "web/index.html",
    "tests/test_hub.py",
    "scripts/build_source_archive.py",
    "scripts/check_inline_js.py",
    "docs/ADDING_PROVIDER.md",
    "docs/ARCHITECTURE.md",
    "docs/CONSOLIDATION.md",
    "docs/RELEASE_CHECKLIST.md",
    "docs/SECURITY_REVIEW.md",
)
_BACKSLASH = re.escape(b"\\")
_SLASH = re.escape(b"/")
_USER_DIRECTORY = re.escape(b"Users")
_HOME_DIRECTORY = re.escape(b"home")
LOCAL_PATH_PATTERN = re.compile(
    rb"(?i)(?:\b[A-Z]:" + _BACKSLASH + _USER_DIRECTORY + _BACKSLASH + rb"[^\\/\s]+|"
    + _SLASH + _USER_DIRECTORY + _SLASH + rb"[^/\s]+|"
    + _SLASH + _HOME_DIRECTORY + _SLASH + rb"[^/\s]+)"
)
SECRET_PATTERNS = (
    re.compile(rb"\bsk-[A-Za-z0-9_-]{24,}\b"),
    re.compile(rb"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def _version(root: Path) -> str:
    content = (root / "pyproject.toml").read_text(encoding="utf-8")
    project = re.search(r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", content)
    version = re.search(r'(?m)^version\s*=\s*"([0-9A-Za-z.+!-]+)"\s*$', project.group(1) if project else "")
    if version is None:
        raise ValueError("pyproject.toml must declare a project version before packaging.")
    return version.group(1)


def _validate_source_content(relative: str, data: bytes) -> None:
    if LOCAL_PATH_PATTERN.search(data):
        raise ValueError(f"Machine-specific absolute path found in source file: {relative}")
    if any(pattern.search(data) for pattern in SECRET_PATTERNS):
        raise ValueError(f"Credential-like material found in source file: {relative}")


def _archive_inputs(root: Path) -> list[tuple[str, bytes]]:
    root = root.resolve()
    contents: list[tuple[str, bytes]] = []
    for relative in sorted(ARCHIVE_FILES):
        source = root / relative
        if not source.is_file() or source.is_symlink():
            raise FileNotFoundError(f"Required source file is missing or unsafe: {relative}")
        resolved = source.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"Source file escapes the project root: {relative}")
        data = source.read_bytes()
        _validate_source_content(relative, data)
        contents.append((relative.replace("\\", "/"), data))
    return contents


def build_archive_bytes(root: Path = ROOT) -> bytes:
    """Return identical archive bytes for identical allowlisted source content."""
    prefix = f"Poly-LLM-Hub-{_version(root)}"
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for relative, data in _archive_inputs(root):
            info = zipfile.ZipInfo(f"{prefix}/{relative}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return output.getvalue()


def main() -> int:
    version = _version(ROOT)
    destination = ROOT / "dist" / f"Poly-LLM-Hub-{version}-source.zip"
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite an existing archive: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = build_archive_bytes(ROOT)
    destination.write_bytes(data)
    print(f"Created {destination} ({len(data)} bytes, SHA-256 {hashlib.sha256(data).hexdigest()}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
