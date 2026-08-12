# Open-source Release Security Checklist

This checklist is the repository's source of truth for preparing a public release. It complements, but does not replace, GitHub secret scanning and dependency alerts.

## Required before the first public push

1. Run `python tools/audit_public_release.py` and resolve every finding.
2. Run `python tools/audit_public_release.py --history`. If it reports historical credentials, cookies, signed URLs, user exports, or logs, revoke the affected credential first and then rewrite history before publishing.
3. Confirm `git ls-files` contains no real `.env`, database dump, `backend/storage`, `backend/downloads`, `backend/backups`, browser cookie export, request log, certificate, or private key.
4. Check sample configuration only contains placeholders or explicitly documented development-only values. Production credentials must always come from environment variables or a secret manager.
5. Confirm runtime logging redacts provider keys, platform cookies, authorization headers, signed URLs, and request bodies that can contain image data or user content.
6. Confirm the repository has a chosen `LICENSE`, `SECURITY.md`, and a contributor-facing setup guide before announcing it publicly.

## Required on every release

1. Run the current-tree audit in CI.
2. Review newly added binary files and data fixtures for personal, customer, or copyrighted material.
3. Rotate any credential or platform login state that was ever pasted into a terminal, chat transcript, log, or commit, even if it has since been deleted.
4. Enable GitHub secret scanning, push protection, Dependabot alerts, and private vulnerability reporting in repository settings.

## Scope of the built-in audit

`tools/audit_public_release.py` reports only paths and rule names, never matching secret text. It checks the tracked tree for common credential patterns, signed object URLs, cookie/session values, and forbidden local-data paths. `--history` reports historical signed URLs and cookie/session values as a fast preflight gate; investigate the affected commit before publishing. Use GitHub Secret Scanning or a dedicated history scanner such as Gitleaks for full secret-pattern coverage. Neither is a substitute for incident response.

The script intentionally does not inspect ignored `.env` files. Local credentials must not be copied into a ticket or terminal output during an audit.
