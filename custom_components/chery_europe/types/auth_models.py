"""Authentication models for the Chery Europe integration."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthResponse:
    """Response from authentication endpoint."""

    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str


@dataclass(frozen=True)
class LoginRequest:
    """Request payload for email OTP login."""

    email: str
    code: str
