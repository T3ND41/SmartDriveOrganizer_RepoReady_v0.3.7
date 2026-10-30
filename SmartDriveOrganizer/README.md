# Smart Drive Organizer

**Version 0.3.7 — multi-drive organization, background monitoring, custom routing and URL-based GitHub publishing**

A local-first Windows desktop utility that detects mounted drives, scans several selected drives and folders in one operation, groups files by meaningful filename/document keywords, and collects them into one destination folder on a drive you choose. It is designed around preview-before-action and non-overwriting file operations.

## The folder structure it creates

For example, with a source containing monthly statements and delivery notes in PDF, Word and Excel formats:

```text
Organized_Output/
└── Documents/
    ├── Monthly Statements/
    │   ├── PDF/
    │   ├── DOCX/
    │   └── XLSX/
    └── Delivery Notes/
        ├── PDF/
        ├── DOCX/
        └── XLSX/
```

The same pattern is used for images, videos, audio, archives, code, applications, fonts, 3D models and other files:

```text
Organized_Output/
├── Images/Photographs/JPG/
├── Videos/Training Videos/MP4/
├── Audio/Music/MP3/
└── Archives/Unclassified Archives/ZIP/
```

The category and topic folders are created only when you apply a plan. The file extension folder keeps different formats together without mixing PDFs, DOCX and XLSX files.

## Current features

- Automatically detect mounted Windows fixed, removable and mapped network drives.
- Preselect local fixed/removable drives; mapped network drives are listed but left unselected until you choose them.
- Select several drives and manually added folders for one combined scan and one output destination.
- Recursively scan each selected source, or scan only its top level.
- Collapse duplicate/nested source selections so the same files are not intentionally scanned twice.
- Allow the output folder to live on a selected drive, including inside a selected drive root; the output folder itself is excluded from scanning.
- Select one or more file families: Documents, Images, Videos, Audio, Archives, Code, Applications, Fonts, 3D Models and Others.
- Match common business document names such as monthly statements, delivery notes, requisitions and purchase requisitions, purchase orders, invoices, quotations, tenders, receipts, contracts, reports, payslips, tax documents, certificates and manuals.
- Add your own keyword phrases and choose the folder label they should create.
- For each custom topic, select partial/contains matching or whole-word/phrase matching. For example, `QUO` in Contains mode matches `Quotation - S01610.pdf`.
- Assign an exact destination folder to each topic rule. Matching files are placed directly in that folder; the folder is created if missing and reused for future matching files. Leave it blank to use the standard Category/Topic/Extension structure.
- Exact per-topic routing works in manual scans and automatic monitoring. The selected topic destination is excluded from a monitored source tree to prevent the organizer from reprocessing its own output.
- The background monitor refreshes topic rules while running, so saved keyword and destination edits take effect without restarting the monitor.
- Read text from supported local document formats where optional readers are installed. Filename matching works without optional packages.
- Review the planned destination for every scanned file before changing anything.
- Choose **Copy** or **Move**. Copy is selected by default for the first run.
- Never overwrite an existing destination file. A collision receives a numbered filename such as `statement (1).pdf`.
- Copy through a temporary staging file and compare SHA-256 hashes before publishing it.
- Same-volume moves use a rename operation. Cross-volume moves copy and verify the destination before relocating the original path.
- Keep a JSON audit journal for every run, written before each file operation. Move runs can be undone, provided the original paths are free; an interrupted move can be recovered from the journal when the source/destination state is clear.
- Skip common Windows system folders and system files, recycle bins, symlinks/junctions, offline cloud placeholders, shortcuts, temporary downloads, Git metadata, virtual environments, dependency folders and detected software-project roots.
- Core scanning and organization use the Python standard library. There is no cloud service or API key requirement.
- Save automation settings for selected monitored folders, a destination folder, file categories, and Copy/Move mode.
- Monitor selected folders recursively in a separate background process, even after the desktop window is closed.
- Poll new files at a configurable interval, wait for stable file size/time, and skip common incomplete download extensions. Windows also checks that the file is not held open by another process.
- Persist a SQLite index so arrivals that occur while the monitor is stopped can be found after it restarts, without repeatedly organizing known files.
- Optionally register the monitor to start at the current user's Windows sign-in through the HKCU Run key.
- Keep an append-only JSONL activity log and a background-service status file. Start/Stop monitoring, undo the most recent automatic Move, and open the activity log from the desktop UI.
- Record each automatic Move action in the transaction journal; the desktop UI includes **Undo last automatic move**. Undo restores the source path only when it is free and updates the watcher index so the restored file is not immediately moved again.


