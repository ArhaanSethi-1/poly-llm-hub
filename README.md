# Poly-LLM Hub

Poly-LLM Hub is a local model workspace with a single-model chat as its primary view and a side-by-side comparison mode for selected models. Configure provider connections and exact model IDs once, chat with one model at a time, and switch models while carrying a chosen amount of recent context. Comparison remains available as a secondary mode. It does not claim a universal “best model” score.

The longer-term product goal is one clear interface for hosted APIs, local inference servers, and carefully isolated coding-agent integrations. It should show which provider, model, and destination handle each request, then help the user compare reliability, latency, usage, cost, and quality from repeatable empirical runs. Provider-specific limitations and data handling should remain visible.

## Current implementation

This iteration provides:

- A configurable catalog that keeps provider connections separate from model entries. One connection can contain multiple models.
- Built-in starter connections for OpenAI Chat Completions, Anthropic Messages, Gemini generateContent, xAI and DeepSeek OpenAI-compatible APIs, and local Ollama.
- User-defined OpenAI-compatible endpoints, including loopback services. A compatible endpoint may implement only part of the protocol; confirm its behavior and enter the exact model ID it expects.
- Explicit model discovery follows provider pagination where supported, collects up to 500 model IDs, and imports provider-reported names, limits, descriptions, and known capability flags when available. Unknown capabilities stay unknown; manual model entry remains available when discovery is unavailable or incomplete.
- Search, favorites, tags, capabilities, optional limits, and exact-model pricing metadata.
- Side-by-side comparisons of up to five catalog entries, with up to three active comparisons and three provider calls per comparison.
- A single-model chat workspace that carries recent user/assistant turns across supported provider protocols. It offers lean, balanced, and full-context choices; changing the active model makes no provider call, and a failed turn is resent only after explicit user action. Chat context lives in the browser session unless opt-in local history is enabled.
- An optional shared output-token cap, translated by the provider adapter and stored with each saved result.
- Cancellation, preferred-answer marking, explicit bounded retries for failed model calls, categorized prompt sets, sequential prompt-set runs, prompt-level cross-run summaries, 1–5 user ratings, and opt-in local run history.
- Temporary summary filters for minimum success rate, maximum average latency, and maximum average estimated cost; missing metrics are excluded only when their filter is active.
- User-initiated JSONL and CSV exports of saved history.
- CSV export prefixes risky spreadsheet-formula text so prompt/response fields are less likely to execute as formulas when opened in spreadsheet software.
- Cost estimates only when exact-model rates and provider-reported input/output tokens are present.
- A local Python standard-library server and browser interface.

API request and discovery paths implemented by this version:

| Connection protocol | Comparison request | Discovery request |
| --- | --- | --- |
| OpenAI-compatible | POST /chat/completions | GET /models |
| Anthropic Messages | POST /messages | GET /models |
| Gemini generateContent | POST /models/{model}:generateContent | GET /models |
| Ollama | POST /api/chat | GET /api/tags |

