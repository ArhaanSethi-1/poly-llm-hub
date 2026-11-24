# Poly-LLM Hub Roadmap

Last reviewed: 2026-11-24. This roadmap describes the checked-in implementation, not a promise that planned items already work.

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
- Explicit model discovery is implemented for OpenAI-compatible endpoints, Anthropic, Gemini, and Ollama. It follows cursor/page-token metadata where available and caps discovery at 500 IDs. Manual model IDs remain available when discovery does not work.
- Discovery can import provider-reported display names, descriptions, token limits, and Anthropic image/thinking flags. Unsupported fields remain unknown; metadata source and check date are retained.
- The catalog includes optional tags, favorites, capability values, context/output limits, and metadata provenance/date fields.
- Remote endpoints require HTTPS. Plain HTTP is limited to loopback URLs. The UI shows local or remote destination before a prompt is sent.
- User-initiated catalog JSON export and validated merge import are implemented for connections, models, and saved prompt sets. Backups exclude credentials and run history; existing connection IDs are preserved on import.
- Connection checks and model discovery retain the last success or sanitized failure and show it on the connection card.

Still needed:

- Broader provider capability metadata where list APIs expose it; OpenAI-compatible and Ollama list responses currently provide model IDs without comparable capability fields.
- User-defined model groups and richer bulk catalog editing remain future work.
- An explicit allow-list flow for private-network HTTP services, if that is needed.

The catalog is stored at %APPDATA%\Poly-LLM-Hub\catalog.json on Windows (or the platform data directory fallback). It contains configuration, environment-variable names, and any prompt sets explicitly saved, not credential values.

## Phase 2 — Connections and credentials

**Status: Partial**

- Users can enter or replace a provider key in a native masked dialog that writes to Windows Credential Manager, Linux Secret Service through `secret-tool`, or the macOS login Keychain through Apple's `security` tool.
- The browser sends a connection ID to open the Local Proxy key dialog; proxy key values are not placed in browser storage, catalog files, exports, source files, command-line arguments, or app logs. Direct Anthropic mode is documented separately and stores its user-provided key in browser localStorage.
- Environment-variable credentials remain available as a fallback. A saved OS-vault key takes priority.
- Users can remove a saved key locally and check connectivity through a model-list request that sends no prompt.
- Built-in provider cards include official key and documentation links. Provider account access and billing remain separate.
- OAuth/device authorization where officially supported and setup.exe packaging are not implemented.

## Phase 3 — Comparison workbench

**Status: Partial**

Implemented:

- A primary single-model chat workspace. Each turn targets exactly one catalog model through its configured provider; provider adapters receive the selected user/assistant transcript.
- Chat context stays in the browser session. Users can switch models without a provider call, choose lean/balanced/full context for the next request, and explicitly resend a failed user turn to another model. There is no automatic failover or retry.
- Chat is provider-backed conversation only; it does not edit workspace files, launch terminals, or operate a browser as a coding agent.
- Searchable model catalog, favorites, and selection of up to five models per comparison.
- The same prompt is sent to each selected model using its configured protocol adapter.
- Up to three comparisons may be active, with up to three provider calls per comparison running at once.
- Results show the provider connection, exact model ID, local/remote destination, status, duration, token usage when returned, and safe error text. Streaming text appears as it arrives for supported protocols; time-to-first-token is retained when measured.
- A shared optional maximum output-token setting is mapped to each adapter and recorded with results. Compare retries only 429 rate limits automatically with bounded backoff; other failures still require explicit retry.
- A preferred response can be set, changed, or cleared without triggering another model request. Choices are stored in opt-in history as append-only events.
- The Cancel control immediately stops local result collection and marks queued/in-flight cards cancelled.
- Failed model calls can be retried by explicit user action up to twice per retry chain. Compare and prompt-set runs also retry only HTTP 429 throttles with bounded exponential backoff; other failures remain explicit. Only one user retry per failed result may run at a time.

Limitations and remaining work:

- Provider APIs are stateless, so the chosen context is sent again on each turn. Lean and balanced windows reduce token use by omitting older messages; users can choose full context when needed. Automatic model failover and provider-specific context-window estimation are not implemented.
- Cancel closes the tracked HTTP response and prevents late results from being accepted. This is a best-effort transport disconnect; provider-side stop and billing behavior are not guaranteed by the APIs used here. The concurrency cap remains occupied while calls are still unwinding.
- Streaming is implemented for the four supported text-generation protocols. A shared temperature control is deferred because supported ranges and behavior vary by provider and model; a value may be rejected or silently ignored. Other provider-specific generation parameters, manual settings for per-call concurrency, and automated synthesis are not implemented.
- No model response is treated as HTML.

