Add-Type @"
using System;
using System.Runtime.InteropServices;
public class RestoreGame {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
}
"@
$h = [IntPtr]526880
[RestoreGame]::ShowWindow($h, 9) | Out-Null
Start-Sleep -Seconds 1
[RestoreGame]::SetForegroundWindow($h) | Out-Null
Write-Host "iconic=$([RestoreGame]::IsIconic($h))"
