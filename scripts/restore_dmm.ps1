$ErrorActionPreference = 'Continue'
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class DmmWin {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
"@
$p = Get-Process DMMGamePlayer -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } |
    Select-Object -First 1
if ($p) {
    [DmmWin]::ShowWindow($p.MainWindowHandle, 9) | Out-Null
    [DmmWin]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
    Write-Host "restored $($p.Id) $($p.MainWindowTitle)"
} else {
    Write-Host "no DMM window"
}
