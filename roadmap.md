# Poly-LLM Hub Roadmap

Last reviewed: 2026-11-14. This roadmap describes the checked-in implementation, not a promise that planned items already work.

## Product goal

Poly-LLM Hub is a local model workbench for user-managed provider connections and model catalogs, with comparisons that expose model identity, destination, latency, reliability, token usage, and documented cost assumptions. It is intended to help a user study their own model choices. It does not claim a universal best-model ranking.

## Status key

- **Implemented** — available in the current code and covered by the stated checks.
- **Partial** — a usable first slice exists; important requested behavior is still missing.
- **Planned** — not implemented.

## Phase 1 — Provider connections and model catalog

**Status: Partial**

Implemented:

- Provider connections and model entries are separate records in a local JSON catalog.
- Starter connections exist for OpenAI-compatible Chat Completions, Anthropic Messages, Gemini generateContent, xAI and DeepSeek OpenAI-compatible APIs, and Ollama.
- Users can add, edit, and remove custom connections; built-in connections can be edited.
- Users can add, edit, and remove model entries without changing application source.
- Explicit model discovery is implemented for OpenAI-compatible endpoints, Anthropic, Gemini, and Ollama. Manual model IDs remain available when discovery does not work.
- The catalog includes optional tags, favorites, capability values, context/output limits, and metadata provenance/date fields.
- Remote endpoints require HTTPS. Plain HTTP is limited to loopback URLs. The UI shows local or remote destination before a prompt is sent.

Still needed:

- Provider-specific connection health state and model pagination.
- Discovery-derived capability metadata.
- User-defined model groups and bulk import/export of non-secret catalog data.
- An explicit allow-list flow for private-network HTTP services, if that is needed.

The catalog is stored at %APPDATA%\Poly-LLM-Hub\catalog.json on Windows (or the platform data directory fallback). It contains configuration, environment-variable names, and any prompt sets explicitly saved, not credential values.

## Phase 2 — Connections and credentials

**Status: Partial**

- On Windows, users can enter or replace a provider key in a native masked dialog that writes directly to the current user's Windows Credential Manager.
- The browser sends a connection ID to open the dialog; provider key values are not placed in browser storage, catalog files, exports, source files, command-line arguments, or app logs.
- Environment-variable credentials remain available as a development fallback. A saved Windows key takes priority.
- Users can remove a saved key locally and check connectivity through a model-list request that sends no prompt.
- Built-in provider cards include official key and documentation links. Provider account access and billing remain separate.
- macOS/Linux native credential stores, OAuth/device authorization where officially supported, and setup.exe packaging are not implemented.

## Phase 3 — Comparison workbench

**Status: Partial**

Implemented:

- Searchable model catalog, favorites, and selection of up to five models per comparison.
- The same prompt is sent to each selected model using its configured protocol adapter.
- Up to three comparisons may be active, with up to three provider calls per comparison running at once.
- Results show the provider connection, exact model ID, local/remote destination, status, duration, token usage when returned, and safe error text.
- A preferred response can be set or changed without triggering another model request.
- The Cancel control immediately stops local result collection and marks queued/in-flight cards cancelled.

Limitations and remaining work:

- The standard-library HTTP transport cannot reliably abort an upstream request after it has been sent. A cancelled provider may continue generation and billing. The concurrency cap remains occupied while calls that cannot be interrupted are still running.
- Streaming, provider-specific generation parameters, per-model retry, manual settings for per-call concurrency, and automated synthesis are not implemented.
- No model response is treated as HTML.

## Phase 4 — Repeatable empirical comparisons

**Status: Partial**

Implemented:

- Users can create, edit, and remove prompt sets with categorized prompt items. Seven original starter examples are available in the UI.
- A user can run the saved prompts sequentially against the selected models. The server uses the saved prompt text as the source of truth for each benchmark request.
- A separate local-history switch is off by default. When enabled, each completed model result is stored locally with the prompt, response, exact model/connection/protocol, timestamp, latency, token counts, status, and cost metadata where available.
- Users can export history to JSONL or CSV and clear it. Exports use an allow-list of credential-free fields. Clearing history also disables future history writes.
- CSV text beginning with common spreadsheet formula characters is prefixed before export to reduce formula-injection risk.

Still needed:

- Persistent history remains an explicit user choice and is local to this machine. There is no multi-device sync.
- Benchmark records do not include time-to-first-token, generation parameters, human quality ratings, or standardized scoring.
- The UI shows the active prompt’s results; aggregate charts and cross-run comparisons are planned.
- Browser-driven long-run recovery and resumable batches are not implemented.

## Phase 5 — Cost and decision support

**Status: Partial**

- Users can enter input/output USD per million tokens for an exact catalog model, with an HTTPS source and checked date.
- Cost is estimated only when both prices and both provider-reported token counts are available.
- Local runs are labeled “Not estimated for local run”; missing data is “Cost unknown”.
- Estimate assumptions and the pricing source/date are shown with a response and included in optional history.

