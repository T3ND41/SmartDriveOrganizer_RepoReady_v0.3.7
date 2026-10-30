# File Organizer Research Notes

**Research date:** 30 October 2026  
**Purpose:** Select capabilities and safety principles for Smart Drive Organizer 0.3.0.  
**Scope:** The three repositories supplied by the user plus additional publicly discoverable organizer projects. Repository READMEs and published documentation were reviewed; this is a feature/architecture review, not a full independent security audit of every source file.

## Executive conclusion

The closest match to the requested behaviour is a hybrid:

1. **Deterministic filename and keyword rules** for predictable business-document folders such as `Monthly Statements` and `Delivery Notes`.
2. **Extension subfolders** inside each topic group (`PDF`, `DOCX`, `XLSX`).
3. **Optional content extraction and local AI** for badly named files whose names do not reveal their purpose.
4. **A mandatory preview, collision-safe actions, operation journal and undo** before/after any move.

The high-end projects demonstrate that AI can help with semantic grouping and media understanding, but using AI for every file from the first release would increase model storage, processing time, setup complexity and classification uncertainty. A rules-first release is easier to test and safer; optional local AI can be added behind a confidence threshold later.

## Repository review

| Project | Approach and useful features | Limitations / relevance |
|---|---|---|
| [hyperfield/ai-file-sorter](https://github.com/hyperfield/ai-file-sorter) | Most mature of the supplied examples. Its README describes a desktop application with local/remote LLMs, image and document analysis, audio/video metadata, category/subcategory suggestions, preview, dry-run, learned review choices, custom whitelists, cache and undo. It also protects recognized software project roots. | Strongest reference for semantic categorization and human review. It is AGPL-3.0, so copying its code into another product requires licence obligations to be assessed. This project borrows ideas, not source code. |
| [SmithaShivakumar/FileOrganizer-Agent](https://github.com/SmithaShivakumar/FileOrganizer-Agent) | Small AI agent for Downloads. Its documented signals are filename, extension, metadata and project naming; it creates project folders, supports dry-run, renames collisions and batches model calls. | Narrower scope: the README describes only the Downloads directory and files directly in it, not a full-drive library organizer. Requires a provider API key. |
| [diganto-deb/local_file_organizer](https://github.com/diganto-deb/local_file_organizer) | Python/MCP example with explicit allowed directories, recursive processing, type-based folders for documents/images/videos/audio/archives/code/apps, project-root detection and directory statistics. | A small MCP integration rather than a full desktop organizer with a preview and transaction history. Useful for access boundaries and recursive type classification. |
| [FreakySneaky787/Simple-Organizer](https://github.com/FreakySneaky787/Simple-Organizer) | Windows/Linux desktop app using Python standard library. Documents preview, undo/history, custom rules, staging/commit/revert, recursive-scan limits, collision-safe names and a strict no-delete/no-overwrite approach. It records undo information while moving. | Mostly category/type sorting rather than deep content-aware topic classification. Its safety philosophy is especially relevant to this project. |
| [mojouto3/mojo-file-organizer](https://github.com/mojouto3/mojo-file-organizer) | Windows Electron desktop app. Documents preview, custom categories, extension maps, client/store-name grouping, duplicate tools, folder monitoring, rules, statistics and session history. The rule workflow has preview, conflict warning and undo. | More UI and rule-automation oriented than semantic document grouping. Useful roadmap ideas after the basic engine is stable. |
| [Smart AI File Organizer](https://pypi.org/project/smart-ai-file-organizer/) | Python project describing content-based classification, transformer embeddings with TF-IDF fallback, hash-based duplicate detection, semantic search, dry-run and structured undo history. | Published as beta; richer ML modes bring model and dependency overhead. The structured history and offline fallback are worth adopting as later capabilities. |
| [Local File Organizer](https://pypi.org/project/local-file-organizer/) | Describes a broad local-first toolkit using Ollama or compatible endpoints, optional vision, document analysis, audio transcription, video keyframes, rule automation, tagging, analytics and undo/redo. | Broad capability set, but optional model/media dependencies can be heavy. Better treated as a feature reference than a base dependency for a lightweight first release. |
| [ForgeLabsSoft/ai-file-butler](https://github.com/ForgeLabsSoft/ai-file-butler) | Windows/C# local-AI concept. Describes document extraction, Windows OCR, image analysis, media metadata, learned corrections and offline privacy. | Windows-specific and GPL-3.0. Useful as a media/OCR roadmap reference, not a direct dependency. |
| [narendradodke/smart-file-organizer](https://github.com/narendradodke/smart-file-organizer) | Python desktop UI concept with editable extension maps, date organization, hash duplicate checking, collision-safe names, confirmation preview and transactional undo. | Small repository; feature claims should be validated against actual implementation and tests before adopting. |

## Feature decisions for this implementation

| Capability | Stage 1 decision | Reason |
|---|---|---|
| Recursive scan | Included | Required for drive-wide collection. |
| File family selection | Included | User can select documents, images, video, audio, etc. |
| Keyword grouping | Included | Primary user requirement; includes common business document phrases and user-defined rules. |
| Extension subfolders | Included | Produces `Monthly Statements/PDF`, `Monthly Statements/DOCX`, etc. |
| Text extraction | Included, optional packages | Adds document-text matching without requiring cloud services. |
| AI semantic classification | Later stage | Keep initial classification deterministic, local and auditable. Add optional Ollama after baseline performance and confidence handling are tested. |
| Image OCR / visual analysis | Later stage | Requires OCR/vision libraries or a local vision model; do not block core file sorting on this. |
| Audio transcription / video keyframes | Later stage | Computationally expensive; optional feature packs only. |
| Preview before changes | Included | No file mutations during scan. |
| Copy or Move | Included | Copy is the default safer first-run action. |
| Collision handling | Included | Never overwrite; use numbered alternatives. |
| Hash verification | Included for copies and cross-volume moves | A cross-drive move only removes the old path after a checksum-verified destination has been published. |
| Undo | Included for Move | Restores to original paths when free; refuses to overwrite a file already there. Copy mode is not automatically undone because that would require deleting created copies. |
| Duplicate removal | Not included | The user explicitly says the tool must not delete files. A later duplicate finder should be report-only. |
| Project/system protection | Included | Avoid moving Windows folders/files, VCS metadata, dependency trees, virtual environments, cloud placeholders, shortcuts, temporary downloads and detected code project roots. |
| Watch folders | Included in 0.3.0 | Saved folder monitoring with file-stability checks, persistent SQLite state, background service, log and optional Windows sign-in launch. |

## Current implementation status

Smart Drive Organizer 0.3.0 retains the recursive multi-drive manual workflow and adds automatic monitoring of selected folders. The background process polls those folders recursively, keeps a persistent SQLite inventory, waits for new files to stabilize, applies saved keyword/content rules and category settings, creates or reuses `Category/Topic/Extension` folders, and records actions in a local JSONL activity log. It can be configured to start at the current user's Windows sign-in using the per-user Run registry key. The first scan of each newly configured root is a baseline: pre-existing files are indexed but not automatically moved or copied. Automatic Move actions are individually journaled and can be reversed from the desktop UI; the persistent watcher index is refreshed after an undo so it does not immediately move the restored file again. New files arriving after baseline, including files that arrive while the service is stopped, are automatically handled when stable. If the output drive is temporarily unavailable, eligible new files remain queued in the source folder. The selected monitor roots are explicit; it is not a system-wide filesystem hook or a pre-login Windows service.

The project does **not** yet include local AI, OCR, image understanding, or full audio/video content analysis. Duplicate detection is not part of automatic organization; no files are automatically deleted.

The automated tests use temporary folders and synthetic sample files. They verify phrase grouping, extension folders, custom category-specific rules, project-folder skipping, destination self-exclusion, multi-source collection, nested-source deduplication, copy-preserves-original, collision-safe names, move-and-undo, persistent monitoring state, first-run baselines, stable-file checks, temporary-download exclusion, automatic Move undo, and background process start/stop/file arrival on the development environment. They do not constitute a physical Windows laptop test, Windows registry startup test, Windows file-lock test, or multi-terabyte drive performance test.
