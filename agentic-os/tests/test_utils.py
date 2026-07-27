import pytest
import os
import json
import stat
from pathlib import Path
from unittest.mock import patch, MagicMock
from utils import (
    atomic_json_write,
    atomic_yaml_write,
    atomic_roundtrip_yaml_update,
    safe_json_loads,
    fast_safe_load,
    env_int,
    env_float,
    env_bool,
    normalize_proxy_url,
    normalize_proxy_env_vars,
    base_url_hostname,
    model_forces_max_completion_tokens,
    base_url_host_matches,
    _get_fast_yaml_loader,
    _preserve_file_owner,
    _restore_file_owner,
    _preserve_file_mode,
    _restore_file_mode,
    atomic_replace,
    is_truthy_value
)

def test_safe_json_loads():
    assert safe_json_loads('{"a": 1}') == {"a": 1}
    assert safe_json_loads('invalid', default={"fallback": True}) == {"fallback": True}
    assert safe_json_loads(None, default={}) == {}

def test_fast_safe_load():
    assert fast_safe_load('a: 1\nb: 2') == {'a': 1, 'b': 2}

def test_env_int():
    with patch.dict(os.environ, {"TEST_INT": "42", "TEST_INVALID_INT": "abc"}):
        assert env_int("TEST_INT") == 42
        assert env_int("TEST_INVALID_INT", 10) == 10
        assert env_int("TEST_MISSING", 20) == 20

def test_env_float():
    with patch.dict(os.environ, {"TEST_FLOAT": "42.5", "TEST_INVALID_FLOAT": "abc"}):
        assert env_float("TEST_FLOAT") == 42.5
        assert env_float("TEST_INVALID_FLOAT", 10.5) == 10.5
        assert env_float("TEST_MISSING", 20.5) == 20.5

def test_env_bool():
    with patch.dict(os.environ, {"TEST_BOOL_TRUE": "1", "TEST_BOOL_FALSE": "0"}):
        assert env_bool("TEST_BOOL_TRUE") is True
        assert env_bool("TEST_BOOL_FALSE") is False
        assert env_bool("TEST_MISSING", default=True) is False

def test_normalize_proxy_url():
    assert normalize_proxy_url(None) is None
    assert normalize_proxy_url("") is None
    assert normalize_proxy_url("socks://127.0.0.1:1080") == "socks5://127.0.0.1:1080"
    assert normalize_proxy_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080"

def test_normalize_proxy_env_vars():
    with patch.dict(os.environ, {"HTTP_PROXY": "socks://127.0.0.1:1080", "HTTPS_PROXY": "http://proxy:80"}):
        normalize_proxy_env_vars()
        assert os.environ["HTTP_PROXY"] == "socks5://127.0.0.1:1080"
        assert os.environ["HTTPS_PROXY"] == "http://proxy:80"

def test_base_url_hostname():
    assert base_url_hostname("") == ""
    assert base_url_hostname(None) == ""
    assert base_url_hostname("api.openai.com") == "api.openai.com"
    assert base_url_hostname("https://api.openai.com/v1") == "api.openai.com"
    assert base_url_hostname("http://localhost:8080") == "localhost"
    assert base_url_hostname("https://API.OPENAI.COM.") == "api.openai.com"

def test_model_forces_max_completion_tokens():
    assert model_forces_max_completion_tokens("gpt-4o") is True
    assert model_forces_max_completion_tokens("gpt-4o-mini") is True
    assert model_forces_max_completion_tokens("gpt-4.1") is True
    assert model_forces_max_completion_tokens("gpt-5") is True
    assert model_forces_max_completion_tokens("o1") is True
    assert model_forces_max_completion_tokens("o1-preview") is True
    assert model_forces_max_completion_tokens("o3-mini") is True
    assert model_forces_max_completion_tokens("o4") is True
    assert model_forces_max_completion_tokens("openai/gpt-4o") is True
    assert model_forces_max_completion_tokens("gpt-3.5-turbo") is False
    assert model_forces_max_completion_tokens("") is False
    assert model_forces_max_completion_tokens(None) is False

