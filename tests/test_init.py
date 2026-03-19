"""Test BLE Trilateration setup process."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from homeassistant.core import HomeAssistant

# from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ble_trilateration.const import DOMAIN, IrkTypes
from custom_components.ble_trilateration.coordinator import BermudaDataUpdateCoordinator

from .const import MOCK_CONFIG
from homeassistant.config_entries import ConfigEntryState

# from pytest_homeassistant_custom_component.common import AsyncMock


# We can pass fixtures as defined in conftest.py to tell pytest to use the fixture
# for a given test. We can also leverage fixtures and mocks that are available in
# Home Assistant using the pytest_homeassistant_custom_component plugin.
# Assertions allow you to verify that the return value of whatever is on the left
# side of the assertion matches with the right side.
async def test_setup_unload_and_reload_entry(
    hass: HomeAssistant, bypass_get_data, setup_bermuda_entry: MockConfigEntry
):
    """Test entry setup and unload."""

    # Reload the entry and assert that the data from above is still there
    assert await hass.config_entries.async_reload(setup_bermuda_entry.entry_id)
    assert setup_bermuda_entry.state == ConfigEntryState.LOADED

    assert set(IrkTypes.unresolved()) == {
        IrkTypes.ADRESS_NOT_EVALUATED.value,
        IrkTypes.NO_KNOWN_IRK_MATCH.value,
        IrkTypes.NOT_RESOLVABLE_ADDRESS.value,
    }

    # Unload the entry and verify that the data has been removed
    assert await hass.config_entries.async_unload(setup_bermuda_entry.entry_id)
    assert setup_bermuda_entry.state == ConfigEntryState.NOT_LOADED


async def test_setup_entry_exception(hass, error_on_get_data):
    """Test ConfigEntryNotReady when API raises an exception during entry setup."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")

    assert config_entry is not None

    # In this case we are testing the condition where async_setup_entry raises
    # ConfigEntryNotReady using the `error_on_get_data` fixture which simulates
    # an error.

    # Hmmm... this doesn't seem to be how this works. The super's _async_refresh might
    # handle exceptions, in which it then sets self.last_update_status, which is what
    # async_setup_entry checks in order to raise ConfigEntryNotReady, but I don't think
    # anything will "catch" our over-ridded async_refresh's exception.
    #  with pytest.raises(ConfigEntryNotReady):
    #     assert await async_setup_entry(hass, config_entry)


@dataclass(eq=False)
class _FakeScanner:
    """Minimal scanner object with source-based equality."""

    source: str
    age_s: float
    name: str = "Fake Scanner"
    discovered_devices_and_advertisement_data: dict = None

    def time_since_last_detection(self) -> float:
        """Return the configured age."""
        return self.age_s

    def __hash__(self) -> int:
        return hash(self.source)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _FakeScanner) and self.source == other.source


async def test_refresh_scanners_replaces_equal_source_scanner_object(setup_bermuda_entry: MockConfigEntry):
    """Scanner refresh must replace HA scanner objects after reconnects."""
    coordinator = setup_bermuda_entry.runtime_data.coordinator

    scanner_v1 = _FakeScanner("10:06:1c:16:69:ca", 120.0)
    scanner_v2 = _FakeScanner("10:06:1c:16:69:ca", 1.0)

    coordinator._manager = SimpleNamespace(async_current_scanners=lambda: [scanner_v1])
    coordinator._refresh_scanners(force=True)

    scanner_device = coordinator.devices["10:06:1c:16:69:ca"]
    assert scanner_device._hascanner is scanner_v1

    coordinator._manager = SimpleNamespace(async_current_scanners=lambda: [scanner_v2])
    coordinator._refresh_scanners()

    assert scanner_device._hascanner is scanner_v2
    assert next(iter(coordinator._hascanners)) is scanner_v2
