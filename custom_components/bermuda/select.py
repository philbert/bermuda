"""Create Select entities for Bermuda devices."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    ANCHOR_DISABLED,
    ANCHOR_ENABLED,
    ANCHOR_ENABLED_OPTIONS,
    DEFAULT_ANCHOR_ENABLED,
    DEFAULT_MOBILITY_TYPE,
    MOBILITY_OPTIONS,
    SIGNAL_DEVICE_NEW,
    SIGNAL_SCANNERS_CHANGED,
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
    created_devices: list[str] = []
    created_scanners: list[str] = []

    @callback
    def device_new(address: str) -> None:
        """Create mobility select for newly tracked device."""
        if address not in created_devices:
            async_add_devices([BermudaMobilityTypeSelect(coordinator, entry, address)], False)
            created_devices.append(address)
        coordinator.select_created(address)

    @callback
    def scanners_changed() -> None:
        """Create scanner anchor-enabled selects when scanners change."""
        entities = []
        for address, device in coordinator.devices.items():
            if device.is_scanner and address not in created_scanners:
                entities.append(BermudaScannerAnchorEnabledSelect(coordinator, entry, address))
                created_scanners.append(address)
        if entities:
            async_add_devices(entities, False)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_NEW, device_new))
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_SCANNERS_CHANGED, scanners_changed))


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


class BermudaScannerAnchorEnabledSelect(BermudaEntity, SelectEntity, RestoreEntity):
    """Per-scanner selector to include/exclude scanner as a trilat anchor."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Trilat Anchor Enabled"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = ANCHOR_ENABLED_OPTIONS

    async def async_added_to_hass(self) -> None:
        """Restore saved anchor mode when available."""
        await super().async_added_to_hass()
        if (old_state := await self.async_get_last_state()) is not None:
            self._device.anchor_enabled = old_state.state == ANCHOR_ENABLED
        else:
            self._device.anchor_enabled = DEFAULT_ANCHOR_ENABLED == ANCHOR_ENABLED

    @property
    def unique_id(self) -> str:
        """Return unique ID for this scanner anchor select entity."""
        return f"{self._device.unique_id}_trilat_anchor_enabled"

    @property
    def current_option(self) -> str:
        """Return current selected anchor inclusion mode."""
        return ANCHOR_ENABLED if getattr(self._device, "anchor_enabled", False) else ANCHOR_DISABLED

    async def async_select_option(self, option: str) -> None:
        """Set selected anchor inclusion mode."""
        self._device.anchor_enabled = option == ANCHOR_ENABLED
        self.async_write_ha_state()
