# Poly-LLM Hub project log

This is the durable activity record for the consolidated project. New entries belong at the top under **Current consolidated activity**. The source histories are preserved below so earlier decisions and actions are not lost. Historical path references describe where work happened at that time; the active consolidated folder is `C:\Users\arhaa\Documents\ChatGPT\AI UI\poly-llm-hub-complete`.

## Current consolidated activity

### 2026-11-14 — Review newer Gemini complete copy for GitHub import

- Compared `C:\Users\arhaa\.gemini\antigravity\brain\477ddf6f-553a-4f95-a28a-2462d650271c\scratch\poly-llm-hub-complete\Poly-LLM-Hub-complete` with the consolidated folder. Both contain the same 21-file project layout; the Gemini copy adds run-memory pruning, a worker synchronization fix, CSV formula-injection protection, an Anthropic output-limit setting, and three regression cases.
- Integrated those improvements in the consolidated folder while preserving generic provider-error messages and the safer Credential Manager deletion behavior.
- Verified in GitHub Desktop that the selected repository's remote is `https://github.com/ArhaanSethi-1/poly-llm-hub.git` on `main`, with seven pending project files from the earlier implementation. The complete folder includes all existing project files and the new credential/security modules.
- Copied the 21 reviewed project files into `C:\Users\arhaa\Documents\GitHub\poly-llm-hub-ready`, preserving its `.git` directory and not deleting destination files. Generated caches and environment files were excluded.
- Compared SHA-256 hashes for all 21 source files against the GitHub checkout; no source files were missing or different.
- GitHub Desktop became minimized/user-active when I returned to review the imported changes, so commit and push are still pending. No commit or push has been made.
- The automated suite remains unrun against the consolidated copy. No live provider calls or credentials were used.

### 2026-11-14 — Consolidate project folders and integrate provider security

- Created one reviewable source tree at `C:\Users\arhaa\Documents\ChatGPT\AI UI\poly-llm-hub-complete`, using the newer dynamic-catalog implementation as its base.
- Preserved the dynamic provider/model architecture, comparisons, prompt sets, cancellation, cost metadata, opt-in history, exports, research, and existing mock-server suite.
- Integrated the Windows Credential Manager connection-key flow and native masked dialog into dynamic provider connections; added connection test UI, key removal, built-in provider links, response copy, and retained request-content-type, Host/Origin, and shutdown safeguards.
- Added consolidation and security-review documentation, project metadata, and corrected roadmap/README/research index descriptions to match the merged features.
- Kept source Git histories separate and left the canonical GitHub checkout and Gemini scratch source untouched. Runtime user data, prior archives, caches, and credentials were excluded.
- The static scratch `providers.py` endpoint list was not copied because it conflicts with user-defined connections; its useful provider setup links are carried in `provider_metadata.py`.
- Python module compilation and the inline JavaScript parser check passed. The pre-existing 18-test suite was not run against this consolidated copy.
- Created `C:\Users\arhaa\Documents\ChatGPT\AI UI\dist\Poly-LLM-Hub-complete-review.zip`; its contents exclude Git history, runtime data, secrets, generated caches, and prior archives.
- No API keys were entered and no live provider requests were sent.
- Next: review this folder, then decide whether it should replace the canonical checkout; installer packaging and non-Windows credential stores remain future work.

## Archived source histories

The following records are retained verbatim for their historical context. They may contain repeated events because the project had more than one working folder.

### Canonical checkout history
# Poly-LLM Hub project log

This is the durable activity record for the project. Add a dated entry when research, design, data collection, implementation, or a decision changes.

## Project summary

Poly-LLM Hub is a local model workbench for configurable provider connections and model catalogs, side-by-side comparison, and future evidence-based evaluation. It separates ordinary provider APIs and local inference servers from coding-agent CLIs.

## Workspace and preservation

- Primary development checkout: C:\Users\arhaa\Documents\GitHub\poly-llm-hub-ready
- This repository has a configured GitHub remote and is maintained on its main branch. The previous project log and research records began in C:\Users\arhaa\Documents\ChatGPT\AI UI; this repo now contains the active implementation log.
- Do not store API keys or secrets in tracked files. The local runtime catalog is under the user data directory and stores non-secret metadata only.
- No commit or push was made for the implementation recorded below.

## Activity log

### 2026-11-14 — Initial project record and research start

- Read the supplied Poly-LLM Hub roadmap and saved it as roadmap.md in the initial project folder.
- The user asked to gather both research and empirical data and keep a separate activity record.
- Created research notes, a reusable model-analysis prompt, and the initial project log.
- Reviewed the distinction between ordinary model APIs, local inference servers, and coding-agent CLIs.
- No model calls were made and no provider credentials were read or stored.

