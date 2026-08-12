# Security Policy

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability, credential exposure, or privacy leak.
Use GitHub's private security advisory flow for this repository, or contact the repository owner privately through the contact method listed on the project profile. Include a minimal reproduction and avoid attaching real credentials, cookies, user exports, or copyrighted source material.

## Local credentials

YLCraft stores provider keys, platform cookies, and local database settings outside Git. Copy the relevant `.env.example` file to a local `.env` file and provide your own values. Never commit `.env`, browser exports, cookies, generated media, database backups, or request/response logs.

## Supported disclosure scope

Report issues involving authentication, credential storage or logging, arbitrary file access, server-side request forgery, unsafe publishing, cross-user data exposure, and dependency supply-chain risks.

Before publishing a release, run:

```powershell
python tools/audit_public_release.py
python tools/audit_public_release.py --history
```

The history scan is intentionally stricter. A finding in history must be revoked or rotated first; removing the file from the latest commit alone does not remove it from a public Git repository.
