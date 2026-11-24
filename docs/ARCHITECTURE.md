# Architecture

Poly-LLM Hub is a local Python server with a browser UI. The server binds to `127.0.0.1:8765`; provider requests go directly from that process to the configured provider or local inference endpoint.

```mermaid
flowchart LR
    Browser[Browser UI\nweb/index.html] -->|HTTP on loopback| App[HTTP routes and run orchestration\napp.py]
    App --> Core[Catalog, adapters, discovery, history, estimates\nhub_core.py]
    Core --> Catalog[(catalog.json)]
    Core --> History[(history.jsonl\nopt-in)]
    App --> Dialog[Masked native key dialog\ncredential_dialog.py]
    Dialog --> Vault[(OS credential vault)]
    Core -->|key read in server process| Vault
    Core -->|HTTPS or loopback HTTP| Provider[Provider API or local model server]
    App --> Metadata[Built-in help links\nprovider_metadata.py]
```

## Request flow

1. The browser loads the static page from `app.py` and reads the public catalog. The page stores selected model-entry IDs in `localStorage`; prompts, answers, and credentials are not written there.
2. A comparison request includes the prompt, selected model-entry IDs, and run settings. The server validates the request, loads the current catalog, resolves model entries to connections, and starts a bounded comparison run.
3. `hub_core.py` maps the request to the configured protocol. The server reads a saved OS-vault key when available, otherwise uses the configured environment-variable fallback, and sends the prompt directly to the selected destination.
4. The browser polls the in-memory run record. With streaming enabled, text deltas are added to that record as they arrive.
5. If the user enabled history, completed model results are appended to `history.jsonl`. Summaries and user ratings are derived from those records and append-only rating/preference events.

## Persistence and security boundaries

- The catalog lives under `%APPDATA%\\Poly-LLM-Hub` on Windows and `~/.local/share/Poly-LLM-Hub` when `APPDATA` is absent. It stores provider configuration, model metadata, and prompt sets explicitly saved by the user.
- History is separate, local, and off by default. It may contain prompts and complete model responses and is not encrypted. The user can export or clear it.
- Credentials are stored by `secret_store.py` in Windows Credential Manager, Linux Secret Service (`secret-tool`), or macOS Keychain. The browser only passes a connection ID to open the native masked dialog.
- `app.py` accepts browser requests on loopback and protects mutations with Host and Origin checks. These checks do not authenticate other processes running as the same user.
- Remote provider calls use HTTPS; HTTP is allowed for loopback services. Redirects are restricted to the configured origin.

## Key modules

| Module | Responsibility |
| --- | --- |
| `app.py` | Local HTTP routes, request validation, run lifecycle, concurrency limits, retry/cancel behavior, history endpoints, and native credential-dialog launch. |
| `hub_core.py` | Catalog normalization and storage, provider request/response adapters, model discovery, usage/cost estimates, JSONL history, and empirical summaries. |
| `secret_store.py` | OS-specific credential read/write/delete operations. |
| `credential_dialog.py` | Native masked key-entry UI. |
| `provider_metadata.py` | Trusted key-creation and documentation links for built-in connections. |
| `web/index.html` | Browser UI, run polling/rendering, catalog forms, and local history views. |

The current design does not launch coding-agent CLIs, host a provider proxy, or provide a multi-user service. See [SECURITY_REVIEW.md](SECURITY_REVIEW.md) for limitations and [ADDING_PROVIDER.md](ADDING_PROVIDER.md) for extension guidance.