## Phase 4 — Repeatable empirical comparisons

**Status: Partial**

Implemented:

- Users can create, edit, and remove prompt sets with categorized prompt items. Seven original starter examples are available in the UI.
- A user can run the saved prompts sequentially against the selected models. The server uses the saved prompt text as the source of truth for each benchmark request.
- A separate local-history switch is off by default. When enabled, each completed model result is stored locally with the prompt, response, exact model/connection/protocol, timestamp, latency, token counts, status, and cost metadata where available.
- Optional AES-GCM at-rest encryption uses a random key in the existing OS credential store. The UI confirms before migrating existing JSONL records; backend reads and exports remain decrypted and human-readable.
- Users can export history to JSONL or CSV and clear it. Exports use an allow-list of credential-free fields and decrypt history when enabled. Clearing history also disables future history writes.
- CSV text beginning with common spreadsheet formula characters is prefixed before export to reduce formula-injection risk.
- When local history is enabled, users can rate each successful response from 1 to 5. Rating changes are appended as separate events and merged into exports and summaries.
- Saved-history summaries group runs by catalog model and report success, preferred-answer selections with recorded-choice sample counts, average latency, average time-to-first-token, token totals, user ratings with sample counts, and available cost estimates.
- The saved-history view includes a success-rate bar chart with run counts and an explicit note that it is not a composite model score.
- A daily trend chart can show all models together, a selected model, or a prompt category; it plots success rate and result count for the latest 30 active UTC dates in the saved-history year, with a table of the plotted daily values. Category counts are model results, not unique prompts.
- A prompt-level benchmark table compares saved prompt-set results across model entries without returning prompt text; it reports success, recorded preferred picks, latency, user rating, output-token usage samples, and estimated cost totals. Missing choices, unknown costs, and local runs are distinguished from zero values.
- Saved model and prompt-level summaries can be filtered by a temporary minimum success rate, maximum average latency, and maximum average estimated cost. Rows without a required measurement are excluded while that threshold is active.

Still needed:

- Persistent history remains an explicit user choice and is local to this machine. There is no multi-device sync.
- Benchmark records include the optional maximum output-token cap, measured time-to-first-token when streaming is available, and optional human ratings; they lack temperature and other provider-specific parameters and standardized scoring.
- The UI shows the active prompt’s results, model-level success rates and trends, daily trends by model and prompt category, and model-level and prompt-level summary tables.
- Browser-driven long-run recovery and resumable batches are not implemented.

## Phase 5 — Cost and decision support

**Status: Partial**

- Users can enter input/output USD per million tokens for an exact catalog model, with an HTTPS source and checked date.
- Cost is estimated only when both prices and both provider-reported token counts are available.
- Manual prices older than 90 days are explicitly marked stale on results and counted in summary tables; future checked dates are rejected.
- Local runs are labeled “Not estimated for local run”; missing data is “Cost unknown”.
- Estimate assumptions and the pricing source/date are shown with a response and included in optional history.

Planned:

- Automated price refresh with provenance and staleness rules.
- Persistent filter presets and category-specific threshold summaries.
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

- Server binds to 127.0.0.1, checks the expected Host, and requires the exact local Origin for POST/PUT/DELETE mutations. Read-only GETs may omit Origin for normal navigation.
- API requests require the expected loopback Host; JSON mutations require `Content-Type: application/json`.
- Security headers include a hash-restricted inline script policy, object/base/form restrictions, frame denial, content-type sniffing protection, and a no-referrer policy. Inline styles remain allowed for the current single-file UI.
- Prompt length, response-body size, selection count, active comparison count, parallel model calls, and provider request duration are bounded.
- Provider errors are reduced to safe messages; request bodies are not logged.
- Provider API redirects are followed only when scheme, host, and port remain the same as the configured endpoint.
- API keys can be stored in Windows Credential Manager, Linux Secret Service with `secret-tool`, or macOS Keychain. Keys are read server-side only when needed; environment variables remain a fallback.
- Catalog data contains no credential values. Prompt-set text is written only when the user explicitly saves the set.
- Prompt and response history is off by default, opt-in, local, user-exportable, and clearable.
- Catalog replacement is atomic and flushed; history appends are flushed to disk. On POSIX, the data directory and files receive user-only modes; on Windows, data uses the current user's AppData access controls.
- A malformed final history fragment is excluded with a visible warning and left untouched; subsequent appends are rejected until the user exports readable rows and clears the damaged history, preventing accidental concatenation or silent repair.
- Model outputs are rendered as text. Settled in-memory run records are pruned after 30 minutes; active records and calls still pending after cancellation remain tracked until settled.