## Create and publish the GitHub repository

Run `PUSH_TO_GITHUB.bat` on Windows to create the public `T3ND41/SmartDriveOrganizer` repository, push the full source, and publish tag `v0.3.7`. The helper uses GitHub CLI, checks that you are authenticated as `T3ND41`, shows the staged file list, and never force-pushes. See `REPOSITORY_SETUP.md`.

## One-line Windows installer (0.3.7 distribution setup)

After the public repository and its first tagged GitHub Release are published, users can install the Windows application without manually downloading or extracting a ZIP. The installer automatically downloads the latest release, checks the package against the release SHA-256 manifest, installs it under the current Windows user's LocalAppData, creates a Start Menu shortcut, and launches the app. It does not request administrator rights.

Direct GitHub Raw command:

```powershell
irm https://raw.githubusercontent.com/T3ND41/SmartDriveOrganizer/main/install.ps1 | iex
```

Custom short command (only after the optional Cloudflare Worker and `smart.drive.win` DNS route are configured):

```powershell
irm https://smart.drive.win | iex
```

The one-line command avoids manual downloading; the installer still downloads and installs the executable automatically in the background. `irm | iex` executes remote code in the current PowerShell session. Read the installer source from the Raw URL first, and only run it when you trust the repository and HTTPS endpoint. The installer verifies the release ZIP hash before installing it.

### Publishing a Windows release

Push source to `main`, then create and push a version tag, for example:

```powershell
git tag v0.3.7
git push origin v0.3.7
```

GitHub Actions runs the test suite on Windows, then builds `SmartDriveOrganizer.exe` on a Windows runner and publishes `SmartDriveOrganizer-windows-x64.zip` plus `SHA256SUMS.txt` as a GitHub Release. The installer fetches the latest release assets.

### Optional custom domain

`cloudflare/worker.js` serves the installer source at the root URL as `text/plain` so PowerShell receives source text rather than an HTML page. Deploy it with the instructions in `cloudflare/README.md`. This requires administrative control of the `drive.win` DNS zone and a Cloudflare account with that zone. Until it is configured, use the direct GitHub Raw URL above.

## Important safety behaviour

1. **No action happens during scanning.** Scanning builds a preview only. Files are not changed until you click **Apply organization** and confirm.
2. **Copy mode leaves every source file in place.** Use this first with a small test folder.
3. **Move mode relocates files; it does not discard their contents.** For same-drive moves, the file is renamed into its new path. For cross-drive moves, the app stages a copy, compares SHA-256 hashes, publishes the verified destination, and only then removes the original pathname as part of the move. If verification or copying fails, the source is left untouched.
4. **Existing files are never overwritten.** A new numbered filename is selected instead.
5. **The destination is protected from self-scanning.** The application blocks a destination that is the same as, or an ancestor of, a selected source root. A destination folder inside a source root is allowed, but that exact output folder and its contents are pruned from the scan. This lets you organize a drive onto itself without collecting its previous output again.
6. **Undo is available for manual and automatic Move runs.** The desktop app has separate controls for the latest manual Move and latest automatic Move journal. Undo restores files to their original paths only when those paths are free. If an original path is occupied or the organized copy is missing, the app skips that file and records the reason rather than overwriting anything. After an automatic Move is undone, the monitor index is refreshed so the restored file is not automatically moved again.
7. **Copy runs are not automatically undone.** Reversing a copy would require deleting the new copies, which conflicts with the project's no-delete policy. The originals remain untouched.
8. **No duplicate files are automatically deleted.** Identical files are retained; duplicate detection/reporting is a later stage.
9. **Automatic monitoring has a first-run baseline.** When you first enable a monitored folder, the monitor indexes files already present and leaves them where they are. Use the manual Scan and preview workflow for older files. Only new arrivals after that baseline are automatically organized.
10. **Automatic monitoring waits for downloads to finish.** It ignores common temporary suffixes and waits for stable file metadata over multiple polling cycles. On Windows it also attempts an exclusive read open before processing.
11. **Automatic monitoring is limited to folders you select.** It is not a hidden system-wide hook. It recursively checks those folders at the chosen interval; full-drive monitoring is possible but can use noticeable disk activity.

The application creates and removes its own temporary staging files while copying. It does not run a cleanup operation against the user's source folders.

### What "whole-device scan" means in this release

