Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinMax {
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint processId);
}
"@
$dmmIds = @(Get-Process DMMGamePlayer -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
$found = 0
$cb = [WinMax+EnumProc]{
    param($h, $p)
    if (-not [WinMax]::IsWindowVisible($h)) { return $true }
    $procId = [uint32]0
    [void][WinMax]::GetWindowThreadProcessId($h, [ref]$procId)
    if ($dmmIds -contains [int]$procId) {
        [void][WinMax]::ShowWindow($h, 3)
        [void][WinMax]::SetForegroundWindow($h)
        $script:found = $script:found + 1
        Write-Host "maximized hwnd=$h pid=$procId"
    }
    return $true
}
[void][WinMax]::EnumWindows($cb, [IntPtr]::Zero)
Write-Host "found=$found"
Start-Sleep -Seconds 1
