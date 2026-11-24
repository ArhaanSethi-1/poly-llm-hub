# Poly-LLM Hub project log

This is the durable activity record for the consolidated project. New entries belong at the top under **Current consolidated activity**. The source histories are preserved below so earlier decisions and actions are not lost. Historical path references describe where work happened at that time; the active checkout is `the canonical repository checkout`.

## Current consolidated activity

### 2026-11-24 — Add agent-first single-model chat

- Reshaped the browser UI into a local agent workspace with Chat as the primary view and the original side-by-side comparison retained as a secondary mode.
- Added multi-turn chat over all four provider protocols. One chat turn targets one catalog model; changing the active model makes no API request. Users may explicitly resend a failed turn to another model, with the chosen recent/full transcript context. No automatic failover or retry occurs.
- Chat context is bounded to 32 messages and 32,000 characters and remains in browser memory unless opt-in history is enabled. Lean/balanced windows reduce repeated input context; the provider APIs remain stateless, so selected context is resent per turn. The UI does not execute coding-agent tools, edit files, or run terminal commands.
- Added provider role-mapping and API validation coverage. All 43 Python tests pass on Windows with Python 3.10; Python compilation, browser-script syntax/runtime checks, and `git diff --check` pass. The preview is running at localhost with a fresh isolated catalog; no provider key or prompt was used.

### 2026-11-24 — Build a privacy-checked source archive

- Replaced machine-specific paths and account identifiers in consolidation/activity notes with neutral descriptions. Added `scripts/build_source_archive.py`, which packages a fixed 21-file product allowlist, rejects common credential signatures and absolute user paths, and writes a byte-reproducible ZIP with fixed metadata.
- The archive deliberately omits Git history, the project activity log, local research inventory, local catalogs/history, caches, and build output. CI now builds the same source archive on its OS/Python matrix.
- Added determinism/member-list and scanner-rejection tests. The complete suite passes with 41 tests; Python compilation and browser syntax/runtime checks pass.
- Rebuilt the local review artifact after adding single-model chat at `dist/Poly-LLM-Hub-0.2.0-source.zip` (380,505 bytes; SHA-256 `afa74621db36b47ae22dd928eda23fcce185a053ea1271954a39aac35cfca0dd`). It has not been published.

### 2026-11-24 — Verify credential non-disclosure at API boundaries

- Added a sentinel-key test that mocks a successful vault read and verifies `/api/catalog` reports only credential status. The sentinel is absent from the catalog response, catalog backup, JSONL history export, and CSV history export.
- The complete Python suite passes with 39 tests on Windows with Python 3.10. The test performs no real vault operation and makes no provider request.
- Updated README and roadmap evidence.

### 2026-11-24 — Restrict inline script execution with a CSP hash

- Replaced `script-src 'unsafe-inline'` with the SHA-256 hash of the single served UI script. Added `object-src 'none'`, `base-uri 'none'`, same-origin form restriction, and frame denial while retaining inline styles required by the existing page.
- Added an HTTP route test for the emitted policy. The full suite passes with 38 tests; Python compilation and browser script syntax/runtime checks pass.
- The CSP hash is computed from the served HTML at startup with browser line-ending normalization, so source edits do not require a hand-maintained digest.

### 2026-11-24 — Smoke the clean application startup

- Started `python app.py` with a temporary empty catalog outside the project data directory. `GET /` returned HTTP 200 with the workbench title and history/streaming controls; `GET /api/catalog` returned zero connections, zero models, and history disabled.
- No provider endpoints or credential vaults were accessed. Stopped the server, removed the isolated catalog directory, and verified port 8765 had no remaining listener.
- Added the isolated startup smoke to the release checklist. This confirms serving/API startup but does not replace rendered browser review.

### 2026-11-24 — Verify streamed cancellation races

- Added a deterministic two-model race test: both streams emit partial text, the run is cancelled, then late stream callbacks and successful provider results arrive. The test confirms those late updates are discarded, cancelled cards remain result-free, and pending-call counts drain after settlement.
- The complete Python suite passes with 37 tests on Windows with Python 3.10. Removed the remaining listed cancellation-race test gap from the roadmap.

### 2026-11-24 — Run browser preference recovery checks in Node

- Extended `scripts/check_inline_js.py` to execute the selected-model storage loader against valid arrays with invalid entries, malformed JSON, unexpected JSON types, and storage access failure.
- The check uses Node's built-in VM and assertion modules, so it adds no package dependency and remains part of the cross-platform CI job. It passed on the current Windows checkout.
- Updated README and roadmap evidence. Rendered browser interaction remains unverified.

