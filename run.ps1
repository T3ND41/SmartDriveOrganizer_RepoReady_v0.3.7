$ErrorActionPreference = 'Stop'

$owner = 'T3ND41'
$repository = 'SmartDriveOrganizer_RepoReady_v0.3.7'
$apiUri = "https://api.github.com/repos/$owner/$repository/releases/latest"
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'SmartDriveOrganizer\PortableRuntime'

Write-Host ''
Write-Host 'SMART DRIVE ORGANIZER' -ForegroundColor White
Write-Host 'Portable PowerShell launcher' -ForegroundColor Red
Write-Host 'No installer, no administrator rights, no Start Menu shortcut.' -ForegroundColor DarkGray
Write-Host ''

try {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw 'Windows did not provide a LOCALAPPDATA folder for this user.'
    }

    Write-Host 'Checking the latest published version...' -ForegroundColor Cyan
    $release = Invoke-RestMethod -Uri $apiUri -Headers @{
        Accept = 'application/vnd.github+json'
        'X-GitHub-Api-Version' = '2022-11-28'
    }

    $tag = [string]$release.tag_name
    if ($tag -notmatch '^[A-Za-z0-9._-]+$') {
        throw "GitHub returned an unexpected release tag: $tag"
    }

    $zipAsset = $release.assets | Where-Object { $_.name -eq 'SmartDriveOrganizer-windows-x64.zip' } | Select-Object -First 1
    $hashAsset = $release.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' } | Select-Object -First 1
    if (-not $zipAsset -or -not $hashAsset) {
        throw "The latest release ($tag) does not contain the expected Windows ZIP and checksum files."
    }

    $versionFolder = Join-Path $runtimeRoot $tag
    $exePath = Join-Path $versionFolder 'SmartDriveOrganizer.exe'

    if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
        New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

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

            if (Test-Path -LiteralPath $versionFolder) {
                Remove-Item -LiteralPath $versionFolder -Recurse -Force
            }
            Move-Item -LiteralPath $stagingFolder -Destination $versionFolder
        }
        finally {
            if (Test-Path -LiteralPath $workFolder) {
                Remove-Item -LiteralPath $workFolder -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }
    else {
        Write-Host "$tag is already available locally. Skipping the download." -ForegroundColor Green
    }

    if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
        throw 'The application executable is not present after extraction.'
    }

    Write-Host "Starting Smart Drive Organizer $tag..." -ForegroundColor Green
    Start-Process -FilePath $exePath -WorkingDirectory $versionFolder
    Write-Host 'Application launched. You can close this PowerShell window.' -ForegroundColor Green
    Write-Host 'To remove the downloaded program files, delete:' -ForegroundColor DarkGray
    Write-Host "  $runtimeRoot" -ForegroundColor Gray
}
catch {
    Write-Host ''
    Write-Host "Smart Drive Organizer could not be started: $($_.Exception.Message)" -ForegroundColor Red
    throw
}