def test_base_url_host_matches():
    assert base_url_host_matches("https://api.moonshot.ai/v1", "moonshot.ai") is True
    assert base_url_host_matches("https://moonshot.ai", "moonshot.ai") is True
    assert base_url_host_matches("https://evil.com/moonshot.ai/v1", "moonshot.ai") is False
    assert base_url_host_matches("https://moonshot.ai.evil/v1", "moonshot.ai") is False
    assert base_url_host_matches("", "moonshot.ai") is False
    assert base_url_host_matches("https://api.moonshot.ai", "") is False

def test_get_fast_yaml_loader():
    assert _get_fast_yaml_loader() is not None

def test_file_permissions(tmp_path):
    f1 = tmp_path / "f1.txt"
    f1.write_text("test")
    f2 = tmp_path / "f2.txt"
    f2.write_text("test")

    orig_mode = _preserve_file_mode(f1)
    f2.chmod(stat.S_IRUSR)

    _restore_file_mode(f2, orig_mode)
    assert _preserve_file_mode(f2) == orig_mode

    assert _preserve_file_mode(tmp_path / "missing") is None
    _restore_file_mode(tmp_path / "missing", orig_mode)

    owner = _preserve_file_owner(f1)
    _restore_file_owner(f2, owner)
    assert _preserve_file_owner(tmp_path / "missing") is None

def test_atomic_json_write(tmp_path):
    target = tmp_path / "test.json"
    atomic_json_write(target, {"hello": "world"})
    assert json.loads(target.read_text()) == {"hello": "world"}

    atomic_json_write(target, {"hello": "world2"})
    assert json.loads(target.read_text()) == {"hello": "world2"}

def test_atomic_json_write_error(tmp_path):
    target = tmp_path / "test.json"
    with patch("os.fsync", side_effect=Exception("Failed sync")):
        with pytest.raises(Exception, match="Failed sync"):
            atomic_json_write(target, {"hello": "world"})
    assert not target.exists()

def test_atomic_yaml_write(tmp_path):
    target = tmp_path / "test.yaml"
    atomic_yaml_write(target, {"hello": "world"})
    assert "hello: world" in target.read_text()

    atomic_yaml_write(target, {"hello": "world2"}, extra_content="\n# Test comment\n")
    text = target.read_text()
    assert "hello: world2" in text
    assert "# Test comment" in text

def test_atomic_yaml_write_error(tmp_path):
    target = tmp_path / "test.yaml"
    with patch("os.fsync", side_effect=Exception("Failed sync")):
        with pytest.raises(Exception, match="Failed sync"):
            atomic_yaml_write(target, {"hello": "world"})
    assert not target.exists()

def test_atomic_roundtrip_yaml_update(tmp_path):
    target = tmp_path / "test.yaml"
    target.write_text("parent:\n  child: value1\n# Comment\n")

    atomic_roundtrip_yaml_update(target, "parent.child", "value2")

    text = target.read_text()
    assert "child: value2" in text
    assert "# Comment" in text

    atomic_roundtrip_yaml_update(target, "new_parent.new_child", "value3")
    text = target.read_text()
    assert "new_child: value3" in text

def test_atomic_roundtrip_yaml_update_error(tmp_path):
    target = tmp_path / "test.yaml"
    with patch("os.fsync", side_effect=Exception("Failed sync")):
        with pytest.raises(Exception, match="Failed sync"):
            atomic_roundtrip_yaml_update(target, "parent.child", "value")

def test_truthy_value_bool():
    assert is_truthy_value(True) is True
    assert is_truthy_value(False) is False
    assert is_truthy_value(1) is True
    assert is_truthy_value(0) is False
    assert is_truthy_value(None, True) is True
    assert is_truthy_value(None, False) is False

