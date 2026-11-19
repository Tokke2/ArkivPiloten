@echo off
if /i not "%~1"=="--hidden" (
    wscript.exe //B //NoLogo "%~dp0ArkivPiloten - Starta tyst.vbs" "%~f0"
    exit /b
)
shift
setlocal EnableExtensions EnableDelayedExpansion
rem ======================================================================
rem ArkivPiloten - ENDA startfilen (utokad installationsrunda 2026-10-16).
rem 1) Hittar befintlig Python; fragar bara om installation om den saknas.
rem 2) Python-versionen andras inte automatiskt.
rem    Python-tillagg uppdateras veckovis, mandagar kl. 08:00.
rem 3) Kontrollerar Tesseract OCR (winget, basta forsok).
rem 4) Fragar om autostart (standard ja, kan stangas av).
rem Fungerar fran valfri mapp/USB - allt utgar fran denna fils plats.
rem 5) Startar appen utan konsol-fonster.
rem Misslyckas ett tillagg startar appen anda och visar i Hjalp-menyn
rem (Komplettera installationen) vad som saknas.
rem ======================================================================
cd /d "%~dp0"
title ArkivPiloten
if not exist "%~dp0temp" mkdir "%~dp0temp"
if not exist "%~dp0logs" mkdir "%~dp0logs"
if not exist "%~dp0cache\pip" mkdir "%~dp0cache\pip"
set "TEMP=%~dp0temp"
set "TMP=%~dp0temp"
set "PIP_CACHE_DIR=%~dp0cache\pip"
set "LOG=%~dp0logs\install.log"
echo ================================================== >> "%LOG%"
echo ArkivPiloten installation %DATE% %TIME% >> "%LOG%"

echo [1/6] Kontrollerar att Python finns ...
set "PSSCRIPT=%~dp0arkivpiloten_python.ps1"
set "PYEXE="
if not exist "%PSSCRIPT%" (
    echo       Python-kontrollskript saknas: %PSSCRIPT% >> "%LOG%"
    exit /b 1
)
for /f "delims=" %%i in ('powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%PSSCRIPT%"') do set "PYEXE=%%i"
if "%PYEXE%"=="" (
    powershell.exe -NoProfile -WindowStyle Hidden -Command "Add-Type -AssemblyName System.Windows.Forms; if ([System.Windows.Forms.MessageBox]::Show('Python saknas. Vill du installera senaste Python nu?', 'ArkivPiloten', [System.Windows.Forms.MessageBoxButtons]::YesNo, [System.Windows.Forms.MessageBoxIcon]::Question) -eq [System.Windows.Forms.DialogResult]::Yes) { exit 0 } else { exit 1 }"
    if errorlevel 1 exit /b 2
    echo       Hamtar senaste stabila Python fran python.org ...
    for /f "delims=" %%i in ('powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%PSSCRIPT%" -InstallIfMissing') do set "PYEXE=%%i"
)
if "%PYEXE%"=="" (
    echo       Python kunde inte installeras. Se felmeddelandet ovan.
    exit /b 1
)
echo       Python: %PYEXE%
echo Python: %PYEXE% >> "%LOG%"

set "PKGSTATE=%~dp0cache\python-packages-state.txt"
if not exist "%PKGSTATE%" (
    echo [2/6] Kontrollerar Python-tillagg forsta gangen ...
    "%PYEXE%" -c "import importlib.util as u,sys;mods=['fitz','pypdf','pdfminer','PIL','pystray','pytesseract'];sys.exit(any(u.find_spec(m) is None for m in mods))" >nul 2>&1
    if errorlevel 1 (
        echo       Nagra tillagg saknas - installerar dem en gang ...
        powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%PSSCRIPT%" -BootstrapPackages -PythonExe "%PYEXE%" -RequirementsPath "%~dp0requirements.txt" -LogPath "%LOG%"
        if errorlevel 1 echo VARNING: tillaggsinstallationen misslyckades; se logs\install.log och veckokontrollen forsoker igen. >> "%LOG%"
    ) else (
        echo       Tillaeggen finns redan; versionsuppdatering sker mandag kl. 08:00.
    )
    rem Markera engangskontrollen sa tillagg inte kontrolleras vid varje appstart.
    > "%PKGSTATE%" echo bootstrap-attempted
    "%PYEXE%" "%~dp0pdfsorter.py" --status >> "%LOG%" 2>&1
) else (
    echo [2/6] Python-tillagg uppdateras schemalagt mandagar kl. 08:00.
)

