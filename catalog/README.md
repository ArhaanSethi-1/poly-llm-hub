# Seed model catalog

`seed_models.json` supplies the default 15 entries when the local catalog has no models and has not been seeded before. Each row keeps its provider ID, context/output limits, published pricing URL, model metadata source, and provenance. Ollama entries cost no API tokens; the user still needs Ollama installed, running, and the model pulled.

`rank_score` is the published LMArena text style-control overall `index_score` where the exact model family and tested configuration can be matched. `rank_source` records the tested variant and snapshot date. This is a human-preference leaderboard measure, not a guarantee of performance on an individual task. Entries with no comparable published score use `null`; the UI sorts scored rows first and labels unscored rows clearly. No score is inferred from pricing or context length.

Provider model, context, pricing, and Arena data can change. Every score points to the official Arena dataset; model metadata and pricing fields link to provider documentation and include a checked date. Refresh the static seed with provider documentation before a release when current model IDs or prices have changed. Existing catalogs are never refreshed or overwritten by this file.

## Direct browser calls

Direct Connection mode is not enabled in this release. Provider browser CORS and API-key handling differ, and the current first-party docs do not provide a reliable cross-provider CORS guarantee. The current default remains the local proxy with keys in the operating system's credential vault.
