# Security Policy

## Reporting a vulnerability

Please do not publish exploit details in a public issue. Contact the repository owner through GitHub's private vulnerability reporting feature when available.

## Installer safety

The PowerShell bootstrap is intentionally small and should be reviewed before use. It downloads release assets only from the configured GitHub repository, checks the SHA-256 hash in the release manifest, installs per-user, and does not request administrator rights. The `irm | iex` pattern executes remote code in the current PowerShell session; only run it when you trust the repository and HTTPS endpoint.

## Data handling

Smart Drive Organizer is designed to work locally. Do not commit personal settings, absolute file paths, scanned file lists, activity logs, databases, tokens, or documents.