echo [3/6] Schemalagger tillaggskontroll till mandagar kl. 08:00 ...
set "SCHEDULESCRIPT=%~dp0arkivpiloten_schedule_python_updates.ps1"
if exist "%SCHEDULESCRIPT%" (
    powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%SCHEDULESCRIPT%"
    if errorlevel 1 (
        echo       VARNING: kunde inte skapa veckoschemat; se logs\python-packages-update.log.
        echo Kunde inte skapa veckoschemat %DATE% %TIME% >> "%LOG%"
    )
) else (
    echo       VARNING: schemalaggningsskriptet saknas.
)

echo [4/6] Kontrollerar Tesseract OCR (for skannade PDF:er) ...
set "TESS="
where tesseract >nul 2>&1 && for /f "delims=" %%i in ('where tesseract') do if not defined TESS set "TESS=%%i"
if not defined TESS if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESS=%ProgramFiles%\Tesseract-OCR\tesseract.exe"
if not defined TESS (
    echo       Tesseract saknas - installerar via winget ...
    winget install --id UB-Mannheim.TesseractOCR -e --silent --accept-package-agreements --accept-source-agreements
    if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESS=%ProgramFiles%\Tesseract-OCR\tesseract.exe"
)
if defined TESS (
    set "PATH=%PATH%;%ProgramFiles%\Tesseract-OCR"
    echo       Tesseract: %TESS%
    "%TESS%" --version 2>nul | findstr /C:"tesseract"
    "%TESS%" --list-langs 2>nul | findstr /X /C:"swe" >nul
    if errorlevel 1 (
        echo       Svenska saknas - hamtar swe.traineddata ...
        powershell.exe -NoProfile -WindowStyle Hidden -Command "try{Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/swe.traineddata' -OutFile '%ProgramFiles%\Tesseract-OCR\tessdata\swe.traineddata'}catch{exit 1}"
        if errorlevel 1 echo       Kunde inte skriva till Tesseract-mappen - svenskan kan kompletteras i appen: Hjalp, Komplettera installationen.
    ) else (
        echo       Sprak: svenska + engelska OK
    )
) else (
    echo       VARNING: Tesseract kunde inte installeras automatiskt.
    echo       Skannade PDF:er kan da inte OCR-lasas. Hamta det gratis har:
    echo         https://ub-mannheim.github.io/tesseract/
    echo       eller via appen: Hjalp, Komplettera installationen.
)

set "PYW=%PYEXE:python.exe=pythonw.exe%"
if not exist "%PYW%" set "PYW=%PYEXE%"
echo [5/6] Autostart (standard ja) ...
powershell.exe -NoProfile -WindowStyle Hidden -Command "Add-Type -AssemblyName System.Windows.Forms; if ([System.Windows.Forms.MessageBox]::Show('Starta ArkivPiloten automatiskt vid inloggning?', 'ArkivPiloten', [System.Windows.Forms.MessageBoxButtons]::YesNo, [System.Windows.Forms.MessageBoxIcon]::Question) -eq [System.Windows.Forms.DialogResult]::Yes) { exit 0 } else { exit 1 }"
if errorlevel 1 (
    echo       Autostart stangs av enligt ditt val.
    "%PYEXE%" "%~dp0pdfsorter.py" --remove-autostart >> "%LOG%" 2>&1
) else (
    "%PYEXE%" "%~dp0pdfsorter.py" --install-autostart >> "%LOG%" 2>&1
)
echo [6/6] Startar ArkivPiloten ...
echo Startar: %PYW% pdfsorter.pyw >> "%LOG%"
start "" "%PYW%" "%~dp0pdfsorter.pyw"
exit /b 0
