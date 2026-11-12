Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class BringFront {
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint processId);
}
"@
$dmmIds = @(Get-Process DMMGamePlayer -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
Write-Host "dmm pids: $($dmmIds -join ',')"
$script:done = 0
$cb = [BringFront+EnumProc]{
    param($h, $p)
    if (-not [BringFront]::IsWindowVisible($h)) { return $true }
    $procId = [uint32]0
    [void][BringFront]::GetWindowThreadProcessId($h, [ref]$procId)
    if ($dmmIds -contains [int]$procId) {
        Write-Host "bringing hwnd=$h pid=$procId"
        [void][BringFront]::ShowWindow($h, 9)
        [void][BringFront]::BringWindowToTop($h)
        [void][BringFront]::SetForegroundWindow($h)
        $script:done = 1
    }
    return $true
}
[void][BringFront]::EnumWindows($cb, [IntPtr]::Zero)
Write-Host "done=$($script:done) fg=$([BringFront]::GetForegroundWindow())"
Start-Sleep -Seconds 1
