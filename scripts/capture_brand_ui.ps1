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
  private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr extra);
  [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  public static IntPtr FindVisibleWindow(int targetPid) {
    IntPtr found = IntPtr.Zero;
    EnumWindows((hWnd, extra) => {
      uint pid;
      GetWindowThreadProcessId(hWnd, out pid);
      if (pid == (uint)targetPid && IsWindowVisible(hWnd)) {
        RECT r;
        if (GetWindowRect(hWnd, out r) && r.Right-r.Left >= 900 && r.Bottom-r.Top >= 650) {
          found = hWnd;
          return false;
        }
      }
      return true;
    }, IntPtr.Zero);
    return found;
  }
}
"@

foreach ($theme in @('light', 'dark', 'redline')) {
  @{ theme = $theme } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $appData 'ui_preferences.json')
  $process = Start-Process -FilePath $exe -PassThru
  try {
    $handle = [IntPtr]::Zero
    for ($i = 0; $i -lt 60; $i++) {
      Start-Sleep -Milliseconds 500
      $process.Refresh()
      if ($process.HasExited) { throw "Application exited before its window appeared for theme $theme (exit $($process.ExitCode))." }
      $handle = [WindowCapture]::FindVisibleWindow($process.Id)
      if ($handle -ne [IntPtr]::Zero) { break }
    }
    if ($handle -eq [IntPtr]::Zero) { throw "Could not find a visible application window at least 900x650 for theme $theme (PID $($process.Id))." }
    Start-Sleep -Seconds 2
    $rect = New-Object WindowCapture+RECT
    if (-not [WindowCapture]::GetWindowRect($handle, [ref]$rect)) { throw "Could not measure the app window for theme $theme." }
    $width = $rect.Right - $rect.Left
    $height = $rect.Bottom - $rect.Top
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
