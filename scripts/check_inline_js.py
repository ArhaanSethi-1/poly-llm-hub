"""Syntax-check inline JavaScript in the served HTML with Node.js."""

from __future__ import annotations

import re
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js is required to check the inline browser script.")

    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script\s*>", html, flags=re.IGNORECASE | re.DOTALL)
    if len(scripts) != 1:
        raise SystemExit(f"Expected one inline script in web/index.html; found {len(scripts)}.")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", encoding="utf-8", delete=False) as handle:
            handle.write(scripts[0])
            temporary_path = Path(handle.name)
        subprocess.run([node, "--check", str(temporary_path)], check=True)

        loader_line = next(
            (line.strip() for line in scripts[0].splitlines() if line.lstrip().startswith("function loadSelection()")),
            None,
        )
        if loader_line is None:
            raise SystemExit("Could not find the selected-model preference loader in web/index.html.")
        runtime_check = f"""
const assert = require("node:assert/strict");
const vm = require("node:vm");
const loader = {json.dumps(loader_line)};
const scenarios = [
  {{ name: "valid array filters non-string entries", getItem: () => '["model-a", 7, null]', expected: ["model-a"] }},
  {{ name: "malformed JSON clears selection", getItem: () => "{{", expected: [] }},
  {{ name: "unexpected JSON type leaves empty default", getItem: () => '{{"model":"model-a"}}', expected: [] }},
  {{ name: "storage access failure clears selection", getItem: () => {{ throw new Error("blocked"); }}, expected: [] }},
];
for (const scenario of scenarios) {{
  const context = {{ selected: new Set(), localStorage: {{ getItem: scenario.getItem }} }};
  vm.runInNewContext(loader + "\\nloadSelection();", context);
  assert.deepEqual(Array.from(context.selected), scenario.expected, scenario.name);
}}
"""
        subprocess.run([node, "-e", runtime_check], check=True)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
