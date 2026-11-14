# Poly-LLM Hub research workspace

This folder keeps provider-integration research and the reusable model/service briefing template alongside the app. The snapshot date for the current research notes is 2026-11-14 (Asia/Calcutta).

## Files

- `integration-landscape.md` — provider APIs, local inference servers, coding-agent CLIs, and architecture implications.
- `local-client-inventory.md` — executables observed on the Windows PATH during the initial project survey; this is a dated snapshot, not a current machine scan.
- `model-analysis-template.md` — reusable template for researching an individual AI model/service.
- `../prompts/parallel-research-prompts.md` — three coordinated prompt briefs for gathering project research.
- `../docs/PROJECT_LOG.md` — consolidated dated record of project activity and preserved predecessor logs.
- `../docs/SECURITY_REVIEW.md` — security boundaries and manual review points for this implementation.

The app's built-in starter prompt examples are in `web/index.html`. Users can save editable prompt sets to their local catalog and optionally collect comparison history; no provider benchmark responses are included in this source folder.

## Research handling

- Provider features, prices, model IDs, terms, and quotas can change. Recheck official sources and record a checked date before relying on them.
- “Not publicly disclosed” means the official materials reviewed did not state the information.
- No live provider model calls or benchmark responses are included in this source copy.
- Keep API keys and private run outputs out of Git. Local comparison history is a separate, opt-in file in the user's application-data folder.
