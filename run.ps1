$ErrorActionPreference = 'Stop'

$owner = 'T3ND41'
$repository = 'SmartDriveOrganizer_RepoReady_v0.3.7'
$apiUri = "https://api.github.com/repos/$owner/$repository/releases/latest"
$managedRoot = $null
$runtimeRoot = $null

function Get-VersionValue([string]$Value) {
    $text = ([string]$Value).Trim()
    if ($text.StartsWith('v', [StringComparison]::OrdinalIgnoreCase)) {
        $text = $text.Substring(1)
    }
    try { return [version]::Parse($text) }
    catch { return [version]'0.0.0' }
}

function Get-AppVersion([string]$Executable, [string]$Fallback = '') {
    $folder = Split-Path -Parent $Executable
    $versionFile = Join-Path $folder 'VERSION.txt'
    if (Test-Path -LiteralPath $versionFile -PathType Leaf) {
        return (Get-Content -LiteralPath $versionFile -Raw).Trim()
    }
    return $Fallback
}

function Find-LocalCopies {
    $found = @()

    $managedExe = Join-Path $managedRoot 'SmartDriveOrganizer.exe'
    if (Test-Path -LiteralPath $managedExe -PathType Leaf) {
        $version = Get-AppVersion $managedExe 'unknown'
        $found += [pscustomobject]@{
            Path = $managedRoot
            Exe = $managedExe
            Version = $version
            ParsedVersion = (Get-VersionValue $version)
            Priority = 2
            Type = 'per-user app location'
        }
    }

    if (Test-Path -LiteralPath $runtimeRoot -PathType Container) {
        foreach ($folder in Get-ChildItem -LiteralPath $runtimeRoot -Directory -ErrorAction SilentlyContinue) {
            $candidateExe = Join-Path $folder.FullName 'SmartDriveOrganizer.exe'
            if (-not (Test-Path -LiteralPath $candidateExe -PathType Leaf)) { continue }
            $fallback = $folder.Name
            $version = Get-AppVersion $candidateExe $fallback
            $found += [pscustomobject]@{
                Path = $folder.FullName
                Exe = $candidateExe
                Version = $version
                ParsedVersion = (Get-VersionValue $version)
                Priority = 1
                Type = 'portable runtime'
            }
        }
    }

    return @($found | Sort-Object -Property @{Expression='ParsedVersion';Descending=$true}, @{Expression='Priority';Descending=$true})
}

function Start-ExistingCopy($Copy) {
    if (-not $Copy -or -not (Test-Path -LiteralPath $Copy.Exe -PathType Leaf)) {
        throw 'The selected local application copy is no longer available.'
    }
    Write-Host "Launching Smart Drive Organizer $($Copy.Version) from $($Copy.Path)" -ForegroundColor Green
    Start-Process -FilePath $Copy.Exe -WorkingDirectory $Copy.Path
}

Write-Host ''
Write-Host 'SMART DRIVE ORGANIZER' -ForegroundColor White
Write-Host 'Portable PowerShell launcher' -ForegroundColor Red
Write-Host 'No administrator rights, installer wizard, Start Menu shortcut or registry setup.' -ForegroundColor DarkGray
Write-Host ''

