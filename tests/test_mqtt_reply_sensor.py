"""The MQTT reply sensor shows the last frame the car pushed.

Frames the integration does not act on (notifications, service codes such as
``301``) used to disappear in the debug log.  They now land in
``mqtt_last_service`` / ``mqtt_last_payload`` and are published by one
diagnostic sensor.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("homeassistant")

from homeassistant.const import EntityCategory  # noqa: E402

from custom_components.chery_europe.coordinator import (  # noqa: E402
    MQTT_REPLY_MAX_CHARS,
    CheryEuropeDataUpdateCoordinator,
)
from custom_components.chery_europe.data import CheryData  # noqa: E402
from custom_components.chery_europe.sensor import (  # noqa: E402
    MQTT_REPLY_SENSOR_DESCRIPTIONS,
    CheryEuropeMqttReplySensor,
)

VIN = "VIN123"


def _coordinator() -> CheryEuropeDataUpdateCoordinator:
    hass = Mock()
    hass.config_entries = Mock(async_update_entry=Mock())
    hass.async_create_task = Mock()
    entry = SimpleNamespace(options={}, title="Chery Europe")
    with patch(
        "custom_components.chery_europe.coordinator.DataUpdateCoordinator.__init__",
        return_value=None,
    ):
        coordinator = CheryEuropeDataUpdateCoordinator(
            hass, SimpleNamespace(), entry, None, vin=VIN
        )
    coordinator.hass = hass
    coordinator.async_set_updated_data = Mock(
        side_effect=lambda data: setattr(coordinator, "data", data) or data
    )
    coordinator.data = CheryData(vin=VIN)
    return coordinator


def _state(coordinator: CheryEuropeDataUpdateCoordinator):
    description = MQTT_REPLY_SENSOR_DESCRIPTIONS[0]
    return description.value_fn(coordinator.data)


def test_last_frame_is_published():
    """A frame the integration ignores still reaches the sensor."""
    coordinator = _coordinator()

    coordinator._apply_mqtt_payload("301", {"someReply": "ok"})

    assert _state(coordinator) == "301"
    assert coordinator.data.mqtt_frames_seen == 1
    assert "someReply" in (coordinator.data.mqtt_last_payload or "")
    assert coordinator.data.mqtt_last_at is not None


def test_notification_envelope_without_telemetry_is_kept():
    """Message-centre notifications carry no ``data`` dict; they are not lost."""
    coordinator = _coordinator()
    envelope = {
        "content": {
            "serviceType": "501",
            "data": {},
            "message": {"title": "Nowa wiadomość"},
        }
    }

    coordinator._apply_mqtt_payload("501", {}, envelope)

    assert _state(coordinator) == "501"
    assert coordinator.data.mqtt_frames_seen == 1
    assert "Nowa wiadomość" in (coordinator.data.mqtt_last_payload or "")


def test_counter_grows_with_every_frame():
    """``frames_seen`` tells whether pushes arrive at all after a quiet day."""
    coordinator = _coordinator()

    coordinator._apply_mqtt_payload("301", {"n": 1})
    coordinator._apply_mqtt_payload("1301", {"n": 2})

    assert coordinator.data.mqtt_frames_seen == 2
    assert _state(coordinator) == "1301"


def test_payload_is_truncated_for_the_recorder():
    """A status push is huge; only an excerpt goes into the attributes."""
    coordinator = _coordinator()

    coordinator._apply_mqtt_payload("301", {"blob": "x" * (MQTT_REPLY_MAX_CHARS * 2)})

    payload = coordinator.data.mqtt_last_payload or ""
    assert len(payload) == MQTT_REPLY_MAX_CHARS + 1
    assert payload.endswith("…")


def test_empty_service_falls_back_to_the_dash():
    """An envelope without a service code still shows a readable state."""
    coordinator = _coordinator()

    coordinator._apply_mqtt_payload("", {"n": 1})

    assert _state(coordinator) == "brak"


def _entity(coordinator: CheryEuropeDataUpdateCoordinator):
    entry = SimpleNamespace(options={}, title="Chery Europe", entry_id="abc")
    description = MQTT_REPLY_SENSOR_DESCRIPTIONS[0]
    return CheryEuropeMqttReplySensor(coordinator, description, entry)


def test_sensor_is_disabled_after_install():
    """It is a debug aid: registered off, switched on by hand when needed."""
    entity = _entity(_coordinator())

    assert entity.entity_registry_enabled_default is False
    assert entity.entity_category is EntityCategory.DIAGNOSTIC
