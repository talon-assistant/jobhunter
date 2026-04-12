"""Tests for profile_vault.py."""

import pytest
from pathlib import Path

from jobhunter.core.profile_vault import ProfileVault


@pytest.fixture
def vault(tmp_path):
    return ProfileVault(tmp_path / "vault")


def test_vault_available(vault):
    """cryptography + keyring should be installed in test env."""
    # This may be False if deps aren't installed; skip gracefully
    if not vault.is_available:
        pytest.skip("cryptography/keyring not installed")


def test_no_profile_initially(vault):
    assert not vault.has_profile
    assert not vault.is_unlocked


def test_unlock_creates_temp_dir(vault):
    profile_dir = vault.unlock()
    assert Path(profile_dir).exists()
    assert vault.is_unlocked


def test_lock_encrypts_and_wipes(vault):
    if not vault.is_available:
        pytest.skip("cryptography/keyring not installed")

    # Unlock and create some fake session data
    profile_dir = vault.unlock()
    (Path(profile_dir) / "Cookies").write_text("fake_cookie_data")
    (Path(profile_dir) / "Local Storage").mkdir(exist_ok=True)

    # Lock should encrypt and wipe
    vault.lock()
    assert not vault.is_unlocked
    assert vault.has_profile  # encrypted archive exists


def test_round_trip(vault):
    """Data survives encrypt -> decrypt cycle."""
    if not vault.is_available:
        pytest.skip("cryptography/keyring not installed")

    # Write data
    profile_dir = vault.unlock()
    test_file = Path(profile_dir) / "test_session.txt"
    test_file.write_text("linkedin_session_token_abc123")
    vault.lock()

    # Read it back
    profile_dir = vault.unlock()
    recovered = Path(profile_dir) / "test_session.txt"
    assert recovered.exists()
    assert recovered.read_text() == "linkedin_session_token_abc123"
    vault.lock()


def test_import_existing(vault, tmp_path):
    if not vault.is_available:
        pytest.skip("cryptography/keyring not installed")

    # Create a fake existing profile
    existing = tmp_path / "old_profile"
    existing.mkdir()
    (existing / "Cookies").write_text("old_cookies")

    vault.import_existing(existing)
    assert vault.has_profile

    # Verify contents survived
    profile_dir = vault.unlock()
    assert (Path(profile_dir) / "Cookies").read_text() == "old_cookies"
    vault.lock()


def test_delete(vault):
    if not vault.is_available:
        pytest.skip("cryptography/keyring not installed")

    profile_dir = vault.unlock()
    (Path(profile_dir) / "data.txt").write_text("test")
    vault.lock()
    assert vault.has_profile

    vault.delete()
    assert not vault.has_profile
    assert not vault.is_unlocked


def test_graceful_without_deps(tmp_path):
    """Vault degrades gracefully if cryptography/keyring aren't installed."""
    vault = ProfileVault(tmp_path / "vault")
    # Even if deps are missing, unlock should return a usable directory
    profile_dir = vault.unlock()
    assert Path(profile_dir).exists()