### 2026-11-24 — Exercise credential-store adapters without real keys

- Added mocked round-trip tests for Windows Credential Manager, Linux Secret Service, and macOS Keychain. They verify connection IDs are hashed in vault targets and provider keys are passed through platform APIs or stdin, not process arguments. No real credential store was accessed and no key was entered.
- The complete suite now has 36 passing tests on Windows with Python 3.10. These mocks add code-path coverage but do not replace manual review on Linux or macOS or a UI review of the Windows key-entry flow.
- Updated README and roadmap test evidence; platform-specific manual review remains a release gate.

### 2026-11-24 — Verify history exports and run expiry

- Added regression checks that JSONL and CSV exports reflect the latest rating/preference events, including cleared values. Added a TTL test proving settled runs expire while pending calls remain tracked.
- After correcting a missing `csv` import in the test harness, the complete Python suite passes: 33 tests on Windows with Python 3.10.
- Updated README and roadmap counts and removed these cases from the remaining test gaps.

### 2026-11-24 — Verify per-run parallel-call cap

- Added an integration regression case that starts five model calls and verifies only three execute concurrently, matching the configured per-run limit, then confirms every selected model completes.
- The full Python unittest suite now has 32 passing tests on Windows with Python 3.10. Updated README and roadmap test evidence and removed this item from the remaining verification gaps.

### 2026-11-24 — Verify streaming response bounds

- Added regression coverage for SSE total-byte and per-line limits, Ollama per-line limits, and the parsed-text cap before oversized streamed content reaches UI callbacks.
- The full Python unittest suite now has 31 passing tests on Windows with Python 3.10. Python compilation and the inline browser-script syntax check also pass.
- Updated README and roadmap evidence. Remaining quality gaps include browser-level review, cross-platform credential-store review, and several concurrency/history edge cases.

### 2026-11-24 — Cover Anthropic discovery metadata

- Added a mock regression case for Anthropic model-list cursor pagination and the supported display name, input/output limits, image/thinking capability flags, and metadata provenance/date fields.
- The test uses mocked provider responses and sends no live request. The full Python unittest suite now has 28 passing tests on Windows with Python 3.10; compileall and the inline JavaScript syntax check also pass.
- Updated the README and roadmap test counts and removed Anthropic pagination/metadata from the remaining test gaps. Hosted CI and browser-level verification remain outstanding.

### 2026-11-24 — Reject invalid cost-estimate inputs

- Cost calculation now rejects boolean, negative, non-finite, and overflowing token/rate inputs as unknown instead of producing invalid or negative estimates.
- Pricing normalization rejects non-finite rates, including JSON values that overflow Python floats. Updated the README; no tests were run.

### 2026-11-24 — Flag stale manual pricing

- Manual price dates in the future are rejected. Estimates based on prices older than 90 days remain available but carry a visible stale-price warning.
- Model and prompt-level history summaries count stale-price estimates separately; legacy records are evaluated using the price date and run timestamp. Updated README and roadmap; no tests were run.

### 2026-11-24 — Add prompt-category history trends

- Added dated success and result-count aggregates for saved prompt-set categories, exposed through the history summary API.
- The trend selector now compares overall results, individual models, or prompt categories. The UI explains that category samples count model results and can include multiple results per prompt. Updated README and roadmap; no tests were run.

### 2026-11-24 — Make JSON writes safe for escaped surrogate values

- Switched catalog, history, provider-request, API-response, and JSONL export serialization to ASCII escapes. JSON semantics and decoded Unicode values are preserved while lone surrogates can no longer break UTF-8 encoding at those boundaries.
- CSV exports use backslash replacement for code points UTF-8 cannot encode. No tests were run.

### 2026-11-24 — Add per-model history trends

- Added UTC-day success/run aggregates by catalog model entry and a selector to plot all models together or inspect one model's trend.
- Model trend payloads are bounded to each model's latest 30 active dates within the saved-history year. Updated README and roadmap; no tests were run.

### 2026-11-24 — Recover readable history after a partial append

- History readers now ignore only an invalid final JSONL fragment that lacks a newline, preserve the source file, and expose a warning in the UI/API. Earlier malformed complete lines still fail closed.
- New appends are blocked while an incomplete tail exists, preventing data from being concatenated onto the fragment. A valid final JSON record without a newline is safely delimited before the next append. No tests were run.

### 2026-11-24 — Add daily saved-run success trends

