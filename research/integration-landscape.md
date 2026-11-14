# Integration landscape and early product findings

Snapshot: 2026-11-14. This is an initial survey of first-party documentation, not a complete market or legal review.

## Three integration classes

| Class | Examples | What the hub integrates | Main constraints |
|---|---|---|---|
| Provider inference API | OpenAI Responses, Anthropic Messages, Gemini Interactions, xAI Responses, DeepSeek Responses/Chat | Send a canonical message and parse a provider-native response | Separate auth, request/response dialects, tool support, price/rate rules, retention policies |
| Local inference server | Ollama, LM Studio, Jan | Localhost HTTP API; usually an OpenAI-compatible subset, sometimes an Anthropic-compatible endpoint | Server may not be running; local model IDs/capabilities vary; local and cloud modes must be distinguished |
| Coding-agent CLI | Codex CLI, Claude Code, Gemini CLI, Google Antigravity CLI | Spawn a headless agent process and parse stdout/events | May read/write a workspace, run tools, keep session state, request permissions, or act beyond single-turn chat |

Treating these as one generic “model CLI” would hide important differences. A response from a coding-agent harness may include project context, tool results, or policy prompts that a direct inference API does not.

## First-party command and API evidence

| Service | Documented programmatic route | Output / compatibility | Hub implication |
|---|---|---|---|
| OpenAI API | Official `openai` CLI for REST API operations; direct Responses API is available. Codex is a separate coding-agent CLI. | OpenAI CLI supports JSON/JSONL output options; Codex `exec` can stream events as JSONL. | Keep OpenAI API and Codex agent adapters separate. `openai api chat.completions` in the supplied roadmap is not supported by the current OpenAI CLI reference. |
| Claude | Claude Code supports `claude -p` and text, JSON, or stream-JSON output. Direct Claude API uses Messages. | Native Anthropic Messages schema differs from OpenAI Responses/Chat Completions. | Prefer Messages API for plain chat; use Claude Code adapter only when the user intentionally selects the agent harness. |
| Gemini | Gemini API; Gemini CLI supports `-p` and JSON/stream-JSON output. | CLI headless output includes response and usage; streaming can include tool-use events. | Use Gemini API for clean inference comparisons; label CLI agent runs and block tool execution unless the user selected agent behavior. |
| Google Antigravity | `agy -p` supports JSON/stream-JSON and JSON-schema output. | Headless output includes agent/run metadata; tool permissions and workspace context matter. | This is an agent CLI, not simply a Gemini model alias. Record CLI/model IDs and working directory in each run. |
| xAI / Grok | Official Responses API; OpenAI-compatible REST surface. Chat Completions is documented as legacy. | Responses is recommended for new integrations, especially reasoning/tool use. | Implement Responses first; keep `grok-4.7` model and price thresholds in live configuration. |
| DeepSeek | OpenAI-compatible and Anthropic-compatible APIs; Responses API supported for the current Flash model. | DeepSeek Responses is stateless; send conversation history on each call. | Model and endpoint are API-first. The older roadmap's `anthropic` command is not supported by current official docs reviewed. |
| Ollama | Local API normally at `http://localhost:11434/api`; OpenAI-compatible and Anthropic-compatible routes are documented. | Same software can also access Ollama cloud, which is a different data/cost path. | Mark provider mode as local or cloud; discover model IDs through the local model-list endpoint rather than a hardcoded file path. |
| LM Studio | Local developer server; OpenAI-compatible, Anthropic-compatible, and native APIs. | OpenAI-compatible endpoints include Responses, Chat Completions, embeddings, and other APIs. | Detect a configured local server and its model list; don't assume an installed desktop app is serving requests. |
| Jan | Local API defaults to `http://127.0.0.1:1337/v1`; OpenAI-compatible and Anthropic-compatible routes. | Supports chat completions, streaming, tools, and model listing. | Another local server path; this project should not require the Jan CLI if the API is enabled. |

## Notes from the supplied roadmap