These adapters were verified against local mock servers only. No live provider calls have been made from this project. Gemini generateContent remains implemented for compatibility; current Gemini documentation recommends the newer Interactions API for new projects, so check the provider docs before extending this adapter. [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) · [OpenAI model listing](https://developers.openai.com/api/reference/resources/models/methods/list) · [Anthropic Messages](https://docs.anthropic.com/en/api/messages) · [Anthropic model listing](https://platform.claude.com/docs/en/api/models/list) · [Gemini generateContent](https://ai.google.dev/api/generate-content) · [Gemini model listing](https://ai.google.dev/api/models) · [Gemini API overview](https://ai.google.dev/gemini-api/docs) · [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md)

## Run locally

Requirements: Python 3.10 or later. The app uses only the Python standard library.

1. Open PowerShell in the repository folder.
2. Start the server:

       python app.py

3. Open http://127.0.0.1:8765 in a browser.
4. Add model entries through discovery or by entering the exact model ID.
5. In Chat, choose one model and send a message. Choose Compare when you want the same prompt sent to up to five selected catalog models.

Stop the server with Ctrl+C. The server binds to 127.0.0.1.

## Connections and model catalog

The initial catalog includes common provider connections. Edit a connection to change its base URL or optional environment-variable fallback, or add another connection using one of the supported protocols. Connections are stored separately from exact model IDs, so each connection can contain multiple models.

Use **Connect key** on a connection. A native masked dialog writes the key to the current user's Windows Credential Manager, Linux Secret Service when `secret-tool` and a logged-in keyring are available, or the macOS login Keychain. On macOS, the key is sent to Apple's `security` tool over stdin in encoded form; the key itself is not placed in process arguments. The browser sends only the connection ID to the local app; the key is not submitted through JavaScript, placed in the catalog, passed in command-line arguments, or written to logs. **Get API key** and **Provider docs** links are shown for built-in providers. A saved vault key takes precedence over an environment-variable fallback.

Windows PowerShell fallback examples:

    $env:OPENAI_API_KEY = "your-key"
    $env:ANTHROPIC_API_KEY = "your-key"
    $env:GEMINI_API_KEY = "your-key"
    $env:XAI_API_KEY = "your-key"
    $env:DEEPSEEK_API_KEY = "your-key"

Set a key in the same shell before starting the app. Linux systems without `secret-tool` or an available desktop keyring can use environment variables. Do not paste API keys into the browser or save them in project files.

Each cloud API needs its own provider account and credential. Google sign-in does not connect OpenAI, Anthropic, xAI, or DeepSeek. Gemini uses a Google AI Studio API key in this build; Google OAuth and a shared Poly-LLM Hub account are not configured. Ollama is local and usually needs no cloud key.

The comparison form has an optional shared **Maximum output tokens** setting. It is translated to the configured adapter field: OpenAI Chat Completions uses `max_completion_tokens`, other OpenAI-compatible connections use `max_tokens`, Anthropic uses `max_tokens`, Gemini uses `generationConfig.maxOutputTokens`, and Ollama uses `options.num_predict`. Leave it blank to use provider defaults. Provider/model limits and support can differ, so a configured endpoint may reject a cap. The value is recorded with each saved result; it does not make model output deterministic. See the [OpenAI](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), [Anthropic](https://platform.claude.com/docs/en/api/messages/create), [Gemini](https://ai.google.dev/api/generate-content), and [Ollama](https://docs.ollama.com/api/chat) API references.

**Test connection** makes a provider model-list request and sends no prompt or generated-content request. Some compatible endpoints do not implement model listing; add the exact model ID manually in that case. A successful model-list check does not guarantee that every model ID is available to your account.

The connection card keeps the result and time of its latest model-list check or discovery, including a sanitized failure message, so a failed check remains visible after the page reloads.

Remote connection URLs must use HTTPS. Plain HTTP is accepted only for loopback names or addresses such as localhost and 127.0.0.1. Non-loopback HTTP endpoints are rejected. The UI labels loopback destinations as local and other destinations as remote. Discovery runs only after you click Discover models and sends no prompt. When discovery is unsupported, add the provider’s exact model ID manually.

Model IDs, names, tags, capability metadata, and optional prices are stored separately from provider connections. Capability values remain “unknown” unless you enter known information. Price metadata requires exact-model input and output USD rates per million tokens, an HTTPS source URL, and a checked date.

Use **Export catalog JSON** to back up connections, models, and saved prompt sets. Import validates the file and merges models and prompt sets by ID. Existing connection IDs are kept to avoid silently routing a saved credential to a different endpoint; add imported connections with new IDs or edit existing connections manually when restoring them. Catalog backups do not include API keys, environment-variable values, or run history.

The local catalog is stored at:

    %APPDATA%\Poly-LLM-Hub\catalog.json

This JSON file contains provider/model configuration, environment-variable names, and any prompt sets you explicitly save. It may contain your saved prompt-set text, but not run responses or credential values. It is not encrypted. On POSIX systems, the app restricts its data directory to the current user and writes catalog/history files with user-only permissions. On Windows, files live under the current user's AppData directory and inherit its access controls. Windows Credential Manager, Linux Secret Service, or macOS Keychain stores saved API keys separately. The OS protects those credentials at rest for the current user; software already running as that user may still be able to use them.

## Prompt sets and empirical comparisons

The workbench includes original starter prompts for instruction following, structured extraction, summarization, coding, reasoning, translation, and uncertainty handling. You can edit these examples or create categorized prompt sets. Saving a prompt set writes its prompt text to the local catalog. A set run sends each saved prompt sequentially to the currently selected models; the app does not calculate an automatic quality score or call a judge model. When local history is enabled, you can rate each successful answer from 1 to 5; ratings are your own feedback, not an objective model score.

For repeatable records, explicitly enable **local history** in the UI. It is off by default. When enabled, each completed model result writes a local record with the prompt, response, model/connection/protocol, timestamp, latency, token counts, status, and any supported cost estimate. You can then add or change a 1–5 rating per answer (1 = poor, 5 = excellent) and save a preferred answer for a comparison; both are appended as separate history events and merged into exports and summaries. Records are stored at:

    %APPDATA%\Poly-LLM-Hub\history.jsonl

The UI can export the saved records as JSONL or CSV, or clear all history. The history file is not encrypted. Catalog updates use an atomic file replacement; history appends are flushed to disk. If a crash leaves an invalid, incomplete final JSONL line, the app keeps the source file unchanged, excludes that tail from reads/exports, warns in the UI, and blocks further appends so records cannot be concatenated onto the damaged tail. Export the readable records, clear history, then enable history again to resume saving. A failed history write leaves the response available in the current run and shows a recovery message rather than silently discarding it. Clearing history also turns off future saves. Turning the setting off stops future saves but leaves existing records until you clear them. History files contain prompts and responses, so handle and back them up accordingly. Exports use an explicit field allow-list and never include credential values or environment-variable names.

The saved-history summary groups records by model and shows run success, preferred-answer selections out of comparisons where a choice was recorded, average reported latency, average time to first token for streaming runs, token totals, average user rating with the number of rated runs, and the sum of available cost estimates. A success-rate chart shows the saved-run sample count and is not a composite model score. A daily trend chart can show all models together, one selected model, or a prompt category; it plots the latest 30 active UTC dates in the saved-history year with success rate and result count. Category counts are model results, so one prompt can contribute multiple results. A second table compares saved prompt-set runs by prompt and model, with run success, recorded preferred picks, latency, rating, output-token samples, and estimated-cost totals; it does not return saved prompt text. A “no saved choice” or “unknown cost” remains distinct from zero; local runs are labeled as not estimated. Cost totals include only runs with a supported estimate and are not provider invoices.

## Comparison, cancellation, and privacy

Chat is the primary workspace and sends each turn to exactly one active catalog model. You can change models without making a request, then explicitly continue the last user turn with another model if a provider limit or error stops the current model. The transcript stays in the browser session; choose lean context (the latest two completed exchanges plus the current message), balanced context (the latest four exchanges plus the current message), or the full conversation. Provider APIs are stateless, so chosen context is resent on each turn. Lean context can reduce input-token use but may omit older details. No automatic retries or silent failover occur. The chat UI does not edit project files, run terminal commands, or operate a browser like a coding agent.

When a comparison starts, the app sends the same prompt to each selected model through its configured connection. Streaming is enabled by default, so text appears in each result card as it arrives; turn it off in Shared run settings for compatible endpoints that do not support streaming. The page shows each provider/model, destination, status, duration, time to first token when measured, token usage where reported, and errors.

- With history off, prompts and results remain in process memory only. Settled run records, including retry context, expire after 30 minutes and may be evicted sooner when the run cache reaches its size limit. Active runs and cancelled runs with provider calls still pending remain tracked until those calls settle. The prompt is not returned by the run API or written to disk unless history is enabled.
- Browser localStorage contains selected model entry IDs only. Prompts, responses, prompt-set text, and credentials are not stored there.
- The app does not log request bodies, prompts, responses, or credential values.
- Provider API redirects are limited to the configured origin; endpoints that require a cross-origin redirect must be configured using their final API URL.
- Saved OS credentials are read only by the local Python process when a provider request or connection check runs. Removing a saved key removes the local vault entry; it does not revoke the provider's key.
- A remote request sends the prompt to the configured service under that service’s terms and may incur a charge. A local destination sends it to the configured local or loopback server.
- Cancel stops this app from waiting for and accepting late results. The current urllib transport cannot reliably interrupt a request already sent upstream. The provider may continue generation and billing after local cancellation.
- Marking a preferred answer updates the in-memory run record and does not call another model. When local history is enabled for that run, the choice is appended as a separate event and included in saved-history summaries.
- A failed model can be retried only by user action, up to two times per retry chain. Only one retry for a failed result can run at a time; another retry is available after it settles. Each retry sends a new provider request and may incur another charge. Retries honor the current history setting and are blocked if the model or endpoint configuration changed. Response synthesis, automatic routing, agent CLI execution, and provider policy/license engine are not implemented.

## Cost estimates

An estimate uses:

    (input tokens × input USD per million + output tokens × output USD per million) ÷ 1,000,000

The page labels cost “unknown” if exact-model rates or either token count is missing or invalid. Local runs show “Not estimated for local run.” Each estimate links to the manually entered source and checked date. Prices older than 90 days are marked stale in result cards and counted separately in history summaries; the estimate is still shown with that warning. Future checked dates are rejected. Provider discounts, cached tokens, tiers, taxes, and final billing adjustments may differ from this estimate. The app does not fetch or refresh prices automatically.

## Coding-agent CLIs

The app can detect a few CLI executables on PATH, but detection is informational only. It does not connect to or launch coding-agent CLIs. A CLI agent is not treated as an ordinary text-completion API.

## Consolidated workspace architecture

The dynamic connection/model catalog in `hub_core.py` is the source of truth for endpoints and exact model IDs. Built-in provider help links live separately in `provider_metadata.py`; custom connections remain user-configurable. See [the architecture guide](docs/ARCHITECTURE.md), [the provider guide](docs/ADDING_PROVIDER.md), [the release checklist](docs/RELEASE_CHECKLIST.md), [the consolidation notes](docs/CONSOLIDATION.md), and [the security review](docs/SECURITY_REVIEW.md) for module boundaries, extension steps, release gates, and limitations.

## Tests

The repository includes 43 Python unittest cases with temporary loopback mock servers; they do not call live providers or require real API credentials. Most recently, all 43 passed on Windows with Python 3.10 on 2026-11-24. The suite covers JSON and streaming response bounds, discovery pagination/metadata, provider adapters and multi-turn chat role mapping, local API origin checks, a hash-restricted script CSP, credential non-disclosure across catalog and export routes, bounded per-run parallelism, streamed cancellation races, history event folding/exports, run retention, mocked Windows/Linux/macOS credential-store round trips, and source-archive determinism and secret/path rejection. Mocked vault tests do not replace manual platform review. The GitHub Actions workflow is configured to run the suite, Python compilation, browser-script syntax/runtime checks, and source-archive build on Ubuntu and Windows with Python 3.10 and 3.12; a hosted workflow run is still needed before claiming CI is green. The integrated Windows credential UI and Linux/macOS vault flows still need manual platform review.

    python -m unittest discover -s tests -v

## Current limits

The adapters send one user message using basic protocol request shapes and support optional per-comparison output caps. Streaming is available for OpenAI-compatible, Anthropic Messages, Gemini, and Ollama chat endpoints. Temperature, other provider-specific generation parameters, images, tool use, provider-side cancellation, and all non-chat endpoints are not implemented. A provider’s model list may include IDs that the account cannot use or that do not support the chosen endpoint. Always verify access, exact IDs, model terms, and billing with the provider before relying on a live connection.
