# Poly-LLM Hub security review notes

## What this build does

- Binds the Python server to `127.0.0.1`, checks the expected local Host, requires the exact local browser Origin on POST/PUT/DELETE mutations, and requires JSON content types for JSON mutation requests. Its CSP permits the single inline UI script only by SHA-256 hash and blocks objects, base URL changes, form submissions to other origins, and framing; inline styles remain allowed. Read-only GETs may omit Origin for normal browser navigation.
- Opens a native masked Tkinter dialog for key entry on supported systems. The browser sends only a connection ID; the API key is not submitted through JavaScript, placed in browser storage, or passed in process arguments.
- Saves keys in Windows Credential Manager, Linux Secret Service through `secret-tool`, or macOS Keychain through Apple's `security` tool. Linux storage sends key material over stdin. On macOS the key bytes are hex-encoded for the interactive command over stdin; the process argument list only selects interactive mode, while the stdin command contains the fixed service label and a one-way digest of the connection ID.
- Reads a saved key in the local Python process only when it needs to make a provider request. The UI receives credential status, not the secret.
- Uses HTTPS for remote provider URLs and provider-specific headers. Gemini keys use `x-goog-api-key`, not a URL query string.
- Restricts provider HTTP redirects to the same scheme, host, and port as the configured endpoint, so an authenticated call cannot be redirected to a different origin.
- Checks connectivity using the provider's model-list endpoint. The check sends no prompt and does not request generated content.
- Retains environment-variable support as a fallback. A saved OS-vault key takes priority.
- Removes a saved key locally when requested. This does not revoke it at the provider; revoke a key in the provider console if needed.
- Leaves prompt and response history off by default. The user can opt in to local JSONL history; the catalog and history files are not encrypted.

## Provider identity model

There is no shared Poly-LLM Hub account, backend proxy, or universal Google login. Each provider has separate API access, billing, and credentials. Gemini uses a Google AI Studio API key in this build. Google OAuth is not configured, and Google sign-in does not grant access to other providers.

## Limits of the security claim

- Windows Credential Manager, a configured Linux Secret Service keyring, and the macOS login Keychain protect credentials at rest for the current user. A malicious process already running as that user may be able to read or use the user's credentials.
- Provider keys exist briefly in process memory when entered and when making an API call. Python cannot guarantee immediate clearing of immutable string objects from memory.
- The local HTTP server has no user-account login because it is intended for one user on one computer and binds only to loopback. Host and Origin checks help prevent browser-based cross-origin access; they do not authenticate other processes on the same computer. An unrelated local process can forge an Origin header.
- HTTPS protects traffic from this app to cloud providers. Prompts go directly to the selected providers when the user runs a comparison, and are subject to their terms, retention, and billing.
- A provider endpoint that depends on redirecting requests to another origin will fail; configure the final API origin directly.
- The model-list check contacts the provider and may count toward its quotas or be recorded by that provider. Some compatible services do not expose a model-list endpoint.
- Local history may contain prompts and responses and is not encrypted. Clear it in the UI or handle the JSONL file as sensitive data.
- Linux key storage depends on `secret-tool` and an available desktop Secret Service session. The macOS Keychain flow uses Apple's command-line tool and still needs manual review on supported macOS versions. The project has not been packaged into a `setup.exe`, code-signed, penetration-tested, or reviewed by an independent security auditor.

## Manual review points

1. Inspect `secret_store.py` and `credential_dialog.py` to confirm keys go through the platform vault and never appear in command-line arguments.
2. Inspect `app.py` to confirm credential-management routes accept only connection IDs and do not return secret values.
3. Inspect `hub_core.py` to review URL validation, provider request construction, and secret header placement.
4. Confirm prompt disclosure and provider retention policies before sending real prompts.
5. Use test credentials or low-limit keys during initial manual review. Revoke a credential with the provider if exposure is suspected.