- Client detection using `where` works only on Windows. Cross-platform discovery should use platform-aware PATH resolution and then verify the executable with a documented, low-risk version/help check.
- Current official OpenAI CLI documentation describes the `openai` API command. The coding-agent executable is `codex`. They solve different jobs.
- Current Claude Code docs show `claude`, not an `anthropic completion` executable.
- Gemini and Antigravity both document machine-readable headless modes. Those formats can reduce fragile terminal scraping, but tool events and agent state still need to be represented explicitly.
- Avoid passing arbitrary prompt text into shell command strings. Use an argument array or stdin with a timeout and output-size cap. For headless agent CLIs, use an isolated working directory and an explicit tool/permission policy.
- The roadmap's fixed `file:///C:/.../models.json` UI fetch will not be a portable way to load configuration in a cross-platform desktop app. Let the local dispatcher expose discovery results through a bounded local API or IPC.

## Adjacent tools and product space

This is a starting map, not an exhaustive competitor audit.

- OpenRouter offers one OpenAI-compatible API across many hosted providers/models and provider routing. It competes with the “one model selector / many hosted models” part of the concept, but it is not a local installed-CLI discovery product.
- LiteLLM is a self-hosted OpenAI-compatible gateway with provider routing, fallbacks, virtual keys, spend tracking, and guardrails. It can cover much of the backend gateway layer.
- Jan, LM Studio, and Ollama already expose local model runtimes or local HTTP endpoints and may connect to cloud providers. Their docs reinforce that local inference and cloud inference are separate privacy and cost modes.
- A promising product distinction is an inspectable desktop comparison workflow that connects user-owned credentials and local runtimes, reports the actual execution path, and records comparable cost/latency/quality measurements. Validate this through the empirical study before treating it as a market differentiator.

## Early architecture recommendation

1. Define a provider-neutral prompt and result schema for ordinary inference. Preserve provider-specific options under a namespaced extension rather than silently dropping them.
2. Build separate adapter interfaces for: provider API, local HTTP inference server, and agent CLI.
3. Make capability support explicit: streaming, structured output, vision, tools, cancellation, usage, cost, and server-side state.
4. Store per-provider configuration and model IDs separately from client executable discovery.
5. On each request, disclose the route in the research record: provider, model ID, local/cloud, API/CLI, and the CLI or API version if available.
6. Add concurrency limits, timeout handling, bounded output buffers, cancellation, and rate-limit retry behavior to the dispatcher.
7. Treat provider policy configuration as versioned source-linked metadata with “last checked” dates. A static universal policy.json cannot prove that every user’s account, region, or plan permits a particular usage.

## Official source links

- [OpenAI CLI reference](https://developers.openai.com/api/reference/cli)
- [OpenAI CLI output formats and API usage](https://developers.openai.com/api/docs/libraries/openai-cli)
- [Codex CLI reference](https://learn.chatgpt.com/docs/cli/reference)
- [Claude Code CLI usage](https://docs.anthropic.com/en/docs/claude-code/cli-usage)
- [Claude Messages API](https://platform.claude.com/docs/en/api/messages/create)
- [Gemini CLI headless mode](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/headless.md)
- [Gemini Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview)
- [Antigravity CLI headless mode](https://antigravity.google/docs/cli/headless/)
- [xAI Grok 4.7 developer guide](https://docs.x.ai/developers/grok-4-7)
- [DeepSeek API integration guide](https://api-docs.deepseek.com/quick_start/agent_integrations/)
- [Ollama API introduction](https://docs.ollama.com/api/introduction)
- [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)
- [LM Studio API server](https://lmstudio.ai/docs/developer/core/server)
- [LM Studio OpenAI-compatible endpoints](https://lmstudio.ai/docs/developer/openai-compat)
- [Jan local API server](https://docs.jan.ai/desktop/api-server)
- [OpenRouter developer platform](https://openrouter.ai/developers)
- [LiteLLM proxy overview](https://docs.litellm.ai/docs)