def test_atomic_replace_fallback(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("source")
    dst = tmp_path / "dst.txt"
    dst.write_text("dest")

    import errno
    def mock_replace(src, dst):
        err = OSError("Invalid cross-device link")
        err.errno = errno.EXDEV
        raise err

    with patch("os.replace", side_effect=mock_replace):
        res = atomic_replace(src, dst)
        assert dst.read_text() == "source"
        assert not src.exists()
        assert res == str(dst)

def test_atomic_replace_fallback_copystat_error(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("source")
    dst = tmp_path / "dst.txt"
    dst.write_text("dest")

    import errno
    def mock_replace(src, dst):
        err = OSError("Invalid cross-device link")
        err.errno = errno.EXDEV
        raise err

    with patch("os.replace", side_effect=mock_replace):
        with patch("shutil.copystat", side_effect=OSError("Copystat failed")):
            res = atomic_replace(src, dst)
            assert dst.read_text() == "source"
            assert not src.exists()
            assert res == str(dst)

def test_atomic_replace_fallback_fsync_error(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("source")
    dst = tmp_path / "dst.txt"
    dst.write_text("dest")

    import errno
    def mock_replace(src, dst):
        err = OSError("Invalid cross-device link")
        err.errno = errno.EXDEV
        raise err

    with patch("os.replace", side_effect=mock_replace):
        with patch("os.fsync", side_effect=OSError("fsync failed")):
            res = atomic_replace(src, dst)
            assert dst.read_text() == "source"
            assert not src.exists()
            assert res == str(dst)

def test_atomic_replace_other_error(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("source")
    dst = tmp_path / "dst.txt"

    import errno
    def mock_replace(src, dst):
        err = OSError("Permission denied")
        err.errno = errno.EACCES
        raise err

    with patch("os.replace", side_effect=mock_replace):
        with pytest.raises(OSError, match="Permission denied"):
            atomic_replace(src, dst)

def test_file_permissions_oserror(tmp_path):
    f = tmp_path / "f.txt"
    with patch("pathlib.Path.stat", side_effect=OSError("stat error")):
        assert _preserve_file_mode(f) is None
    with patch("pathlib.Path.stat", side_effect=OSError("stat error")):
        assert _preserve_file_owner(f) is None

def test_file_permissions_windows(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("test")
    with patch("os.name", "nt"):
        assert _preserve_file_owner(f) is None
        _restore_file_owner(f, (1000, 1000))

def test_atomic_json_write_chmod(tmp_path):
    target = tmp_path / "test.json"
    with patch("os.fchmod", create=True) as mock_fchmod:
        atomic_json_write(target, {"hello": "world"}, mode=0o644)
        mock_fchmod.assert_called_once()

    with patch.object(os, 'fchmod', spec=False, create=True) as mock_fchmod:
        del os.fchmod
        atomic_json_write(target, {"hello": "world2"}, mode=0o644)

    with patch("os.chmod", side_effect=OSError("chmod error")):
        atomic_json_write(target, {"hello": "world3"}, mode=0o644)

def test_atomic_json_write_unlink_error(tmp_path):
    target = tmp_path / "test.json"
    with patch("os.fsync", side_effect=Exception("sync error")):
        with patch("os.unlink", side_effect=OSError("unlink error")):
            with pytest.raises(Exception, match="sync error"):
                atomic_json_write(target, {"hello": "world"})

def test_atomic_yaml_write_unlink_error(tmp_path):
    target = tmp_path / "test.yaml"
    with patch("os.fsync", side_effect=Exception("sync error")):
        with patch("os.unlink", side_effect=OSError("unlink error")):
            with pytest.raises(Exception, match="sync error"):
                atomic_yaml_write(target, {"hello": "world"})

def test_atomic_roundtrip_yaml_update_unlink_error(tmp_path):
    target = tmp_path / "test.yaml"
    with patch("os.fsync", side_effect=Exception("sync error")):
        with patch("os.unlink", side_effect=OSError("unlink error")):
            with pytest.raises(Exception, match="sync error"):
                atomic_roundtrip_yaml_update(target, "hello", "world")
