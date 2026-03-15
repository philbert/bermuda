"""Create Select entities for Bermuda devices."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DEFAULT_MOBILITY_TYPE,
    MOBILITY_OPTIONS,
    SIGNAL_DEVICE_NEW,
)
from .entity import BermudaEntity

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import BermudaConfigEntry
    from .coordinator import BermudaDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BermudaConfigEntry,
    async_add_devices: AddEntitiesCallback,
) -> None:
    """Load Select entities for a config entry."""
    coordinator: BermudaDataUpdateCoordinator = entry.runtime_data.coordinator
    _remove_legacy_scanner_anchor_selects(hass, entry.entry_id)
    created_devices: list[str] = []

    @callback
    def device_new(address: str) -> None:
        """Create mobility select for newly tracked device."""
        if address not in created_devices:
            async_add_devices([BermudaMobilityTypeSelect(coordinator, entry, address)], False)
            created_devices.append(address)
        coordinator.select_created(address)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_NEW, device_new))


def _remove_legacy_scanner_anchor_selects(hass: HomeAssistant, entry_id: str) -> None:
    """Remove entity-registry entries for retired scanner anchor select entities."""
    entity_registry = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(entity_registry, entry_id):
        if entity_entry.domain != "select":
            continue
        if entity_entry.unique_id.endswith("_trilat_anchor_enabled"):
            entity_registry.async_remove(entity_entry.entity_id)


class BermudaMobilityTypeSelect(BermudaEntity, SelectEntity, RestoreEntity):
    """Per-device mobility mode selector used by Bermuda filtering logic."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Mobility Type"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = MOBILITY_OPTIONS

    async def async_added_to_hass(self) -> None:
        """Restore saved mobility mode when available."""
        await super().async_added_to_hass()
        if (old_state := await self.async_get_last_state()) is not None:
            self._device.set_mobility_type(old_state.state)
        else:
            self._device.set_mobility_type(DEFAULT_MOBILITY_TYPE)

    @property
    def unique_id(self) -> str:
        """Return unique ID for this mobility select entity."""
        return f"{self._device.unique_id}_mobility"

    @property
    def current_option(self) -> str:
        """Return current selected mobility mode."""
        return self._device.get_mobility_type()

    async def async_select_option(self, option: str) -> None:
        """Set selected mobility mode."""
        self._device.set_mobility_type(option)
        self.async_write_ha_state()
