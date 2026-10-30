$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Owner = 'T3ND41'
$RepositoryName = 'SmartDriveOrganizer'
$Repository = "$Owner/$RepositoryName"
$Description = 'Local-first Windows desktop file organizer with multi-drive scanning, custom keyword routing, background monitoring and a verified PowerShell installer.'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$TargetTag = 'v0.3.7'

function Write-Step {
    param([string]$Message, [ConsoleColor]$Color = [ConsoleColor]::Cyan)
    Write-Host "[Smart Drive Organizer] $Message" -ForegroundColor $Color
}

function Stop-Safely {
    param([string]$Message)
    Write-Step $Message -Color Red
    throw $Message
}

try {
    Write-Step "Project folder: $ProjectRoot"

    $gitCommand = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitCommand) {
        Stop-Safely 'Git for Windows is not installed. Install Git for Windows, reopen PowerShell, and run this script again.'
    }

    $ghCommand = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $ghCommand) {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if (-not $winget) {
            Stop-Safely 'GitHub CLI (gh) is required to create and publish the repository. Install it from https://cli.github.com/ and reopen PowerShell.'
        }

        $answer = Read-Host 'GitHub CLI is missing. Install it with Windows Package Manager now? (Y/N)'
        if ($answer -notmatch '^(?i)y(es)?$') {
            Stop-Safely 'GitHub CLI installation was skipped. Install it from https://cli.github.com/ and run this script again.'
        }
        & $winget.Source install --id GitHub.cli --exact --source winget --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) {
            Stop-Safely 'GitHub CLI installation failed. Install it manually from https://cli.github.com/.'
        }

        $candidatePaths = @(
            (Join-Path $env:ProgramFiles 'GitHub CLI\gh.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\GitHub CLI\gh.exe')
        )
        $ghPath = $candidatePaths | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
        if (-not $ghPath) {
            Stop-Safely 'GitHub CLI was installed. Close this window, open a new PowerShell window, and run PUSH_TO_GITHUB.bat again.'
        }
    }
    else {
        $ghPath = $ghCommand.Source
    }

    Write-Step 'Checking GitHub CLI authentication...'
    & $ghPath auth status --hostname github.com
    if ($LASTEXITCODE -ne 0) {
        Write-Step 'A browser sign-in is required. Follow the GitHub CLI prompts.' -Color Yellow
        & $ghPath auth login --hostname github.com --git-protocol https --web
        if ($LASTEXITCODE -ne 0) {
            Stop-Safely 'GitHub sign-in did not complete.'
        }
    }

    $authenticatedUser = (& $ghPath api user --jq '.login' 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $authenticatedUser -ine $Owner) {
        Stop-Safely "GitHub CLI is authenticated as '$authenticatedUser', but this project is configured for '$Owner'. Run 'gh auth switch --hostname github.com --user $Owner' and retry."
    }
    Write-Step "Authenticated as $authenticatedUser." -Color Green

    # Initialize a local Git repository only if this extracted project has none.
    $insideRepo = $false
    & git -C $ProjectRoot rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -eq 0) { $insideRepo = $true }
    if (-not $insideRepo) {
        & git -C $ProjectRoot init --initial-branch=main
        if ($LASTEXITCODE -ne 0) { Stop-Safely 'Could not initialize the local Git repository.' }
    }

    & git -C $ProjectRoot branch -M main
    if ($LASTEXITCODE -ne 0) { Stop-Safely 'Could not set the local branch to main.' }

    # Set only repository-local author identity if it is not already configured.
    $gitName = (& git -C $ProjectRoot config user.name 2>$null | Out-String).Trim()
    if (-not $gitName) {
        & git -C $ProjectRoot config user.name $authenticatedUser
        if ($LASTEXITCODE -ne 0) { Stop-Safely 'Could not set the local Git author name.' }
    }
    $gitEmail = (& git -C $ProjectRoot config user.email 2>$null | Out-String).Trim()
    if (-not $gitEmail) {
        & git -C $ProjectRoot config user.email "$authenticatedUser@users.noreply.github.com"
        if ($LASTEXITCODE -ne 0) { Stop-Safely 'Could not set the local Git author email.' }
    }

    # Stage only an explicit application-source allowlist. Never run `git add --all`:
    # that could accidentally include documents or personal files placed in this folder.
    $allowedPaths = [System.Collections.Generic.List[string]]::new()
    $fixedPaths = @(
        '.gitignore', 'README.md', 'CHANGELOG.md', 'LICENSE.txt', 'PUBLISHING_TO_GITHUB.md',
        'REPOSITORY_SETUP.md', 'INSTALLER_ENDPOINTS.txt', 'START_HERE.txt', 'SECURITY.md',
        'TEST_RESULTS.txt', 'VERSION.txt', 'PUSH_TO_GITHUB.bat', 'Start_SmartDriveOrganizer.bat',
        'run.py', 'pyproject.toml', 'requirements-content.txt', 'install.ps1',
        'config/keyword_rules.json', 'config/published_topic_rules.json', 'config/topic_rules.example.json'
    )
    foreach ($relative in $fixedPaths) {
        if (Test-Path -LiteralPath (Join-Path $ProjectRoot $relative) -PathType Leaf) {
            $allowedPaths.Add($relative)
        }
    }
    $sourceGroups = @(
        @{ Directory = 'smart_drive_organizer'; Pattern = '*.py' },
        @{ Directory = 'tests'; Pattern = '*.py' },
        @{ Directory = 'scripts'; Pattern = '*.ps1' },
        @{ Directory = '.github/workflows'; Pattern = '*.yml' },
        @{ Directory = 'cloudflare'; Pattern = '*.js' },
        @{ Directory = 'cloudflare'; Pattern = '*.toml' },
        @{ Directory = 'cloudflare'; Pattern = '*.md' }
    )
    $rootPrefix = $ProjectRoot.TrimEnd([char[]]@('\', '/')) + [System.IO.Path]::DirectorySeparatorChar
    foreach ($group in $sourceGroups) {
        $directory = Join-Path $ProjectRoot $group.Directory
        if (Test-Path -LiteralPath $directory -PathType Container) {
            Get-ChildItem -LiteralPath $directory -File -Filter $group.Pattern | ForEach-Object {
                $relative = $_.FullName.Substring($rootPrefix.Length).Replace('\', '/')
                if (-not $allowedPaths.Contains($relative)) { $allowedPaths.Add($relative) }
            }
        }
    }
    if ($allowedPaths.Count -eq 0) { Stop-Safely 'The application source allowlist resolved to no files.' }
    $gitAddArgs = @('-C', $ProjectRoot, 'add', '--') + $allowedPaths.ToArray()
    & git @gitAddArgs
    if ($LASTEXITCODE -ne 0) { Stop-Safely 'Git could not stage the approved project files.' }
    $stagedFiles = @(& git -C $ProjectRoot diff --cached --name-only)
    $allowedLookup = @{}
    foreach ($path in $allowedPaths) { $allowedLookup[$path.ToLowerInvariant()] = $true }
    $unexpectedStaged = @($stagedFiles | Where-Object { -not $allowedLookup.ContainsKey($_.ToLowerInvariant()) })
    if ($unexpectedStaged.Count -gt 0) {
        $unexpectedStaged | ForEach-Object { Write-Host "Unexpected staged file: $_" -ForegroundColor Red }
        Stop-Safely 'The Git index contains files outside the source allowlist. Nothing was committed or pushed. Review and unstage those files first.'
    }
    if ($stagedFiles.Count -gt 0) {
        Write-Step 'Files staged for the initial/update commit:'
        $stagedFiles | ForEach-Object { Write-Host "  $_" }

        $confirm = Read-Host 'Review the list above. Commit these project files? (Y/N)'
        if ($confirm -notmatch '^(?i)y(es)?$') {
            Stop-Safely 'Commit cancelled. No files were pushed.'
        }

        $message = if ((& git -C $ProjectRoot rev-parse --verify HEAD 2>$null) -and $LASTEXITCODE -eq 0) {
            'Update Smart Drive Organizer project'
        } else {
            'Initial release: Smart Drive Organizer v0.3.7'
        }
        & git -C $ProjectRoot commit -m $message
        if ($LASTEXITCODE -ne 0) { Stop-Safely 'Git commit failed. Review the message above and retry.' }
    }
    else {
        Write-Step 'No uncommitted project changes to add.' -Color Yellow
    }

    # Determine whether the requested GitHub repository already exists.
    & $ghPath repo view $Repository --json url,isPrivate,defaultBranchRef *> $null
    $repoExists = ($LASTEXITCODE -eq 0)

    $origin = (& git -C $ProjectRoot remote get-url origin 2>$null | Out-String).Trim()
    $expectedHttps = "https://github.com/$Repository.git"
    $expectedSsh = "git@github.com:$Repository.git"
    if ($origin -and $origin -notin @($expectedHttps, $expectedSsh)) {
        Stop-Safely "The existing origin remote points to '$origin', not $Repository. No push was attempted."
    }

    if (-not $repoExists) {
        if ($origin) {
            Stop-Safely "A local origin exists but GitHub could not find $Repository. Check the remote before continuing."
        }
        Write-Step "Creating the public GitHub repository $Repository and pushing main..." -Color Yellow
        & $ghPath repo create $Repository --public --description $Description --source $ProjectRoot --remote origin --push
        if ($LASTEXITCODE -ne 0) {
            Stop-Safely 'GitHub repository creation or initial push failed. No force-push was attempted.'
        }
    }
    else {
        $repoJson = (& $ghPath repo view $Repository --json url,isPrivate,defaultBranchRef | Out-String | ConvertFrom-Json)
        if ($repoJson.isPrivate) {
            Stop-Safely "$Repository already exists but is private. The anonymous PowerShell installer requires a public repository. No visibility change was made."
        }
        if (-not $origin) {
            & git -C $ProjectRoot remote add origin $expectedHttps
            if ($LASTEXITCODE -ne 0) { Stop-Safely 'Could not add the GitHub origin remote.' }
        }
        Write-Step "Pushing main to existing public repository $Repository..."
        & git -C $ProjectRoot push --set-upstream origin main
        if ($LASTEXITCODE -ne 0) {
            Stop-Safely 'Push was rejected. This usually means the remote contains commits not present locally. Nothing was force-pushed; reconcile the histories before retrying.'
        }
    }

    # Tag the exact tested source revision. The GitHub Actions release workflow builds the EXE.
    & git -C $ProjectRoot rev-parse --verify "refs/tags/$TargetTag" *> $null
    if ($LASTEXITCODE -ne 0) {
        & git -C $ProjectRoot tag -a $TargetTag -m "Smart Drive Organizer $TargetTag"
        if ($LASTEXITCODE -ne 0) { Stop-Safely "Could not create tag $TargetTag." }
    }
    & git -C $ProjectRoot push origin "refs/tags/$TargetTag"
    if ($LASTEXITCODE -ne 0) { Stop-Safely "The source was pushed, but tag $TargetTag was not pushed. Push that tag after checking the remote." }

    Write-Step 'Project published successfully.' -Color Green
    Write-Step "Repository: https://github.com/$Repository" -Color Green
    Write-Step 'GitHub Actions should now run tests, build the Windows executable and publish the v0.3.7 release.' -Color Green
    Write-Step 'After the release is published, install with:' -Color Green
    Write-Host "irm https://raw.githubusercontent.com/$Repository/main/install.ps1 | iex" -ForegroundColor White
    Write-Step 'The smart.drive.win alias remains unavailable until its Cloudflare Worker and DNS are configured.' -Color Yellow
}
catch {
    Write-Host "`nSetup stopped: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'The script never force-pushes and does not change or organize your personal files.' -ForegroundColor Yellow
    exit 1
}
