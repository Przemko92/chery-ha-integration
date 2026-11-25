import asyncio
import inspect
import json
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import aiohttp

from .auth import CheryEuropeAuth
from .const import (
    API_CHARGE_APPOINT_QUERY_PATH,
    API_CPM_CHECK_PASSWORD_PATH,
    API_MESSAGES_PAGING_PATH,
    API_MESSAGES_UNREAD_PATH,
    API_MESSAGES_UPDATE_READ_PATH,
    API_QUERY_LOCATION_PATH,
    API_REALTIME_PATH,
    API_THEFT_QUERY_PATH,
    API_TRAVEL_APPOINT_CONTROL_PATHS,
    API_TRAVEL_APPOINT_QUERY_FALLBACKS,
    API_TSP_LOGIN_PATH,
    API_VMC_QUERY_AUTHORITY_PATH,
    API_VMC_QUERY_LIST_PATH,
    API_VMC_SET_VEC_DEFAULT_PATH,
    COMMAND_BUSY_CODE,
    COMMAND_BUSY_RETRY_DELAYS,
    DEFAULT_BASE_URL,
    DEFAULT_CHANNEL_ID,
    DEFAULT_MESSAGES_PAGE_SIZE,
    DEFAULT_TSP_HOST,
    TOKEN_REFRESH_QUOTA,
    TRAVEL_APPOINT_ENDPOINT,
    TSP_CODE_ASLEEP,
    TSP_CODE_OK,
)
from .crypto import encrypt_command_pin
from .data import (
    parse_charge_appointment,
    parse_theft_alarm,
    parse_travel_appointment,
)
from .exceptions import (
    CheryEuropeAuthError,
    CheryEuropeCommandError,
    CheryEuropeConnectionError,
    CheryEuropeRateLimitError,
    CheryEuropeTimeoutError,
)
from .messages import parse_unread_messages
from .permissions import UNKNOWN, adapt_command, normalize_permissions
from .request_queue import ApiRequestQueue, command_interval_key
from .signing import SIGN_SECRET, get_identity_headers
from .tsp_sign import auth_headers, sign_body
from .types.auth_models import AuthResponse
from .types.vehicle_models import VehicleStatus
from .vehicle_commands import (
    COMMAND_SPECS,
    build_travel_appoint_body,
    command_result,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
MAX_RETRIES = 3
TASK_ID_TTL_SECONDS = 600
TASK_ID_INVALID_CODES = frozenset({"A00089", "A00546", "A00567", "A00643"})

TokensUpdatedCallback = Callable[[AuthResponse], Awaitable[None] | None]


class CheryEuropeApi:
    """HTTP API wrapper for Chery Europe."""

    def __init__(
        self,
        auth: CheryEuropeAuth,
        session: aiohttp.ClientSession,
        base_url: str = DEFAULT_BASE_URL,
        channel_id: int = DEFAULT_CHANNEL_ID,
        tsp_host: str = DEFAULT_TSP_HOST,
        on_tokens_updated: TokensUpdatedCallback | None = None,
    ) -> None:
        self._auth = auth
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._tsp_host = tsp_host.rstrip("/")
        self._channel_id = channel_id
        self._t_user_id: str | None = None
        self._user_token: str | None = None
        self._task_ids: dict[str, tuple[str, float]] = {}
        self._permissions: dict[int, int] = UNKNOWN
        self._on_tokens_updated = on_tokens_updated
        # Chery rotates refresh_token on every use; parallel refreshes burn the
        # session. Serialize and double-check like the Omoda integration.
        self._token_lock = asyncio.Lock()
        self._tsp_login_lock = asyncio.Lock()
        # One in-flight HTTP call, and the same vehicle command at most every 5s.
        self._request_queue = ApiRequestQueue()
        # Injected so tests can drive the pause between busy retries.
        self._sleep = asyncio.sleep
        # Set by the coordinator to see every vehicle command outcome; keeps the
        # diagnostics entities honest even when a caller swallows the failure.
        self.command_result_callbacks: list[Any] = []

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

    @property
    def t_user_id(self) -> str | None:
        """Return the TSP user id after login."""
        return self._t_user_id

    @property
    def channel_id(self) -> int:
        """Return the BFF channel id used by this session."""
        return self._channel_id

    @property
    def permissions(self) -> dict[int, int]:
        """Return the last queryVehicleAuthority map (empty when unknown)."""
        return self._permissions

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
        return await self._tsp_query_payload(API_REALTIME_PATH, vin)

    async def get_vehicle_location(self, vin: str) -> dict[str, Any] | None:
        """Return GPS coordinates from queryVehicleLocation when the car is awake."""
        payload = await self._tsp_query_payload(API_QUERY_LOCATION_PATH, vin)
        if payload:
            return payload
        return None

    async def query_charge_appointment(
        self, vin: str
    ) -> tuple[bool | None, dict[str, Any] | None] | None:
        """Return the scheduled-charge plan from chargeAppointQuery.

        ``None`` means the query failed or the car was asleep. A tuple is a
        usable answer: enabled flag and the first plan, either of which may
        still be missing.
        """
        await self._ensure_tsp_session()
        if not self._user_token:
            return None
        try:
            response = await self._tsp_signed_post(
                API_CHARGE_APPOINT_QUERY_PATH, {"vin": vin}
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Charge appointment query failed for %s: %s", vin, exc)
            return None
        if not isinstance(response, dict):
            return None
        code = response.get("code")
        if code == TSP_CODE_ASLEEP:
            return None
        if code not in (TSP_CODE_OK, 0, "0", None):
            _LOGGER.debug("Charge appointment query for %s returned code %s", vin, code)
            return None
        return parse_charge_appointment(response)

    async def query_travel_appointment(self, vin: str) -> list[dict[str, Any]] | None:
        """Return the scheduled cabin/battery preparation plans.

        ``None`` means the query failed or the car did not answer, so callers
        keep the last known plan list instead of clearing it. The working path
        is remembered, so the fallbacks are only tried once per session.
        """
        await self._ensure_tsp_session()
        if not self._user_token:
            return None
        for path in self._travel_query_paths():
            try:
                response = await self._tsp_signed_post(path, {"vin": vin})
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug(
                    "Travel appointment query %s failed for %s: %s", path, vin, exc
                )
                continue
            if not isinstance(response, dict):
                continue
            code = response.get("code")
            if code == TSP_CODE_ASLEEP:
                return None
            if code not in (TSP_CODE_OK, 0, "0", None):
                _LOGGER.debug(
                    "Travel appointment query %s for %s returned code %s",
                    path,
                    vin,
                    code,
                )
                continue
            plans = parse_travel_appointment(response)
            if plans is None:
                continue
            if getattr(self, "_travel_query_path", None) != path:
                _LOGGER.debug("Travel appointment query path is %s", path)
                self._travel_query_path = path
            return plans
        return None

    def _travel_query_paths(self) -> list[str]:
        """Return the query paths to try, cheapest first."""
        cached = getattr(self, "_travel_query_path", None)
        paths = [path for path in API_TRAVEL_APPOINT_QUERY_FALLBACKS]
        if cached and cached in paths:
            paths.remove(cached)
            paths.insert(0, cached)
        return paths

    async def send_travel_appointment(
        self,
        vin: str,
        pin: str,
        plans: list[dict[str, Any]],
        permissions: Any = None,
    ) -> dict[str, Any]:
        """Write the complete preparation plan list to the car.

        The body is the whole list — the car replaces what is stored — so the
        caller must pass every plan that should survive, disabled ones too.
        The write path is discovered once (HTTP 404 means "not this module")
        and then cached for the rest of the session.
        """
        body = build_travel_appoint_body({"plans": plans, "vin": vin})
        perms = self._permissions if permissions is None else permissions
        endpoint, body = adapt_command(TRAVEL_APPOINT_ENDPOINT, body, perms)
        last_error: Exception | None = None
        for path in self._travel_control_paths():
            try:
                response = await self._send_vehicle_control_retrying(
                    vin=vin, pin=pin, endpoint=endpoint, body=body, path=path
                )
            except CheryEuropeConnectionError as exc:
                if "status 404" not in str(exc):
                    raise
                _LOGGER.debug("Travel appointment control path %s is 404", path)
                last_error = exc
                continue
            if getattr(self, "_travel_control_path", None) != path:
                _LOGGER.debug("Travel appointment control path is %s", path)
                self._travel_control_path = path
            return command_result(response)
        raise last_error or CheryEuropeCommandError(
            "No travel appointment control endpoint answered"
        )

    def _travel_control_paths(self) -> list[str]:
        """Return the control paths to try, the known-good one first."""
        cached = getattr(self, "_travel_control_path", None)
        paths = list(API_TRAVEL_APPOINT_CONTROL_PATHS)
        if cached and cached in paths:
            paths.remove(cached)
            paths.insert(0, cached)
        return paths

    async def query_theft_alarm(self, vin: str) -> bool | None:
        """Return the theft-alarm switch, or None when the car did not answer."""
        await self._ensure_tsp_session()
        if not self._user_token:
            return None
        try:
            response = await self._tsp_signed_post(API_THEFT_QUERY_PATH, {"vin": vin})
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Theft alarm query failed for %s: %s", vin, exc)
            return None
        if not isinstance(response, dict):
            return None
        code = response.get("code")
        if code == TSP_CODE_ASLEEP:
            return None
        if code not in (TSP_CODE_OK, 0, "0", None):
            _LOGGER.debug("Theft alarm query for %s returned code %s", vin, code)
            return None
        return parse_theft_alarm(response)

    async def fetch_messages(
        self, page: int = 1, page_size: int = DEFAULT_MESSAGES_PAGE_SIZE
    ) -> dict[str, Any] | None:
        """Return one page of the vehicle message inbox.

        The message service lives under ``/api/message/...`` (its own routing
        prefix, not ``tsp``) and wants the paging values in a JSON body; a GET
        with query parameters ends in a 500 from the Spring gateway.  ``None``
        means the request failed, so callers keep the last known list.
        """
        await self._ensure_tsp_session()
        try:
            response = await self._request(
                "POST",
                API_MESSAGES_PAGING_PATH,
                json={"pageNo": page, "pageSize": page_size},
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Vehicle messages query failed: %s", exc)
            return None
        if not isinstance(response, dict):
            return None
        if response.get("code") not in (TSP_CODE_OK, 0, "0", None):
            _LOGGER.debug(
                "Vehicle messages query returned code %s", response.get("code")
            )
            return None
        return response

    async def fetch_messages_unread(self) -> bool | None:
        """Return whether the inbox has unread messages (``None`` on failure).

        The endpoint only answers GET; a POST body is rejected with a 500.
        """
        await self._ensure_tsp_session()
        try:
            response = await self._request("GET", API_MESSAGES_UNREAD_PATH)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Unread messages query failed: %s", exc)
            return None
        return parse_unread_messages(response)

    async def mark_messages_read(self) -> bool:
        """Mark the whole inbox as read; ``True`` when the cloud accepted it.

        ``updateStatusToRead`` flips every entry in one shot -- an ``id`` in
        the body is accepted but not needed, and the response carries
        ``data: true`` on success.  The call is user triggered only; polling
        must never touch it so the account stays well below the rate limits.
        """
        await self._ensure_tsp_session()
        try:
            response = await self._request(
                "POST", API_MESSAGES_UPDATE_READ_PATH, json={}
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Marking the inbox read failed: %s", exc)
            return False
        if not isinstance(response, dict):
            return False
        if response.get("code") not in (TSP_CODE_OK, 0, "0", None):
            _LOGGER.debug(
                "Marking the inbox read returned code %s", response.get("code")
            )
            return False
        return bool(response.get("data", True))

    async def _tsp_query_payload(self, path: str, vin: str) -> dict[str, Any] | None:
        """Return a tspconsole dict payload, or None when the vehicle is asleep."""
        await self._ensure_tsp_session()
        if not self._user_token:
            _LOGGER.debug("Chery Europe TSP userToken missing; skipping %s", path)
            return None

        response = await self._tsp_signed_post(path, {"vin": vin})
        if not isinstance(response, dict):
            return None

        code = response.get("code")
        if code == TSP_CODE_ASLEEP:
            _LOGGER.debug("Vehicle %s asleep (%s code %s)", vin, path, code)
            return None
        if code not in (TSP_CODE_OK, 0, "0"):
            _LOGGER.debug("Vehicle %s returned code %s for %s", vin, code, path)
            return None

        payload = _extract_realtime_payload(response)
        if isinstance(payload, dict):
            return payload
        if any(
            response.get(key) not in (None, "")
            for key in ("lat", "latitude", "lon", "longitude")
        ):
            return response
        return None

    async def send_command(
        self,
        vin: str,
        command_id: str,
        pin: str,
        permissions: Mapping[int, int] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a remote vehicle command through tspconsole vehicleControl."""
        await self._ensure_tsp_session()
        if not self._user_token:
            raise CheryEuropeAuthError("Missing TSP userToken")

        spec = COMMAND_SPECS.get(command_id)
        if spec is None:
            raise CheryEuropeConnectionError(f"Unsupported command id: {command_id}")

        body = spec.build_body(kwargs)
        perms = self._permissions if permissions is None else permissions
        endpoint, body = adapt_command(spec.endpoint, body, perms)
        response = await self._send_vehicle_control_retrying(
            vin=vin,
            pin=pin,
            endpoint=endpoint,
            body=body,
            path=spec.path,
            command_id=command_id,
        )
        return command_result(response)

    async def _send_vehicle_control_retrying(
        self,
        *,
        vin: str,
        pin: str,
        endpoint: str,
        body: dict[str, Any],
        path: str | None = None,
        command_id: str | None = None,
    ) -> Any:
        """Send a command, waiting out the car while it reports it is busy.

        The car executes one command at a time, so a command that arrives while
        the previous one is still running comes back as A00082 and is not
        executed at all; the very same request a few seconds later lands.
        """
        attempt = 0
        while True:
            response = await self._send_vehicle_control(
                vin=vin, pin=pin, endpoint=endpoint, body=body, path=path
            )
            busy = isinstance(response, dict) and response.get("code") == COMMAND_BUSY_CODE
            if not busy or attempt >= len(COMMAND_BUSY_RETRY_DELAYS):
                self._notify_command_result(vin, command_id or endpoint, response)
                return response
            delay = COMMAND_BUSY_RETRY_DELAYS[attempt]
            _LOGGER.debug(
                "Chery Europe: the car is busy (A00082) with %s; retrying in %ss",
                command_id or endpoint,
                delay,
            )
            await self._sleep(delay)
            attempt += 1

    def _notify_command_result(self, vin: str, command_id: str, response: Any) -> None:
        """Hand the outcome to the coordinators for their diagnostics entities."""
        callbacks = self.command_result_callbacks
        if not callbacks:
            return
        result = command_result(response)
        for callback in list(callbacks):
            try:
                callback(vin, command_id, result)
            except Exception:  # noqa: BLE001 - reporting must never break a command
                _LOGGER.debug(
                    "Chery Europe: command result callback failed", exc_info=True
                )

    async def get_vehicle_authority(self, vin: str) -> dict[int, int]:
        """Return the vehicle command permission map, or UNKNOWN on failure."""
        await self._ensure_tsp_session()
        try:
            response = await self._request(
                "POST",
                API_VMC_QUERY_AUTHORITY_PATH,
                json={
                    "vin": vin,
                    "tUserId": self._t_user_id,
                    "channelId": self._channel_id,
                },
            )
            self._permissions = normalize_permissions(response)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Vehicle authority unavailable for %s: %s", vin, exc)
            self._permissions = UNKNOWN
        return self._permissions

    async def _send_vehicle_control(
        self,
        vin: str,
        pin: str,
        endpoint: str,
        body: dict[str, Any],
        *,
        path: str | None = None,
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
        request_path = path or f"/asc/vehicleControl/{endpoint}"
        response = await self._tsp_signed_post(request_path, payload)

        if isinstance(response, dict) and response.get("code") in TASK_ID_INVALID_CODES:
            if force_new_task_id:
                return response
            self._invalidate_task_id(vin)
            return await self._send_vehicle_control(
                vin,
                pin,
                endpoint,
                body,
                path=path,
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
        """Signed POST against tspconsole; re-login TSP once when it is rejected.

        The official app on the same account takes over the TSP session
        (userToken) while the OAuth token stays valid, so every later TSP call
        from Home Assistant gets 401/424 until the integration is reloaded.
        Minting a fresh TSP session and retrying once recovers without OTP.
        """
        used_token = self._user_token
        try:
            return await self._tsp_signed_post_once(path, params)
        except CheryEuropeAuthError as exc:
            if not getattr(exc, "tsp_rejected", False):
                raise
            _LOGGER.debug("Chery Europe TSP session rejected on %s; re-login", path)
            await self._tsp_relogin(used_token)
            return await self._tsp_signed_post_once(path, params)

    async def _tsp_relogin(self, used_token: str | None) -> None:
        """Mint a new TSP session unless a parallel request already did."""
        async with self._tsp_login_lock:
            if self._user_token and self._user_token != used_token:
                return
            self._t_user_id = None
            self._user_token = None
            self._task_ids.clear()
            await self.tsp_login()

    async def _tsp_signed_post_once(self, path: str, params: dict[str, Any]) -> Any:
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

        async def _post() -> Any:
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
                if response.status in {401, 424}:
                    exc = CheryEuropeAuthError("TSP authentication failed")
                    exc.tsp_rejected = True
                    raise exc
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

        try:
            return await self._request_queue.execute(
                _post,
                command_key=command_interval_key(path, params),
            )
        except TimeoutError as exc:
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

        async def _send() -> Any:
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
                    seen_access = self._auth.access_token
                    await self._refresh_token(seen_access_token=seen_access)
                    return await self._request_with_retry(
                        method,
                        endpoint,
                        refresh_on_401=False,
                        **kwargs,
                    )
                if response.status == 401:
                    raise CheryEuropeAuthError("Authentication failed")
                if response.status == 424:
                    raise CheryEuropeAuthError(
                        "Chery Europe session expired; sign in again"
                    )
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

        try:
            return await self._request_queue.execute(_send)
        except TimeoutError as exc:
            raise CheryEuropeTimeoutError("Chery Europe API request timed out") from exc
        except aiohttp.ClientConnectionError as exc:
            raise CheryEuropeConnectionError(
                "Unable to connect to Chery Europe"
            ) from exc
        except aiohttp.ClientError as exc:
            raise CheryEuropeConnectionError("Chery Europe HTTP error") from exc

    async def ensure_fresh_token(self, quota: float = TOKEN_REFRESH_QUOTA) -> bool:
        """Proactively refresh when the access token is near expiry.

        Returns ``True`` when a refresh was performed. Network/auth failures
        propagate to the caller (keep-alive should treat them as non-fatal).
        """
        if not self._auth.needs_proactive_refresh(quota):
            return False
        seen_access = self._auth.access_token
        await self._refresh_token(seen_access_token=seen_access)
        return True

    async def _refresh_token(self, seen_access_token: str | None = None) -> None:
        """Refresh OAuth tokens, persist them, and clear the TSP session.

        ``seen_access_token`` is the access token observed by the caller before
        waiting on the lock. If another coroutine already refreshed past that
        value, this call is a no-op so the new refresh_token is not burned.
        """
        async with self._token_lock:
            current = self._auth.access_token
            if seen_access_token and current and current != seen_access_token:
                _LOGGER.debug("Chery Europe token already refreshed by another request")
                return

            refresh_token = self._auth.refresh_token_value
            if refresh_token is None:
                raise CheryEuropeAuthError("No refresh token available")

            self._t_user_id = None
            self._user_token = None
            auth_response = await self._auth.refresh_token(refresh_token)
            await self._persist_tokens(auth_response)

    async def _persist_tokens(self, response: AuthResponse) -> None:
        """Persist rotated tokens when a callback is configured."""
        if self._on_tokens_updated is None:
            return
        result = self._on_tokens_updated(response)
        if inspect.isawaitable(result):
            await result


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
