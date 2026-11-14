# Poly-LLM Hub: three parallel research prompts

Use one prompt per model or research agent. Each prompt is standalone. Run them in parallel, then bring the three reports back together for review. They ask for research and an empirical-data plan; they do not authorize paid API calls or claim that model runs have happened.

## Prompt 1 — Model technology and capability profiles

You are a careful AI model analyst supporting **Poly-LLM Hub**, a planned cross-platform desktop app for connecting hosted AI APIs, local model servers, and selected agent CLIs. The goal is to gather trustworthy information before implementation.

Research the latest generally available API model from each of these provider families as of **2026-11-14**: OpenAI, Anthropic, Google Gemini, xAI Grok, and DeepSeek. Verify the current model IDs and release dates from official sources; if the date or availability differs by region, tier, or preview status, say so. Do not assume a candidate model is current without checking.

For each model, cover:

1. Model family/architecture and algorithms: decoder-only, encoder-decoder, MoE, multimodal design, reasoning/training approach, and known special techniques.
2. Parameter count, layer details, hidden size, context length, and training volume/data sources. Mark each item **not publicly disclosed** if the provider has not disclosed it. Distinguish exact evidence from inference.
3. Published capabilities and provider-reported benchmark results, including benchmark version/date and caveats about harnesses or self-reported scores.
4. Practical strengths, limitations, known failure modes, multimodal/tool support, and important safety or alignment disclosures.
5. Versioning, release date, model lifecycle/deprecation details, and announced roadmap items.

Use official model cards, system cards, release notes, and developer documentation as primary sources. Cite direct URLs next to claims. Do not invent facts or silently substitute third-party estimates for provider disclosures. Finish with a concise comparison table: provider, model ID, context, input/output modalities, public architecture details, likely strengths, and key caveat. Save/return the report as Markdown named `research/01-model-technology.md` if you can edit the project; otherwise return the complete Markdown text for that file.

## Prompt 2 — APIs, integration, cost, privacy, and operations

You are a senior integration researcher for **Poly-LLM Hub**, a planned cross-platform desktop app. Research the current official integration options as of **2026-11-14**. Cover hosted model APIs for OpenAI, Anthropic, Google Gemini, xAI, and DeepSeek; local inference servers Ollama, LM Studio, and Jan; and agent CLIs Codex, Claude Code, Gemini CLI, and Google Antigravity where official headless use is documented.

For each relevant service, report:

- Recommended API/CLI, base URL or command, authentication method and environment-variable convention.
- Minimal valid request shape and response/streaming format. Include a short safe example with placeholder credentials only.
- Supported features and parameters: streaming, tools/function calls, structured output, images/audio/video, cancellation, token usage, and server-side state. Mark unsupported or undocumented capabilities clearly.
- Current price, cache/long-context tiers, rate-limit model, and quota behavior. Include source date, units, and per-1K-token conversion when possible. Mark account-dependent values as variable.
- Prompt retention, training use, zero-retention options, data residency, encryption/deployment choices, and publicly stated compliance certifications. Distinguish consumer products from API terms.
- Common errors/retry guidance and a practical fallback approach for a multi-provider dispatcher.

Explain why ordinary inference APIs, localhost model servers, and coding-agent CLIs need separate adapter types. Note agent side effects such as workspace reads/writes, command execution, tool approvals, and session state. Use official docs and policy pages as primary sources, cite direct URLs, and mark information that is not publicly disclosed. Do not copy or request real credentials, execute commands, call model APIs, or claim to have tested a provider. Return a Markdown report named `research/02-integration-operations.md` if you can edit the project; otherwise return complete Markdown text for that file.

## Prompt 3 — Empirical comparison and data collection design

You are an evaluation-methods researcher helping **Poly-LLM Hub** compare models fairly before the app is built. Design a small, repeatable empirical study that can be run across hosted APIs and local model servers without confusing API performance with coding-agent behavior.

Deliver:

1. A practical protocol for selecting model/version IDs, keeping prompts and parameters identical where possible, setting deterministic or low-variance settings, doing repeated trials, randomizing run order, recording timestamps, and handling timeouts/rate limits.
2. A balanced original prompt set with at least 24 prompts across eight categories: arithmetic/math, instruction following, structured extraction, summarization, coding, translation, reasoning, and uncertainty/abstention. Keep tasks self-contained, avoid up-to-date factual questions, and provide expected answers or explicit scoring rubrics. Do not copy benchmark questions from proprietary datasets.
3. A JSONL schema for each prompt and each run, including prompt/model/provider/interface/version, parameters, UTC start time, latency and time-to-first-token, input/output token usage, estimated cost, response or secure response-file reference, finish/error status, and rubric scores. Never include API keys.
4. A scoring plan for correctness, instruction adherence, format validity, uncertainty handling, latency, reliability, and cost. Separate human-rated quality from objective checks, explain evaluator bias, and do not use one model as the sole judge without calibration.
5. A privacy, safety, licensing, and data-retention plan for prompts and raw outputs. Explain how to label source (API, local server, or agent CLI), prevent accidental workspace/tool side effects, and report missing data fairly.
6. A results-table template and a clear list of what evidence the study will and will not support.

Do not make any provider calls, use paid credits, fabricate measurements, or claim that results exist. Provide only the design and original prompts so the project owner can approve and run the study later. Return a Markdown report named `research/03-empirical-study.md` and, if possible, a separate original prompt corpus at `data/benchmark-prompts-v1.jsonl`; otherwise provide complete Markdown and valid JSONL text. Cite methodological or provider-policy claims with authoritative sources.