- Added UTC-day aggregates for saved result counts and success rates, limited to the 365-day window represented by the history data.
- The history UI plots the latest 30 active dates and provides an expandable table with the plotted values. Updated README and roadmap. No tests were run.

### 2026-11-24 — Add model success-rate visualization

- Added an accessible per-model success-rate bar chart to saved-history summaries, with saved-run counts shown beside each rate.
- The chart is explicitly labeled as a measured run outcome, not a composite model score. Updated the README and roadmap; no tests were run.

### 2026-11-24 — Add macOS Keychain credential storage

- Added macOS Keychain save, read, and delete support through Apple's `security` command, using its interactive stdin mode so the credential does not appear in process arguments. A hex stdin token avoids command-parser whitespace and quoting issues while the Keychain stores the original key bytes.
- Updated native credential-store detection and the README, roadmap, and security review. This Windows workspace cannot exercise the macOS Keychain or UI; no tests or live credential operations were run.

### 2026-11-24 — Persist preferred-answer selections

- Preferred answers can now be cleared, and selection changes append a history event when the run started with local history enabled and the setting is still on. Existing comparison behavior remains in-memory when history is off.
- History reads fold the latest selection into each model result; model and prompt-level summaries count user picks separately from ratings and measured metrics, and show the number of recorded choices to avoid treating missing votes as zero. Summary tables also distinguish unknown costs from local runs that are not estimated. Updated the history consent copy, README, and roadmap.
- `git diff --check` is the only check run for this increment; tests were not run.

### 2026-11-24 — Add prompt-level benchmark comparisons

- Added a history summary grouped by saved prompt set, prompt ID, and model entry. It compares sample count, success rate, latency, user ratings, reported output tokens, and supported estimated-cost totals without returning prompt text.
- Added the table to the local history UI and updated the README and roadmap. `git diff --check` is the only check run for this increment; tests and live provider requests were not run.

### 2026-11-24 — Add opt-in human response ratings

- Successful answers can now receive or clear a user-entered 1–5 rating when the result is saved in opt-in local history. Rating changes append separate JSONL events; history reads fold the latest rating into its original result record.
- Added average user ratings with rated-run sample counts to the model summary and included ratings in JSONL/CSV exports. UI and docs distinguish personal feedback from automatic or objective model scores.
- `git diff --check` is the only check run for this increment; tests and live provider requests were not run.

### 2026-11-24 — Require local browser Origin for mutations

- POST, PUT, and DELETE requests now require the exact `http://127.0.0.1:<port>` Origin in addition to the expected Host. Read-only GET requests can still omit Origin for normal page navigation.
- Updated the security review and roadmap; documented that these browser checks do not authenticate local processes. `git diff --check` is the only check run for this increment; tests were not run.

### 2026-11-24 — Add Linux Secret Service credentials

- Added Linux OS-keyring support when `secret-tool` is available. The native masked dialog writes keys to Secret Service over stdin; lookups remain server-side, and keys are never placed in command-line arguments or browser JavaScript.
- Credential-store labels and UI messages now follow the active OS vault. Windows Credential Manager remains supported; macOS and Linux systems without an available Secret Service use environment-variable credentials.
- Updated the README, roadmap, and security review. `git diff --check` is the only check run for this increment; tests and live keyring/provider calls were not run.

### 2026-11-24 — Harden local catalog and history files

- Catalog updates now write to a private temporary file, flush it, and atomically replace the catalog. History records are appended through a private file descriptor and flushed to disk; clearing history syncs the directory entry.
- On POSIX systems, the app restricts its data directory to mode 0700 and catalog/history files to mode 0600, including existing files when read. History and catalog paths must be regular files, and history appends reject symbolic links. Windows storage remains under the current user's AppData ACL.
- Updated the README and roadmap. `git diff --check` is the only check run for this increment; tests and live provider requests were not run.

### 2026-11-24 — Import provider-reported model metadata

- The discovery API now returns allow-listed metadata alongside IDs. Newly added Gemini models can inherit provider display names, descriptions, and input/output token limits; Anthropic entries can also inherit documented image-input and thinking support flags and token limits.
- OpenAI-compatible and Ollama entries retain unknown capabilities when their list responses do not state them. Provenance and the local check date are stored with imported model metadata.
- Updated the README and roadmap. `git diff --check` is the only check run for this increment; no tests or live provider calls were run.

### 2026-11-24 — Follow model-list pagination

