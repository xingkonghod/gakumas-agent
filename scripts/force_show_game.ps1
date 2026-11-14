$ErrorActionPreference = 'Continue'
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class ForceShow {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
}
"@
$ps = Get-Process gakumas -ErrorAction SilentlyContinue
foreach ($p in $ps) {
    $h = $p.MainWindowHandle
    if ($h -ne 0) {
        Write-Host "hwnd=$h iconic=$([ForceShow]::IsIconic($h))"
        [ForceShow]::ShowWindowAsync($h, 9) | Out-Null
        [ForceShow]::ShowWindow($h, 9) | Out-Null
        [ForceShow]::SetForegroundWindow($h) | Out-Null
    }
}
Start-Sleep -Seconds 2
