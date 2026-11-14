# Poly-LLM Hub

Poly-LLM Hub is a local model workbench for configuring provider connections, maintaining your own exact model catalog, and comparing selected models on the same prompt. Its focus is flexible model management and evidence-based comparison; it does not claim a universal “best model” score.

The longer-term product goal is one clear interface for hosted APIs, local inference servers, and carefully isolated coding-agent integrations. It should show which provider, model, and destination handle each request, then help the user compare reliability, latency, usage, cost, and quality from repeatable empirical runs. Provider-specific limitations and data handling should remain visible.

## Current implementation

This iteration provides:

- A configurable catalog that keeps provider connections separate from model entries. One connection can contain multiple models.
- Built-in starter connections for OpenAI Chat Completions, Anthropic Messages, Gemini generateContent, xAI and DeepSeek OpenAI-compatible APIs, and local Ollama.
- User-defined OpenAI-compatible endpoints, including loopback services. A compatible endpoint may implement only part of the protocol; confirm its behavior and enter the exact model ID it expects.
- Explicit model discovery and manual model entry when discovery is unavailable or incomplete.
- Search, favorites, tags, capabilities, optional limits, and exact-model pricing metadata.
- Side-by-side comparisons of up to five catalog entries, with up to three active comparisons and three provider calls per comparison.
- Cancellation, preferred-answer marking, categorized prompt sets, sequential prompt-set runs, and opt-in local run history.
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

