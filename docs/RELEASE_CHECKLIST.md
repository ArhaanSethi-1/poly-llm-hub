# Release checklist

This project currently runs as a Python source checkout. It has no installer, signed binary, auto-updater, or CI release workflow. Until those exist, treat a release as a reviewed source snapshot, not a Windows `setup.exe` or native desktop application.

## Before a source release

### 1. Freeze and identify the candidate

- Choose the release version and date; update `pyproject.toml` and release notes together.
- Review the complete diff from the last release. Confirm that unrelated local work is not included.
- Confirm the candidate can start from a clean checkout using the documented Windows command in the README. Record supported Python versions and any platform-specific limitations.
- Smoke the actual entry point with an isolated empty `APPDATA` catalog: verify `GET /` and `/api/catalog` succeed, the catalog is empty, and history is off. This check must not use the user's existing catalog or contact a provider.
- Keep the repository's Apache 2.0 license and include the matching source and documentation.

### 2. Run software checks

- Run the Python suite with `python -m unittest discover -s tests` and record the interpreter version and result.
- Run static checks available for the candidate, including Python compilation and the browser script syntax/runtime check. Confirm the served content security policy hash matches the inline script.
- Confirm the GitHub Actions checks workflow completed successfully for the exact release commit; a configured workflow without a hosted result is not a release pass.
- Manually open the UI at `http://127.0.0.1:8765`. Review catalog editing/import/export, comparison, cancellation, retries, history opt-in/export/clear, and keyboard/accessibility behavior.
- Review single-model chat handoff: switch models without sending a request, check the lean/balanced/full context windows, and confirm a failed turn is resent only after the explicit action.
- Keep CI/mock validation separate from live-provider validation. Mock success proves request and parsing behavior only.

### 3. Review security and privacy

- Confirm history is off by default and that catalog backups omit keys and run history.
- Review Host/Origin checks, loopback binding, redirect restrictions, body/output limits, and safe error handling against [SECURITY_REVIEW.md](SECURITY_REVIEW.md).
- Review credential entry and removal on each platform being claimed: Windows Credential Manager, Linux Secret Service with an active keyring, and macOS login Keychain. Do not claim a platform flow is verified until it has been manually reviewed there.
- Inspect the release tree for API keys, `.env` files, local catalogs/history, logs, model weights, temporary test data, and unrelated archives.
- Build the source archive with `python scripts/build_source_archive.py`. It uses a fixed file allowlist, rejects common credential signatures and machine-specific absolute paths, and excludes the project activity log and local research inventory. Inspect the archive member list and checksum before attaching it.
- Confirm provider links, model IDs, pricing sources/dates, retention disclosures, and licensing statements are current. User prompts sent during a live check require an explicitly selected provider and credential.

### 4. Verify provider compatibility

- Use mock servers for protocol coverage without credentials or live provider traffic.
- For any live claim, record the provider, endpoint, exact model ID, date, protocol, and tested features. Use a low-risk prompt and a low-limit credential; do not include the key or sensitive prompt in release notes.
- A model-list connection check does not prove generation, streaming, output-cap, or billing compatibility.
- Revoke or rotate any credential that may have been exposed during manual review.

### 5. Publish and preserve

- Review the generated source archive contents before attaching them. The archive builder writes a deterministic ZIP under `dist/` and refuses to overwrite an existing artifact. Do not include `.git`, local data, credentials, build output, or untracked review material.
- Tag the exact reviewed commit. Release notes should list supported behavior, known limitations, required Python version, and the fact that the app sends prompts directly to selected providers.
- Keep a copy of the release notes and source artifact with the project activity record.

## Installer release gates

Do not publish a `setup.exe` or other installer until all of these are complete:

- A reproducible packaging configuration includes only necessary application files and clearly identifies the Python/runtime dependencies.
- Install, upgrade, uninstall, data preservation, and rollback behavior are documented and manually reviewed.
- The Windows credential dialog and Credential Manager behavior are reviewed from the installed build, not only from a source checkout.
- The artifact is malware-scanned and code-signed under the release owner's identity; signing and update ownership are documented.
- A clean-machine install and launch are verified, including the local-only binding and absence of any bundled API key or user data.

Cross-platform installers require equivalent platform-specific packaging, signing, credential-store, and upgrade reviews. A source release does not satisfy these gates.