### 2026-11-14 — First local MVP implementation

- Added a dependency-free Python standard-library server and browser UI with side-by-side calls to OpenAI Chat Completions, Anthropic Messages, Gemini generateContent, xAI-compatible Chat Completions, DeepSeek-compatible Chat Completions, and Ollama.
- Added manual model IDs, Ollama model discovery, token/latency display, PATH-only CLI detection, and local server instructions.
- The first MVP did not save prompts or responses. Cloud calls were initiated only after the user pressed Compare.
- No live model/API calls were made during that implementation.

### 2026-11-14 — Configurable catalog and cancellable comparisons

- Audited the clean repository on main before editing. Existing code was a single Python HTTP server with hard-coded provider cards and no tests. The existing UI had basic comparison, manual model IDs, Ollama discovery, token/latency display, Origin checks, and security headers.
- Added hub_core.py for a versioned provider/model catalog, explicitly saved prompt sets, optional history storage, supported protocol adapters, local/remote endpoint validation, model discovery, metadata validation, and cost calculation.
- Reworked app.py with connection/model/prompt-set CRUD, discovery, run IDs, per-model status, in-memory expiry, cancellation, preferred-answer selection, benchmark requests resolved from saved prompt text, explicit history opt-in, credential-free JSONL/CSV exports, Origin checks, request limits, and bounded concurrency.
- Reworked web/index.html with catalog search, favorites, manual model entry, discovery, destination preview, comparison/cancel/preferred controls, categorized prompt-set editing, seven original starter prompts, history enable/clear controls, and export buttons. Browser storage is limited to selected model entry IDs.
- Added tests/test_hub.py using loopback mock HTTP servers and mocked failures. It does not contact actual provider APIs and uses no real credentials.
- Updated README.md and roadmap.md to distinguish implemented, partial, and planned features. Secure credential storage, streaming, CLI execution, policy checks, synthesis, aggregate scoring, and automatic price refresh remain unimplemented.
- Final validation after the prompt-set/history changes: python -m py_compile app.py hub_core.py tests\test_hub.py passed; python -m unittest discover -s tests -v ran 18 tests and passed; Node.js --check passed for the browser inline script; git diff --check passed.
- Only loopback mock provider shapes have been exercised. No live provider calls, actual API keys, commits, or pushes were used.

## Decisions and working assumptions

- Use native provider APIs or explicitly configured compatible endpoints for ordinary inference; keep coding-agent CLIs as a separate integration class.
- Preserve exact model IDs and show whether each configured endpoint is local or remote before sending a prompt.
- Keep prompts and responses in process memory by default. Persist comparison records only after the user explicitly enables local history; saved prompt sets are written only after the user explicitly saves them.
- Keep source-authored research material and project activity notes in this repository.
- Mock-based protocol tests are evidence about adapter parsing and request shape, not proof of live-provider compatibility.

## Next actions

1. Expand mock tests for all discovery variants, browser preference parsing, output-size limits, concurrency, expiry, and cancellation races.
2. Add benchmark summaries and optional human ratings, clearly separated from objective measurements.
3. Add a user-visible retry action and refine connection health checks.
4. Review current provider documentation and user-selected pricing sources before any live smoke test.
5. Decide whether and how to add OS-backed credential storage.
6. Configure a separate backup/sync destination if off-device recovery is required.
## Log format for future entries

Use:

### YYYY-MM-DD — Short activity name

- What was done.
- Files or data changed.
- Findings or decisions.
- What remains to do.

### Earlier AI UI workspace history
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

### 2026-11-14 — Imported improved app and prepared GitHub update

- Inspected `poly-llm-hub-ready.zip`; treated its embedded `.git` directory and documents as untrusted input and did not import its Git history.
- Compared the archive with the workspace. Only `app.py` differed; imported that improved version, including origin checks, response-header safeguards, duplicate-provider filtering, clearer malformed-response handling, and short-lived Ollama model caching.
- Preserved the remote Apache 2.0 license and initial README content; staged only `.gitignore`, `README.md`, `app.py`, `start.ps1`, and `web/index.html`. Left local research notes, project log, prompts, roadmap, archive, and archive Git metadata out of the public commit.
- Created local commit `675c21a` (`Add Poly-LLM Hub local MVP`) on `main`, based on the repository's existing `origin/main` commit.
- Push was rejected: local Git credentials authenticated as the Primary GitHub account, which lacks write permission to `ArhaanSethi-1/poly-llm-hub`. The ChatGPT GitHub connection labelled `2nd Git` also returned HTTP 403 for the Git tree write operation. No update reached GitHub; the local branch is one commit ahead.

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