Planned:

- Automated price refresh with provenance and staleness rules.
- User-defined summaries based on recorded runs, such as latency, cost, success rate, or user ratings.
- Optional user-invoked comparison synthesis or fusion, clearly labeled as model-generated and separate from raw answers and measured data.
- No universal best-model score and no automatic model routing are implemented.

Estimates can differ from provider invoices because of caching, tiers, discounts, taxes, or billing adjustments.

## Phase 6 — Coding-agent CLIs

**Status: Partial**

- A small PATH check can report that CLI executables are detected.
- The UI and docs label these as detected, not connected.
- No CLI is launched. Agent execution requires a separate explicit adapter, permission model, working-directory display, bounded runtime/output, and cancellation support.

## Phase 7 — Security, privacy, and failure handling

**Status: Partial**

Implemented:

- Server binds to 127.0.0.1 and validates browser Origin on API requests.
- API requests require the expected loopback Host; JSON mutations require `Content-Type: application/json`.
- Basic security response headers are sent.
- Prompt length, response-body size, selection count, active comparison count, parallel model calls, and provider request duration are bounded.
- Provider errors are reduced to safe messages; request bodies are not logged.
- On Windows, API keys can be stored in the current user's Credential Manager and are read server-side only when a provider request runs. Environment variables remain a fallback.
- Catalog data contains no credential values. Prompt-set text is written only when the user explicitly saves the set.
- Prompt and response history is off by default, opt-in, local, user-exportable, and clearable.
- Model outputs are rendered as text. In-memory run records are pruned after 30 minutes.

Still needed:

- Cross-platform credential stores, broader security review, and browser end-to-end tests.
- Streaming and reliable cancellation of already-submitted upstream requests.
- Bounded retry with explicit user action; no automatic billed retry is performed.

## Phase 8 — Tests

**Status: Partial**

- A Python unittest suite uses temporary loopback mock HTTP servers and patched transport errors. It does not use real API keys or contact live provider services.
- It verifies the four response adapters/parsers, representative discovery and manual model entry, endpoint validation, missing credentials, authentication/rate-limit/timeout/invalid-JSON handling, cost estimates, Origin checks, connection/model/prompt-set CRUD, selection limits, preferred-answer behavior, cancellation, opt-in history, benchmark prompt source, JSONL/CSV export, CSV formula-injection handling, run-memory pruning, and Anthropic output limits.
- Current suite: 21 tests. The prior 18-test run is recorded in the archived project log; the three added cases have not been run in this consolidated copy.
- Further cases are still needed, including all discovery shapes, malformed browser preferences in a JavaScript runtime, response-size limits, concurrent-run limits, and longer cancellation/expiry races.

## Phase 9 — Desktop and cross-platform packaging

**Status: Planned**

- The current interface is a browser UI served by a local Python process; it is not a native desktop shell or installer.
- Decide whether a desktop shell is needed after the local workflow is reviewed. Keep provider APIs, local inference servers, and agent CLIs behind separate adapters if the UI is replaced.
- Add macOS Keychain and Linux Secret Service credential stores before promising native credential onboarding on those platforms.
- Package a Windows installer only after the source and Windows Credential Manager flow are reviewed; signing and update behavior need their own release plan.

## Phase 10 — Documentation, evaluation, and release

**Status: Partial**

- README, roadmap, integration research, model-analysis prompt, security review, and activity records are included in this source tree.
- Still planned: architecture diagram, guide for adding a provider/model, CI and browser-level checks, a small user study, and a documented release process.
- Keep any pilot data opt-in, disclose which provider receives each prompt, and distinguish project measurements from provider-published benchmark claims.

## Explicitly not implemented in this iteration

- Cross-platform secure credential storage and an installer.
- A native Electron/React Native interface or published release binary.
- Coding-agent CLI execution.
- Streaming responses.
- Automated answer synthesis.
- Policy/license enforcement checks.
- Automated price refresh or automatic model routing.
- Aggregate benchmark charts, human ratings, standardized scoring, and time-to-first-token measurement.

## Next work

1. Expand mock tests for discovery variants, browser preference parsing, output-size limits, concurrency, expiry, and cancellation races.
2. Add benchmark summaries/charts and optional human ratings, clearly distinct from objective measurements.
3. Add a user-visible retry action and refine connection health checks.
4. Consider credential-store integration before supporting multi-user or remote hosting.
5. Live-smoke-test provider protocols only with the user’s explicit choice of provider and credentials; mock success is not live compatibility evidence.

## Comparison baseline

The project may compare its configurable catalog and workflow with [Open WebUI provider connections](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/) and [Open WebUI multi-model chats](https://docs.openwebui.com/features/chat-conversations/chat-features/multi-model-chats/). No current claim that Poly-LLM Hub is universally better than Open WebUI is made here.
