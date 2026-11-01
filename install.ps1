# Smart Drive Organizer per-user installer.
# Usage after the repository is public:
#   irm https://raw.githubusercontent.com/T3ND41/SmartDriveOrganizer_RepoReady_v0.3.7/main/install.ps1 | iex
# Custom-domain alias (after the Cloudflare Worker and DNS are configured):
#   irm https://smart.drive.win | iex

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Repository = 'T3ND41/SmartDriveOrganizer_RepoReady_v0.3.7'
$ReleaseApi = "https://api.github.com/repos/$Repository/releases/latest"
$ExpectedZipName = 'SmartDriveOrganizer-windows-x64.zip'
$ExpectedChecksumName = 'SHA256SUMS.txt'
$InstallDirectory = Join-Path $env:LOCALAPPDATA 'Programs\SmartDriveOrganizer'
$StartMenuDirectory = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Smart Drive Organizer'

function Write-InstallerMessage {
    param([string]$Message, [ConsoleColor]$Color = [ConsoleColor]::Cyan)
    Write-Host "[Smart Drive Organizer] $Message" -ForegroundColor $Color
}

try {
    if (-not $env:LOCALAPPDATA) {
        throw 'LOCALAPPDATA is unavailable. Run this installer from a signed-in Windows user session.'
    }
    if (-not $env:OS -or $env:OS -ne 'Windows_NT') {
        throw 'This installer currently supports Windows 10 and Windows 11.'
    }

    $running = Get-Process -Name 'SmartDriveOrganizer' -ErrorAction SilentlyContinue
    if ($running) {
        throw 'Smart Drive Organizer is already running. Close its desktop window and stop the background monitor, then run the installer again.'
    }

    Write-InstallerMessage 'Checking the latest published Windows release...'
    $headers = @{
        'Accept' = 'application/vnd.github+json'
        'X-GitHub-Api-Version' = '2022-11-28'
        'User-Agent' = 'SmartDriveOrganizer-Installer'
    }
    # Bypass intermediary caches so the installer resolves the latest published stable release.
    $cacheBuster = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $requestUri = "$ReleaseApi?cacheBust=$cacheBuster"
    $headers['Cache-Control'] = 'no-cache, no-store'
    $headers['Pragma'] = 'no-cache'
    $release = Invoke-RestMethod -Uri $requestUri -Headers $headers -Method Get -ErrorAction Stop
    if (-not $release -or -not $release.assets -or $release.draft -or $release.prerelease) {
        throw 'GitHub did not return a published release with downloadable assets. The project owner must publish a v* release first.'
    }

    $releaseTag = [string]$release.tag_name
    if ($releaseTag -notmatch '^v[0-9]+[.][0-9]+[.][0-9]+$') {
        throw "GitHub returned an invalid stable release tag: $releaseTag"
    }

    Write-InstallerMessage "Latest published stable release: $releaseTag" -Color Green
    $zipAsset = $release.assets | Where-Object { $_.name -eq $ExpectedZipName } | Select-Object -First 1
    $checksumAsset = $release.assets | Where-Object { $_.name -eq $ExpectedChecksumName } | Select-Object -First 1
    if (-not $zipAsset -or -not $checksumAsset) {
        throw "Release $($release.tag_name) is missing $ExpectedZipName or $ExpectedChecksumName. Please report this release packaging issue."
    }

    $allowedPrefix = "https://github.com/$Repository/releases/download/"
    foreach ($asset in @($zipAsset, $checksumAsset)) {
        if (-not ([string]$asset.browser_download_url).StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "GitHub returned an unexpected download host for asset $($asset.name). Installation was stopped."
        }
    }

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("SmartDriveOrganizer-" + [Guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $tempRoot -Force
    try {
        $zipPath = Join-Path $tempRoot $ExpectedZipName
        $checksumPath = Join-Path $tempRoot $ExpectedChecksumName
        $extractPath = Join-Path $tempRoot 'payload'

        Write-InstallerMessage "Downloading release $($release.tag_name)..."
        Invoke-WebRequest -Uri $zipAsset.browser_download_url -OutFile $zipPath -Headers @{ 'User-Agent' = 'SmartDriveOrganizer-Installer' } -ErrorAction Stop
        Invoke-WebRequest -Uri $checksumAsset.browser_download_url -OutFile $checksumPath -Headers @{ 'User-Agent' = 'SmartDriveOrganizer-Installer' } -ErrorAction Stop

        $checksumLine = Get-Content -LiteralPath $checksumPath -ErrorAction Stop |
            Where-Object { $_ -match [regex]::Escape($ExpectedZipName) } |
            Select-Object -First 1
        if (-not $checksumLine) {
            throw 'The release checksum manifest does not contain the Windows package entry.'
        }
        $match = [regex]::Match($checksumLine, '^(?<hash>[0-9a-fA-F]{64})\s+\*?(?<name>.+?)\s*$')
        if (-not $match.Success -or $match.Groups['name'].Value -ne $ExpectedZipName) {
            throw 'The release checksum manifest has an invalid entry.'
        }
        $expectedHash = $match.Groups['hash'].Value.ToUpperInvariant()
        $actualHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($actualHash -ne $expectedHash) {
            throw 'SHA-256 verification failed. The downloaded package will not be installed.'
        }
        Write-InstallerMessage 'Package checksum verified.' -Color Green

        Expand-Archive -LiteralPath $zipPath -DestinationPath $extractPath -Force
        $sourceExe = Join-Path $extractPath 'SmartDriveOrganizer.exe'
        if (-not (Test-Path -LiteralPath $sourceExe -PathType Leaf)) {
            throw 'The release archive does not contain SmartDriveOrganizer.exe.'
        }
        $packageVersionFile = Join-Path $extractPath 'VERSION.txt'
        if (-not (Test-Path -LiteralPath $packageVersionFile -PathType Leaf)) {
            throw 'The release archive does not contain VERSION.txt; its embedded version cannot be verified.'
        }
        $packageVersion = (Get-Content -LiteralPath $packageVersionFile -Raw).Trim()
        if ($packageVersion -ne [string]$release.tag_name) {
            throw "Package version $packageVersion does not match latest release $($release.tag_name). Installation was stopped."
        }

        $null = New-Item -ItemType Directory -Path $InstallDirectory -Force
        Copy-Item -LiteralPath $sourceExe -Destination (Join-Path $InstallDirectory 'SmartDriveOrganizer.exe') -Force
        foreach ($supportFile in @('README.md', 'LICENSE.txt', 'VERSION.txt')) {
            $candidate = Join-Path $extractPath $supportFile
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                Copy-Item -LiteralPath $candidate -Destination (Join-Path $InstallDirectory $supportFile) -Force
            }
        }

        $null = New-Item -ItemType Directory -Path $StartMenuDirectory -Force
        $shortcutPath = Join-Path $StartMenuDirectory 'Smart Drive Organizer.lnk'
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = Join-Path $InstallDirectory 'SmartDriveOrganizer.exe'
        $shortcut.WorkingDirectory = $InstallDirectory
        $shortcut.Description = 'Organize files using your saved Smart Drive Organizer rules.'
        $shortcut.Save()

        Write-InstallerMessage "Installed version $packageVersion to $InstallDirectory" -Color Green
        Write-InstallerMessage 'Starting Smart Drive Organizer...'
        Start-Process -FilePath (Join-Path $InstallDirectory 'SmartDriveOrganizer.exe') -WorkingDirectory $InstallDirectory
        Write-InstallerMessage 'Installation completed. Your application settings and personal rules remain in your Windows user profile.' -Color Green
    }
    finally {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
catch {
    Write-InstallerMessage $_.Exception.Message -Color Red
    Write-InstallerMessage 'No source documents were changed by this installer.' -Color Yellow
    throw
}
) {
        throw "GitHub returned an invalid stable release tag: $($release.tag_name)"
    }

    Write-InstallerMessage "Latest published stable release: $($release.tag_name)" -Color Green
    $zipAsset = $release.assets | Where-Object { $_.name -eq $ExpectedZipName } | Select-Object -First 1
    $checksumAsset = $release.assets | Where-Object { $_.name -eq $ExpectedChecksumName } | Select-Object -First 1
    if (-not $zipAsset -or -not $checksumAsset) {
        throw "Release $($release.tag_name) is missing $ExpectedZipName or $ExpectedChecksumName. Please report this release packaging issue."
    }

    $allowedPrefix = "https://github.com/$Repository/releases/download/"
    foreach ($asset in @($zipAsset, $checksumAsset)) {
        if (-not ([string]$asset.browser_download_url).StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "GitHub returned an unexpected download host for asset $($asset.name). Installation was stopped."
        }
    }

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("SmartDriveOrganizer-" + [Guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $tempRoot -Force
    try {
        $zipPath = Join-Path $tempRoot $ExpectedZipName
        $checksumPath = Join-Path $tempRoot $ExpectedChecksumName
        $extractPath = Join-Path $tempRoot 'payload'

        Write-InstallerMessage "Downloading release $($release.tag_name)..."
        Invoke-WebRequest -Uri $zipAsset.browser_download_url -OutFile $zipPath -Headers @{ 'User-Agent' = 'SmartDriveOrganizer-Installer' } -ErrorAction Stop
        Invoke-WebRequest -Uri $checksumAsset.browser_download_url -OutFile $checksumPath -Headers @{ 'User-Agent' = 'SmartDriveOrganizer-Installer' } -ErrorAction Stop

        $checksumLine = Get-Content -LiteralPath $checksumPath -ErrorAction Stop |
            Where-Object { $_ -match [regex]::Escape($ExpectedZipName) } |
            Select-Object -First 1
        if (-not $checksumLine) {
            throw 'The release checksum manifest does not contain the Windows package entry.'
        }
        $match = [regex]::Match($checksumLine, '^(?<hash>[0-9a-fA-F]{64})\s+\*?(?<name>.+?)\s*$')
        if (-not $match.Success -or $match.Groups['name'].Value -ne $ExpectedZipName) {
            throw 'The release checksum manifest has an invalid entry.'
        }
        $expectedHash = $match.Groups['hash'].Value.ToUpperInvariant()
        $actualHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($actualHash -ne $expectedHash) {
            throw 'SHA-256 verification failed. The downloaded package will not be installed.'
        }
        Write-InstallerMessage 'Package checksum verified.' -Color Green

        Expand-Archive -LiteralPath $zipPath -DestinationPath $extractPath -Force
        $sourceExe = Join-Path $extractPath 'SmartDriveOrganizer.exe'
        if (-not (Test-Path -LiteralPath $sourceExe -PathType Leaf)) {
            throw 'The release archive does not contain SmartDriveOrganizer.exe.'
        }

        $null = New-Item -ItemType Directory -Path $InstallDirectory -Force
        Copy-Item -LiteralPath $sourceExe -Destination (Join-Path $InstallDirectory 'SmartDriveOrganizer.exe') -Force
        foreach ($supportFile in @('README.md', 'LICENSE.txt', 'VERSION.txt')) {
            $candidate = Join-Path $extractPath $supportFile
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                Copy-Item -LiteralPath $candidate -Destination (Join-Path $InstallDirectory $supportFile) -Force
            }
        }

        $null = New-Item -ItemType Directory -Path $StartMenuDirectory -Force
        $shortcutPath = Join-Path $StartMenuDirectory 'Smart Drive Organizer.lnk'
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = Join-Path $InstallDirectory 'SmartDriveOrganizer.exe'
        $shortcut.WorkingDirectory = $InstallDirectory
        $shortcut.Description = 'Organize files using your saved Smart Drive Organizer rules.'
        $shortcut.Save()

        Write-InstallerMessage "Installed to $InstallDirectory" -Color Green
        Write-InstallerMessage 'Starting Smart Drive Organizer...'
        Start-Process -FilePath (Join-Path $InstallDirectory 'SmartDriveOrganizer.exe') -WorkingDirectory $InstallDirectory
        Write-InstallerMessage 'Installation completed. Your application settings and personal rules remain in your Windows user profile.' -Color Green
    }
    finally {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
catch {
    Write-InstallerMessage $_.Exception.Message -Color Red
    Write-InstallerMessage 'No source documents were changed by this installer.' -Color Yellow
    throw
}
) {
        throw "GitHub returned an invalid stable release tag: $($release.tag_name)"
    }

    Write-InstallerMessage "Latest published stable release: $($release.tag_name)" -Color Green
    $zipAsset = $release.assets | Where-Object { $_.name -eq $ExpectedZipName } | Select-Object -First 1
    $checksumAsset = $release.assets | Where-Object { $_.name -eq $ExpectedChecksumName } | Select-Object -First 1
    if (-not $zipAsset -or -not $checksumAsset) {
        throw "Release $($release.tag_name) is missing $ExpectedZipName or $ExpectedChecksumName. Please report this release packaging issue."
    }

    $allowedPrefix = "https://github.com/$Repository/releases/download/"
    foreach ($asset in @($zipAsset, $checksumAsset)) {
        if (-not ([string]$asset.browser_download_url).StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "GitHub returned an unexpected download host for asset $($asset.name). Installation was stopped."
        }
    }

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("SmartDriveOrganizer-" + [Guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $tempRoot -Force
    try {
        $zipPath = Join-Path $tempRoot $ExpectedZipName
        $checksumPath = Join-Path $tempRoot $ExpectedChecksumName
        $extractPath = Join-Path $tempRoot 'payload'

        Write-InstallerMessage "Downloading release $($release.tag_name)..."
        Invoke-WebRequest -Uri $zipAsset.browser_download_url -OutFile $zipPath -Headers @{ 'User-Agent' = 'SmartDriveOrganizer-Installer' } -ErrorAction Stop
        Invoke-WebRequest -Uri $checksumAsset.browser_download_url -OutFile $checksumPath -Headers @{ 'User-Agent' = 'SmartDriveOrganizer-Installer' } -ErrorAction Stop

        $checksumLine = Get-Content -LiteralPath $checksumPath -ErrorAction Stop |
            Where-Object { $_ -match [regex]::Escape($ExpectedZipName) } |
            Select-Object -First 1
        if (-not $checksumLine) {
            throw 'The release checksum manifest does not contain the Windows package entry.'
        }
        $match = [regex]::Match($checksumLine, '^(?<hash>[0-9a-fA-F]{64})\s+\*?(?<name>.+?)\s*$')
        if (-not $match.Success -or $match.Groups['name'].Value -ne $ExpectedZipName) {
            throw 'The release checksum manifest has an invalid entry.'
        }
        $expectedHash = $match.Groups['hash'].Value.ToUpperInvariant()
        $actualHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($actualHash -ne $expectedHash) {
            throw 'SHA-256 verification failed. The downloaded package will not be installed.'
        }
        Write-InstallerMessage 'Package checksum verified.' -Color Green

        Expand-Archive -LiteralPath $zipPath -DestinationPath $extractPath -Force
        $sourceExe = Join-Path $extractPath 'SmartDriveOrganizer.exe'
        if (-not (Test-Path -LiteralPath $sourceExe -PathType Leaf)) {
            throw 'The release archive does not contain SmartDriveOrganizer.exe.'
        }
        $packageVersionFile = Join-Path $extractPath 'VERSION.txt'
        if (-not (Test-Path -LiteralPath $packageVersionFile -PathType Leaf)) {
            throw 'The release archive does not contain VERSION.txt; its embedded version cannot be verified.'
        }
        $packageVersion = (Get-Content -LiteralPath $packageVersionFile -Raw).Trim()
        if ($packageVersion -ne [string]$release.tag_name) {
            throw "Package version $packageVersion does not match latest release $($release.tag_name). Installation was stopped."
        }

        $null = New-Item -ItemType Directory -Path $InstallDirectory -Force
        Copy-Item -LiteralPath $sourceExe -Destination (Join-Path $InstallDirectory 'SmartDriveOrganizer.exe') -Force
        foreach ($supportFile in @('README.md', 'LICENSE.txt', 'VERSION.txt')) {
            $candidate = Join-Path $extractPath $supportFile
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                Copy-Item -LiteralPath $candidate -Destination (Join-Path $InstallDirectory $supportFile) -Force
            }
        }

        $null = New-Item -ItemType Directory -Path $StartMenuDirectory -Force
        $shortcutPath = Join-Path $StartMenuDirectory 'Smart Drive Organizer.lnk'
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = Join-Path $InstallDirectory 'SmartDriveOrganizer.exe'
        $shortcut.WorkingDirectory = $InstallDirectory
        $shortcut.Description = 'Organize files using your saved Smart Drive Organizer rules.'
        $shortcut.Save()

        Write-InstallerMessage "Installed version $packageVersion to $InstallDirectory" -Color Green
        Write-InstallerMessage 'Starting Smart Drive Organizer...'
        Start-Process -FilePath (Join-Path $InstallDirectory 'SmartDriveOrganizer.exe') -WorkingDirectory $InstallDirectory
        Write-InstallerMessage 'Installation completed. Your application settings and personal rules remain in your Windows user profile.' -Color Green
    }
    finally {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
catch {
    Write-InstallerMessage $_.Exception.Message -Color Red
    Write-InstallerMessage 'No source documents were changed by this installer.' -Color Yellow
    throw
}
) {
        throw "GitHub returned an invalid stable release tag: $($release.tag_name)"
    }

    Write-InstallerMessage "Latest published stable release: $($release.tag_name)" -Color Green
    $zipAsset = $release.assets | Where-Object { $_.name -eq $ExpectedZipName } | Select-Object -First 1
    $checksumAsset = $release.assets | Where-Object { $_.name -eq $ExpectedChecksumName } | Select-Object -First 1
    if (-not $zipAsset -or -not $checksumAsset) {
        throw "Release $($release.tag_name) is missing $ExpectedZipName or $ExpectedChecksumName. Please report this release packaging issue."
    }

    $allowedPrefix = "https://github.com/$Repository/releases/download/"
    foreach ($asset in @($zipAsset, $checksumAsset)) {
        if (-not ([string]$asset.browser_download_url).StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "GitHub returned an unexpected download host for asset $($asset.name). Installation was stopped."
        }
    }

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("SmartDriveOrganizer-" + [Guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $tempRoot -Force
    try {
        $zipPath = Join-Path $tempRoot $ExpectedZipName
        $checksumPath = Join-Path $tempRoot $ExpectedChecksumName
        $extractPath = Join-Path $tempRoot 'payload'

        Write-InstallerMessage "Downloading release $($release.tag_name)..."
        Invoke-WebRequest -Uri $zipAsset.browser_download_url -OutFile $zipPath -Headers @{ 'User-Agent' = 'SmartDriveOrganizer-Installer' } -ErrorAction Stop
        Invoke-WebRequest -Uri $checksumAsset.browser_download_url -OutFile $checksumPath -Headers @{ 'User-Agent' = 'SmartDriveOrganizer-Installer' } -ErrorAction Stop

        $checksumLine = Get-Content -LiteralPath $checksumPath -ErrorAction Stop |
            Where-Object { $_ -match [regex]::Escape($ExpectedZipName) } |
            Select-Object -First 1
        if (-not $checksumLine) {
            throw 'The release checksum manifest does not contain the Windows package entry.'
        }
        $match = [regex]::Match($checksumLine, '^(?<hash>[0-9a-fA-F]{64})\s+\*?(?<name>.+?)\s*$')
        if (-not $match.Success -or $match.Groups['name'].Value -ne $ExpectedZipName) {
            throw 'The release checksum manifest has an invalid entry.'
        }
        $expectedHash = $match.Groups['hash'].Value.ToUpperInvariant()
        $actualHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($actualHash -ne $expectedHash) {
            throw 'SHA-256 verification failed. The downloaded package will not be installed.'
        }
        Write-InstallerMessage 'Package checksum verified.' -Color Green

        Expand-Archive -LiteralPath $zipPath -DestinationPath $extractPath -Force
        $sourceExe = Join-Path $extractPath 'SmartDriveOrganizer.exe'
        if (-not (Test-Path -LiteralPath $sourceExe -PathType Leaf)) {
            throw 'The release archive does not contain SmartDriveOrganizer.exe.'
        }

        $null = New-Item -ItemType Directory -Path $InstallDirectory -Force
        Copy-Item -LiteralPath $sourceExe -Destination (Join-Path $InstallDirectory 'SmartDriveOrganizer.exe') -Force
        foreach ($supportFile in @('README.md', 'LICENSE.txt', 'VERSION.txt')) {
            $candidate = Join-Path $extractPath $supportFile
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                Copy-Item -LiteralPath $candidate -Destination (Join-Path $InstallDirectory $supportFile) -Force
            }
        }

        $null = New-Item -ItemType Directory -Path $StartMenuDirectory -Force
        $shortcutPath = Join-Path $StartMenuDirectory 'Smart Drive Organizer.lnk'
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = Join-Path $InstallDirectory 'SmartDriveOrganizer.exe'
        $shortcut.WorkingDirectory = $InstallDirectory
        $shortcut.Description = 'Organize files using your saved Smart Drive Organizer rules.'
        $shortcut.Save()

        Write-InstallerMessage "Installed to $InstallDirectory" -Color Green
        Write-InstallerMessage 'Starting Smart Drive Organizer...'
        Start-Process -FilePath (Join-Path $InstallDirectory 'SmartDriveOrganizer.exe') -WorkingDirectory $InstallDirectory
        Write-InstallerMessage 'Installation completed. Your application settings and personal rules remain in your Windows user profile.' -Color Green
    }
    finally {
        if (Test-Path -LiteralPath $tempRoot) {
            Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
catch {
    Write-InstallerMessage $_.Exception.Message -Color Red
    Write-InstallerMessage 'No source documents were changed by this installer.' -Color Yellow
    throw
}
