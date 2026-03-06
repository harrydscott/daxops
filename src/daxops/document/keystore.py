"""API key storage using OS keychain via keyring package."""
from __future__ import annotations

SERVICE_NAME = "daxops"


def _keyring():
    """Import keyring lazily — it's an optional dependency."""
    try:
        import keyring
        return keyring
    except ImportError:
        raise RuntimeError(
            "keyring package required for API key storage. "
            "Install with: pip install daxops[llm]"
        )


def store_api_key(provider: str, api_key: str) -> None:
    """Store an API key in the OS keychain."""
    kr = _keyring()
    kr.set_password(SERVICE_NAME, provider, api_key)


def get_api_key(provider: str) -> str | None:
    """Retrieve an API key from the OS keychain."""
    kr = _keyring()
    return kr.get_password(SERVICE_NAME, provider)


def delete_api_key(provider: str) -> None:
    """Remove an API key from the OS keychain."""
    kr = _keyring()
    try:
        kr.delete_password(SERVICE_NAME, provider)
    except kr.errors.PasswordDeleteError:
        pass