### 2026-11-14 — Provider onboarding and API credential setup design

- The user asked how a Windows `setup.exe` could guide each user through connecting provider APIs so Poly-LLM Hub can use them.
- Recommended a local-first, bring-your-own-key flow: install the app, select providers individually, enter or authorize each provider through its documented method, validate the connection, and discover available models. Connecting providers should be optional and can be done later.
- A provider API key is an API credential, not a universal permission grant. Each provider has separate account, billing, and authentication rules; the app cannot infer API access from a consumer ChatGPT/Claude subscription. Use OAuth/device authorization only where the provider officially supports it for this application/API.
- Recommended storing secrets in Windows Credential Manager (or DPAPI-protected storage), with only non-secret provider settings/credential references in app configuration. Never place keys in source code, installer files, browser `localStorage`, logs, or command-line arguments. Keep secret entry and API requests in the local app backend/native shell, not frontend JavaScript.
- Current workspace MVP reads provider keys from environment variables. The first-run setup wizard, Windows secure credential-store integration, connection management UI, and packaged installer are not implemented yet.
- No credentials were collected and no files in the provider app code were changed during this design discussion; this project log was updated to preserve the decision and next work item.

### 2026-11-14 — Evaluate Google sign-in as a universal provider connection

- The user proposed letting users sign in once with a Google account and using it to connect all model providers, with safety as a requirement.
- Finding: Google sign-in can identify a user to Poly-LLM Hub, and Google OAuth can authorize access to eligible Google APIs (including supported Gemini/Google Cloud paths), but it cannot authorize OpenAI, Anthropic, or other independent providers. Each provider's own API credential, official OAuth grant, or supported identity federation remains separate.
- Recommended safe MVP: local-first bring-your-own-key setup, with optional Google OAuth limited to Google/Gemini APIs. Treat Google SSO for Poly-LLM Hub as a separate future feature for app identity or settings sync, not as the authentication credential for every model.
- A single Google sign-in could front a hosted Poly-LLM Hub proxy that owns provider credentials, but that makes the service responsible for provider billing, quotas, user isolation, key management, abuse prevention, privacy disclosures, and provider terms. It does not make the Google credential itself valid at all provider APIs.
- Never collect Google passwords or browser cookies. Use provider-approved OAuth flows and narrowly scoped grants; store any persistent refresh credentials in the operating-system credential vault. No code or provider settings changed during this discussion.

### 2026-11-14 — Add Windows provider-key onboarding for review

- Added a per-provider connection panel with a native masked key-entry window, connection test, and local remove action. The browser submits only a provider ID; the native window writes the key directly to Windows Credential Manager.
- Updated provider adapters to prefer Credential Manager keys and retain environment variables as a development fallback. Gemini API keys now go in the `x-goog-api-key` request header rather than the URL.
- Added no-prompt model-list checks, tightened local Host checks, documented the provider-specific Google/API-key distinction, and added a security review note with known threat-model limits.
- Updated README and roadmap; created the review ZIP at `dist/Poly-LLM-Hub-security-review.zip`, excluding `.git`, the older ZIP, and local data.
- No provider credentials were entered; no live provider API requests, automated tests, or setup.exe build were performed. The next review steps are manual Windows inspection, a low-limit key smoke check if desired, then cross-platform credential stores and installer packaging.

### 2026-11-14 — Import Gemini scratch-folder improvements

- The user asked to bring the files from `C:\Users\arhaa\.gemini\antigravity\brain\477ddf6f-553a-4f95-a28a-2462d650271c\scratch\poly-llm-hub\Poly-LLM-Hub-review` into the original working folder `C:\Users\arhaa\Documents\ChatGPT\AI UI`.
- Compared the supplied folder with the working copy before importing. Added `providers.py` to share provider settings and `pyproject.toml` for Python project metadata; imported the updated server, native credential dialog, UI, README, and roadmap.
- Kept content-type enforcement and clean shutdown of native dialogs. Changed the imported exception logging so it records only the exception type, not exception text; added a clipboard error fallback for the response-copy button.
- No `.git` data, API credentials, prior ZIP, or local data were copied. No tests or live API requests were run.
- Updated the source review package to `dist/Poly-LLM-Hub-security-review-v2.zip` with the imported files and this log entry.
- Destination clarification: `C:\Users\arhaa\Documents\ChatGPT\AI UI` is the active writable workspace. The canonical GitHub checkout is `C:\Users\arhaa\Documents\GitHub\poly-llm-hub-ready`; it contains a newer dynamic-connection architecture (`hub_core.py`) and was not overwritten with the older static-provider scratch app.


