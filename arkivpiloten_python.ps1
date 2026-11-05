$ErrorActionPreference = 'Stop'

function Get-PythonVersion([string]$exe) {
    if (-not $exe -or -not (Test-Path -LiteralPath $exe)) { return $null }
    try {
        $v = & $exe -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) { return $v.Trim() }
    } catch { }
    return $null
}

function Find-Python {
    try {
        $cmd = Get-Command py -ErrorAction Stop
        $v = & $cmd.Source -3 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) {
            $candidate = $v.Trim()
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    } catch { }

    try {
        $cmd = Get-Command python -ErrorAction Stop
        $candidate = $cmd.Source
        if ($candidate -and (Test-Path -LiteralPath $candidate) -and
                $candidate -notlike "$env:LOCALAPPDATA\Microsoft\WindowsApps\*") {
            $candidateVersion = Get-PythonVersion $candidate
            if ($candidateVersion) { return $candidate }
        }
    } catch { }

    $roots = @("$env:LOCALAPPDATA\Programs\Python", $env:ProgramFiles,
               ${env:ProgramFiles(x86)})
    foreach ($root in $roots) {
        if (-not $root -or -not (Test-Path -LiteralPath $root)) { continue }
        $dirs = Get-ChildItem -LiteralPath $root -Directory -Filter 'Python3*' `
            -ErrorAction SilentlyContinue | Sort-Object Name -Descending
        foreach ($dir in $dirs) {
            $candidate = Join-Path $dir.FullName 'python.exe'
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    }
    return $null
}

function Get-LatestPythonVersion {
    try {
        $page = Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/downloads/' `
            -TimeoutSec 15
        if ($page.Content -match 'Download Python (3\.\d+\.\d+)') {
            return $Matches[1]
        }
    } catch { }
    return $null
}

function Install-Python([string]$version, [string]$targetDir, [int]$allUsers,
                        [bool]$freshInstall) {
    $url = "https://www.python.org/ftp/python/$version/python-$version-amd64.exe"
    $installer = Join-Path $env:TEMP 'arkivpiloten-python-setup.exe'
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $installer -TimeoutSec 60
        $installArgs = @('/quiet', "InstallAllUsers=$allUsers", 'Include_pip=1')
        if ($freshInstall) {
            $installArgs += @('PrependPath=1', 'Include_launcher=1')
        } else {
            $installArgs += @('Include_launcher=0')
            if ($targetDir) {
                $installArgs += @(('TargetDir="' + $targetDir + '"'), 'PrependPath=0')
            } else {
                $installArgs += @('PrependPath=1')
            }
        }
        $process = Start-Process -FilePath $installer -ArgumentList $installArgs `
            -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            throw "Python-installern avslutades med kod $($process.ExitCode)."
        }
        return $true
    } finally {
        Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
    }
}

$latest = Get-LatestPythonVersion
$exe = Find-Python
$cur = Get-PythonVersion $exe

if ($exe -and $latest -and $cur -and ([version]$cur -lt [version]$latest)) {
    $currentTrack = ($cur.Split('.')[0..1] -join '.')
    $latestTrack = ($latest.Split('.')[0..1] -join '.')
    $allUsers = 0
    $machineRoot = $null
    foreach ($programRoot in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if ($programRoot -and $exe.StartsWith(
                $programRoot, [StringComparison]::OrdinalIgnoreCase)) {
            $allUsers = 1
            $machineRoot = $programRoot
        }
    }

    if ($currentTrack -eq $latestTrack) {
        # Patchuppdatering inom samma Python-serie: återanvänd exakt den
        # befintliga installationen i stället för att skapa en kopia.
        $installDir = Split-Path -Parent $exe
    } else {
        # En ny major/minor-serie har en egen standardmapp på Windows.
        # Behåll befintlig Python och installera den nya serien bredvid.
        $installRoot = if ($allUsers) { $machineRoot } else {
            Join-Path $env:LOCALAPPDATA 'Programs\Python'
        }
        $installDir = Join-Path $installRoot ('Python' + ($latestTrack -replace '\.', ''))
        [Console]::Error.WriteLine(
            "Python $cur hittades; installerar nya serien $latest bredvid den.")
    }

    try {
        $null = Install-Python $latest $installDir $allUsers $false
        $candidate = Join-Path $installDir 'python.exe'
        $candidateVersion = Get-PythonVersion $candidate
        if (-not $candidateVersion -or [version]$candidateVersion -lt [version]$latest) {
            $candidate = Find-Python
            $candidateVersion = Get-PythonVersion $candidate
        }
        if ($candidateVersion -and [version]$candidateVersion -ge [version]$latest) {
            $exe = $candidate
        }
    } catch {
        [Console]::Error.WriteLine(
            "Python kunde inte uppdateras: $($_.Exception.Message). Befintlig Python används.")
    }
} elseif (-not $exe -and $latest) {
    # Nyinstallation sker bara när ingen fungerande Python hittades alls.
    try {
        $null = Install-Python $latest $null 0 $true
        $exe = Find-Python
    } catch {
        [Console]::Error.WriteLine(
            "Python kunde inte installeras från python.org: $($_.Exception.Message)")
    }

    # Sista reserv endast när Python saknas: winget följer senaste minor-spåret.
    if (-not $exe) {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if ($winget) {
            $parts = $latest.Split('.')
            $packageId = 'Python.Python.' + $parts[0] + '.' + $parts[1]
            try {
                & $winget.Source install --id $packageId -e --silent `
                    --accept-package-agreements --accept-source-agreements 2>$null | Out-Null
                $exe = Find-Python
            } catch { }
        }
    }
}

if ($exe -and (Test-Path -LiteralPath $exe)) {
    [Console]::Out.WriteLine($exe)
    exit 0
}
exit 1
