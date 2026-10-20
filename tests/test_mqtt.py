"""MQTT client TLS configuration."""

import ssl
from unittest.mock import MagicMock

from custom_components.chery_europe.mqtt import CheryEuropeMqttClient


def test_mqtt_verifies_broker_hostname(monkeypatch):
    """The client trusts the bundled CA and still checks the broker hostname."""
    import paho.mqtt.client as mqtt

    fake = MagicMock()
    monkeypatch.setattr(mqtt, "Client", lambda *args, **kwargs: fake)
    monkeypatch.setattr(
        "custom_components.chery_europe.mqtt.provision_certs",
        lambda *args, **kwargs: True,
    )

    client = CheryEuropeMqttClient(
        host="tspemqx-app-eu.cheryinternational.com",
        port=8083,
        t_user_id="user-1",
        channel_id=1,
        certs_dir="/tmp/chery-mqtt-certs",
        on_payload=lambda service, data: None,
    )

    assert client.start() is True
    fake.tls_insecure_set.assert_not_called()
    tls_kwargs = fake.tls_set.call_args.kwargs
    assert tls_kwargs["cert_reqs"] == ssl.CERT_REQUIRED
    assert tls_kwargs["tls_version"] == ssl.PROTOCOL_TLS_CLIENT
    assert tls_kwargs["ca_certs"].endswith("ca.pem")
