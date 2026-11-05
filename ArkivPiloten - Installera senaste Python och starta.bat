@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem ======================================================================
rem ArkivPiloten - ENDA startfilen (utokad installationsrunda 2026-10-16).
rem 1) Hittar Python forst; uppdaterar befintlig installation inom samma
rem    versionsserie och installerar en ny serie bredvid vid behov.
rem    Nyinstallation sker bara om Python saknas helt.
rem 2) Uppgraderar pip och installerar ALLA Python-tillagg fran
rem    requirements.txt (PyMuPDF, pypdf, pdfminer.six, Pillow, pystray,
rem    pytesseract) - med retry och importkontroll efterat.
rem 3) Ser till att Tesseract OCR (systemprogram) finns med spraken
rem    svenska + engelska for skannade PDF:er (winget, basta forsok).
rem 4) Kor appens egen statuskontroll sa att anvandaren ser vad som hittats.
rem 5) Fragar om autostart (standard ja, kan stangas av).
rem Fungerar fran valfri mapp/USB - allt utgar fran denna fils plats.
rem 6) Startar appen utan konsol-fonster.
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

echo [1/5] Ser till att senaste stabila Python finns ...
set "PSSCRIPT=%~dp0arkivpiloten_python.ps1"
set "PYEXE="
if not exist "%PSSCRIPT%" (
    echo       Python-kontrollskript saknas: %PSSCRIPT%
    pause
    exit /b 1
)
for /f "delims=" %%i in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%PSSCRIPT%"') do set "PYEXE=%%i"
if "%PYEXE%"=="" (
    echo       Hittade eller kunde inte installera Python. Se felmeddelandet ovan.
    pause
    exit /b 1
)
echo       Python: %PYEXE%
echo Python: %PYEXE% >> "%LOG%"

echo [2/5] Installerar ALLA Python-tillagg (kan ta en stund) ...
"%PYEXE%" -m pip install --upgrade --disable-pip-version-check pip
"%PYEXE%" -m pip install --upgrade --prefer-binary --disable-pip-version-check -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo       Forsok 1 misslyckades - provar igen ...
    "%PYEXE%" -m pip install --upgrade --prefer-binary --disable-pip-version-check -r "%~dp0requirements.txt"
)
echo       Kontrollerar att paketen gar att importera:
"%PYEXE%" -c "import importlib.util as u; mods=[('PyMuPDF','fitz'),('pypdf','pypdf'),('pdfminer.six','pdfminer'),('Pillow','PIL'),('pystray','pystray'),('pytesseract','pytesseract')]; [print('         OK     ' + n) if u.find_spec(m) else print('         SAKNAS ' + n + '  (appen visar hur du kompletterar)') for n,m in mods]"

echo [3/5] Kontrollerar Tesseract OCR (for skannade PDF:er) ...
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
        powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/swe.traineddata' -OutFile '%ProgramFiles%\Tesseract-OCR\tessdata\swe.traineddata'}catch{exit 1}"
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

echo [4/5] Kor ArkivPilotens statuskontroll ...
"%PYEXE%" "%~dp0pdfsorter.py" --status

set "PYW=%PYEXE:python.exe=pythonw.exe%"
if not exist "%PYW%" set "PYW=%PYEXE%"
echo [5/6] Autostart (standard ja) ...
choice /C JN /N /T 15 /D J /M "Starta ArkivPiloten automatiskt vid inloggning? [J/N] "
if errorlevel 2 (
    echo       Autostart stangs av enligt ditt val.
    "%PYEXE%" "%~dp0pdfsorter.py" --remove-autostart
) else (
    "%PYEXE%" "%~dp0pdfsorter.py" --install-autostart
)
echo [6/6] Startar ArkivPiloten ...
echo Startar: %PYW% pdfsorter.pyw >> "%LOG%"
start "" "%PYW%" "%~dp0pdfsorter.pyw"
exit /b 0
