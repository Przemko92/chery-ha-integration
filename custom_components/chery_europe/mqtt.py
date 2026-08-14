"""Optional MQTT push client for live Chery Europe vehicle telemetry."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import ssl
from collections.abc import Callable
from typing import Any

from .cert_bundle import decrypt_region
from .const import DEFAULT_MQTT_HOST, DEFAULT_MQTT_PORT, MQTT_PASSWORD_SEED

_LOGGER = logging.getLogger(__name__)

REQUIRED_CERTS = ("ca.pem", "client.pem", "client.key")


def provision_certs(certs_dir: str, host: str = DEFAULT_MQTT_HOST) -> bool:
    """Write region MQTT client certificates into ``certs_dir``."""
    os.makedirs(certs_dir, mode=0o700, exist_ok=True)
    if all(os.path.isfile(os.path.join(certs_dir, name)) for name in REQUIRED_CERTS):
        return True
    certs = decrypt_region(host)
    if not certs:
        _LOGGER.debug("No bundled MQTT certificates for host %s", host)
        return False
    for name, data in certs.items():
        path = os.path.join(certs_dir, name)
        with open(path, "wb") as handle:
            handle.write(data)
        os.chmod(path, 0o600)
    return True


class CheryEuropeMqttClient:
    """Subscribe to the vehicle message-center topic and forward payloads."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        t_user_id: str,
        channel_id: int,
        certs_dir: str,
        on_payload: Callable[[str, dict[str, Any]], None],
    ) -> None:
        self._host = host
        self._port = port
        self._t_user_id = t_user_id
        self._channel_id = channel_id
        self._certs_dir = certs_dir
        self._on_payload = on_payload
        self._client: Any = None

    def start(self) -> bool:
        """Connect in a background thread. Return False if MQTT cannot start."""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            _LOGGER.debug("paho-mqtt is not installed; skipping vehicle MQTT")
            return False
        if not provision_certs(self._certs_dir, self._host):
            return False

        password = hashlib.md5(
            f"{self._t_user_id}{MQTT_PASSWORD_SEED}".encode(),
            usedforsecurity=False,
        ).hexdigest()
        client_id = f"app_{self._channel_id}_{self._t_user_id}"
        topic = f"app/{self._channel_id}/{self._t_user_id}/account/msgCenter/msg"
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
            clean_session=False,
        )
        client.username_pw_set(self._t_user_id, password)
        client.tls_set(
            ca_certs=os.path.join(self._certs_dir, "ca.pem"),
            certfile=os.path.join(self._certs_dir, "client.pem"),
            keyfile=os.path.join(self._certs_dir, "client.key"),
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        client.tls_insecure_set(True)
        client.reconnect_delay_set(min_delay=1, max_delay=120)

        def on_connect(cl, _u, _flags, rc, _props=None) -> None:
            ok = rc == 0 or getattr(rc, "value", 1) == 0
            _LOGGER.info("Chery Europe MQTT connect rc=%s", rc)
            if ok:
                cl.subscribe(topic, qos=1)

        def on_message(_cl, _u, msg) -> None:
            try:
                obj = json.loads(msg.payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as err:
                _LOGGER.debug("Chery Europe MQTT payload ignored: %s", err)
                return
            service, data = parse_vehicle_mqtt_message(obj)
            if not data:
                return
            _LOGGER.debug("Chery Europe MQTT svc=%s keys=%s", service or "?", sorted(data))
            self._on_payload(service, data)

        client.on_connect = on_connect
        client.on_message = on_message
        try:
            client.connect(self._host, self._port, keepalive=60)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Chery Europe MQTT unavailable: %s", err)
            return False
        client.loop_start()
        self._client = client
        return True

    def stop(self) -> None:
        """Disconnect the MQTT client if it was started."""
        if self._client is None:
            return
        try:
            self._client.disconnect()
            self._client.loop_stop()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Chery Europe MQTT stop failed: %s", err)
        self._client = None


def parse_vehicle_mqtt_message(obj: Any) -> tuple[str, dict[str, Any]]:
    """Return (serviceType, data) from a Chery message-center MQTT envelope."""
    if not isinstance(obj, dict):
        return "", {}
    content = obj.get("content")
    if not isinstance(content, dict):
        content = obj
    data = content.get("data")
    payload = dict(data) if isinstance(data, dict) else {}
    service = str(content.get("serviceType") or obj.get("serviceType") or "")
    for key in (
        "lat",
        "lon",
        "latitude",
        "longitude",
        "lng",
        "gpsTime",
        "direction",
        "altitude",
        "gpsSpeed",
    ):
        if payload.get(key) in (None, "") and content.get(key) not in (None, ""):
            payload[key] = content[key]
    return service, payload