- Discovery now follows OpenAI-compatible `has_more`/cursor responses, Anthropic `after_id`/`last_id`, and Gemini `nextPageToken` pagination. It bounds work to five pages and 500 unique IDs, limits cursor length, and keeps Ollama's current single-list response path.
- The UI and README clarify that discovery shows up to 500 model IDs. The roadmap now reflects implemented pagination; broader capability mappings remain planned where providers do not publish comparable fields.
- `git diff --check` passed. The unittest suite and live provider requests were not run.

### 2026-11-24 — Add bounded user-triggered retries

- Failed model cards now offer an explicit retry action. Each retry is a separate run/history record, uses the original run settings and benchmark metadata, and is bounded to two retries per chain.
- Retries are rejected if the model identity or endpoint protocol/URL changed after the failure. They use the current history opt-in setting. The original prompt remains only in the short-lived in-memory run record so the retry request does not need to resubmit it; the run API does not return it.
- Updated the README and roadmap. `git diff --check` is the only check run for this change; the unittest suite and live provider requests were not run.

### 2026-11-23 — Add incremental provider streaming

- Added protocol-aware streaming for OpenAI-compatible SSE, Anthropic Messages SSE, Gemini SSE, and Ollama newline-delimited JSON responses. Streaming is user-controlled in shared run settings and defaults on in the browser UI.
- Comparison cards now display text as it arrives, preserve partial output when a stream fails, and report measured time-to-first-token. Saved history and the model summary include the metric when a stream emits text.
- Updated the README and roadmap. `git diff --check` passed. The unittest suite and live provider requests were not run.

### 2026-11-23 — Add safe catalog backup and merge

- Added user-initiated JSON export and import for provider connections, model entries, and saved prompt sets.
- Export uses explicit normalized fields and excludes credentials, environment-variable values, history, and run responses.
- Import validates the complete payload before saving. Existing connection IDs are preserved to prevent an imported endpoint from inheriting a locally saved credential; matching models and prompt sets are updated by ID.
- Updated the README and roadmap to describe the backup behavior and its connection-restore limitation.
- `git diff --check` passed. The unittest suite and live provider requests were not run.

### 2026-11-23 — Add opt-in history summary

- Added a saved-history summary grouped by model, with successful/failed run counts, mean reported latency, reported input/output token totals, and available estimated cost totals.
- The UI labels sample counts so missing usage and pricing are not treated as zero or as complete billing totals.
- Benchmark prompt-set runs refresh the summary once at batch completion instead of rereading the full history after every prompt.
- Updated the README and roadmap. The unittest suite and live provider requests were not run.

### 2026-11-23 — Persist connection-check outcomes

- Connection checks and explicit model discovery now retain a timestamped success or sanitized failure in the local catalog.
- Connection cards display the latest result after reload. Results are written only if the connection endpoint and protocol still match the values that were checked.
- Updated the README and roadmap. The unittest suite and live provider requests were not run.

### 2026-11-23 — Add a shared output-token cap

- Added an optional run-level maximum output-token setting and mapped it across OpenAI-compatible chat, Anthropic Messages, Gemini generateContent, and Ollama chat requests.
- The setting is validated against catalogued model output limits, shown with the active comparison, and stored in run history. Anthropic's existing default limit remains recorded when no shared value is set.
- Updated the README and roadmap with the adapter mappings and the remaining non-determinism limits.
- Provider documentation was consulted. The unittest suite and live provider requests were not run.

### 2026-11-14 — Commit and push consolidated project

- GitHub Desktop committed the consolidated project changes on `main` as `ca44689` (`Consolidate multi-provider hub and security`).
- GitHub Desktop completed **Push origin** for `the project GitHub remote`; it reported `push complete` and no local changes.
- The 21 project files copied into the GitHub checkout had matching SHA-256 hashes against the consolidated source before commit.
- Python and JavaScript syntax checks passed. The 21-test suite was not run, and no live provider requests or credentials were used.

### 2026-11-14 — Review newer Gemini complete copy for GitHub import

- Compared `the later Gemini review copy` with the consolidated folder. Both contain the same 21-file project layout; the Gemini copy adds run-memory pruning, a worker synchronization fix, CSV formula-injection protection, an Anthropic output-limit setting, and three regression cases.
- Integrated those improvements in the consolidated folder while preserving generic provider-error messages and the safer Credential Manager deletion behavior.
- Verified in GitHub Desktop that the selected repository's remote is `the project GitHub remote` on `main`, with seven pending project files from the earlier implementation. The complete folder includes all existing project files and the new credential/security modules.
- Copied the 21 reviewed project files into `the canonical repository checkout`, preserving its `.git` directory and not deleting destination files. Generated caches and environment files were excluded.
- Compared SHA-256 hashes for all 21 source files against the GitHub checkout; no source files were missing or different.
- GitHub Desktop became minimized/user-active when I returned to review the imported changes, so commit and push are still pending. No commit or push has been made.
- The automated suite remains unrun against the consolidated copy. No live provider calls or credentials were used.

