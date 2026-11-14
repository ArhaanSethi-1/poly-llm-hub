# Poly-LLM Hub security review notes

## What this build does

- Binds the Python server to `127.0.0.1`, checks the expected local Host and browser Origin, sends basic security headers, and requires JSON content types for JSON mutation requests.
- Opens a native Tkinter dialog for Windows key entry. The browser sends only a connection ID; the API key is not submitted through JavaScript, placed in browser storage, or passed in process arguments.
- Saves keys as Windows generic credentials under the current Windows user. Credential targets use a one-way digest of the connection ID rather than storing provider keys or using arbitrary target names.
- Reads a saved key in the local Python process only when it needs to make a provider request. The UI receives credential status, not the secret.
- Uses HTTPS for remote provider URLs and provider-specific headers. Gemini keys use `x-goog-api-key`, not a URL query string.
- Checks connectivity using the provider's model-list endpoint. The check sends no prompt and does not request generated content.
- Retains environment-variable support as a fallback. A Credential Manager key takes priority.
- Removes a saved key locally when requested. This does not revoke it at the provider; revoke a key in the provider console if needed.
- Leaves prompt and response history off by default. The user can opt in to local JSONL history; the catalog and history files are not encrypted.

## Provider identity model

There is no shared Poly-LLM Hub account, backend proxy, or universal Google login. Each provider has separate API access, billing, and credentials. Gemini uses a Google AI Studio API key in this build. Google OAuth is not configured, and Google sign-in does not grant access to other providers.

## Limits of the security claim

- Windows Credential Manager protects credentials at rest for the current Windows user. A malicious process already running as that user may be able to read or use the user's credentials.
- Provider keys exist briefly in process memory when entered and when making an API call. Python cannot guarantee immediate clearing of immutable string objects from memory.
- The local HTTP server has no user-account login because it is intended for one user on one computer and binds only to loopback. Host and Origin checks help prevent browser-based cross-origin access; they do not authenticate other processes on the same computer.
- HTTPS protects traffic from this app to cloud providers. Prompts go directly to the selected providers when the user runs a comparison, and are subject to their terms, retention, and billing.
- The model-list check contacts the provider and may count toward its quotas or be recorded by that provider. Some compatible services do not expose a model-list endpoint.
- Local history may contain prompts and responses and is not encrypted. Clear it in the UI or handle the JSONL file as sensitive data.
- The project has not been packaged into a `setup.exe`, code-signed, penetration-tested, or reviewed by an independent security auditor. Native credential storage is currently Windows-only.

## Manual review points

1. Inspect `secret_store.py` and `credential_dialog.py` to confirm the key is written through Windows Credential Manager.
2. Inspect `app.py` to confirm credential-management routes accept only connection IDs and do not return secret values.
3. Inspect `hub_core.py` to review URL validation, provider request construction, and secret header placement.
4. Confirm prompt disclosure and provider retention policies before sending real prompts.
5. Use test credentials or low-limit keys during initial manual review. Revoke a credential with the provider if exposure is suspected.
