## 0.7.0 — Branded workspace, live progress and safer duplicate review

- Applied the supplied split red/black face-and-skull mark and both supplied light/dark feature icon atlases to the application UI.
- Added persistent Light, Dark and Redline themes using the official red `#D71920`, black `#101010` and white `#FFFFFF` palette.
- Added a logo-centered circular progress indicator showing selected-drive coverage, files found versus examined, match rate, active search terms and matched groups.
- Kept Pause, Resume and Cancel controls available across recursive scanning, local full-text indexing, duplicate analysis, Copy/Move application and Move undo. Pause and cancellation are cooperative and occur at safe checkpoints.
- Highlighted duplicate findings and added side-by-side oldest/newest review cards with original locations, timestamps, sizes and SHA-256 evidence.
- Restricted the Recycle Bin action to byte-for-byte exact duplicates. It requires explicit user confirmation, defaults to keeping the newest copy and re-hashes the keeper and each older copy immediately before recycling. Possible versions and near-matches are never eligible.
- Confirmed the no-install PowerShell launcher checks installed and portable copies, avoids launching a second running instance, compares the local version with the latest published release, asks before upgrading and updates an existing folder in place.
- Added tests for the theme palette and retained pause/resume/cancel and duplicate safety regression coverage.

## 0.6.0 — Local search, adaptive memory and duplicate intelligence

## 0.6.0 — Local search, adaptive memory and duplicate intelligence

- Added bounded local text extraction for PDF text layers, DOCX, XLSX/XLSM, PPTX, EML, Outlook MSG, common text/code formats, CSV/TSV, HTML/XML and RTF.
- Added a local SQLite/FTS5 index for file metadata and extracted text; unchanged files are not re-indexed when size and modified time match.
- Added a Google-style search dashboard with filename/content search, location, file family, extension, topic, modified-date and size filters, plus Open and Show in folder actions.
- Added a read-only index builder for selected drives and folders; protected OS/application/project folders remain excluded.
- Added adaptive local memory for approved and rejected discoveries, renamed groups and filing corrections. Rejected patterns are suppressed on later scans and can be reinstated from Learning Memory.
- Added a Teach selected file action so the user can save a preferred topic and matching wording from the scan preview.
- Added a local memory review screen for inspecting approvals, rejections and correction history.
- Added duplicate/version inspection: SHA-256 exact copies, possible filename revisions and high text-overlap candidates. The feature never deletes, moves, overwrites or merges files.
- Added tests for content extraction, local full-text search, index caching and protected exclusions, learning memory persistence, and duplicate/version detection.
- Added optional Outlook MSG parsing to the content extra and Windows executable packaging.
- Documented limits: legacy binary DOC/XLS/PPT content extraction, OCR for image-only PDFs, and inaccessible/protected system locations are not supported by this release.

## 0.5.0 — Safe deep search and automatic discovery

- Changed the default scan scope to include all supported file families and extensions across selected local fixed/removable drives and mounted volumes.
- Added read-only repeated-pattern discovery from filenames during recursive scans, including combined discovery across multiple selected drives.
- Requires a pattern to occur in at least two distinct files; repeated words inside one filename do not inflate the match count.
- Filters out built-in and already-saved keywords, separates suggestions by file category, and supplies sample file names and original locations.
- Added a review dialog where users can select, rename or reject suggested groups before any rule is saved.
- Saves only user-approved patterns as persistent local classifier rules, then rescans to create a new organization preview.
- Keeps discovery separate from file operations: scanning and suggesting groups do not copy, move, rename or delete source files.
- Added regression tests for acronym and multiword discovery, single-file rejection, known-rule filtering, file-category separation, selective mode discovery and protected-directory exclusions.
- Clarified safe scan boundaries: Windows, Program Files, ProgramData, AppData, recovery/system areas, recycle bins, links/reparse points, project roots and common dependency folders are excluded; network drives remain opt-in.

## Launcher — run without installing

- Added a one-line PowerShell launcher that fetches the latest stable Windows release, verifies its SHA-256 manifest, extracts into a per-user runtime cache and starts the executable directly.
- The launcher does not run the conventional installer, create shortcuts, set startup entries or require administrator rights.
- Reuses the cached runtime when the latest version is already downloaded; organizer settings remain in the normal per-user data folder.

