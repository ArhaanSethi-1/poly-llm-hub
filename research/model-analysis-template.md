# Reusable model/service briefing prompt

Copy this prompt into a separate research run and replace the placeholders. Use a distinct profile for a provider model, a consumer product, a CLI agent, or a local inference runtime; do not treat them as the same thing.

---

You are a knowledgeable AI-technology analyst. Prepare a comprehensive, technical, practical overview of the AI model or service **~BT~{MODEL_NAME_OR_SERVICE}~BT~** for the Poly‑LLM Hub project.

Research snapshot date: **~BT~{AS_OF_DATE}~BT~**  
Service type: **~BT~{MODEL / API / CONSUMER APP / CLI AGENT / LOCAL RUNTIME}~BT~**  
Target platform or API, if known: **~BT~{PLATFORM_OR_ENDPOINT}~BT~**

Write for a senior software engineer. Use clear headings, concise bullets, and Markdown links to official sources. Separate verified facts from interpretation. For information not publicly disclosed in the official materials reviewed, write **“not publicly disclosed”**. Do not infer parameter counts, architecture, training data volume, or exact latency.

Cover:

## 1. Model architecture and algorithms

- Model family and architecture type, if disclosed: decoder-only, encoder-decoder, MoE, multimodal, or other.
- Parameter count, active parameters, layers, hidden dimensions, or context mechanisms, if disclosed.
- Publicly described innovations, training objectives, post-training, reinforcement learning, retrieval, or tool-use mechanisms.
- Clearly distinguish model details from API and serving-system features.

## 2. Training data and process

- Publicly stated data sources and modalities.
- Approximate token or document volume, if disclosed.
- Publicly stated filtering, deduplication, and data-processing methods.
- Post-training stages and safety training.
- Mark provider-level disclosures separately from model-specific disclosures.

## 3. Capabilities and strengths

- Intended workloads and supported input/output modalities.
- Tools, function calling, structured output, vision, audio, video, search, or computer-use support.
- Official benchmark results with benchmark version, date, and stated harness/settings.
- Label provider-reported results as provider-reported; do not present them as independent comparisons.

## 4. Limitations and known issues

- Published limitations, failure modes, safety findings, hallucination and cutoff information.
- Context-window and output-limit behavior.
- API or CLI compatibility gaps, deprecated endpoints, known timeouts, or unsupported parameters.
- Distinguish documented model limitations from generic LLM limitations.

## 5. API and integration details

- Canonical endpoint and API/SDK/CLI options.
- Required request fields, common parameters, streaming format, token usage, and stop/error signals.
- Minimal cURL or SDK example using an environment variable placeholder; never include a real key.
- For a CLI, show its documented non-interactive mode and machine-readable output, if available.
- Identify whether calls may invoke tools, read/write files, or execute commands.

## 6. Pricing, limits, and quotas

- Current free, paid, and enterprise access options.
- Input/output price per 1 million tokens and converted price per 1,000 tokens; include caches, long-context premiums, tool fees, or time-of-day pricing where relevant.
- Rate limits, concurrency, and billing tiers. If account-dependent, say so rather than inventing a universal limit.
- State the date checked and link the live pricing/rate-limit page.
- Mark typical latency “not publicly disclosed” unless a source gives a comparable measured value.

## 7. Security, privacy, and compliance

- Whether inputs/outputs are used for training and under which product tier or account settings.
- Retention period, application-state storage, abuse-monitoring logs, zero-data-retention eligibility, and feature exceptions.
- On-device/on-premises options and regional processing options.
- Publicly documented compliance claims and their scope; do not imply that a model itself is certified.
- Distinguish consumer product terms from commercial API terms.

## 8. Versioning and roadmap

- Current model ID and release date.
- Stable, preview, deprecated, or restricted-access status.
- Model alias versus pinned snapshot behavior.
- Announced changes and shutdown/deprecation dates. Do not speculate about unannounced roadmaps.

## 9. Fit for Poly‑LLM Hub

- Best integration surface for a basic prompt/response adapter.
- Authentication mechanism and environment-variable name.
- Provider-specific request/response translation needs.
- Streaming, retries, cancellation, rate limits, context constraints, and error mapping.
- Risks of wrapping a coding-agent CLI when a direct inference API exists.
- A short recommendation for an MVP adapter and the tests that should measure behavior.

## 10. Quick-reference table

Include: service/model ID, model or service type, input/output modalities, parameter count (or “not publicly disclosed”), context window, maximum output, current input/output cost per 1,000 tokens, typical latency (or “not publicly disclosed”), version/release date, and best-fit workload.

## Source rules

- Prefer first-party documentation, model cards/system cards, release notes, pricing pages, API references, and terms.
- Cite each time-sensitive or technical claim at the point where it appears.
- Record sources with access date.
- Where only the provider’s own evaluation exists, state that.
- Do not copy long passages from sources; summarize them.
- If a source is unavailable or ambiguous, list the uncertainty and leave the fact unresolved.


