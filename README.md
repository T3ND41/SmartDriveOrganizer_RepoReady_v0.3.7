# Smart Drive Organizer — v0.3.7

A local-first Windows file organizer with custom keyword routing, multi-drive scanning, persistent rules and optional background monitoring.

## One-line PowerShell installation

After the first Windows release is published, run:

```powershell
irm https://raw.githubusercontent.com/T3ND41/SmartDriveOrganizer_RepoReady_v0.3.7/main/install.ps1 | iex
```

The installer fetches the latest GitHub Release, verifies its SHA-256 manifest, installs the per-user Windows application, creates a Start Menu shortcut and launches it.

> This command executes a remote PowerShell installer. Inspect [install.ps1](install.ps1) before running it. The installer does not scan, move, copy, or delete your personal documents.

## Features

- Recursively scans selected folders and mounted drives.
- Supports multiple source drives and one central output destination.
- Custom topic rules with multiple keywords and partial/contains matching.
- A separate destination folder for each keyword rule.
- Reuses or creates topic folders and can separate by extension.
- Copy and Move modes, collision-safe naming, journals and recovery.
- Background monitoring of selected folders, with saved settings.
- Selective organization: unmatched files remain untouched.
- Optional GitHub publishing for approved rules and source changes.

## Run from source

Requires Python 3.10 or later.

```powershell
python -m pip install -e ".[content]"
python run.py
```

Run tests with `python -m unittest discover -s tests -v`.

## CI and Windows releases

Pushes to `main` run tests on Windows and Linux. Pushing a version tag such as `v0.3.7` runs the Windows release workflow, which tests the project, builds the executable, packages it, calculates SHA-256 and publishes a GitHub Release.

## Safety

- Copy is recommended for first use.
- Existing destination files are never overwritten.
- Unknown or unmatched files are not automatically routed by selective rules.
- Protected or inaccessible locations may be skipped.
- Keep backups before large Move operations.
- Background monitoring runs only while Windows is awake and the signed-in user session is active.

## Optional short domain

`https://smart.drive.win` requires deployment of the Cloudflare Worker in `cloudflare/` and control of the `drive.win` DNS zone. Until configured, use the direct GitHub Raw command above.

## Repository

https://github.com/T3ND41/SmartDriveOrganizer_RepoReady_v0.3.7
