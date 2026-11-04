from __future__ import annotations

import pdfsorter_system as S


def test_all_session_logs_share_the_logs_subdirectory(monkeypatch, tmp_path):
    app_data = tmp_path / "app"
    monkeypatch.setattr(S, "config_dir", lambda: app_data)

    assert S.log_dir() == app_data / "logs"
    assert S.session_dir() == app_data / "logs"
    assert S._month_log_path("errors").parent.parent == app_data / "logs"


def test_legacy_root_logs_move_into_logs_without_overwriting(monkeypatch, tmp_path):
    app_data = tmp_path / "app"
    log_dir = app_data / "logs"
    legacy = log_dir / "äldre"
    legacy.mkdir(parents=True)
    app_data.mkdir(exist_ok=True)
    (app_data / "krasch.log").write_text("old crash", encoding="utf-8")
    (app_data / "errors.log").write_text("old errors", encoding="utf-8")
    (log_dir / "krasch.log").write_text("current crash", encoding="utf-8")
    (legacy / "errors.log").write_text("older errors", encoding="utf-8")
    monkeypatch.setattr(S, "config_dir", lambda: app_data)
    monkeypatch.setattr(S, "session_log", lambda *_args, **_kwargs: None)

    S.migrate_legacy_logs()

    assert not (app_data / "krasch.log").exists()
    assert not (app_data / "errors.log").exists()
    assert (log_dir / "krasch.log").read_text(encoding="utf-8") == "current crash"
    assert (legacy / "krasch.log").read_text(encoding="utf-8") == "old crash"
    assert (legacy / "errors.log").read_text(encoding="utf-8") == "older errors"
    assert (legacy / "errors (2).log").read_text(encoding="utf-8") == "old errors"
