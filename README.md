# Smart Drive Organizer — v0.6.0

**Safe deep search, recurring-pattern discovery, reviewable grouping and persistent rules**

A local-first Windows file organizer with a redesigned desktop workspace, custom keyword routing, multi-drive scanning, persistent rules and optional background monitoring.

**Brand system:** black `#101010`, red `#D71920`, and white `#FFFFFF`. The supplied monochrome face-and-skull artwork is the application mark.

## Optional conventional installer

The no-install PowerShell launcher is recommended. The conventional per-user installer is still available separately:

```powershell
irm https://raw.githubusercontent.com/T3ND41/SmartDriveOrganizer_RepoReady_v0.3.7/main/install.ps1 | iex
```

The installer fetches the latest GitHub Release, verifies its SHA-256 manifest, installs the per-user Windows application, creates a Start Menu shortcut and launches it.

> This command executes a remote PowerShell installer. Inspect [install.ps1](install.ps1) before running it. The installer does not scan, move, copy, or delete your personal documents.

## Interface refresh (v0.4.0)

- Added a black navigation rail, white workspace cards, red primary actions and a consistent typography and spacing system.
- Added the supplied monochrome artwork as the application mark and window icon.
- Grouped locations, file formats, organization preferences, topic rules and preview into a scrollable workflow. Existing file operations and safety confirmations remain connected.

## Safe deep search and automatic discovery (v0.5.0)

- The first scan searches recursively through the selected local fixed/removable drives and mounted volumes. The default selection now includes all supported file families and file extensions; network drives remain opt-in.
- The search is read-only. It records accessible file names, paths, categories and file metadata. It never moves, copies, renames or deletes anything during discovery.
- The discovery engine identifies repeated filename words and phrases across **at least two different files**. Discovery currently analyses filename wording; it does not yet build a full-text index of every document. Repeated words inside one file do not count as multiple matches.
- Existing built-in and saved keywords are not suggested again as new discoveries. Candidate groups are separated by file family and include a match count, sample names and original locations.
- A review window lets you select, skip or rename proposed groups. Only groups you approve are saved as reusable local rules. The app then rescans and builds a fresh preview using those rules.
- The existing **Read document text where possible** option can still use supported document text to match saved rules. The final scan preview controls what will be organized. Nothing is copied or moved until you click **Apply organization** and confirm.
- Approved patterns are saved locally and can be reused in later scans. They are also made available to the background organizer, subject to its own selected categories and selective-topic settings.

### Safe search boundaries

To protect Windows, installed applications and development environments, the scanner deliberately skips Windows and recovery directories, Boot/EFI areas, Program Files, ProgramData, AppData, recycle-bin/system-volume folders, protected operating-system files, project roots and common package/dependency/cache folders. It also avoids following symbolic links, junctions and other reparse points. Inaccessible folders are reported as warnings rather than forced open. Network locations are not selected automatically.

This is an intentionally safe deep search of accessible personal/work files on the selected volumes, **not a byte-for-byte search of every protected operating-system location**. Some user data stored inside excluded locations such as AppData will therefore not appear. No scan can promise access to every file on a machine, because permissions, encryption, offline drives and damaged media can prevent access.

## Local full-text search, learning memory and duplicate intelligence (v0.6.0)

### Google-style search dashboard
- Added a central local search screen for filenames and extracted document text, with filters for original location, file family, extension, topic, modified-date range and file-size range.
- Results can open the original file or reveal it in its original folder.
- **Build / refresh index** recursively indexes selected drives/folders. The main scan also refreshes index records for files it processes.
- Metadata and bounded extracted text are stored in a local SQLite database under `%LOCALAPPDATA%\\SmartDriveOrganizer\\file_search.sqlite3` (Windows). No file contents are uploaded to a server.

