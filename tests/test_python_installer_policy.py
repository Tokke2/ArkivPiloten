from pathlib import Path

import pdfsorter_system as S


ROOT = Path(__file__).resolve().parents[1]


def test_windows_launcher_calls_the_python_policy_script():
    launcher = ROOT / "ArkivPiloten - Installera senaste Python och starta.bat"
    text = launcher.read_text(encoding="utf-8")

    assert 'set "PSSCRIPT=%~dp0arkivpiloten_python.ps1"' in text
    assert 'powershell -NoProfile -ExecutionPolicy Bypass -File "%PSSCRIPT%"' in text
    assert "winget install --id Python.Python.3.13" not in text


def test_existing_python_updates_same_track_and_fresh_install_is_missing_only():
    policy = (ROOT / "arkivpiloten_python.ps1").read_text(encoding="utf-8")

    assert "if ($currentTrack -eq $latestTrack)" in policy
    assert 'TargetDir="' in policy
    assert "elseif (-not $exe -and $latest)" in policy
    assert "Install-Python $latest $null 0 $true" in policy
    assert "Behåll befintlig Python och installera den nya serien bredvid." in policy


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
    assert "pip install --upgrade" in bootstrap
    assert "pip install --upgrade" not in later
    assert "if ($WeeklyUpdate -or -not $exe)" in policy
    assert "if ($WeeklyUpdate) {" in policy
    assert "-DaysOfWeek Monday" in scheduler
    assert "AddHours(8)" in scheduler
    assert "-StartWhenAvailable" in scheduler
    assert "Interactive" in scheduler
