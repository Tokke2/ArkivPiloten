@echo off
rem ---------------------------------------------------------------------
rem  Engångsuppgradering till den version som autouppdaterar sig.
rem
rem  Ligger ArkivPiloten 1.0.0/1.1.0 kvar på datorn hittar den aldrig de
rem  nya releaserna (den letade i main-grenen). Kör den här filen en gång:
rem  den hämtar senaste versionen, kontrollerar summan och lägger filerna
rem  på plats. Dina regler, inställningar och historik rörs aldrig.
rem
rem  Filen kan ligga var som helst: den letar upp appmappen sjalv pa
rem  vanliga platser (Skrivbord, Dokument, Nedladdningar, OneDrive, ...),
rem  och du kan ocksa dra appmappen till filen och slappa den dar.
rem ---------------------------------------------------------------------
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
set "SCRIPT_URL=https://github.com/Tokke2/ArkivPiloten/releases/latest/download/install_latest.py"
set "TMPPY=%TEMP%\arkivpiloten_install_latest.py"

echo.
echo   ArkivPiloten - uppgradering till senaste versionen
echo   =================================================
echo.

rem -- 1. Hitta Python ---------------------------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    if exist "%~dp0venv\Scripts\python.exe" set "PY=%~dp0venv\Scripts\python.exe"
)
if not defined PY (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
        if exist "%%D\python.exe" set "PY=%%D\python.exe"
    )
)
if not defined PY (
    echo   Hittar ingen Python.
    echo   Installera Python fran https://www.python.org/downloads/ och kor
    echo   den har filen igen.
    echo.
    pause
    exit /b 1
)
echo   Python: !PY!

rem -- 2. Hämta installationsskriptet ------------------------------------
echo   Hamtar hjalpskriptet ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try{Invoke-WebRequest -UseBasicParsing '%SCRIPT_URL%' -OutFile '%TMPPY%'}catch{exit 1}"
if errorlevel 1 (
    echo.
    echo   Kunde inte hamta skriptet. Kontrollera internetanslutningen
    echo   och att github.com gar att na, och forsok igen.
    echo.
    pause
    exit /b 1
)

rem -- 3. Kör uppgraderingen (stäng appen först) -------------------------
rem  Har du dragit appmappen till filen ar det den som gäller, annars
rem  mappen filen ligger i. Hittas ingen app dar letar skriptet sjalvt.
set "ROOT=%~dp0"
if not "%~1"=="" set "ROOT=%~1"
rem  Ta bort ett avslutande \ - annars blir det " i kommandoraden och
rem  Python tolkar citattecknet som en del av sokvagen.
if "!ROOT:~-1!"=="\" set "ROOT=!ROOT:~0,-1!"
echo.
echo   Stang ArkivPiloten om den ar igang - annars ar filerna lasa.
echo.
!PY! "%TMPPY%" --root "!ROOT!"
set "RC=%ERRORLEVEL%"
del "%TMPPY%" >nul 2>&1

echo.
if "%RC%"=="0" (
    echo   Klart. Starta ArkivPiloten igen.
) else if "%RC%"=="2" (
    echo   Appen ar redan uppdaterad - inget gjordes.
) else (
    echo   Uppgraderingen gick inte igenom. Appmappen ar orord.
    echo   Kor filen igen och las felmeddelandet ovan.
)
echo.
pause
exit /b %RC%