On Windows, the drive picker enumerates assigned logical drive letters for fixed disks, removable storage and mapped network drives. Local fixed/removable disks are preselected; network drives are available to select manually. A scan recursively checks the selected roots and combines matching files into one collection. It is not a forensic scan of every Windows-managed file: protected system/dependency directories, recycle/system metadata, application caches (`AppData`), links/junctions, offline cloud placeholders, temporary/incomplete downloads and detected software project roots are deliberately skipped. Windows access-denied areas are reported as warnings where the operating system permits the error to be observed. Hidden volume mount points that do not have a drive letter are not currently discovered by the Windows drive picker.

## Requirements

- Windows 10 or Windows 11 recommended.
- Python 3.10 or newer. Python 3.12 is supported by the code structure.
- Tkinter, which is normally included with the standard Windows Python installer.
- Optional document readers (see below).
- Drive discovery uses Windows logical drive letters. CD/DVD drives are excluded. On Linux/macOS, mounted-volume discovery is best-effort and can use optional `psutil` if installed.

## Run it on Windows

1. Extract the `SmartDriveOrganizer` folder to a location such as `C:\Tools\SmartDriveOrganizer`.
2. Open the folder in File Explorer.
3. Click the address bar, type `powershell`, and press Enter.
4. Run:

   ```powershell
   python run.py
   ```

5. The **Source drives / folders** list shows detected volumes. Fixed and removable local drives are selected by default. Use Ctrl-click/Shift-click to change the selection; **Select all** also selects listed network drives.
6. Use **Add folder…** to include an extra folder. If a drive root and one of its subfolders are both selected, the child is automatically collapsed to avoid duplicate scanning.
7. Choose an **Output / destination folder** on the drive where you want the organized collection. It can be on a separate drive or inside one of the selected drives; the output folder is excluded from scanning.
8. Select the file types to scan. Documents is selected initially; use **Select all** to include all supported file families.
9. Click **Scan and preview**. Review the proposed keyword group and extension folder. Check any permission or skipped-folder warnings.
10. Start with **Copy files**. Apply the plan only after the preview looks correct. Inspect the destination before considering Move mode.
11. When satisfied, repeat using **Move files** for the actual relocation task.

## Automatic background monitoring

1. Start the desktop application with `python run.py`.
2. Click **Automation settings…**.
3. Add your **Downloads** folder. Add any other folders where files are saved, such as Desktop or Documents. You may select a drive root, but recursive full-drive monitoring is more disk-intensive.
4. Choose the destination folder. It can be on another drive. If the destination is inside a monitored folder, that output subtree is excluded from monitoring.
5. Select the file categories to organize. Select **Others** as well if you want unrecognized extensions collected.
6. Choose **Copy** or **Move**. Copy is recommended until you have checked the results.
7. Check **Enable automatic monitoring now**. On Windows, optionally check **Start the background monitor automatically when I sign in to Windows**.
8. Click **Save settings and start**. The separate background process continues after the desktop window is closed. Open the desktop application and click **Stop monitor** to stop it.

The monitor polls every 5–60 seconds (10 seconds by default). A new file normally needs several unchanged observations before it is processed; actual time depends on the polling interval and download completion. Temporary extensions such as `.crdownload`, `.part`, `.tmp`, `.download` and `.partial` are ignored. On Windows, the application also checks that there is no active writer holding the file. When a browser renames its completed download to the final filename, that final file is picked up. If the output drive is disconnected or unavailable, new files remain in their source folders and stay queued for a later check.

The first time a folder is monitored, its existing files are indexed as a baseline and are not automatically moved or copied. This is deliberate: enabling background monitoring must not suddenly reorganize a whole Downloads folder or drive. Use **Scan and preview** for pre-existing files. The SQLite index persists, so files arriving while the monitor is stopped can be detected when it restarts, provided that folder was already baselined.
For troubleshooting, the background service can also be started directly from PowerShell with `python run.py --background`. The desktop app is the normal way to configure and control it.

Custom keyword rules are reloaded from the saved rules file during monitor cycles. For each new file, the program uses its filename, extension and (when enabled and supported) document text. It creates/reuses `Category\Topic\Extension` folders, preserves the original filename, and gives a numbered suffix to a conflicting destination name rather than overwriting it.

Automation settings and state are stored under `%LOCALAPPDATA%\SmartDriveOrganizer` on Windows. The activity history is `automation_activity.jsonl`; the file-state database is `automation_state.sqlite3`; and service output is `automation_service.log`. The Windows startup entry is stored in the current user's `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` key, so administrator access is not required. It launches after sign-in, not before the Windows login screen. Keep the extracted application folder in the same place after enabling startup because the startup entry points to its `run.py`.