### 2026-11-14 — Consolidate project folders and integrate provider security

- Created one reviewable source tree at `the earlier consolidated workspace`, using the newer dynamic-catalog implementation as its base.
- Preserved the dynamic provider/model architecture, comparisons, prompt sets, cancellation, cost metadata, opt-in history, exports, research, and existing mock-server suite.
- Integrated the Windows Credential Manager connection-key flow and native masked dialog into dynamic provider connections; added connection test UI, key removal, built-in provider links, response copy, and retained request-content-type, Host/Origin, and shutdown safeguards.
- Added consolidation and security-review documentation, project metadata, and corrected roadmap/README/research index descriptions to match the merged features.
- Kept source Git histories separate and left the canonical GitHub checkout and Gemini scratch source untouched. Runtime user data, prior archives, caches, and credentials were excluded.
- The static scratch `providers.py` endpoint list was not copied because it conflicts with user-defined connections; its useful provider setup links are carried in `provider_metadata.py`.
- Python module compilation and the inline JavaScript parser check passed. The pre-existing 18-test suite was not run against this consolidated copy.
- Created `the earlier workspace review archive`; its contents exclude Git history, runtime data, secrets, generated caches, and prior archives.
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

- Primary development checkout: the canonical repository checkout
- This repository has a configured GitHub remote and is maintained on its main branch. The previous project log and research records began in the earlier project workspace; this repo now contains the active implementation log.
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
3. Refine connection health checks and broaden capability mappings only where provider list APIs document them.
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

- Primary project folder: the earlier project workspace
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
- Push was rejected because the configured GitHub account did not have write permission. A separate connected GitHub integration also returned HTTP 403 for its Git tree write request. No update reached GitHub; the local branch remained one commit ahead.

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

### 2026-11-24 — Restrict provider redirects to the configured origin

- Updated JSON and streaming HTTP requests to follow redirects only when scheme, host, and port remain unchanged. This prevents an authenticated API request from being redirected to an unrelated origin.
- Documented that custom endpoints requiring cross-origin redirects must use their final API URL.
- No live provider requests or automated tests were run.

### 2026-11-24 — Keep active comparisons tracked during cache pruning

- Changed run-memory cleanup to expire and evict only settled comparisons with no provider calls pending. Active runs and cancelled runs whose requests are still unwinding stay tracked, preserving their status and the global concurrency count.
- Updated the README and roadmap to describe the settled-run expiry behavior.
- Python syntax parsing and `git diff --check` passed; the automated suite was not run.

### 2026-11-24 — Serialize explicit retries per failed result

- Reserved a failed result while its retry child is active, preventing parallel retry requests from issuing duplicate provider calls. The reservation is released when the retry settles, including after cancellation waits for outstanding provider calls.
- Documented the single-flight retry behavior.
- Python syntax parsing and `git diff --check` passed; the automated suite was not run.

### 2026-11-24 — Add empirical summary thresholds

- Added page-session filters for minimum success rate, maximum average latency, and maximum average estimated cost across saved model and prompt-level summaries. Rows with missing metrics are excluded only when the corresponding filter is active.
- The filters affect the view only; they do not change history or produce a composite model ranking. Updated the README and roadmap.
- No tests or browser runtime checks were run in this increment.

### 2026-11-24 — Align loopback destination classification

- Reused one loopback-host check for HTTP URL validation and local/remote destination labeling. All IPv4/IPv6 loopback literals and `.localhost` names now receive consistent validation and local cost treatment, including trailing-dot hostnames.
- Python syntax parsing and `git diff --check` passed; the automated suite was not run.

### 2026-11-24 — Correct run-expiry help text

- Updated the browser footer to distinguish settled run expiry from active provider calls that remain tracked until they settle.
- Browser script syntax parsing and `git diff --check` passed; no runtime test was run.

### 2026-11-24 — Document architecture and provider extension points

- Added a Mermaid component/data-flow diagram and module responsibility table, plus a guide for configuring an existing protocol or implementing a new adapter.
- Linked both guides from the README and updated the roadmap status.
- No runtime test was run.

