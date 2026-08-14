"""Exceptions for the Chery Europe integration."""

from homeassistant.exceptions import HomeAssistantError


class CheryEuropeException(HomeAssistantError):
    """Base exception for Chery Europe integration errors."""


class CheryEuropeAuthError(CheryEuropeException):
    """Raised when authentication fails."""


class CheryEuropeConnectionError(CheryEuropeException):
    """Raised when a connection error occurs."""


class CheryEuropeCommandError(CheryEuropeException):
    """Raised when a vehicle command fails."""


class CheryEuropePermissionError(CheryEuropeCommandError):
    """Raised when the vehicle is not allowed to run a command."""


class CheryEuropeTimeoutError(CheryEuropeException):
    """Raised when a request times out."""


class CheryEuropeRateLimitError(CheryEuropeException):
    """Raised when the API rate limit is exceeded."""