### Full-text formats and limits
- Extracts text from PDF text layers, DOCX, XLSX/XLSM, PPTX, plain text, CSV/TSV, HTML/XML, RTF, source-code text, EML email and Outlook MSG email.
- Outlook MSG extraction uses the optional `extract-msg` parser, included in the Windows build.
- Document extraction is bounded to protect memory and scan time. Very large or encrypted files, damaged documents and formats without a supported parser may be indexed by name/metadata only.
- Legacy binary Office files (`.doc`, `.xls`, `.ppt`) are listed and searchable by filename/metadata, but their internal text is not currently extracted. Image-only/scanned PDFs require OCR, which is not part of this release.

### Adaptive local memory
- Approved discovery groups, rejected suggestions and filing corrections are saved in `learning_memory.json` on this device.
- Rejected filename patterns are suppressed in later discovery scans; approving a previously rejected pattern removes its rejection.
- Rename a discovered group before approval to store the preferred folder name.
- Select a proposed file in the organization preview and choose **Teach selected file** to save a topic/keyword correction for future scans.
- **Learning memory** in the navigation lets you inspect remembered approvals, rejections and filing corrections, and remove a rejection so it can be suggested again.
- Saved classifier/topic rules are separate from the memory history and remain editable through the existing rule manager.

### Duplicate and version review
- **Find duplicates & versions** in the search dashboard checks indexed files for exact SHA-256 duplicates, likely filename revisions/copies and very high text overlap between supported documents.
- Findings show the files and why they were grouped. Similarity and version grouping are heuristic suggestions; inspect the documents before deciding what to keep.
- This tool is inspection-only. It does not delete, overwrite, merge, rename or move duplicates.

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

## Run without installing

Open PowerShell and paste this single line:

```powershell
irm https://raw.githubusercontent.com/T3ND41/SmartDriveOrganizer_RepoReady_v0.3.7/main/run.ps1 | iex
```

The launcher checks the latest stable GitHub Release, downloads the Windows ZIP and SHA-256 manifest, verifies the ZIP before extraction, caches the executable under `%LOCALAPPDATA%\\SmartDriveOrganizer\\PortableRuntime`, and starts it directly. It does not create a Start Menu shortcut, add a Windows startup entry, write installation registry keys, or require administrator rights or Python. It reuses the cached executable when the latest version is already present. Your application settings remain in the separate per-user `%LOCALAPPDATA%\\SmartDriveOrganizer` data folder.

To remove the downloaded runtime, delete `%LOCALAPPDATA%\\SmartDriveOrganizer\\PortableRuntime`. This does not delete your saved organizer settings and activity data.

**Security:** this one-line command executes a PowerShell script from the public repository. Review [run.ps1](run.ps1) before running it. The launcher verifies the downloaded release ZIP against the SHA-256 manifest published alongside it.

## Run from source

Requires Python 3.10 or later.

```powershell
python -m pip install -e ".[content]"
python run.py
```

Run tests with `python -m unittest discover -s tests -v`.

## CI and Windows releases

Pushes to `main` run tests on Windows and Linux. Pushing a version tag such as `v0.6.0` runs the Windows release workflow, which tests the project, builds the executable, packages it, calculates SHA-256 and publishes a GitHub Release.

## Safety

- Copy is recommended for first use.
- Existing destination files are never overwritten.
- Unknown or unmatched files are not automatically routed by selective rules.
- Protected operating-system/application locations, links, inaccessible folders and unsupported file contents may be skipped; check the scan warnings and coverage summary.
- Start with Copy and inspect discovered groups and the complete preview before applying; keep backups before large Move operations.
- Background monitoring runs only while Windows is awake and the signed-in user session is active.

## Optional short domain

`https://smart.drive.win` requires deployment of the Cloudflare Worker in `cloudflare/` and control of the `drive.win` DNS zone. Until configured, use the direct GitHub Raw command above.

## Repository

https://github.com/T3ND41/SmartDriveOrganizer_RepoReady_v0.3.7
