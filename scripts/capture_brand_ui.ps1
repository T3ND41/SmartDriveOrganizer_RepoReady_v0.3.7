$ErrorActionPreference = 'Stop'
$exe = Join-Path $PWD 'dist/SmartDriveOrganizer.exe'
$out = Join-Path $PWD 'brand-ui-screenshots'
$appData = Join-Path $env:LOCALAPPDATA 'SmartDriveOrganizer'
New-Item -ItemType Directory -Force -Path $out, $appData | Out-Null

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WindowCapture {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
}
"@

foreach ($theme in @('light', 'dark', 'redline')) {
  @{ theme = $theme } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $appData 'ui_preferences.json')
  $process = Start-Process -FilePath $exe -PassThru
  try {
    $handle = [IntPtr]::Zero
    for ($i = 0; $i -lt 40; $i++) {
      Start-Sleep -Milliseconds 500
      $process.Refresh()
      if ($process.HasExited) { throw "Application exited before its window appeared for theme $theme." }
      if ($process.MainWindowHandle -ne [IntPtr]::Zero) { $handle = $process.MainWindowHandle; break }
    }
    if ($handle -eq [IntPtr]::Zero) { throw "Could not find the application window for theme $theme." }
    Start-Sleep -Seconds 2
    $rect = New-Object WindowCapture+RECT
    if (-not [WindowCapture]::GetWindowRect($handle, [ref]$rect)) { throw "Could not measure the app window for theme $theme." }
    $width = $rect.Right - $rect.Left
    $height = $rect.Bottom - $rect.Top
    if ($width -lt 900 -or $height -lt 650) { throw "Unexpected app window size $($width)x$($height) for theme $theme." }
    $bitmap = New-Object System.Drawing.Bitmap($width, $height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bitmap.Size)
    $path = Join-Path $out "smart-drive-organizer-$theme.png"
    $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose()
    $bitmap.Dispose()
    Write-Host "Captured $theme theme: $path ($($width)x$($height))"
  }
  finally {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
  }
}
