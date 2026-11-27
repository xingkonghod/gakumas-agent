param(
    [string]$ProcName = 'DMMGamePlayer',
    [string]$Action = 'shot',   # shot | click | info
    [int]$X = 0,
    [int]$Y = 0,
    [string]$Out = 'D:\Games\gakumas-agent\data\_uiwin.png',
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public class UiWin {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
  [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
}
'@

$procs = @(Get-Process -Name $ProcName -ErrorAction SilentlyContinue)
if (-not $procs) { throw "process $ProcName not found" }
$pids = $procs | Select-Object -ExpandProperty Id
$found = New-Object System.Collections.Generic.List[object]
$cb = [UiWin+EnumProc]{
    param($h, $l)
    $wpid = 0
    [UiWin]::GetWindowThreadProcessId($h, [ref]$wpid) | Out-Null
    if ($pids -contains [int]$wpid) {
        $sb = New-Object System.Text.StringBuilder 256
        [UiWin]::GetWindowText($h, $sb, 256) | Out-Null
        $r = New-Object UiWin+RECT
        [UiWin]::GetWindowRect($h, [ref]$r) | Out-Null
        $found.Add([pscustomobject]@{ H = $h; Pid = $wpid; Title = $sb.ToString(); Vis = [UiWin]::IsWindowVisible($h); W = $r.Right - $r.Left; Ht = $r.Bottom - $r.Top; X = $r.Left; Y = $r.Top })
    }
    return $true
}
[UiWin]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
$found | Where-Object { $_.W -gt 100 -and $_.Ht -gt 100 } | ForEach-Object { "win h=$($_.H) pid=$($_.Pid) vis=$($_.Vis) rect=$($_.W)x$($_.Ht)@$($_.X),$($_.Y) title=[$($_.Title)]" }
$win = $found | Where-Object { $_.Vis -and $_.W -gt 100 -and $_.Ht -gt 100 } | Sort-Object W -Descending | Select-Object -First 1
if (-not $win) { throw 'no visible main window' }
$h = $win.H

if ($Action -eq 'click') {
    [UiWin]::ShowWindow($h, 9) | Out-Null
    [UiWin]::SetWindowPos($h, [IntPtr](-1), 0, 0, 0, 0, 0x0001 -bor 0x0002) | Out-Null
    [UiWin]::SetForegroundWindow($h) | Out-Null
    Start-Sleep -Milliseconds 400
    $cp = New-Object UiWin+POINT
    $cp.X = $X; $cp.Y = $Y
    [UiWin]::ClientToScreen($h, [ref]$cp) | Out-Null
    if ($Force) {
        # 客户端坐标 → 屏幕坐标，真实鼠标事件
        [UiWin]::SetCursorPos($cp.X, $cp.Y) | Out-Null
        Start-Sleep -Milliseconds 120
        [UiWin]::mouse_event(0x0002, 0, 0, 0, [IntPtr]::Zero)
        Start-Sleep -Milliseconds 60
        [UiWin]::mouse_event(0x0004, 0, 0, 0, [IntPtr]::Zero)
        "clicked real at client($X,$Y) -> screen($($cp.X),$($cp.Y))"
    } else {
        $l = [IntPtr](($Y -shl 16) -bor ($X -band 0xFFFF))
        [UiWin]::PostMessage($h, 0x0201, [IntPtr]1, $l) | Out-Null
        Start-Sleep -Milliseconds 60
        [UiWin]::PostMessage($h, 0x0202, [IntPtr]0, $l) | Out-Null
        "clicked post at client($X,$Y)"
    }
    exit 0
}

$cr = New-Object UiWin+RECT
[UiWin]::GetClientRect($h, [ref]$cr) | Out-Null
$cw = $cr.Right - $cr.Left; $ch = $cr.Bottom - $cr.Top
"client $cw x $ch"
if ($Action -eq 'shot') {
    $bmp = New-Object System.Drawing.Bitmap $cw, $ch
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $g.GetHdc()
    $ok = [UiWin]::PrintWindow($h, $hdc, 2)
    $g.ReleaseHdc($hdc); $g.Dispose()
    # PrintWindow 对 Electron 常全白：退化为屏幕截图（先把窗口置前）
    $mean = 0.0
    $px = 0; $py = 0
    for ($yy = 10; $yy -lt $ch; $yy += [Math]::Max(1,[int]($ch/12))) {
        for ($xx = 10; $xx -lt $cw; $xx += [Math]::Max(1,[int]($cw/12))) {
            $c = $bmp.GetPixel($xx, $yy); $mean += ($c.R + $c.G + $c.B) / 3.0; $px++
        }
    }
    $mean = if ($px -gt 0) { $mean / $px } else { 0 }
    if ($ok -and $mean -gt 5) {
        $bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()
        "printwindow=$ok mean=$([Math]::Round($mean,1)) saved=$Out"
    } else {
        $bmp.Dispose()
        [UiWin]::ShowWindow($h, 9) | Out-Null
        [UiWin]::SetWindowPos($h, [IntPtr](-1), 0, 0, 0, 0, 0x0001 -bor 0x0002) | Out-Null
        [UiWin]::SetForegroundWindow($h) | Out-Null
        Start-Sleep -Milliseconds 500
        $cp = New-Object UiWin+POINT
        $cp.X = 0; $cp.Y = 0
        [UiWin]::ClientToScreen($h, [ref]$cp) | Out-Null
        $bmp2 = New-Object System.Drawing.Bitmap $cw, $ch
        $g2 = [System.Drawing.Graphics]::FromImage($bmp2)
        $g2.CopyFromScreen($cp.X, $cp.Y, 0, 0, $bmp2.Size)
        $g2.Dispose()
        $bmp2.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp2.Dispose()
        "screencap fallback: printwindow=$ok mean=$([Math]::Round($mean,1)) saved=$Out"
    }
}