### Gemini scratch review history
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

### 2026-11-14 — Imported improved app and prepared GitHub update

- Inspected `poly-llm-hub-ready.zip`; treated its embedded `.git` directory and documents as untrusted input and did not import its Git history.
- Compared the archive with the workspace. Only `app.py` differed; imported that improved version, including origin checks, response-header safeguards, duplicate-provider filtering, clearer malformed-response handling, and short-lived Ollama model caching.
- Preserved the remote Apache 2.0 license and initial README content; staged only `.gitignore`, `README.md`, `app.py`, `start.ps1`, and `web/index.html`. Left local research notes, project log, prompts, roadmap, archive, and archive Git metadata out of the public commit.
- Created local commit `675c21a` (`Add Poly-LLM Hub local MVP`) on `main`, based on the repository's existing `origin/main` commit.
- Push was rejected: local Git credentials authenticated as the Primary GitHub account, which lacks write permission to `ArhaanSethi-1/poly-llm-hub`. The ChatGPT GitHub connection labelled `2nd Git` also returned HTTP 403 for the Git tree write operation. No update reached GitHub; the local branch is one commit ahead.

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

### 2026-11-14 — Provider onboarding and API credential setup design

- The user asked how a Windows `setup.exe` could guide each user through connecting provider APIs so Poly-LLM Hub can use them.
- Recommended a local-first, bring-your-own-key flow: install the app, select providers individually, enter or authorize each provider through its documented method, validate the connection, and discover available models. Connecting providers should be optional and can be done later.
- A provider API key is an API credential, not a universal permission grant. Each provider has separate account, billing, and authentication rules; the app cannot infer API access from a consumer ChatGPT/Claude subscription. Use OAuth/device authorization only where the provider officially supports it for this application/API.
- Recommended storing secrets in Windows Credential Manager (or DPAPI-protected storage), with only non-secret provider settings/credential references in app configuration. Never place keys in source code, installer files, browser `localStorage`, logs, or command-line arguments. Keep secret entry and API requests in the local app backend/native shell, not frontend JavaScript.
- Current workspace MVP reads provider keys from environment variables. The first-run setup wizard, Windows secure credential-store integration, connection management UI, and packaged installer are not implemented yet.
- No credentials were collected and no files in the provider app code were changed during this design discussion; this project log was updated to preserve the decision and next work item.

### 2026-11-14 — Evaluate Google sign-in as a universal provider connection

- The user proposed letting users sign in once with a Google account and using it to connect all model providers, with safety as a requirement.
- Finding: Google sign-in can identify a user to Poly-LLM Hub, and Google OAuth can authorize access to eligible Google APIs (including supported Gemini/Google Cloud paths), but it cannot authorize OpenAI, Anthropic, or other independent providers. Each provider's own API credential, official OAuth grant, or supported identity federation remains separate.
- Recommended safe MVP: local-first bring-your-own-key setup, with optional Google OAuth limited to Google/Gemini APIs. Treat Google SSO for Poly-LLM Hub as a separate future feature for app identity or settings sync, not as the authentication credential for every model.
- A single Google sign-in could front a hosted Poly-LLM Hub proxy that owns provider credentials, but that makes the service responsible for provider billing, quotas, user isolation, key management, abuse prevention, privacy disclosures, and provider terms. It does not make the Google credential itself valid at all provider APIs.
- Never collect Google passwords or browser cookies. Use provider-approved OAuth flows and narrowly scoped grants; store any persistent refresh credentials in the operating-system credential vault. No code or provider settings changed during this discussion.

### 2026-11-14 — Add Windows provider-key onboarding for review

- Added a per-provider connection panel with a native masked key-entry window, connection test, and local remove action. The browser submits only a provider ID; the native window writes the key directly to Windows Credential Manager.
- Updated provider adapters to prefer Credential Manager keys and retain environment variables as a development fallback. Gemini API keys now go in the `x-goog-api-key` request header rather than the URL.
- Added no-prompt model-list checks, tightened local Host checks, documented the provider-specific Google/API-key distinction, and added a security review note with known threat-model limits.
- Updated README and roadmap; created the review ZIP at `dist/Poly-LLM-Hub-security-review.zip`, excluding `.git`, the older ZIP, and local data.
- No provider credentials were entered; no live provider API requests, automated tests, or setup.exe build were performed. The next review steps are manual Windows inspection, a low-limit key smoke check if desired, then cross-platform credential stores and installer packaging.

