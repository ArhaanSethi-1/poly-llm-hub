# Local command inventory

Checked 2026-11-14 on Windows PowerShell by resolving command names on the current PATH. The commands were not launched to generate responses. File metadata identified Claude Code version 2.1.312.0. Other executable versions were not available from Windows file-version metadata.

| Command found | Result | Notes |
|---|---|---|
| codex.exe | Found | Multiple Codex executable entries were discoverable, including the Codex app installation. The CLI version was not read. |
| claude.exe | Found | Claude Code CLI; file/product version metadata: 2.1.312.0. |
| ollama.exe | Found | Ollama executable is on PATH. The local server state and installed model list were not checked. |

These command names were not discoverable in the current PATH during this check: openai, gemini, agy, deepseek, grok, lms, jan.

This is a PATH snapshot, not a complete software inventory. A program may still be installed outside PATH, exposed through an application UI, or available under another command name. The presence of Ollama does not prove that a model is downloaded or that Ollama is running. The presence of Codex or Claude Code does not prove that authentication or billing is configured.