## 0.4.0 — Branded desktop UI/UX

- Refreshed the desktop workspace with a black navigation rail, white content cards and red action accents.
- Added the supplied face-and-skull artwork as the application mark and window icon.
- Added navigation shortcuts to locations, file formats and topic groups while retaining scan, preview, apply, undo, automation and GitHub actions.
- Included the brand asset in the packaged Windows executable.

## 0.3.8 — Select exact file formats

- Added a second-stage picker for Documents, Images, Videos, Audio, Archives, Code, Applications, Fonts, 3D Models and Others.
- Listed common extensions first and additional/specialist extensions separately.
- Added All supported formats, Only selected formats, Select common, Select all and Clear controls.
- Persisted choices locally and enforced them in manual scans and background monitoring.
- Unselected extensions remain in their original locations.
- Corrected Windows CI fixtures to use project-local temporary directories instead of protected AppData.

# Changelog

## 0.3.6 — One-line installer and automated Windows releases

- Added a PowerShell bootstrap installer that fetches the latest published Windows release, verifies its SHA-256 checksum, installs per-user without administrator rights, creates a Start Menu shortcut, and launches the application.
- Added GitHub Actions workflows for cross-platform tests and Windows executable/release packaging.
- Added an optional Cloudflare Worker endpoint so a controlled custom hostname can serve the installer as `text/plain` at `/`, supporting `irm https://smart.drive.win | iex`.
- Documented the direct GitHub Raw fallback: `irm https://raw.githubusercontent.com/T3ND41/SmartDriveOrganizer/main/install.ps1 | iex`.
- Kept the custom-domain configuration separate because it requires DNS control of the parent domain.
- Kept runtime settings, logs, databases, local destination paths and personal files out of the repository.

## 0.3.5 — Paste-a-link GitHub connection and source publishing

- Replaced the requirement to browse for a pre-cloned repository with a one-time GitHub repository URL field.
- Added HTTPS and SSH GitHub URL validation and automatic clone into a dedicated per-user application-data checkout.
- Persisted repository URL and publishing preferences; retained migration support for existing local-checkout settings.
- Added a separate application-source preview and publish action, with an exact changed-file review before pushing.
- Limited source publishing to an explicit allowlist of application modules, tests, launcher, manifests and documentation; excludes personal rules, drive paths, local databases, activity logs, downloads and arbitrary files.
- Added basic credential/private-key pattern checks before source publishing.
- Kept keyword-rule updates as a separate rules-only commit; absolute local destination paths are omitted from shared rules.
- Added tests for URL validation, automatic clone/reuse, legacy settings migration, source allowlisting, secret checks, preview, and approved source-only commits.

## 0.3.4 — Persistent multi-keyword groups and safe GitHub publishing

- Confirmed and tested multiple keywords/phrases per topic group: any one keyword match routes the file to the same configured destination (OR semantics).
- Topic groups are atomically saved in the per-user application-data folder and survive application restarts.
- Saving changed topic groups asks whether to publish them to the configured GitHub repository by default; the preference can be disabled in the publisher settings.
- Added a testable publish-prompt policy for changed versus unchanged rules.
- GitHub publishing commits only `config/published_topic_rules.json`; local absolute destination paths, source documents, database files and machine-specific settings are excluded.
- Added clearer guidance that the desktop application uses local Git authentication (Git Credential Manager/GitHub Desktop or GitHub CLI); a ChatGPT GitHub connection is not directly inherited by a standalone Windows program.
- The publishing dialog checks repository state and refuses to mix unrelated uncommitted files into the rules commit.

## 0.3.3 — User-defined partial keywords and exact destination routing