These adapters were verified against local mock servers only. No live provider calls have been made from this project. Gemini generateContent remains implemented for compatibility; current Gemini documentation recommends the newer Interactions API for new projects, so check the provider docs before extending this adapter. [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) · [OpenAI model listing](https://developers.openai.com/api/reference/resources/models/methods/list) · [Anthropic Messages](https://docs.anthropic.com/en/api/messages) · [Gemini generateContent](https://ai.google.dev/api/generate-content) · [Gemini model listing](https://ai.google.dev/api/models) · [Gemini API overview](https://ai.google.dev/gemini-api/docs) · [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md)

## Run locally

Requirements: Python 3.10 or later. The app uses only the Python standard library.

1. Open PowerShell in the repository folder.
2. Start the server:

       python app.py

3. Open http://127.0.0.1:8765 in a browser.
4. Add model entries through discovery or by entering the exact model ID.
5. Select models, review the displayed destinations, enter a prompt, and run the comparison.

Stop the server with Ctrl+C. The server binds to 127.0.0.1.

## Connections and model catalog

The initial catalog includes common provider connections. Edit a connection to change its base URL or optional environment-variable fallback, or add another connection using one of the supported protocols. Connections are stored separately from exact model IDs, so each connection can contain multiple models.

On Windows, use **Connect key** on a connection. A native masked dialog writes the key directly to the current user's Windows Credential Manager. The browser sends only the connection ID to the local app; the key is not submitted through JavaScript, placed in the catalog, passed in command-line arguments, or written to logs. **Get API key** and **Provider docs** links are shown for built-in providers. A saved vault key takes precedence over an environment-variable fallback.

Windows PowerShell fallback examples:

    $env:OPENAI_API_KEY = "your-key"
    $env:ANTHROPIC_API_KEY = "your-key"
    $env:GEMINI_API_KEY = "your-key"
    $env:XAI_API_KEY = "your-key"
    $env:DEEPSEEK_API_KEY = "your-key"

Set a key in the same shell before starting the app. On macOS/Linux, native credential dialogs are not implemented yet, so use environment variables if you run the app there. Do not paste API keys into the browser or save them in project files.

Each cloud API needs its own provider account and credential. Google sign-in does not connect OpenAI, Anthropic, xAI, or DeepSeek. Gemini uses a Google AI Studio API key in this build; Google OAuth and a shared Poly-LLM Hub account are not configured. Ollama is local and usually needs no cloud key.

**Test connection** makes a provider model-list request and sends no prompt or generated-content request. Some compatible endpoints do not implement model listing; add the exact model ID manually in that case. A successful model-list check does not guarantee that every model ID is available to your account.

Remote connection URLs must use HTTPS. Plain HTTP is accepted only for loopback names or addresses such as localhost and 127.0.0.1. Non-loopback HTTP endpoints are rejected. The UI labels loopback destinations as local and other destinations as remote. Discovery runs only after you click Discover models and sends no prompt. When discovery is unsupported, add the provider’s exact model ID manually.

Model IDs, names, tags, capability metadata, and optional prices are stored separately from provider connections. Capability values remain “unknown” unless you enter known information. Price metadata requires exact-model input and output USD rates per million tokens, an HTTPS source URL, and a checked date.

The local catalog is stored at:

    %APPDATA%\Poly-LLM-Hub\catalog.json

This JSON file contains provider/model configuration, environment-variable names, and any prompt sets you explicitly save. It may contain your saved prompt-set text, but not run responses or credential values. It is not encrypted. Windows Credential Manager stores saved API keys separately. The OS protects those credentials at rest for the current user; software already running as that user may still be able to use them.

## Prompt sets and empirical comparisons

The workbench includes original starter prompts for instruction following, structured extraction, summarization, coding, reasoning, translation, and uncertainty handling. You can edit these examples or create categorized prompt sets. Saving a prompt set writes its prompt text to the local catalog. A set run sends each saved prompt sequentially to the currently selected models; it does not calculate a quality score or call a judge model.

For repeatable records, explicitly enable **local history** in the UI. It is off by default. When enabled, each completed model result writes a local record with the prompt, response, model/connection/protocol, timestamp, latency, token counts, status, and any supported cost estimate. Records are stored at:

    %APPDATA%\Poly-LLM-Hub\history.jsonl

The UI can export the saved records as JSONL or CSV, or clear all history. The history file is not encrypted. Clearing history also turns off future saves. Turning the setting off stops future saves but leaves existing records until you clear them. History files contain prompts and responses, so handle and back them up accordingly. Exports use an explicit field allow-list and never include credential values or environment-variable names.

## Comparison, cancellation, and privacy

When a comparison starts, the app sends the same prompt to each selected model through its configured connection. The page shows each provider/model, destination, status, duration, token usage where reported, and errors.

- With history off, prompts and results remain in process memory only. In-memory run records are pruned after 30 minutes.
- Browser localStorage contains selected model entry IDs only. Prompts, responses, prompt-set text, and credentials are not stored there.
- The app does not log request bodies, prompts, responses, or credential values.
- Saved Windows credentials are read only by the local Python process when a provider request or connection check runs. Removing a saved key removes the local vault entry; it does not revoke the provider's key.
- A remote request sends the prompt to the configured service under that service’s terms and may incur a charge. A local destination sends it to the configured local or loopback server.
- Cancel stops this app from waiting for and accepting late results. The current urllib transport cannot reliably interrupt a request already sent upstream. The provider may continue generation and billing after local cancellation.
- Marking a preferred answer updates the in-memory run record and does not call another model.
- No streaming, retry button, response synthesis, automatic routing, agent CLI execution, or provider policy/license engine is implemented.

## Cost estimates

An estimate uses:

    (input tokens × input USD per million + output tokens × output USD per million) ÷ 1,000,000

The page labels cost “unknown” if exact-model rates or either token count is missing. Local runs show “Not estimated for local run.” Each estimate links to the manually entered source and checked date. Provider discounts, cached tokens, tiers, taxes, and final billing adjustments may differ from this estimate. The app does not fetch or refresh prices automatically.

## Coding-agent CLIs

The app can detect a few CLI executables on PATH, but detection is informational only. It does not connect to or launch coding-agent CLIs. A CLI agent is not treated as an ordinary text-completion API.

## Consolidated workspace architecture

The dynamic connection/model catalog in `hub_core.py` is the source of truth for endpoints and exact model IDs. Built-in provider help links live separately in `provider_metadata.py`; custom connections remain user-configurable. This keeps the newer dynamic architecture while carrying forward the useful setup links and secure-key onboarding from the earlier prototype. See `docs/CONSOLIDATION.md` for the source folders and merge decisions, and `docs/SECURITY_REVIEW.md` for the security boundaries and remaining limits.

## Tests

The repository includes 21 Python unittest cases with temporary loopback mock servers; they do not call live providers or require real API credentials. The earlier checkout's project log records an 18-test pass; three additional cases cover a custom Anthropic output limit, CSV formula injection, and run-memory pruning. The suite has not been run against this consolidated copy, and the integrated Windows credential UI needs its own manual review.

    python -m unittest discover -s tests -v

## Current limits

The adapters send one user message using basic protocol request shapes. Provider-specific parameters, streaming, images, tool use, provider-side cancellation, and all non-chat endpoints are not implemented. A provider’s model list may include IDs that the account cannot use or that do not support the chosen endpoint. Always verify access, exact IDs, model terms, and billing with the provider before relying on a live connection.