### 2026-11-24 — Add a source and installer release checklist

- Added release gates for source snapshots, security/privacy review, provider compatibility claims, artifact contents, and future installer signing/install/rollback behavior.
- Corrected the roadmap to mark architecture/provider/release guides and summary thresholds as implemented, and removed the completed filter item from next work.
- No test suite or runtime checks were run.

### 2026-11-24 — Surface history write failures

- Result cards now show recovery guidance when an opt-in history append fails, including the existing incomplete-tail export/clear procedure. The model response remains available in the in-memory run.
- Updated the README to describe the failure behavior.
- The user authorized running the existing Python unittest suite; it will be run after static checks.

### 2026-11-24 — Run the Python mock suite

- Ran `python -m unittest discover -s tests` after the user authorized verification. The first sandboxed attempt could not open loopback sockets. The suite was rerun with loopback access; all 21 tests passed on Windows with Python 3.10.
- Updated the app test helper to send the exact local Origin on normal mutations and added an explicit missing-Origin rejection check. The server still enforces the mutation Origin requirement. Core auth-header creation now skips OS-vault lookup when passed a partial connection dictionary without an ID.
- Python syntax, inline browser JavaScript syntax, and `git diff --check` passed. No live provider calls or OS credential-vault review were performed.

### 2026-11-24 — Add regressions for history and run cleanup

- Added coverage that an incomplete-tail history write failure leaves the response available and returns recovery guidance, and that cache pruning retains an old active run with a pending provider call.
- Reran `python -m unittest discover -s tests` with loopback access: all 22 tests passed on Windows with Python 3.10.

### 2026-11-24 — Configure cross-platform CI checks

- Added a GitHub Actions matrix for Ubuntu and Windows with Python 3.10 and 3.12. It compiles Python modules, runs the local mock suite, and checks inline browser-script syntax with Node.js.
- Added a reusable `scripts/check_inline_js.py` helper and documented that a hosted workflow run is still required before claiming CI is green.
- The workflow has not yet run on GitHub; no CI result is claimed.

### 2026-11-24 — Expand run, history, and discovery coverage

- Corrected history folding so a cleared preferred response no longer counts as an active selection in summary denominators.
- Added tests for OpenAI-compatible and Gemini pagination cursors, oversized JSON responses, active comparison limits, rating/preference event folding and clearing.
- Ran the complete suite with loopback access: all 26 tests passed on Windows with Python 3.10. No live provider calls were made.

### 2026-11-24 — Verify redirect boundaries

- Added a two-server regression that confirms same-origin redirects work and cross-origin redirects are rejected before the destination receives a request.
- Reran the full suite with loopback access: all 27 tests passed on Windows with Python 3.10.

### 2026-11-14 — Import Gemini scratch-folder improvements

- The user asked to bring the files from `the earlier Gemini scratch review copy` into the original working folder `the earlier project workspace`.
- Compared the supplied folder with the working copy before importing. Added `providers.py` to share provider settings and `pyproject.toml` for Python project metadata; imported the updated server, native credential dialog, UI, README, and roadmap.
- Kept content-type enforcement and clean shutdown of native dialogs. Changed the imported exception logging so it records only the exception type, not exception text; added a clipboard error fallback for the response-copy button.
- No `.git` data, API credentials, prior ZIP, or local data were copied. No tests or live API requests were run.
- Updated the source review package to `dist/Poly-LLM-Hub-security-review-v2.zip` with the imported files and this log entry.
- Destination clarification: `the earlier project workspace` is the active writable workspace. The canonical GitHub checkout is `the canonical repository checkout`; it contains a newer dynamic-connection architecture (`hub_core.py`) and was not overwritten with the older static-provider scratch app.


### Gemini scratch review history
# Poly‑LLM Hub project log

This is the durable activity record for the project. Add a dated entry when research, design, data collection, implementation, or a decision changes.

## Project summary

Poly‑LLM Hub is intended to provide one desktop interface over model APIs, locally hosted models, and selected model-provider command-line clients. The research goal is to decide which interfaces can be integrated reliably, what data handling and provider terms apply, and how to compare response quality, reliability, cost, and latency.

## Workspace and preservation

- Primary project folder: the earlier project workspace
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
- Push was rejected: local Git credentials authenticated as the configured GitHub account, which lacks write permission to `the project repository`. The ChatGPT GitHub connection a connected GitHub integration also returned HTTP 403 for the Git tree write operation. No update reached GitHub; the local branch is one commit ahead.

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
