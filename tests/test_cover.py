from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.cover import COVER_DESCRIPTIONS, CheryEuropeCover
from custom_components.chery_europe.data import CheryData


def test_trunk_cover_closed():
    coordinator = SimpleNamespace(
        data=CheryData(vin="VIN1", trunk_open=False),
        last_update_success=True,
    )
    entry = SimpleNamespace(entry_id="entry-1")
    description = next(item for item in COVER_DESCRIPTIONS if item.key == "trunk")
    cover = CheryEuropeCover(coordinator, description, entry)
    assert cover.is_closed is True


def test_trunk_cover_open():
    coordinator = SimpleNamespace(
        data=CheryData(vin="VIN1", trunk_open=True),
        last_update_success=True,
    )
    entry = SimpleNamespace(entry_id="entry-1")
    description = next(item for item in COVER_DESCRIPTIONS if item.key == "trunk")
    cover = CheryEuropeCover(coordinator, description, entry)
    assert cover.is_closed is False
