"""Environment bootstrap models for the Chery Europe integration."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EnvConfig:
    """Parsed ``defaultEnv`` response describing the active TSP environment.

    The Chery Europe app calls an unauthenticated ``defaultEnv`` endpoint at
    startup to discover the TSP backend (domain), OAuth client credentials,
    tenant and channel to use for all subsequent requests. The API returns
    camelCase keys; this dataclass exposes snake_case fields and a
    :meth:`from_dict` parser so callers never touch the raw envelope.
    """

    id: str
    name: str
    country: str
    tsp_env: str
    client_id: str
    client_secret: str
    domain: str
    channel_id: int
    map_type: str
    status: int
    tenant_id: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnvConfig":
        """Build an :class:`EnvConfig` from a raw ``defaultEnv`` ``data`` dict.

        The endpoint wraps the payload under a ``data`` key; pass the inner
        dict (or the whole envelope — both are handled) and missing optional
        fields default to empty/zero values rather than raising.
        """
        payload = data.get("data") if isinstance(data.get("data"), dict) else data

        def _str(key: str) -> str:
            value = payload.get(key)
            return str(value) if value is not None else ""

        def _int(key: str) -> int:
            value = payload.get(key)
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0

        return cls(
            id=_str("id"),
            name=_str("name"),
            country=_str("country"),
            tsp_env=_str("tspEnv"),
            client_id=_str("clientId"),
            client_secret=_str("clientSecret"),
            domain=_str("domain"),
            channel_id=_int("channelId"),
            map_type=_str("mapType"),
            status=_int("status"),
            tenant_id=_str("tenantId"),
        )