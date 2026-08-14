import asyncio
import json
import logging
import time
from typing import Any, Mapping

import aiohttp

from .auth import CheryEuropeAuth
from .const import (
    API_CPM_CHECK_PASSWORD_PATH,
    API_REALTIME_PATH,
    API_TSP_LOGIN_PATH,
    API_VMC_QUERY_LIST_PATH,
    API_VMC_SET_VEC_DEFAULT_PATH,
    DEFAULT_BASE_URL,
    DEFAULT_CHANNEL_ID,
    DEFAULT_TSP_HOST,
    TSP_CODE_ASLEEP,
    TSP_CODE_OK,
)
from .crypto import encrypt_command_pin
from .signing import SIGN_SECRET, get_identity_headers
from .tsp_sign import auth_headers, sign_body
from .vehicle_commands import COMMAND_SPECS, command_result
from .exceptions import (
    CheryEuropeAuthError,
    CheryEuropeConnectionError,
    CheryEuropeRateLimitError,
    CheryEuropeTimeoutError,
)
from .types.vehicle_models import VehicleStatus

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
MAX_RETRIES = 3
TASK_ID_TTL_SECONDS = 600
TASK_ID_INVALID_CODES = frozenset({"A00089", "A00546", "A00567", "A00643"})


class CheryEuropeApi:
    """HTTP API wrapper for Chery Europe."""

    def __init__(
        self,
        auth: CheryEuropeAuth,
        session: aiohttp.ClientSession,
        base_url: str = DEFAULT_BASE_URL,
        channel_id: int = DEFAULT_CHANNEL_ID,
        tsp_host: str = DEFAULT_TSP_HOST,
    ) -> None:
        self._auth = auth
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._tsp_host = tsp_host.rstrip("/")
        self._channel_id = channel_id
        self._t_user_id: str | None = None
        self._user_token: str | None = None
        self._task_ids: dict[str, tuple[str, float]] = {}

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        """Perform an authenticated request with retry and token refresh."""
        return await self._request_with_retry(
            method, endpoint, refresh_on_401=True, **kwargs
        )

    async def tsp_login(self) -> None:
        """Exchange the OAuth access token for a TSP session (tUserId/userToken)."""
        response = await self._request(
            "POST",
            API_TSP_LOGIN_PATH,
            json={"channelId": self._channel_id},
        )
        payload = _unwrap_data(response)
        if not isinstance(payload, dict):
            raise CheryEuropeAuthError("Invalid TSP login response")

        t_user_id = payload.get("tUserId")
        if t_user_id is None:
            raise CheryEuropeAuthError("TSP login did not return tUserId")

        self._t_user_id = str(t_user_id)
        user_token = payload.get("userToken")
        self._user_token = str(user_token) if user_token else None
        _LOGGER.debug("Chery Europe TSP login succeeded")

    async def _ensure_tsp_session(self) -> None:
        if self._t_user_id:
            return
        await self.tsp_login()

    async def get_vehicle_list(self) -> list[VehicleStatus]:
        """Return vehicles associated with the account."""
        await self._ensure_tsp_session()
        response = await self._request(
            "POST",
            API_VMC_QUERY_LIST_PATH,
            json={"tUserId": self._t_user_id, "channelId": self._channel_id},
        )
        return _extract_vehicle_list(response)

    async def get_vehicle_status(self, vin: str) -> dict[str, Any] | None:
        """Return live telemetry for a vehicle from tspconsole realtime."""
        await self._ensure_tsp_session()
        if not self._user_token:
            _LOGGER.debug("Chery Europe TSP userToken missing; skipping realtime fetch")
            return None

        response = await self._tsp_signed_post(API_REALTIME_PATH, {"vin": vin})
        if not isinstance(response, dict):
            return None

        code = response.get("code")
        if code == TSP_CODE_ASLEEP:
            _LOGGER.debug("Vehicle %s asleep (realtime code %s)", vin, code)
            return None
        if code not in (TSP_CODE_OK, 0, "0"):
            _LOGGER.debug("Vehicle realtime returned code %s for %s", code, vin)
            return None

        payload = _extract_realtime_payload(response)
        if isinstance(payload, dict):
            return payload
        return None

    async def send_command(
        self, vin: str, command_id: str, pin: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Send a remote vehicle command through tspconsole vehicleControl."""
        await self._ensure_tsp_session()
        if not self._user_token:
            raise CheryEuropeAuthError("Missing TSP userToken")

        spec = COMMAND_SPECS.get(command_id)
        if spec is None:
            raise CheryEuropeConnectionError(f"Unsupported command id: {command_id}")

        body = spec.build_body(kwargs)
        response = await self._send_vehicle_control(
            vin=vin,
            pin=pin,
            endpoint=spec.endpoint,
            body=body,
        )
        return command_result(response)

    async def _send_vehicle_control(
        self,
        vin: str,
        pin: str,
        endpoint: str,
        body: dict[str, Any],
        *,
        force_new_task_id: bool = False,
    ) -> Any:
        """Send a signed vehicle-control command, minting a taskId when needed."""
        task_id = await self._get_task_id(vin, pin, force_new=force_new_task_id)
        timestamp_ms = int(time.time() * 1000)
        payload = {
            **body,
            "clientType": "1",
            "seq": f"{vin}-{timestamp_ms}",
            "taskId": task_id,
            "vin": vin,
        }
        path = f"/asc/vehicleControl/{endpoint}"
        response = await self._tsp_signed_post(path, payload)

        if isinstance(response, dict) and response.get("code") in TASK_ID_INVALID_CODES:
            if force_new_task_id:
                return response
            self._invalidate_task_id(vin)
            return await self._send_vehicle_control(
                vin,
                pin,
                endpoint,
                body,
                force_new_task_id=True,
            )
        return response

    async def _get_task_id(
        self,
        vin: str,
        pin: str,
        *,
        force_new: bool = False,
    ) -> str:
        """Return a cached or freshly minted taskId for vehicle commands."""
        now = time.time()
        if not force_new:
            cached = self._task_ids.get(vin)
            if cached and cached[1] > now:
                return cached[0]

        await self._request(
            "POST",
            API_VMC_SET_VEC_DEFAULT_PATH,
            json={"vin": vin},
        )
        response = await self._request(
            "POST",
            API_CPM_CHECK_PASSWORD_PATH,
            json={
                "vin": vin,
                "tUserId": self._t_user_id,
                "channelId": self._channel_id,
                "password": encrypt_command_pin(pin),
                "needDecode": 0,
                "scene": 0,
                "type": 0,
            },
        )
        payload = _unwrap_data(response)
        task_id = None
        if isinstance(payload, dict):
            task_id = payload.get("taskId")
        if task_id is None and isinstance(response, dict):
            task_id = response.get("taskId")
        if not task_id:
            message = None
            if isinstance(response, dict):
                message = response.get("msg") or response.get("key")
            raise CheryEuropeAuthError(
                message or "Chery Europe rejected the vehicle control PIN"
            )

        self._task_ids[vin] = (str(task_id), now + TASK_ID_TTL_SECONDS)
        return str(task_id)

    def _invalidate_task_id(self, vin: str) -> None:
        self._task_ids.pop(vin, None)

    async def _tsp_signed_post(self, path: str, params: dict[str, Any]) -> Any:
        """Perform a signed POST against the tspconsole host."""
        if not self._user_token:
            raise CheryEuropeAuthError("Missing TSP userToken")

        timestamp_ms = int(time.time() * 1000)
        body = sign_body(dict(params), timestamp_ms)
        headers = {
            **auth_headers(self._user_token, timestamp_ms),
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "okhttp/4.9.0",
            "version": "1.0.6",
            "agent": "android",
        }
        url = f"{self._tsp_host}{path if path.startswith('/') else f'/{path}'}"

        try:
            _LOGGER.debug("Chery Europe TSP request: POST %s", url)
            async with self._session.post(
                url,
                data=json.dumps(body),
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                _LOGGER.debug(
                    "Chery Europe TSP response: POST %s status=%s",
                    url,
                    response.status,
                )
                if response.status == 401:
                    raise CheryEuropeAuthError("TSP authentication failed")
                if response.status == 429:
                    raise CheryEuropeRateLimitError("Rate limit exceeded")
                if response.status >= 400:
                    error_body = await response.text()
                    _LOGGER.error(
                        "Chery Europe TSP error body: POST %s status=%s body=%s",
                        url,
                        response.status,
                        error_body[:500],
                    )
                    raise CheryEuropeConnectionError(
                        f"Chery Europe TSP returned status {response.status}"
                    )
                return await response.json(content_type=None)
        except asyncio.TimeoutError as exc:
            raise CheryEuropeTimeoutError("Chery Europe TSP request timed out") from exc
        except aiohttp.ClientConnectionError as exc:
            raise CheryEuropeConnectionError(
                "Unable to connect to Chery Europe TSP"
            ) from exc
        except aiohttp.ClientError as exc:
            raise CheryEuropeConnectionError("Chery Europe TSP HTTP error") from exc

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        refresh_on_401: bool,
        **kwargs: Any,
    ) -> Any:
        last_exception: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                return await self._single_request(
                    method, endpoint, refresh_on_401=refresh_on_401, **kwargs
                )
            except (
                CheryEuropeConnectionError,
                CheryEuropeTimeoutError,
                CheryEuropeRateLimitError,
            ) as exc:
                last_exception = exc
                if attempt == MAX_RETRIES - 1:
                    raise
                delay = 2**attempt
                _LOGGER.debug("Retrying Chery Europe API request after %ss", delay)
                await asyncio.sleep(delay)
        if last_exception is not None:
            raise last_exception
        raise CheryEuropeConnectionError("Chery Europe API request failed")

    async def _single_request(
        self,
        method: str,
        endpoint: str,
        refresh_on_401: bool,
        **kwargs: Any,
    ) -> Any:
        url = f"{self._base_url}{endpoint if endpoint.startswith('/') else f'/{endpoint}'}"
        method_upper = method.upper()

        # Build identity/signing headers for every BFF request.  GET requests
        # with query params pass the params dict as the signing body so the
        # bracketed query values are included in the signature; the ``keys``
        # header lists the ordered query-parameter names.  POST bodies are not
        # part of the signing string, so body/query_keys stay None for POST.
        params = kwargs.get("params")
        query_keys: list[str] | None = None
        signing_body: Mapping[str, Any] | None = None
        if method_upper == "GET" and isinstance(params, dict) and params:
            query_keys = list(params.keys())
            signing_body = params
        identity_headers = get_identity_headers(
            method=method_upper,
            path=endpoint,
            body=signing_body,
            secret=SIGN_SECRET,
            query_keys=query_keys,
        )

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **kwargs.pop("headers", {}),
            **identity_headers,
        }
        # Authorization is set last so identity headers can never overwrite it.
        if self._auth.access_token:
            headers["Authorization"] = f"Bearer {self._auth.access_token}"

        try:
            _LOGGER.debug("Chery Europe API request: %s %s", method_upper, url)
            async with self._session.request(
                method_upper,
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            ) as response:
                _LOGGER.debug(
                    "Chery Europe API response: %s %s status=%s",
                    method_upper,
                    url,
                    response.status,
                )
                if response.status == 401 and refresh_on_401:
                    await self._refresh_token()
                    return await self._request_with_retry(
                        method,
                        endpoint,
                        refresh_on_401=False,
                        **kwargs,
                    )
                if response.status == 401:
                    raise CheryEuropeAuthError("Authentication failed")
                if response.status == 429:
                    raise CheryEuropeRateLimitError("Rate limit exceeded")
                if response.status >= 400:
                    error_body = await response.text()
                    _LOGGER.error(
                        "Chery Europe API error body: %s %s status=%s body=%s",
                        method_upper,
                        url,
                        response.status,
                        error_body[:500],
                    )
                    raise CheryEuropeConnectionError(
                        f"Chery Europe API returned status {response.status}"
                    )
                if response.status == 204:
                    return None
                return await response.json(content_type=None)
        except asyncio.TimeoutError as exc:
            raise CheryEuropeTimeoutError("Chery Europe API request timed out") from exc
        except aiohttp.ClientConnectionError as exc:
            raise CheryEuropeConnectionError(
                "Unable to connect to Chery Europe"
            ) from exc
        except aiohttp.ClientError as exc:
            raise CheryEuropeConnectionError("Chery Europe HTTP error") from exc

    async def _refresh_token(self) -> None:
        refresh_token = self._auth.refresh_token_value
        if refresh_token is None:
            raise CheryEuropeAuthError("No refresh token available")
        self._t_user_id = None
        self._user_token = None
        await self._auth.refresh_token(refresh_token)


def _extract_realtime_payload(response: Any) -> dict[str, Any] | None:
    """Return the telemetry dict from a tspconsole realtime response."""
    if not isinstance(response, dict):
        return None
    for key in ("body", "data"):
        value = response.get(key)
        if isinstance(value, dict) and value:
            return value
    return None


def _unwrap_data(response: Any) -> Any:
    if isinstance(response, dict):
        data = response.get("data")
        if data is not None:
            return data
    return response


def _extract_vehicle_list(response: Any) -> list[Any]:
    """Return a vehicle list from common Chery API response shapes."""
    if isinstance(response, list):
        return response
    if not isinstance(response, dict):
        return []
    for key in ("data", "list", "vehicleList", "vehicles", "result"):
        value = response.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _extract_vehicle_list(value)
            if nested:
                return nested
    return [response] if response else []