Still needed:

- Broader security review and browser end-to-end tests.
- Provider-side cancellation endpoints and billing effects are not implemented or guaranteed. The local server closes tracked responses, which asks the transport to disconnect.
- Only HTTP 429 retries are automatic for Compare/prompt-set runs. Other failures require user action; every retry is a provider request and may incur charges.

## Phase 8 — Tests

**Status: Partial**

- A Python unittest suite uses temporary loopback mock HTTP servers and patched transport errors. It does not use real API keys or contact live provider services.
- Chat coverage verifies multi-turn role mapping across the four protocol adapters and enforces one-model chat requests with bounded user/assistant context.
- It verifies the four response adapters/parsers, discovery pagination and Anthropic metadata mapping, JSON/streaming bounds, manual model entry, endpoint validation, missing credentials, 429-only retry behavior, cost estimates, Origin checks, connection/model/prompt-set CRUD, pricing refresh, Direct-mode backend rejection and Local Proxy fallback, credential non-disclosure, cancellation response closing, history exports, CSV formula-injection handling, run-memory pruning, bounded parallelism, mocked OS vaults, and archive safety. Three history-encryption tests run when the optional `cryptography` dependency is installed; all 53 tests passed in the current Windows run.
- Current suite count and latest run result are recorded in `docs/PROJECT_LOG.md`. Mocked vault adapters do not establish platform credential-vault behavior; mock provider tests do not establish live provider compatibility. The separate live smoke script requires `--confirm-costs` and is excluded from unittest discovery and CI.
- `.github/workflows/checks.yml` configures the mock suite, Python compilation, browser-script syntax/runtime checks, and source-archive build on Ubuntu and Windows with Python 3.10 and 3.12. A hosted workflow result has not yet been observed.

## Phase 9 — Desktop and cross-platform packaging

**Status: Partial**

- Added a PyInstaller one-file build script for native Windows or macOS builds. It bundles the browser UI and catalog alongside the existing Python app entry point.
- The build must be performed and reviewed separately on each target OS. Code signing, notarization, auto-update, native desktop shell, and installer packaging remain planned.
- Linux Secret Service uses `secret-tool`; macOS Keychain uses Apple's `security` tool with key material sent through stdin rather than process arguments.
- Package a Windows installer only after the source and Windows Credential Manager flow are reviewed; signing and update behavior need their own release plan.

## Phase 10 — Documentation, evaluation, and release

**Status: Partial**

- README, roadmap, integration research, model-analysis prompt, security review, and activity records are included in this source tree.
- Architecture, provider-extension, and source/installer release guides are documented in `docs/ARCHITECTURE.md`, `docs/ADDING_PROVIDER.md`, and `docs/RELEASE_CHECKLIST.md`. A deterministic, allowlisted source-archive builder is included. Cross-platform CI checks Python, browser JavaScript syntax/runtime, and archive contents; rendered browser-level checks and a small user study remain planned.
- Keep any pilot data opt-in, disclose which provider receives each prompt, and distinguish project measurements from provider-published benchmark claims.

## Explicitly not implemented in this iteration

- An installer.
- A native Electron/React Native interface or published release binary.
- Coding-agent CLI execution.
- Automated answer synthesis.
- Policy/license enforcement checks.
- Automated price refresh or automatic model routing.
- Aggregate charts for latency, cost, and ratings, plus standardized scoring.

## Next work

1. Expand mock coverage for additional documented provider-list variants as provider support grows.
2. Refine connection health checks and broaden capability mappings only where provider list APIs document them.
3. Manually review the macOS Keychain flow on supported macOS versions; do not expose a multi-user or remote-hosted mode without a separate credential and access-control design.
4. Live-smoke-test provider protocols only with the user’s explicit choice of provider and credentials; mock success is not live compatibility evidence.

## Comparison baseline

The project may compare its configurable catalog and workflow with [Open WebUI provider connections](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/) and [Open WebUI multi-model chats](https://docs.openwebui.com/features/chat-conversations/chat-features/multi-model-chats/). No current claim that Poly-LLM Hub is universally better than Open WebUI is made here.