**Performance note:** Monitoring Downloads and selected work folders is recommended. Monitoring an entire drive means recursively checking that tree at each polling cycle and can produce noticeable disk activity. Increase the interval for large monitored roots. Removable or network folders that are unavailable are skipped until they become available again.

## Optional document-content readers

The core application classifies by filename and extension without extra packages. To also match terms inside supported document files, install the optional readers:

```powershell
python -m pip install -r requirements-content.txt
```

Optional readers:

- PDF: `pypdf`
- XLSX/XLSM: `openpyxl`
- PPTX: `python-pptx`
- DOCX text is read using Python's built-in ZIP/XML libraries.
- Plain text, CSV, TSV, Markdown, JSON, XML, HTML, YAML and log files are read using the standard library.

Content extraction is best-effort and limited to the first 8 PDF pages, 3 workbook sheets, 15 presentation slides, or 12,000 characters. Large documents over 20 MB are not text-extracted. Scanned PDFs and image OCR are not included yet.

## Select only the topic groups you choose — documents and media

Both the manual Scan and preview screen and the background Automation Settings include a selective topic option. Enable **Only organize files matching the topic groups selected below** and tick only the groups you want. Any file that does not match one of those selected groups is left in its original location.

The built-in groups include Statements, Requisitions and Quotations. You can also click **Add / manage my own topic groups…** to create a group with your own folder label, keywords and file-category scope.

Example custom topic:

- Folder name: `Supplier Invoices`
- Keywords and phrases: `supplier invoice`, `tax invoice`, `vendor bill`, `proforma invoice`
- Apply to file category: `Any` (or choose Documents, Images, Videos, Audio, etc.)

You can create groups such as `Site Photographs`, `Safety Training Videos`, `Supplier Invoices`, `Equipment Manuals`, or any other label. Enter several phrases separated by commas or new lines. The application normalizes case, underscores, hyphens and punctuation when matching. It prefers the longest matching phrase and uses filename matching for all supported file categories. When document-text reading is enabled, supported document text can also be used for a match.

A custom group with the `Any` scope can match any file category selected in the main file-type options. A group scoped to `Images`, for example, only matches image files. The destination is `Category\<Your Topic>\<Extension>`. Existing topic and extension folders are reused; missing folders are created. Unselected groups and nonmatching files are not copied or moved.

Custom selective-topic rules are saved locally at `%LOCALAPPDATA%\SmartDriveOrganizer\topic_rules.json` on Windows (or `~/.config/SmartDriveOrganizer/topic_rules.json` on Linux/macOS). They are shared by manual scans and background monitoring. The checkboxes for selected topic groups are saved with automation settings.

**Classification boundary:** keyword matching is deterministic phrase matching, not general AI understanding. Add the synonyms and alternative wording you want the organizer to recognize. Filename matching works for images, videos, audio and other file types. Content matching currently applies to supported text-based documents; image OCR, visual recognition, video scene analysis and audio transcription are not included yet.

## Add your own general keyword rules

The separate **Add keyword rule…** action adds a general classification rule for the normal, non-selective organization mode. For targeted organization that must leave every unselected file alone, use **Add / manage my own topic groups…** and tick the matching topic group.

General keyword rules are saved locally at:

- Windows: `%LOCALAPPDATA%\SmartDriveOrganizer\keyword_rules.json`
- Linux/macOS: `~/.config/SmartDriveOrganizer/keyword_rules.json` (or `$XDG_CONFIG_HOME` when set)


## Persistent keyword groups and GitHub publishing

A topic group can contain any number of alternative keywords or phrases. Separate them with commas or new lines. Matching uses OR logic: any one phrase can route the file to that group's destination. For example, `QUO`, `Quotation`, `Quote` and `RFQ` can all route to one `Quotations` folder. The group name, keywords, matching mode, category scope and local destination are saved in the user's application-data folder and survive restarts.

After you save changed topic groups, the application can ask whether you want to publish the updated shared rules to GitHub (enabled by default). For one-time GitHub setup, open **Publish rules to GitHub…**, paste the main repository URL and click **Save URL & connect**. The app clones it into its own managed checkout under the user's application-data folder and remembers the URL.

The publisher offers two separate actions:

- **Publish keyword rules** commits only `config/published_topic_rules.json`. It includes the shared topic labels, keywords, category scopes and match modes, but deliberately excludes absolute local destination paths, downloaded files, local databases, watcher state and logs.
- **Preview / publish app source update** compares the approved application source files, displays the new/changed-file list, and asks you before committing and pushing the program update. The allowlist includes application Python modules, tests, launcher, manifests and documentation; it excludes personal settings, databases, logs, downloads, media and arbitrary files. Basic common-token/private-key checks are performed before source publishing. The commit message can be customized; this creates a normal branch commit, not a formal GitHub Release/tag.

