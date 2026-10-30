# GitHub publishing — Smart Drive Organizer

Smart Drive Organizer can publish two different kinds of updates. You connect once by pasting the repository URL; after that, the app remembers it and the publish buttons reuse that connection.

## 1. One-time setup

1. Install **Git for Windows** or **GitHub Desktop**. Git is the command-line transport used by this desktop application.
2. Sign in to GitHub once using GitHub Desktop / Git Credential Manager. Alternatively, install GitHub CLI and run `gh auth login` followed by `gh auth setup-git`.
3. Open Smart Drive Organizer and choose **Publish rules to GitHub…**.
4. Paste the repository's main URL, for example `https://github.com/YOUR-USERNAME/YOUR-REPOSITORY`.
   - HTTPS and SSH clone URLs are accepted.
   - Paste the main repository URL, not a `/tree/...`, `/blob/...`, issue, or pull-request URL.
   - Never paste a personal access token or password into the URL.
5. Click **Save URL & connect**. The app validates the URL and clones the repository into its own managed checkout under `%LOCALAPPDATA%\SmartDriveOrganizer\github_repositories` (Windows) or the corresponding user configuration directory on other systems.
6. Enter your Git commit name and email if they are not already configured in Git. These values identify commits; they are not authentication credentials. Empty GitHub repositories are supported; the app prepares a local initial branch for the first approved commit.

The repository URL, commit identity and prompt preference are saved in the app's per-user settings. The app does not save your GitHub password or token. Git Credential Manager / GitHub CLI handles authentication.

## 2. Publish keyword rules

Use **Publish keyword rules** to publish your custom topic names, multiple keywords, category scope and matching mode. For a group with keywords `QUO`, `Quotation` and `Quote`, all three are included in the same shared group and still route to the same local destination on your computer.

The publisher commits only:

`config/published_topic_rules.json`

It intentionally omits absolute destination paths such as `D:\\Company Records\\Quotations`, because those paths are specific to your laptop. Relative destinations may be shared. The app's local rules remain saved even if a push fails.

When you save changed topic groups, the app can ask whether to publish the rule update. You can disable this prompt in the GitHub publishing window. A manual **Publish rules to GitHub…** button is also available.

## 3. Publish an application source update

Use **Preview / publish app source update…** when you have changed the program code and want those program changes in GitHub.

Before anything is uploaded, the app compares its source tree with the saved repository checkout and shows you the exact new or changed files. It then asks for confirmation. The approved source allowlist is:

- `run.py`, `pyproject.toml`, README, changelog, license, launcher and publishing/setup documentation.
- Python modules under `smart_drive_organizer/`.
- Python tests under `tests/`.
- `config/topic_rules.example.json`.

The source publisher does **not** upload personal topic rules, machine settings, absolute drive paths, local databases, activity logs, downloaded documents, photographs, videos, archives, virtual environments or arbitrary files. It checks approved text files for common credential/private-key patterns and stops if it finds one. Files removed from the local install are not automatically deleted from GitHub.

The application-source update is a normal Git commit pushed to the configured branch, typically named `Update Smart Drive Organizer application` (you can edit the commit message in the window). This is the feature/code update path; keyword-rule updates remain separate small configuration commits. It does not create a formal GitHub Release or version tag.

## 4. Repository safety checks

Before publishing, the app checks that:

- The remote is a GitHub repository and the current branch is checked out.
- The local working tree has no unrelated uncommitted changes.
- The local branch is synchronized with its GitHub remote branch.
- Only the approved file list is staged for the chosen publishing action.

If the repository is dirty or out of sync, publishing stops and asks you to resolve it using GitHub Desktop or Git. It will not mix your unrelated work into the Smart Drive Organizer commit.

## 5. Authentication and troubleshooting

- **Git not found:** Install Git for Windows or GitHub Desktop, then restart Smart Drive Organizer.
- **Authentication failed:** Sign in using GitHub Desktop / Git Credential Manager, or run `gh auth login` and `gh auth setup-git` in a terminal.
- **Private repository:** Your GitHub account must have write access to it.
- **Branch protection:** The app may be allowed to create a commit but GitHub can reject a direct push. Use a branch/pull request workflow if your repository requires it.
- **Repository out of sync:** Pull/reconcile it through GitHub Desktop or Git before retrying.
- **No matching changes:** GitHub already contains the published rules or allowed source files.

The app may report that a commit was created locally but the push failed. Review the local checkout before retrying or use GitHub Desktop to push it. Do not delete that checkout until the local commit is recovered.

## Important distinction

The standalone Windows application uses Git installed and authenticated on that Windows computer. A GitHub connection inside ChatGPT is separate and does not automatically authenticate another application running on your laptop.


## Public repository and one-line installer distribution (0.3.6)

Repository target for this build: `T3ND41/SmartDriveOrganizer` (public, because the Raw bootstrap and release assets must be anonymously readable). The source contains no local settings, databases, activity logs, personal documents or drive-specific paths. Review `.gitignore` before adding any files.

### First release

1. Push the repository contents to the `main` branch.
2. Confirm GitHub Actions has permission to create releases (`contents: write` in `.github/workflows/release.yml`).
3. Create and push tag `v0.3.6`.
4. The Windows workflow tests the program, builds `SmartDriveOrganizer.exe`, creates `SmartDriveOrganizer-windows-x64.zip`, writes `SHA256SUMS.txt`, and publishes both assets as a GitHub Release.
5. Check that the latest release contains both expected assets before publishing the installer command.

### Run without manually downloading a ZIP

After the public repository and first release exist, this command downloads and installs the latest release automatically:

```powershell
irm https://raw.githubusercontent.com/T3ND41/SmartDriveOrganizer/main/install.ps1 | iex
```

The installer runs per-user, checks the downloaded ZIP SHA-256 hash against the release manifest, installs the EXE into `%LOCALAPPDATA%\Programs\SmartDriveOrganizer`, creates a Start Menu shortcut and starts the app. It aborts if the app is currently running or if the checksum does not match.

### `smart.drive.win` alias

GitHub Raw cannot serve a custom hostname by itself. The optional Cloudflare Worker in `cloudflare/worker.js` proxies only `install.ps1` and explicitly returns `Content-Type: text/plain` at `/`, supporting:

```powershell
irm https://smart.drive.win | iex
```

Deploy it using `cloudflare/README.md` and `cloudflare/wrangler.toml`. This requires permission to manage the parent `drive.win` DNS zone and a Cloudflare account that contains that zone. Until DNS and Worker routing are configured and verified, use the Raw URL.

### Remote-script safety

`irm | iex` executes the downloaded installer code in the current PowerShell process. Users should inspect `install.ps1` at the repository's Raw URL before running it. The installer checks that release asset URLs come from the expected GitHub Releases host and verifies the ZIP's SHA-256 against the release manifest before installation. It does not request elevation and does not touch user source files.
