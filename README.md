# Poly-LLM Hub

**GitHub repository description:** A desktop hub for connecting, comparing, and managing multiple hosted and local AI models from one interface.

## General idea

Poly-LLM Hub is a cross-platform desktop application concept for bringing multiple AI model services into one workspace. It aims to let users connect provider APIs, local model servers, and selected command-line clients; choose a model for a task; and compare responses in a consistent interface.

The project is intended to make the execution path clear: which provider and model handled a request, whether it ran locally or through a cloud service, and what usage, latency, and cost information is available. Provider-specific capabilities and limitations should remain visible rather than being hidden behind a one-size-fits-all interface.

## Planned direction

- Connect to supported hosted model APIs and local inference servers.
- Keep provider integrations modular so models and services can be added over time.
- Compare model responses and, where available, token usage, latency, and estimated cost.
- Make configuration and data-handling choices understandable to the user.
- Treat coding-agent command-line tools separately from ordinary chat APIs because agents may use tools or interact with a workspace.

## Status

Early MVP. The first local comparison interface is implemented; provider coverage and features will expand through iteration.

## License

Intended license: Apache License 2.0. Select **Apache License 2.0** when creating the GitHub repository, or add the full Apache-2.0 `LICENSE` file before publishing this README.

## Run the first MVP locally

The first working version uses Python's standard library and does not need a package install.

1. Open PowerShell in this folder.
2. Run `python app.py`.
3. Open http://127.0.0.1:8765 in your browser.
4. Select providers, enter each provider's model ID, write a prompt, and press **Compare selected**.

Ollama must be running locally with a model already installed to use the local option. Cloud providers require their API key to be set as an environment variable in the same PowerShell window before starting the app: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `XAI_API_KEY`, or `DEEPSEEK_API_KEY`. Restart the app after setting a key. Do not put real keys in source files or Git.

Prompts are not written to disk by the app. When you press Compare, the prompt is sent to each selected cloud provider under that provider's terms; this may incur API charges. Ollama requests go to the local Ollama server. The detected CLI tools are informational in this MVP and are not launched.

The server binds to 127.0.0.1 only. Stop it with Ctrl+C in the PowerShell window.
