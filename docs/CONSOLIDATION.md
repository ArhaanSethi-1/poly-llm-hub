# Consolidated project folder

This folder is the single reviewable Poly-LLM Hub source tree created for the user's request to combine the project work.

## Source material brought together

- The newer `poly-llm-hub-ready` implementation supplied the dynamic connection/model catalog, provider protocol adapters, prompt sets, comparison runs, cancellation, response usage and cost estimates, opt-in local history, exports, and the existing mock-server test suite.
- The earlier `AI UI` workspace supplied the durable project log, security review, provider onboarding notes, and research records.
- The Gemini scratch review supplied the Windows Credential Manager flow, native key-entry window, connection-check interaction, clipboard action, stricter request content type, local Host validation, and shutdown cleanup. These were adapted to the dynamic connection catalog here.
- A later Gemini review copy had the same project file set and added run-memory pruning, a worker/run synchronization fix, CSV formula-injection protection, a configurable Anthropic output limit, and matching regression cases. Those improvements are incorporated here.
- The earlier product vision and CLI/fusion/policy/desktop-release goals are carried into the README and roadmap. Its initial React Native/Express code snippets were conceptual sketches and are superseded by the current Python architecture.

## Architecture decisions

- `hub_core.py` remains the source of truth for provider connections, model entries, protocol behavior, catalog validation, comparisons, and history. User-defined connections remain first-class.
- The scratch `providers.py` duplicated a fixed list of provider endpoints and could not represent the newer user-configurable catalog. Its useful key-creation and documentation links are represented by `provider_metadata.py`; adapter configuration remains in each dynamic catalog connection.
- Windows keys are keyed by connection ID in Credential Manager. Environment-variable fallback remains available for development and non-Windows use.
- The provider test is a model-list request and does not generate a response.
- Provider errors remain generic and sanitized. The newer source's raw exception text was not imported because provider/library exceptions can contain sensitive request details.
- Removing a custom connection still fails safely if Credential Manager cannot be read or cleaned up; the newer source's alternate path could leave an unreferenced saved credential behind.

## What was intentionally excluded

- `.git` directories and commit histories from the source folders: this review folder is a consolidated source copy, not a rewritten or pushed Git history.
- Runtime user data, credentials, generated archives, caches, and prior ZIP files. No API key was copied.
- The older single-purpose static-provider app. Its useful onboarding and security behavior was integrated into the dynamic architecture instead of replacing it.

## Source and destination notes

- The consolidated source tree was copied into the canonical repository checkout while preserving its `.git` directory.
- The earlier workspace and Gemini review copies were left untouched; runtime data, credentials, generated archives, caches, and prior ZIPs were excluded.

The source folders are preserved. The repository's `.git` directory and remote history remain in place; reviewed project files were overlaid onto the checkout for review.
