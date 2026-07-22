"""Regression harness — pins config/env load behavior BEFORE managed scope exists.

Every test here must keep passing through all later phases when NO managed scope
is present. They are the 'managed scope is invisible when absent' contract.
"""
import os
import textwrap

import pytest


@pytest.fixture
def agentic_os_home(tmp_path, monkeypatch):
    home = tmp_path / "agentic_os_home"
    home.mkdir()
    monkeypatch.setenv("AGENTIC_OS_HOME", str(home))
    # No managed dir: point the override at a guaranteed-absent path so a real
    # /etc/hermes on the dev/CI box can't influence the test.
    monkeypatch.setenv("HERMES_MANAGED_DIR", str(tmp_path / "no_such_managed_dir"))
    # Clear caches so each test re-reads from disk.
    import agentic_os_cli.config as cfg

    cfg._LOAD_CONFIG_CACHE.clear()
    cfg._RAW_CONFIG_CACHE.clear()
    cfg.invalidate_env_cache()
    return home


def _write_user_config(home, body: str):
    (home / "config.yaml").write_text(textwrap.dedent(body), encoding="utf-8")
    import agentic_os_cli.config as cfg

    cfg._LOAD_CONFIG_CACHE.clear()
    cfg._RAW_CONFIG_CACHE.clear()


def test_user_config_overrides_default(agentic_os_home, monkeypatch):
    from agentic_os_cli.config import load_config, cfg_get

    _write_user_config(
        agentic_os_home,
        """
        model:
          default: user/model-x
        """,
    )
    cfg = load_config()
    assert cfg_get(cfg, "model", "default") == "user/model-x"


def test_env_expansion_in_user_config(agentic_os_home, monkeypatch):
    from agentic_os_cli.config import load_config, cfg_get

    monkeypatch.setenv("MY_BASE", "https://example.test")
    _write_user_config(
        agentic_os_home,
        """
        providers:
          custom:
            base_url: ${MY_BASE}/v1
        """,
    )
    cfg = load_config()
    assert cfg_get(cfg, "providers", "custom", "base_url") == "https://example.test/v1"


def test_no_managed_dir_means_user_value_wins(agentic_os_home):
    """Sanity: with the managed override pointing at an absent dir, nothing changes."""
    from agentic_os_cli.config import load_config, cfg_get

    _write_user_config(
        agentic_os_home,
        """
        model:
          default: user/model-y
        """,
    )
    assert cfg_get(load_config(), "model", "default") == "user/model-y"


def test_user_env_overrides_shell(tmp_path, monkeypatch):
    from agentic_os_cli.env_loader import load_agentic_os_dotenv

    home = tmp_path / "home"
    home.mkdir()
    (home / ".env").write_text("FOO_TOKEN=from_user_env\n", encoding="utf-8")
    monkeypatch.setenv("FOO_TOKEN", "from_shell")
    load_agentic_os_dotenv(agentic_os_home=str(home))
    assert os.environ["FOO_TOKEN"] == "from_user_env"


def test_missing_user_env_is_noop(tmp_path, monkeypatch):
    from agentic_os_cli.env_loader import load_agentic_os_dotenv

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("BAR_TOKEN", "from_shell")
    load_agentic_os_dotenv(agentic_os_home=str(home))
    assert os.environ["BAR_TOKEN"] == "from_shell"
