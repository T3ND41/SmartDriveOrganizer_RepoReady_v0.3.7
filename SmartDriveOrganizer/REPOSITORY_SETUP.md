# Create and publish the Smart Drive Organizer GitHub repository

This project includes a guided Windows script that creates the public GitHub repository, commits the application source, pushes the `main` branch, and pushes the `v0.3.7` tag.

## One-click setup on Windows

1. Extract the complete project folder to a permanent location.
2. Install Git for Windows if it is not already installed: <https://git-scm.com/download/win>.
3. Double-click `PUSH_TO_GITHUB.bat`.
4. If GitHub CLI is missing, the script offers to install it using Windows Package Manager. You can also install it from <https://cli.github.com/>.
5. The script checks GitHub CLI authentication. If needed, it opens the browser sign-in flow. Sign in as `T3ND41`.
6. Review the list of staged project files and confirm the commit.
7. The script creates `T3ND41/SmartDriveOrganizer` as a **public** repository if it does not exist, pushes `main`, then pushes tag `v0.3.7`.

The GitHub CLI's `repo create --source --remote --push` command is the supported mechanism for creating a repository from an existing local project. See <https://cli.github.com/manual/gh_repo_create>.

## Safety checks

- The script requires authentication as `T3ND41` and refuses to use a different account.
- It does not request administrator rights.
- It reviews staged file names and asks for confirmation before committing.
- It stages only an explicit source-file allowlist and checks the staged index before committing. It will not pick up arbitrary documents or personal files placed in the project folder. `.gitignore` also excludes local runtime databases, activity logs, local/private settings, virtual environments and build output.
- It refuses to replace an unrelated `origin` remote.
- It never force-pushes. If the remote already contains unrelated commits, it stops and asks for history reconciliation.
- It does not upload scanned documents, personal files, or local absolute destination paths.
- Repository visibility must be public for anonymous `irm` installation. The script creates a public repository; if an existing repository is private, it stops rather than silently changing visibility.

## First Windows release and installer

Pushing tag `v0.3.7` triggers `.github/workflows/release.yml`. GitHub Actions runs the tests on a Windows runner, packages the Windows executable and publishes:

- `SmartDriveOrganizer-windows-x64.zip`
- `SHA256SUMS.txt`

After the release is published, install from PowerShell with:

```powershell
irm https://raw.githubusercontent.com/T3ND41/SmartDriveOrganizer/main/install.ps1 | iex
```

This command runs the published installer script, which downloads the latest release ZIP, verifies its SHA-256 checksum, installs the application per-user and creates a Start Menu shortcut. It does not eliminate downloading; it automates it without asking the user to manually download or extract the package.

## Optional short domain

`irm https://smart.drive.win | iex` only works after the Cloudflare Worker in `cloudflare/worker.js` is deployed and the `smart.drive.win` DNS route is configured by whoever controls the `drive.win` DNS zone. Until that is completed, use the GitHub Raw command above.
