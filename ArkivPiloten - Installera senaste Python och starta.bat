@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem ======================================================================
rem ArkivPiloten - ENDA startfilen.
rem 1) Ser till att SENASTE stabila Python alltid finns installerad
rem    (per user, kräver inget admin; uppgraderar vid behov).
rem 2) Installerar appens basberoenden (requirements.txt).
rem 3) Startar appen utan konsolfönster.
rem Fungerar från valfri mapp/USB - allt utgår från denna fils plats.
rem ======================================================================
cd /d "%~dp0"
title ArkivPiloten

echo [1/3] Ser till att senaste stabila Python finns ...
set "PSSCRIPT=%TEMP%\arkivpiloten_python.ps1"
(
echo $ErrorActionPreference='Stop'
echo function vnum($s){try{$p=$s.Split('.');[int64]([int]$p[0]*10000+[int]$p[1]*100+[int]$p[2])}catch{0}}
echo $latest=$null
echo try{$w=(Invoke-WebRequest -UseBasicParsing 'https://www.python.org/downloads/').Content;if($w -match 'Download Python (3\.\d+\.\d+)'){$latest=$Matches[1]}}catch{}
echo $exe=$null
echo try{$c=py -3 -c 'import sys;print(sys.executable)' 2^>$null;if($c){$exe=$c.Trim()}}catch{}
echo if(-not $exe){try{$c=python -c 'import sys;print(sys.executable)' 2^>$null;if($c){$e=$c.Trim();if(Test-Path $e){$exe=$e}}}catch{}}
echo if(-not $exe){foreach($b in @("$env:LOCALAPPDATA\Programs\Python",$env:ProgramFiles)){if(Test-Path $b){foreach($d in (Get-ChildItem $b -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue^|Sort-Object Name -Descending)){if(Test-Path ($d.FullName+'\python.exe')){$exe=$d.FullName+'\python.exe';break}};if($exe){break}}}}
echo $cur=$null
echo if($exe){try{$cur=& $exe -c 'import sys;print(".".join(map(str,sys.version_info[:3])))' 2^>$null}catch{}}
echo if($latest -and (-not $exe -or (vnum $cur) -lt (vnum $latest))){Write-Host ('Installerar senaste Python '+$latest+' (tyst, per user) ...');$url='https://www.python.org/ftp/python/'+$latest+'/python-'+$latest+'-amd64.exe';$t=$env:TEMP+'\python-setup.exe';try{Invoke-WebRequest -UseBasicParsing $url -OutFile $t;Start-Process -FilePath $t -ArgumentList '/quiet','InstallAllUsers=0','PrependPath=1','Include_pip=1','Include_launcher=1' -Wait;Remove-Item $t -Force}catch{Write-Host ('Installationsfel: '+$_.Exception.Message)}}
echo if($latest){$b=$env:LOCALAPPDATA+'\Programs\Python';if(Test-Path $b){foreach($d in (Get-ChildItem $b -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue^|Sort-Object Name -Descending)){if(Test-Path ($d.FullName+'\python.exe')){$n=$d.FullName+'\python.exe';if(-not $exe -or (vnum $latest) -ge (vnum $cur)){$exe=$n};break}}}}
echo if($exe){Write-Output $exe}else{exit 1}
) > "%PSSCRIPT%"

set "PYEXE="
for /f "delims=" %%i in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%PSSCRIPT%"') do set "PYEXE=%%i"
del "%PSSCRIPT%" >nul 2>&1
if "%PYEXE%"=="" (
    echo.
    echo Kunde inte hitta eller installera Python.
    echo Kontrollera nätverket eller installera manuellt:
    echo   https://www.python.org/downloads/
    pause
    exit /b 1
)
echo       Python: %PYEXE%

echo [2/3] Kontrollerar ArkivPilotens Python-tillägg ...
"%PYEXE%" -m pip install --quiet --disable-pip-version-check -r "%~dp0requirements.txt" >nul 2>&1

set "PYW=%PYEXE:python.exe=pythonw.exe%"
if not exist "%PYW%" set "PYW=%PYEXE%"
echo [3/3] Startar ArkivPiloten ...
start "" "%PYW%" "%~dp0pdfsorter.pyw"
exit /b 0
