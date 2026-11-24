# Adding a provider or model

## Configure an existing protocol

For a provider that implements one of the supported request protocols, add it through the UI instead of editing source:

1. Add a connection and choose the protocol that matches its API shape: OpenAI-compatible Chat Completions, Anthropic Messages, Gemini `generateContent`, or Ollama chat.
2. Enter the provider's final API base URL. Remote endpoints must use HTTPS; plain HTTP is accepted only for loopback hosts.
3. Add the exact model ID expected by that endpoint. Use discovery when available, then review any imported name, limits, capabilities, and metadata date before relying on them.
4. Enter a credential in the native key dialog or configure the connection's environment-variable name. Do not put a key in the URL, model metadata, notes, or a prompt set.
5. Run the connection check, then compare using a low-risk prompt. A successful model-list request does not prove that every listed model is available for generation.

An OpenAI-compatible endpoint may implement only part of that protocol. If generation, streaming, model discovery, or output-token limits differ, turn off streaming or enter the model manually as appropriate. The UI cannot make an incompatible endpoint conform to the protocol.

## Add a new protocol adapter

Keep provider-specific behavior in `hub_core.py` and preserve the separation between connection configuration and model entries.

1. Add the protocol identifier to `PROTOCOLS` and expose it in the connection protocol selector in `web/index.html`.
2. Map authentication in `auth_headers()`. Put credentials only in the documented header or request field; never put them in a URL query string or error message.
3. Add request construction and response parsing in `call_model()`. Normalize output text, input/output token counts, finish status, and latency into the existing result shape. Translate the shared output-token cap only when the provider documents a corresponding field.
4. If streaming is supported, handle the provider's event format in `_read_stream()` and retain the existing response-size bounds and partial-response behavior.
5. Add model discovery in `_discover_model_records()` and pagination handling in `_discover_model_pages()` when the provider documents a list API. Import only documented metadata; unknown capability fields must stay unknown.
6. Add trusted key and documentation links to `provider_metadata.py` for a built-in provider. Custom connections should remain possible without adding a built-in entry.
7. Update the README protocol table, roadmap, and security review. Extend the local mock-server coverage for request shape, parsing, errors, limits, and discovery; live compatibility still needs a separately authorized provider check.

Before adding a new protocol, check whether the endpoint already supports the OpenAI-compatible adapter. Keep coding-agent CLIs separate: they can execute tools and have different permissions and side effects from an inference API.

## Review checklist

- The destination and exact model ID remain visible in the result.
- Prompts and responses are not logged. History remains opt-in.
- Error messages do not include credentials or raw request bodies.
- Remote requests use HTTPS, and redirects cannot change origin.
- Output size, request duration, discovery pagination, and concurrency remain bounded.
- Provider claims about model access, capabilities, pricing, and retention are labeled by source and checked date where available.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the request/data flow and [SECURITY_REVIEW.md](SECURITY_REVIEW.md) for the current threat-model limits.
