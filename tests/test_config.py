"""Tests for configuration loading."""
from backend.config import Settings, get_settings


def test_get_settings_has_no_filesystem_side_effect(tmp_path, monkeypatch):
    """Reading settings must NOT create data_root on disk.

    A filesystem side effect here means merely *importing* the app (which calls
    get_settings() at module load) touches the production data_root — that
    breaks test isolation and crashes when the suite runs as a user that
    doesn't own the data directory. Directory creation belongs at write time.
    """
    target = tmp_path / "should_not_be_created"
    monkeypatch.setenv("JOB_ACE_DATA_ROOT", str(target))
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.data_root == target
        assert not target.exists(), (
            "get_settings() created data_root as a side effect; config reads "
            "must be pure so importing the app never touches the filesystem"
        )
    finally:
        get_settings.cache_clear()


def test_settings_data_root_defaults_relative():
    """Default data_root stays a relative path (no implicit absolute prod path)."""
    assert Settings(_env_file=None).data_root.is_absolute() is False
