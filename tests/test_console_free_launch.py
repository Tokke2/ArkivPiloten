from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_bootstrap_has_a_hidden_vbs_entry_point():
    launcher = (ROOT / "ArkivPiloten - Starta tyst.vbs").read_text(
        encoding="utf-8")
    batch = (ROOT / "ArkivPiloten - Installera senaste Python och starta.bat"
             ).read_text(encoding="utf-8")

    assert "shell.Run(command, 0, True)" in launcher
    assert 'shell.SpecialFolders("Desktop")' in launcher
    assert 'shell.SpecialFolders("Programs")' in launcher
    assert "CreateArkivPilotenShortcut" in launcher
    assert '"%~1"=="--hidden"' in batch
    assert "ArkivPiloten - Starta tyst.vbs" in batch
    assert "choice /C" not in batch
    assert "pause" not in batch
    assert "pythonw.exe" in batch


def test_pythonw_redirects_diagnostics_and_python_exe_hands_off_the_gui():
    launcher = (ROOT / "pdfsorter.pyw").read_text(encoding="utf-8")
    app = (ROOT / "pdfsorter.py").read_text(encoding="utf-8")

    assert "def _fixa_stdio()" in launcher
    assert "sys.stderr = open(logg" in launcher
    assert "def _start_gui_without_console" in app
    assert "pythonw.exe" in app
    assert "CREATE_NO_WINDOW" in app
