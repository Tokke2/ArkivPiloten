$ErrorActionPreference = 'Stop'

$appDir = $PSScriptRoot
$pythonScript = Join-Path $appDir 'arkivpiloten_python.ps1'
$requirements = Join-Path $appDir 'requirements.txt'
$logs = Join-Path $appDir 'logs'
$logPath = Join-Path $logs 'python-packages-update.log'
$statePath = Join-Path $appDir 'cache\python-packages-state.txt'
$taskName = 'ArkivPiloten Python weekly update'
$powershell = Join-Path $PSHOME 'powershell.exe'

$arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $pythonScript +
    '" -WeeklyUpdate -RequirementsPath "' + $requirements +
    '" -LogPath "' + $logPath + '" -StatePath "' + $statePath + '"'

try {
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    $sameAction = $false
    if ($existing -and $existing.Actions.Count -gt 0) {
        $sameAction = ($existing.Actions[0].Execute -eq $powershell -and
                       $existing.Actions[0].Arguments -eq $arguments)
    }
    if ($sameAction) { exit 0 }

    $action = New-ScheduledTaskAction -Execute $powershell -Argument $arguments `
        -WorkingDirectory $appDir
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday `
        -At ([datetime]::Today.AddHours(8))
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 30) `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $user `
        -LogonType Interactive -RunLevel Limited

    Register-ScheduledTask -TaskName $taskName -Action $action `
        -Trigger $trigger -Settings $settings -Principal $principal `
        -Description 'Kontrollerar och uppdaterar ArkivPilotens Python och tillägg varje måndag kl. 08:00.' `
        -Force | Out-Null
} catch {
    [Console]::Error.WriteLine(
        "Kunde inte schemalägga Python-uppdatering: $($_.Exception.Message)")
    exit 1
}
