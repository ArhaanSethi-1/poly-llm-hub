# Consolidated project folder

This folder is the single reviewable Poly-LLM Hub source tree created for the user's request to combine the project work.

## Source material brought together

- The newer `poly-llm-hub-ready` implementation supplied the dynamic connection/model catalog, provider protocol adapters, prompt sets, comparison runs, cancellation, response usage and cost estimates, opt-in local history, exports, and the existing mock-server test suite.
- The earlier `AI UI` workspace supplied the durable project log, security review, provider onboarding notes, and research records.
- The Gemini scratch review supplied the Windows Credential Manager flow, native key-entry window, connection-check interaction, clipboard action, stricter request content type, local Host validation, and shutdown cleanup. These were adapted to the dynamic connection catalog here.
- The newer Gemini complete folder at `C:\Users\arhaa\.gemini\antigravity\brain\477ddf6f-553a-4f95-a28a-2462d650271c\scratch\poly-llm-hub-complete\Poly-LLM-Hub-complete` has the same project file set and adds run-memory pruning, a worker/run synchronization fix, CSV formula-injection protection, a configurable Anthropic output limit, and matching regression cases. Those improvements are incorporated here.
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

## Source and destination paths

- Consolidated folder: `C:\Users\arhaa\Documents\ChatGPT\AI UI\poly-llm-hub-complete`
- Canonical GitHub Desktop checkout targeted for the reviewed copy: `C:\Users\arhaa\Documents\GitHub\poly-llm-hub-ready`
- Gemini scratch source, left untouched: `C:\Users\arhaa\.gemini\antigravity\brain\477ddf6f-553a-4f95-a28a-2462d650271c\scratch\poly-llm-hub\Poly-LLM-Hub-review`
- Newer Gemini complete source, left untouched: `C:\Users\arhaa\.gemini\antigravity\brain\477ddf6f-553a-4f95-a28a-2462d650271c\scratch\poly-llm-hub-complete\Poly-LLM-Hub-complete`
- Earlier AI UI workspace source files and user artifacts were left in place; this consolidated child folder and its review ZIP were added: `C:\Users\arhaa\Documents\ChatGPT\AI UI`

The source folders are preserved. The GitHub checkout's `.git` directory and remote history are kept in place; the reviewed files from this consolidated tree are overlaid onto that checkout for the requested push.
