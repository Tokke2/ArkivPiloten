from types import SimpleNamespace

import pdfsorter as P


def test_about_dialog_displays_copyright_notice(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "config_dir", lambda: tmp_path)
    monkeypatch.setattr(P, "session_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(P, "_module_versions", lambda: {"pdfsorter": P.APP_VERSION})
    app = SimpleNamespace(settings={"check_updates": False})

    text = P.App._meny_om_text(app)

    assert "© 2026 Rickard Längkvist" in text
