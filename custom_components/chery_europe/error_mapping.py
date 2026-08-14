"""Centralized exception-to-error-key mapping for the Chery Europe integration."""

from .exceptions import (
    CheryEuropeAuthError,
    CheryEuropeCommandError,
    CheryEuropeConnectionError,
    CheryEuropeException,
    CheryEuropeRateLimitError,
    CheryEuropeTimeoutError,
)

ERROR_KEYS: dict[type[Exception], str] = {
    CheryEuropeAuthError: "invalid_auth",
    CheryEuropeConnectionError: "cannot_connect",
    CheryEuropeTimeoutError: "cannot_connect",
    CheryEuropeRateLimitError: "rate_limit",
    CheryEuropeCommandError: "command_failed",
    CheryEuropeException: "unknown",
}


def map_error(exc: Exception) -> str | None:
    """Return the error key for errors["base"] based on exception type.

    Uses isinstance() checking so subclasses are supported.
    Returns None if the exception is not mapped to an error key.
    """
    for exc_type, key in ERROR_KEYS.items():
        if isinstance(exc, exc_type):
            return key
    return None
