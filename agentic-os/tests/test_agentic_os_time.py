import pytest
import os
from unittest.mock import patch, MagicMock
from agentic_os_time import _resolve_timezone_name, get_timezone, reset_cache, now, _get_zoneinfo

def test_resolve_timezone_name_yaml_fallback(monkeypatch, tmp_path):
    reset_cache()
    def mock_read_raw_config():
        raise Exception("Not found")

    mock_cli_config = MagicMock()
    mock_cli_config.read_raw_config = mock_read_raw_config

    with patch.dict('sys.modules', {"agentic_os_cli.config": mock_cli_config}):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("timezone: 'Europe/Paris'")

        with patch("agentic_os_time.get_config_path", return_value=config_file):
            tz = _resolve_timezone_name()
            assert tz == "Europe/Paris"

def test_resolve_timezone_name_yaml_fallback_missing_file(monkeypatch, tmp_path):
    reset_cache()
    def mock_read_raw_config():
        raise Exception("Not found")

    mock_cli_config = MagicMock()
    mock_cli_config.read_raw_config = mock_read_raw_config

    with patch.dict('sys.modules', {"agentic_os_cli.config": mock_cli_config}):
        config_file = tmp_path / "config.yaml"

        with patch("agentic_os_time.get_config_path", return_value=config_file):
            tz = _resolve_timezone_name()
            assert tz == ""

def test_resolve_timezone_name_managed_scope_exception(monkeypatch):
    reset_cache()
    def mock_read_raw_config():
        return {"timezone": "Asia/Tokyo"}

    def mock_apply_managed_overlay(cfg):
        raise Exception("Managed scope error")

    mock_cli_config = MagicMock()
    mock_cli_config.read_raw_config = mock_read_raw_config
    mock_managed_scope = MagicMock()
    mock_managed_scope.apply_managed_overlay = mock_apply_managed_overlay

    with patch.dict('sys.modules', {
        "agentic_os_cli.config": mock_cli_config,
        "agentic_os_cli.managed_scope": mock_managed_scope
    }):
        tz = _resolve_timezone_name()
        assert tz == "Asia/Tokyo"

def test_resolve_timezone_name_general_exception(monkeypatch):
    reset_cache()
    def mock_read_raw_config():
        return []

    mock_cli_config = MagicMock()
    mock_cli_config.read_raw_config = mock_read_raw_config

    with patch.dict('sys.modules', {"agentic_os_cli.config": mock_cli_config}):
        tz = _resolve_timezone_name()
        assert tz == ""

def test_managed_scope_exception_trigger(monkeypatch):
    reset_cache()
    import builtins

    def mock_read_raw_config():
        return {"timezone": "Asia/Tokyo"}

    def mock_apply_managed_overlay(cfg):
        raise Exception("Managed scope error")

    mock_cli_config = MagicMock()
    mock_cli_config.read_raw_config = mock_read_raw_config

    mock_managed_scope = MagicMock()
    mock_managed_scope.apply_managed_overlay = mock_apply_managed_overlay

    original_import = builtins.__import__
    def patched_import(name, *args, **kwargs):
        if name == "agentic_os_cli.managed_scope" or name == "agentic_os_cli":
            if name == "agentic_os_cli":
                mock_cli = MagicMock()
                mock_cli.managed_scope = mock_managed_scope
                return mock_cli
            return mock_managed_scope
        return original_import(name, *args, **kwargs)

    with patch.dict('sys.modules', {"agentic_os_cli.config": mock_cli_config}):
        with patch("builtins.__import__", side_effect=patched_import):
            tz = _resolve_timezone_name()
            assert tz == "Asia/Tokyo"

def test_resolve_timezone_name_yaml_read_error(monkeypatch, tmp_path):
    reset_cache()
    def mock_read_raw_config():
        raise Exception("Not found")

    mock_cli_config = MagicMock()
    mock_cli_config.read_raw_config = mock_read_raw_config

    with patch.dict('sys.modules', {"agentic_os_cli.config": mock_cli_config}):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: :")

        with patch("agentic_os_time.get_config_path", return_value=config_file):
            with patch("builtins.open", side_effect=Exception("File read error")):
                tz = _resolve_timezone_name()
                assert tz == ""

def test_get_zoneinfo_invalid_tz(caplog):
    zone = _get_zoneinfo("Invalid/Zone")
    assert zone is None
    assert "Invalid timezone 'Invalid/Zone'" in caplog.text

def test_get_zoneinfo_empty():
    assert _get_zoneinfo("") is None

def test_now_fallback():
    reset_cache()
    with patch("agentic_os_time.os.getenv", return_value=""):
        with patch("agentic_os_time._resolve_timezone_name", return_value=""):
            dt = now()
            assert dt.tzinfo is not None
