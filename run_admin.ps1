param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$run = 'D:\Games\gakumas-agent\run.py'
$python = 'D:\Games\MaaGakumasu\python\python.exe'

$quoted = @()
foreach ($a in $Rest) {
    if ($a -match '\s') { $quoted += '"' + $a + '"' } else { $quoted += $a }
}
$argString = '"' + $run + '" ' + ($quoted -join ' ')

Write-Host "Elevating: $python $argString"
$p = Start-Process -FilePath $python -ArgumentList $argString -Verb RunAs -Wait -PassThru
exit $p.ExitCode
