"""Registry behaviour that is easy to get wrong and expensive to get wrong.

The launcher itself needs a real browser, so it is exercised by hand (see
docs/OWN_FINGERPRINT_BROWSER.md). What is tested here is the part that decides
where a secret ends up.
"""

import json
import sys
import types

import pytest

from agent.ec_skills.browser_use_extension.fingerprint import profile_registry as reg


class _FakeKeyring:
    """Stands in for the OS vault so tests never touch the real one."""

    def __init__(self):
        self.store = {}
        self.fail = False

    def set_password(self, service, account, password):
        if self.fail:
            raise RuntimeError("no backend")
        self.store[(service, account)] = password

    def get_password(self, service, account):
        return self.store.get((service, account))

    def delete_password(self, service, account):
        self.store.pop((service, account), None)


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """A registry rooted in tmp_path, with a fake keyring."""
    path = tmp_path / "browser_profiles.json"
    monkeypatch.setattr(reg, "_registry_path", lambda: path)
    monkeypatch.setenv("ECAN_BROWSER_DATA_ROOT", str(tmp_path / "data"))
    fake = _FakeKeyring()
    monkeypatch.setitem(sys.modules, "keyring", fake)
    return types.SimpleNamespace(path=path, keyring=fake)


def test_proxy_password_never_reaches_disk(registry):
    prof = reg.make_profile("etsy", proxy={"scheme": "socks5",
                                           "host": "p.example", "port": 1080,
                                           "username": "u"})
    reg.save_profile(prof, proxy_password="s3cret")

    on_disk = registry.path.read_text(encoding="utf-8")
    assert "s3cret" not in on_disk
    assert "ecan_browser_proxy/etsy" in on_disk
    assert reg.get_proxy_password(reg.get_profile("etsy")) == "s3cret"


def test_save_refuses_rather_than_falling_back_to_plaintext(registry):
    """If the vault is unavailable we must fail, not quietly write the secret."""
    registry.keyring.fail = True
    prof = reg.make_profile("etsy", proxy={"host": "p.example", "port": 1080,
                                           "username": "u"})
    with pytest.raises(RuntimeError):
        reg.save_profile(prof, proxy_password="s3cret")
    assert not registry.path.exists() or "s3cret" not in registry.path.read_text(
        encoding="utf-8")


def test_save_replaces_rather_than_duplicates(registry):
    reg.save_profile(reg.make_profile("etsy", label="old"))
    reg.save_profile(reg.make_profile("etsy", label="new"))
    profiles = reg.list_profiles()
    assert len(profiles) == 1
    assert profiles[0]["label"] == "new"


def test_user_data_dir_is_derived_once_and_kept(registry):
    """The directory name must not drift — it IS the session."""
    first = reg.make_profile("etsy")["user_data_dir"]
    reg.save_profile(reg.make_profile("etsy"))
    assert reg.make_profile("etsy")["user_data_dir"] == first
    assert reg.get_profile("etsy")["user_data_dir"] == first


def test_a_corrupt_registry_is_set_aside_not_lost(registry):
    registry.path.write_text("{ this is not json", encoding="utf-8")
    assert reg.list_profiles() == []
    salvaged = list(registry.path.parent.glob("browser_profiles.broken-*.json"))
    assert len(salvaged) == 1

    reg.save_profile(reg.make_profile("etsy"))
    assert json.loads(registry.path.read_text(encoding="utf-8"))["profiles"]


def test_delete_forgets_the_password_too(registry):
    reg.save_profile(reg.make_profile("etsy", proxy={"host": "p", "port": 1,
                                                     "username": "u"}),
                     proxy_password="s3cret")
    assert reg.delete_profile("etsy") is True
    assert reg.get_profile("etsy") is None
    assert registry.keyring.store == {}
    assert reg.delete_profile("etsy") is False


class TestVendorImportCopy:
    """The copy filter: what must travel, and what must not."""

    def _tree(self, root):
        (root / "Default").mkdir(parents=True)
        (root / "Default" / "Cookies").write_bytes(b"session")
        (root / "Local State").write_text("{}", encoding="utf-8")
        for cache in ("Cache", "Code Cache", "Service Worker"):
            (root / cache).mkdir()
            (root / cache / "blob").write_bytes(b"x" * 2048)
        (root / "SingletonLock").write_text("held", encoding="utf-8")
        (root / "DevToolsActivePort").write_text("9222", encoding="utf-8")

    def test_session_travels_and_caches_do_not(self, tmp_path):
        from agent.ec_skills.browser_use_extension.fingerprint import vendor_import

        src, dest = tmp_path / "src", tmp_path / "dest"
        self._tree(src)
        vendor_import._copy_profile(src, dest, None)

        assert (dest / "Default" / "Cookies").read_bytes() == b"session"
        assert (dest / "Local State").exists()
        for cache in ("Cache", "Code Cache", "Service Worker"):
            assert not (dest / cache).exists(), f"{cache} should not be copied"

    def test_lock_files_do_not_travel(self, tmp_path):
        """A copied lock makes the new profile look open somewhere else."""
        from agent.ec_skills.browser_use_extension.fingerprint import vendor_import

        src, dest = tmp_path / "src", tmp_path / "dest"
        self._tree(src)
        vendor_import._copy_profile(src, dest, None)

        assert not (dest / "SingletonLock").exists()
        assert not (dest / "DevToolsActivePort").exists()
