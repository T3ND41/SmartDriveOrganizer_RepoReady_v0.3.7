# Smart Drive Organizer — v0.4.0

**Branded desktop interface with selectable file extensions for manual and automatic organization**

A local-first Windows file organizer with a redesigned desktop workspace, custom keyword routing, multi-drive scanning, persistent rules and optional background monitoring.

**Brand system:** black `#101010`, red `#D71920`, and white `#FFFFFF`. The supplied monochrome face-and-skull artwork is the application mark.

## One-line PowerShell installation

After the first Windows release is published, run:

```powershell
irm https://raw.githubusercontent.com/T3ND41/SmartDriveOrganizer_RepoReady_v0.3.7/main/install.ps1 | iex
```

The installer fetches the latest GitHub Release, verifies its SHA-256 manifest, installs the per-user Windows application, creates a Start Menu shortcut and launches it.

> This command executes a remote PowerShell installer. Inspect [install.ps1](install.ps1) before running it. The installer does not scan, move, copy, or delete your personal documents.

## Interface refresh (v0.4.0)

- Added a black navigation rail, white workspace cards, red primary actions and a consistent typography and spacing system.
- Added the supplied monochrome artwork as the application mark and window icon.
- Grouped locations, file formats, organization preferences, topic rules and preview into a scrollable workflow. Existing file operations and safety confirmations remain connected.

## Features

- Choose exact extensions within Documents, Images, Videos, Audio, Archives, Code, Applications, Fonts, 3D Models and Others. Common formats are listed first, followed by specialist formats.
- The same saved extension filters apply to manual scans and background monitoring; unselected extensions remain untouched.

- Recursively scans selected folders and mounted drives.
- Supports multiple source drives and one central output destination.
- Custom topic rules with multiple keywords and partial/contains matching.
- A separate destination folder for each keyword rule.
- Reuses or creates topic folders and can separate by extension.
- Copy and Move modes, collision-safe naming, journals and recovery.
- Background monitoring of selected folders, with saved settings.
- Selective organization: unmatched files remain untouched.
- Optional GitHub publishing for approved rules and source changes.

## Choose exact file extensions

After selecting broad file families, click **Choose file formats…**. For each selected family, choose **All supported formats** or **Only the formats I select below**. The Documents common list starts with PDF, DOCX, XLSX, XLS, CSV, PPTX, DOC, TXT, PPT and RTF. Additional and specialist formats follow. Selections are saved locally and enforced before classification and organization in both manual and automatic modes.

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