try {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw 'Windows did not provide a LOCALAPPDATA folder for this user.'
    }
    $managedRoot = Join-Path $env:LOCALAPPDATA 'Programs\SmartDriveOrganizer'
    $runtimeRoot = Join-Path $env:LOCALAPPDATA 'SmartDriveOrganizer\PortableRuntime'

    # Do not start a second window or replace an executable while it is running.
    $running = Get-Process -Name 'SmartDriveOrganizer' -ErrorAction SilentlyContinue
    if ($running) {
        Write-Host 'Smart Drive Organizer is already running. No second copy was opened.' -ForegroundColor Yellow
        exit 0
    }

    Write-Host 'Checking for an existing application copy...' -ForegroundColor Cyan
    $localCopies = Find-LocalCopies
    $existing = $localCopies | Select-Object -First 1

    if ($existing) {
        Write-Host "Found $($existing.Type): version $($existing.Version)" -ForegroundColor Green
        Write-Host "Location: $($existing.Path)" -ForegroundColor DarkGray
    }
    else {
        Write-Host 'No existing per-user or portable copy was found.' -ForegroundColor DarkGray
    }

    Write-Host 'Checking the latest published GitHub release...' -ForegroundColor Cyan
    $release = Invoke-RestMethod -Uri $apiUri -Headers @{
        Accept = 'application/vnd.github+json'
        'X-GitHub-Api-Version' = '2022-11-28'
    }

    $tag = [string]$release.tag_name
    if ($tag -notmatch '^v?\d+\.\d+\.\d+([.-][A-Za-z0-9.-]+)?$') {
        throw "GitHub returned an unexpected release version: $tag"
    }
    $latestVersion = Get-VersionValue $tag

    $zipAsset = $release.assets | Where-Object { $_.name -eq 'SmartDriveOrganizer-windows-x64.zip' } | Select-Object -First 1
    $hashAsset = $release.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' } | Select-Object -First 1
    if (-not $zipAsset -or -not $hashAsset) {
        throw "The latest release ($tag) does not contain the expected Windows ZIP and checksum files."
    }

    if ($existing -and $existing.ParsedVersion -ge $latestVersion) {
        Write-Host "You already have the latest published version ($tag). No download or duplicate copy is needed." -ForegroundColor Green
        Start-ExistingCopy $existing
        exit 0
    }

    if ($existing) {
        Write-Host ''
        Write-Host "An update is available: $($existing.Version) -> $tag" -ForegroundColor Yellow
        $answer = Read-Host 'Update the existing copy now? [Y]es / [N]o'
        if ($answer -notmatch '^(y|yes)$') {
            Write-Host 'Keeping the current version. No files were downloaded or changed.' -ForegroundColor Yellow
            Start-ExistingCopy $existing
            exit 0
        }
        # Update in-place in the selected existing folder so the launcher does
        # not create another application directory or duplicate Start Menu entry.
        $targetFolder = $existing.Path
    }
    else {
        # First run: keep a single portable runtime in the per-user app-data area.
        $targetFolder = Join-Path $runtimeRoot 'Current'
    }

    $workFolder = Join-Path ([System.IO.Path]::GetTempPath()) ("SmartDriveOrganizer-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $workFolder -Force | Out-Null
    try {
        $zipPath = Join-Path $workFolder 'SmartDriveOrganizer-windows-x64.zip'
        $hashPath = Join-Path $workFolder 'SHA256SUMS.txt'
        $stagingFolder = Join-Path $workFolder 'extracted'

        Write-Host "Downloading $tag..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri $zipAsset.browser_download_url -OutFile $zipPath
        Invoke-WebRequest -Uri $hashAsset.browser_download_url -OutFile $hashPath

        $expectedLine = Select-String -Path $hashPath -Pattern '^(?<hash>[A-Fa-f0-9]{64})\s+\*?SmartDriveOrganizer-windows-x64\.zip$' |
            Select-Object -First 1
        if (-not $expectedLine) {
            throw 'The release checksum file is missing the expected ZIP checksum.'
        }

        $expectedHash = $expectedLine.Matches[0].Groups['hash'].Value.ToLowerInvariant()
        $actualHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $expectedHash) {
            throw 'The downloaded ZIP failed SHA-256 verification. It will not be opened.'
        }

        Write-Host 'Checksum verified. Extracting the application...' -ForegroundColor Green
        Expand-Archive -LiteralPath $zipPath -DestinationPath $stagingFolder -Force
        $stagedExe = Join-Path $stagingFolder 'SmartDriveOrganizer.exe'
        if (-not (Test-Path -LiteralPath $stagedExe -PathType Leaf)) {
            throw 'The downloaded archive did not contain SmartDriveOrganizer.exe.'
        }

        New-Item -ItemType Directory -Path $targetFolder -Force | Out-Null
        Copy-Item -LiteralPath $stagedExe -Destination (Join-Path $targetFolder 'SmartDriveOrganizer.exe') -Force
        foreach ($name in @('README.md', 'LICENSE.txt', 'VERSION.txt')) {
            $sourceFile = Join-Path $stagingFolder $name
            if (Test-Path -LiteralPath $sourceFile -PathType Leaf) {
                Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $targetFolder $name) -Force
            }
        }
    }
    finally {
        if (Test-Path -LiteralPath $workFolder) {
            Remove-Item -LiteralPath $workFolder -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    $targetExe = Join-Path $targetFolder 'SmartDriveOrganizer.exe'
    if (-not (Test-Path -LiteralPath $targetExe -PathType Leaf)) {
        throw 'The application executable is not present after updating.'
    }

    Write-Host "Smart Drive Organizer $tag is ready in the existing application location." -ForegroundColor Green

    # Report any other old per-user runtime folders; never delete them silently.
    $otherCopies = @($localCopies | Where-Object { $_.Path -ne $targetFolder })
    if ($otherCopies.Count -gt 0) {
        Write-Host 'Other older cached copy/copies were detected:' -ForegroundColor Yellow
        foreach ($copy in $otherCopies) {
            Write-Host "  $($copy.Version)  $($copy.Path)" -ForegroundColor DarkGray
        }
        Write-Host 'They were left untouched. Remove an obsolete portable cache manually after confirming the new copy works.' -ForegroundColor DarkGray
    }

    Write-Host "Starting Smart Drive Organizer $tag..." -ForegroundColor Green
    Start-Process -FilePath $targetExe -WorkingDirectory $targetFolder
    Write-Host 'Application launched. You can close this PowerShell window.' -ForegroundColor Green
}
catch {
    Write-Host ''
    Write-Host "Smart Drive Organizer could not be started: $($_.Exception.Message)" -ForegroundColor Red
    throw
}
