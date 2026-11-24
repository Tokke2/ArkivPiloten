from pathlib import Path

import pdfsorter_system as S


ROOT = Path(__file__).resolve().parents[1]


def test_windows_launcher_calls_the_python_policy_script():
    launcher = ROOT / "ArkivPiloten - Installera senaste Python och starta.bat"
    text = launcher.read_text(encoding="utf-8")

    assert 'set "PSSCRIPT=%~dp0arkivpiloten_python.ps1"' in text
    assert 'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%PSSCRIPT%"' in text
    assert "winget install --id Python.Python.3.13" not in text
    assert "choice /C" not in text
    assert "[System.Windows.Forms.MessageBox]::Show('Python saknas." in text
    guard_start = text.index('if "%PYEXE%"=="" (')
    guard_end = text.index('if "%PYEXE%"=="" (', guard_start + 1)
    missing_python_branch = text[guard_start:guard_end]
    assert "MessageBoxButtons]::YesNo" in missing_python_branch
    assert "-File \"%PSSCRIPT%\" -InstallIfMissing" in missing_python_branch


def test_python_runtime_is_not_auto_updated_but_is_installed_if_missing():
    policy = (ROOT / "arkivpiloten_python.ps1").read_text(encoding="utf-8")

    assert "Automatisk versionsuppdatering av Python är avstängd." in policy
    assert "if (-not $exe -and $InstallIfMissing) { $latest = Get-LatestPythonVersion }" in policy
    assert "if (-not $exe -and $InstallIfMissing -and $latest) {" in policy
    assert "Install-Python $latest $null 0 $true" in policy
    assert "if ($currentTrack -eq $latestTrack)" not in policy
    assert "if ($WeeklyUpdate -and $exe -and $latest" not in policy


def test_python_policy_is_in_the_release_update_manifest():
    assert "arkivpiloten_python.ps1" in S.UPDATE_FILES
    assert "arkivpiloten_schedule_python_updates.ps1" in S.UPDATE_FILES


def test_package_updates_are_scheduled_weekly_not_run_on_each_start():
    launcher = (ROOT / "ArkivPiloten - Installera senaste Python och starta.bat")
    batch = launcher.read_text(encoding="utf-8")
    policy = (ROOT / "arkivpiloten_python.ps1").read_text(encoding="utf-8")
    scheduler = (ROOT / "arkivpiloten_schedule_python_updates.ps1").read_text(
        encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "==" not in requirements
    assert all(name in requirements for name in (
        "PyMuPDF", "pypdf", "pdfminer.six", "Pillow", "pystray", "pytesseract"))
    assert 'if not exist "%PKGSTATE%"' in batch
    assert 'set "SCHEDULESCRIPT=%~dp0arkivpiloten_schedule_python_updates.ps1"' in batch
    assert batch.count("--status") == 1  # bara vid engångs-bootstrap
    package_block = batch.split('if not exist "%PKGSTATE%"', 1)[1]
    bootstrap, later = package_block.split(") else (", 1)
    assert "-BootstrapPackages" in bootstrap
    assert "pip install --upgrade" not in bootstrap
    assert "pip install --upgrade" not in later
    assert "Invoke-PipLogged" in policy
    assert "INFO (ofarlig PATH-varning" in policy
    assert "kvarlämnad metadata från avbruten avinstallation" in policy
    assert "incompletely removed|invalid" in policy
    assert "if (-not $exe -and $InstallIfMissing) { $latest = Get-LatestPythonVersion }" in policy
    assert "if ($WeeklyUpdate) {" in policy
    assert "'--upgrade', '--prefer-binary'" in policy
    assert "Automatisk versionsuppdatering av Python är avstängd." in policy
    assert "Python-versionen ändras inte automatiskt." in scheduler
    assert "-DaysOfWeek Monday" in scheduler
    assert "$nextMonday = $now.Date.AddDays($daysUntilMonday).AddHours(8)" in scheduler
    assert "if ($nextMonday -le $now) { $nextMonday = $nextMonday.AddDays(7) }" in scheduler
    assert "-At $nextMonday" in scheduler
    assert "-StartWhenAvailable" in scheduler
    assert "Interactive" in scheduler


def test_python_itself_is_never_updated_automatically():
    launcher = (ROOT / "ArkivPiloten - Installera senaste Python och starta.bat")
    startup = launcher.read_text(encoding="utf-8")
    updater = (ROOT / "arkivpiloten_python.ps1").read_text(encoding="utf-8")
    scheduler = (ROOT / "arkivpiloten_schedule_python_updates.ps1").read_text(
        encoding="utf-8")

    assert "arkivpiloten_python.ps1" in startup
    assert "-WeeklyUpdate" not in startup
    assert "Python-versionen ändras inte automatiskt" in scheduler
    assert "if ($WeeklyUpdate -and $exe -and $latest" not in updater
    assert "if (-not $exe -and $InstallIfMissing) { $latest = Get-LatestPythonVersion }" in updater
    assert 'Install-Python $latest $null 0 $true' in updater


def test_macos_linux_bootstrap_offers_python_only_when_missing():
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert 'if ! command -v "$PYTHON" >/dev/null 2>&1; then' in installer
    assert 'read -r -p "Installera senaste Python 3 från systemets pakethanterare? [j/N] "' in installer
    assert 'install_missing_python\nfi' in installer
    assert 'brew install python' in installer
    assert 'apt-get install -y python3 python3-venv python3-tk' in installer


def test_release_excludes_and_removes_the_standalone_python_installer():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8")

    assert "Installera senaste Python.bat" not in S.UPDATE_FILES
    assert not (ROOT / "Installera senaste Python.bat").exists()
    assert "gh release delete-asset" in workflow
    assert "Installera senaste Python.bat" in workflow


def test_manual_addon_update_remains_available_in_help_dialog():
    source = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")
    assert '_action("Uppdatera tillägg", _uppdatera_paket)' in source
    assert "Du kan uppdatera tilläggen manuellt här." in source
