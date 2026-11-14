# Poly‑LLM Hub project log

This is the durable activity record for the project. Add a dated entry when research, design, data collection, implementation, or a decision changes.

## Project summary

Poly‑LLM Hub is intended to provide one desktop interface over model APIs, locally hosted models, and selected model-provider command-line clients. The research goal is to decide which interfaces can be integrated reliably, what data handling and provider terms apply, and how to compare response quality, reliability, cost, and latency.

## Workspace and preservation

- Primary project folder: C:\Users\arhaa\Documents\ChatGPT\AI UI
- Research and activity records are stored inside this folder.
- Git was initialized before this log was created. At the first inspection it had no commits and no configured remote. This folder is therefore a local working copy, not an off-device backup.
- Do not store API keys or secrets in tracked files. Keep any future raw response data separate from the public/source-authored research notes.

## Activity log

### 2026-11-14 — Initial project record and research start

- Read the supplied Poly‑LLM Hub roadmap and saved it as roadmap.md in the project folder.
- The user said to gather as much data as possible first, covering both research and empirical data.
- The user asked for a separate, persistent record of project activity and supplied a reusable model/service analysis prompt.
- Created the research folder and this project log. The reusable prompt is saved in research/model-analysis-template.md.
- Checked the current Windows PATH without launching the detected tools. Found Codex CLI, Claude Code CLI version 2.1.312.0, and the Ollama executable. Gemini CLI, Antigravity CLI, OpenAI API CLI, DeepSeek CLI, Grok CLI, LM Studio CLI, and Jan CLI were not discoverable on PATH in that check. This does not prove they are not installed elsewhere.
- Reviewed official docs for OpenAI/Codex, Anthropic/Claude Code, Gemini API/CLI, Google Antigravity, xAI/Grok, DeepSeek, Ollama, LM Studio, Jan, LiteLLM, and OpenRouter.
- Key finding: the roadmap mixes ordinary model APIs, local inference servers, and coding-agent CLIs. These do not have the same request formats, side effects, identity/authentication, data retention, or cost model.
- Created a first integration landscape, five current model profiles, an original prompt-corpus draft, a structured run-record schema, and a proposed evaluation protocol.
- No model calls were made. No credentials were read or stored, and no provider accounts were used.
- Current evidence snapshot date: 2026-11-14.

### 2026-11-14 — First local MVP implementation

- The user asked to start building the Poly-LLM Hub and iterate on it together.
- Chose a dependency-free Python standard-library server and browser UI for the first usable slice.
- Added a loopback-only app with parallel comparison adapters for OpenAI Chat Completions, Anthropic Messages, Gemini generateContent, xAI-compatible Chat Completions, DeepSeek-compatible Chat Completions, and the local Ollama chat API.
- Added provider selection, manual model IDs, Ollama model discovery, response cards, latency/token metadata, PATH-only CLI discovery, and Windows startup instructions.
- Added `.gitignore` entries for Python environments, secrets, local model weights, generated builds, and future frontend dependencies.
- The app does not save prompts or responses. Cloud requests happen only when the user presses Compare. API keys are read from environment variables and are not stored by the app.
- No model/API calls were made and the app was not launched during this implementation turn. No files were committed or pushed to GitHub.
- Files: `app.py`, `web/index.html`, `start.ps1`, `.gitignore`, and updated `README.md`.

## Decisions and working assumptions

- Use native provider APIs for ordinary chat/inference adapters where available; treat coding-agent CLIs as a separate integration class.
- Prefer explicit model IDs and record the model ID, API/CLI version, parameters, and date on every future run.
- Preserve the exact provider text and structured metadata separately in future empirical runs. Do not assume a CLI response is equivalent to a direct model API response.
- Use a small, original, repeatable prompt set for early comparison. Public benchmarks can be added later after checking their version, contamination limitations, and license.
- Keep source-authored research material in this project folder. A future external backup location has not been configured.

## Next actions

1. Confirm which model profiles should be expanded first or continue with the provider families already listed in research/model-profiles.md.
2. Review and refine the original prompt corpus before any model calls.
3. Decide which APIs or local models to include in a paid/compute-aware pilot.
4. Collect opt-in model outputs and latency/token metadata, keeping raw runs separate from summary statistics.
5. Recheck provider model IDs, pricing, data retention, and policy pages before release.
6. Set up a remote backup or synced storage location if off-device recovery is required.

## Log format for future entries

Use:

### YYYY-MM-DD — Short activity name

- What was done.
- Files or data changed.
- Findings or decisions.
- What remains to do.