- Added a configurable keyword-matching mode per custom topic: partial/contains matching (for example `QUO` matches `Quotation - S01610.pdf`) or whole-word/phrase matching.
- Added an optional exact destination folder for every custom topic rule. Matching files are sent directly into that folder; the folder is created when needed and reused thereafter.
- Added destination selection via folder browser plus support for entering a new destination path manually.
- Applied exact-destination routing consistently to manual scans and automatic background monitoring.
- Added custom-destination exclusions so files already placed in a chosen destination are not repeatedly re-scanned by a monitored parent folder.
- The background monitor refreshes saved custom topic rules during operation so keyword and destination edits take effect without restarting it.
- Kept legacy custom rules on conservative whole-phrase matching unless the user explicitly selects partial matching in the topic editor.
- Added tests for `QUO` matching, exact destination routing, destination exclusion, rule persistence, live rule refresh, and undo of automatic Move actions into custom destinations.

## 0.3.2 — User-defined selective topic groups

- Added a topic-group manager so users can create, edit and remove their own folder labels and keyword/phrase lists.
- Added category scope per topic: Any file type or one specific file category.
- Selective organization now works across selected documents, images, videos, audio, archives, code and other supported file types.
- Manual Scan and preview and background automation share the same saved topic rules.
- Matching uses normalized phrases in filenames for all categories and supported extracted document text for documents.
- Nonmatching files and unselected topic groups remain untouched.
- Added unit and integration tests for custom topic matching, category scope, media routing and rule persistence.

## 0.3.1 — Selective topic organization

- Added a selective document-topic filter for Statements, Requisitions and Quotations in both manual scan/preview and background automation.
- Selective mode normalizes filename variants (for example Monthly Statement and Purchase Requisition) into the selected folder names.
- In selective mode, only matching document files are planned or processed; images, videos, invoices and other non-selected files remain in their original locations.
- Added validation to require Documents and at least one selected topic before selective organization can start.
- Added regression tests for selective routing, unselected-file preservation, and settings persistence.

# Changelog

## 0.3.0 — Automatic background monitoring

- Added saved automation settings for monitored folders, destination, selected file categories, Copy/Move mode and document-text extraction.
- Added recursive polling monitor for selected folders and all their subfolders; new files are discovered without requiring a manual scan.
- Added a persistent SQLite state index so files that arrive while the monitor is stopped can be detected after it starts again, without reprocessing files already known to the monitor.
- Added first-run baseline behaviour: files already present when a folder is first monitored are indexed but left untouched. Use the manual preview workflow for existing files.
- Added file-stability checks, Windows exclusive-read checks, and exclusion of common incomplete-download suffixes before organization.
- Added safe topic-folder names, extension buckets, no-overwrite collision handling and verified copy / safe move behavior for automatic actions.
- Added append-only JSONL activity history, background service status, stop request and single-instance lock.
- Added optional Windows sign-in startup through the current user's Run registry key. This starts after the user signs in; no administrator rights are required for the startup entry.
- Added Automation Settings dialog, Start/Stop monitor controls and Activity log access in the desktop UI.
- Existing manual scan, preview, Copy/Move and Undo workflow remains available.
- Automatic Move actions are recorded as transaction journals and can be reversed with the desktop app’s **Undo last automatic move** control. Restored files are synchronized with the watcher database to prevent immediate reprocessing.
- Added regression coverage for automatic Move undo and rejection of output folders that are ancestors of monitored roots.
- Automated test suite: 44 tests pass in the development environment. The detached background process, first-run baseline, automatic file-arrival organization, activity log and clean stop were integration-tested in the development environment. Windows startup registry behaviour, Windows file locks and real drive permissions still require validation on a Windows machine.

## 0.2.1
- Added built-in Requisitions and Purchase Requisitions topic matching.
- Improved folder reuse, extension subfolders and collision handling.

## 0.2.0
- Added multi-drive discovery and selection.
- Added combined scanning into one output folder and destination self-exclusion.

## 0.1.0
- Initial local-first organizer with recursive scan, keyword grouping, extension buckets, preview, copy/move, audit journal and move undo.


## 0.3.7 — 2026-10-30

- Added `PUSH_TO_GITHUB.bat` and a guided PowerShell script that can create the public GitHub repository, push the full source tree, and publish the first release tag.
- Added checks for Git/GitHub CLI, authenticated account identity, public repository visibility, existing remotes, and non-fast-forward push rejection.
- The setup script stages only an explicit source allowlist, never collects arbitrary documents from the project folder, never force-pushes and asks for confirmation before committing.
- Updated repository setup documentation and the version number to 0.3.7.
