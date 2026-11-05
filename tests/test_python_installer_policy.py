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