GitHub authentication is provided by Git for Windows / Git Credential Manager / GitHub Desktop or GitHub CLI on the Windows computer. The standalone application does not store GitHub passwords or access tokens. The ChatGPT GitHub connection is separate from the desktop application's local Git authentication.

See [PUBLISHING_TO_GITHUB.md](PUBLISHING_TO_GITHUB.md) for step-by-step setup, publishing boundaries and troubleshooting.

## Run the tests

From the project folder:

```powershell
python -m unittest discover -s tests -v
```

The tests use temporary folders and sample files. They do not touch the user's real drives.

## Build a Windows EXE (optional)

The source version is the recommended first test. Once the UI is tested on the target Windows laptop, a single-folder or one-file executable can be built with PyInstaller:

```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm --windowed --name SmartDriveOrganizer run.py
```

The executable is created under `dist`. This build instruction is provided, but a Windows executable has **not** been compiled or verified in this environment.

## Roadmap

### Stage 1 — safe organizer foundation (implemented)
- Recursive single-folder and multi-drive scanning.
- Mounted drive discovery and multi-source selection.
- One shared destination across selected sources, with destination self-exclusion.
- Keyword rules from filenames and supported document text.
- Category → topic → extension folder structure.
- Copy/move selection, collision protection, preview, audit log and Move undo.

### Stage 2 — stronger classification
- Configurable keyword-rule manager: edit, disable, reorder and import/export rules.
- Better automatic phrase discovery from repeated filename patterns.
- Optional local Ollama text classification for ambiguous documents, with a confidence threshold and mandatory review.
- Optional semantic grouping using local embeddings; rules remain the deterministic fallback.

### Stage 3 — richer media support
- Image metadata (EXIF, dimensions, date taken) and optional local vision model analysis.
- Audio tags and optional local speech transcription.
- Video metadata, optional keyframe analysis and local scene summaries.
- OCR for scanned PDFs and image-based documents, only when explicitly enabled.

### Stage 4 — library management and scale
- Hash-based duplicate report (report-only; no automatic deletion).
- Searchable run history and safe recovery dashboard.
- Large-drive scanning improvements, resumable scans and better cancellation.
- System-tray menu, scheduled rules and Windows Explorer integration.
- Advanced analytics and exportable CSV/HTML reports.

### Stage 5 — richer local intelligence
- Optional local Ollama text classification for ambiguous documents, with a confidence threshold and review queue.
- Image metadata, optional local image understanding, OCR for scanned PDFs and image-based documents.
- Audio tags and optional local speech transcription; video metadata and optional keyframe summaries.
- Local embeddings for semantic search and suggestions, with deterministic keyword rules as fallback.

## Research references

The implementation was independently written for this project. These public projects informed the feature review and roadmap; their source code has not been copied into this application:

- [hyperfield/ai-file-sorter](https://github.com/hyperfield/ai-file-sorter) — preview-first categorization, local models, learned review decisions, custom category whitelists and project-root protection. It is licensed AGPL-3.0, so direct code reuse would require a separate licence review.
- [SmithaShivakumar/FileOrganizer-Agent](https://github.com/SmithaShivakumar/FileOrganizer-Agent) — filename/extension/metadata context, project categorization, dry-run, duplicate filename handling and batched AI categorization.
- [diganto-deb/local_file_organizer](https://github.com/diganto-deb/local_file_organizer) — explicit allowed directories, recursive file-type grouping and directory analytics.
- [FreakySneaky787/Simple-Organizer](https://github.com/FreakySneaky787/Simple-Organizer) — standard-library design, preview, undo and “nothing deleted or overwritten” emphasis.
- [Smart AI File Organizer](https://pypi.org/project/smart-ai-file-organizer/) — structured history, dry-run, content-aware classification, duplicate hashing and semantic search.
- [Local File Organizer](https://pypi.org/project/local-file-organizer/) — optional local Ollama, image analysis, audio transcription, video keyframes, rule automation and learned preferences.
- [ForgeLabsSoft/ai-file-butler](https://github.com/ForgeLabsSoft/ai-file-butler) — offline local-AI architecture for documents and rich media metadata.
- [narendradodke/smart-file-organizer](https://github.com/narendradodke/smart-file-organizer) — extension rules, date-based organization, checksum duplicate detection, collision-safe naming and transaction journals.


