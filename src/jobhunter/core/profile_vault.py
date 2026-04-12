"""Encrypt/decrypt the LinkedIn browser profile at rest.

The profile directory contains session cookies and tokens that could be
used to impersonate the user's LinkedIn account.  This module encrypts
the profile into a single archive when not in use and decrypts it to a
temp directory only while scraping is active.

Encryption key is stored in the OS credential manager via the ``keyring``
library:
  - Windows: Windows Credential Manager
  - macOS:   Keychain
  - Linux:   Secret Service (GNOME Keyring / KWallet)

The archive uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
"""

from __future__ import annotations

import logging
import os
import secrets
import shutil
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

_SERVICE_NAME = "jobhunter"
_KEY_ACCOUNT = "linkedin_profile_key"


def _get_or_create_key() -> bytes:
    """Retrieve the encryption key from OS keyring, or create one."""
    import keyring
    from cryptography.fernet import Fernet

    stored = keyring.get_password(_SERVICE_NAME, _KEY_ACCOUNT)
    if stored:
        return stored.encode("utf-8")

    # Generate a new Fernet key
    key = Fernet.generate_key()
    keyring.set_password(_SERVICE_NAME, _KEY_ACCOUNT, key.decode("utf-8"))
    log.info("Generated new encryption key and stored in OS keyring")
    return key


def _get_fernet():
    """Get a Fernet cipher instance."""
    from cryptography.fernet import Fernet

    key = _get_or_create_key()
    return Fernet(key)


def _archive_path(vault_dir: Path) -> Path:
    """Path to the encrypted archive file."""
    return vault_dir / "linkedin_profile.vault"


def _pack_directory(source_dir: Path) -> bytes:
    """Pack a directory into a tar.gz bytes blob."""
    import io
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(source_dir), arcname="profile")
    return buf.getvalue()


def _unpack_directory(data: bytes, target_dir: Path) -> None:
    """Unpack a tar.gz bytes blob into a target directory."""
    import io
    import tarfile

    target_dir.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO(data)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        tar.extractall(str(target_dir), filter="data")


class ProfileVault:
    """Manages encryption/decryption of the LinkedIn browser profile.

    Usage::

        vault = ProfileVault(Path.home() / ".jobhunter")

        # Before scraping: decrypt to a temp directory
        profile_dir = vault.unlock()
        # ... use profile_dir with Playwright ...

        # After scraping: re-encrypt and wipe the temp copy
        vault.lock()
    """

    def __init__(self, vault_dir: str | Path) -> None:
        self.vault_dir = Path(vault_dir)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self._temp_dir: Path | None = None
        self._available = self._check_deps()

    @property
    def is_available(self) -> bool:
        """True if encryption dependencies are installed."""
        return self._available

    @property
    def has_profile(self) -> bool:
        """True if an encrypted profile archive exists."""
        return _archive_path(self.vault_dir).exists()

    @property
    def is_unlocked(self) -> bool:
        """True if the profile is currently decrypted to a temp dir."""
        return self._temp_dir is not None and self._temp_dir.exists()

    def unlock(self) -> Path:
        """Decrypt the profile to a temp directory. Returns the path.

        If no encrypted archive exists yet, returns a fresh temp directory
        (for first-time LinkedIn login).
        """
        if self._temp_dir and self._temp_dir.exists():
            profile = self._temp_dir / "profile"
            if profile.exists():
                return profile
            return self._temp_dir

        # Create a temp directory
        self._temp_dir = Path(tempfile.mkdtemp(prefix="jh_linkedin_"))

        archive = _archive_path(self.vault_dir)
        if archive.exists() and self._available:
            try:
                fernet = _get_fernet()
                encrypted = archive.read_bytes()
                decrypted = fernet.decrypt(encrypted)
                _unpack_directory(decrypted, self._temp_dir)
                log.info("Profile decrypted to %s", self._temp_dir)
                profile = self._temp_dir / "profile"
                return profile if profile.exists() else self._temp_dir
            except Exception:
                log.exception("Failed to decrypt profile, starting fresh")
                # Fall through to return empty temp dir

        log.info("No existing profile, using fresh directory: %s", self._temp_dir)
        return self._temp_dir

    def lock(self) -> None:
        """Re-encrypt the profile and securely wipe the temp copy."""
        if not self._temp_dir or not self._temp_dir.exists():
            return

        if not self._available:
            log.warning(
                "Encryption not available (install 'cryptography' and 'keyring'). "
                "Profile left unencrypted at %s", self._temp_dir
            )
            return

        try:
            # Determine what to encrypt: either temp_dir/profile or temp_dir itself
            profile_dir = self._temp_dir / "profile"
            source = profile_dir if profile_dir.exists() else self._temp_dir

            # Only encrypt if there's actual content
            if any(source.iterdir()):
                data = _pack_directory(source)
                fernet = _get_fernet()
                encrypted = fernet.encrypt(data)
                archive = _archive_path(self.vault_dir)
                archive.write_bytes(encrypted)
                log.info("Profile encrypted to %s (%d bytes)", archive, len(encrypted))
        except Exception:
            log.exception("Failed to encrypt profile")
            return

        # Wipe the temp directory
        try:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None
            log.info("Temp profile directory wiped")
        except Exception:
            log.exception("Failed to wipe temp directory")

    def import_existing(self, source_dir: str | Path) -> None:
        """Import an existing unencrypted profile directory into the vault.

        Use this for migrating from an unencrypted profile to the vault.
        """
        source = Path(source_dir)
        if not source.is_dir():
            raise FileNotFoundError(f"Profile directory not found: {source}")

        if not self._available:
            raise RuntimeError("Encryption deps not available")

        data = _pack_directory(source)
        fernet = _get_fernet()
        encrypted = fernet.encrypt(data)
        archive = _archive_path(self.vault_dir)
        archive.write_bytes(encrypted)
        log.info("Imported and encrypted profile from %s", source)

    def delete(self) -> None:
        """Delete the encrypted archive and any temp copies."""
        archive = _archive_path(self.vault_dir)
        if archive.exists():
            archive.unlink()
        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None
        log.info("Profile vault cleared")

    @staticmethod
    def _check_deps() -> bool:
        """Check if encryption dependencies are installed."""
        try:
            import cryptography  # noqa: F401
            import keyring  # noqa: F401
            return True
        except ImportError:
            return False
