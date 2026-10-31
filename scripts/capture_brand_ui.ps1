$ErrorActionPreference = 'Stop'
$exe = [System.IO.Path]::GetFullPath((Join-Path $PWD 'dist/SmartDriveOrganizer.exe'))
$out = Join-Path $PWD 'brand-ui-screenshots'
$appData = Join-Path $env:LOCALAPPDATA 'SmartDriveOrganizer'
New-Item -ItemType Directory -Force -Path $out, $appData | Out-Null

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class WindowCapture {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr extra);
  [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("kernel32.dll", SetLastError=true)] private static extern IntPtr OpenProcess(uint access, bool inherit, uint processId);
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] private static extern bool QueryFullProcessImageName(IntPtr process, uint flags, StringBuilder path, ref int size);
  [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr handle);
  public static IntPtr FindVisibleWindow(string expectedExe) {
    IntPtr found = IntPtr.Zero;
    EnumWindows((hWnd, extra) => {
      if (!IsWindowVisible(hWnd)) return true;
      uint pid;
      GetWindowThreadProcessId(hWnd, out pid);
      IntPtr process = OpenProcess(0x1000, false, pid);
      if (process == IntPtr.Zero) return true;
      try {
        StringBuilder path = new StringBuilder(32768);
        int size = path.Capacity;
        if (!QueryFullProcessImageName(process, 0, path, ref size) ||
            !String.Equals(path.ToString(), expectedExe, StringComparison.OrdinalIgnoreCase)) return true;
        RECT r;
        if (GetWindowRect(hWnd, out r) && r.Right-r.Left >= 600 && r.Bottom-r.Top >= 400) {
          found = hWnd;
          return false;
        }
      } finally { CloseHandle(process); }
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
      $handle = [WindowCapture]::FindVisibleWindow($exe)
      if ($handle -ne [IntPtr]::Zero) { break }
    }
    if ($handle -eq [IntPtr]::Zero) {
      $running = Get-CimInstance Win32_Process -Filter "Name='SmartDriveOrganizer.exe'" |
        Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine
      $running | Format-Table -AutoSize | Out-String | Write-Host
      throw "Could not find a visible application window for theme $theme. The executable may be running without an interactive desktop."
    }
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
    Get-CimInstance Win32_Process -Filter "Name='SmartDriveOrganizer.exe'" |
      Where-Object { $_.ExecutablePath -eq $exe } |
      ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
  }
}
