"""Create Number entities - like per-device rssi ref_power, etc."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberExtraStoredData,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import SIGNAL_DEVICE_NEW, SIGNAL_SCANNERS_CHANGED
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
    """Load Number entities for a config entry."""
    coordinator: BermudaDataUpdateCoordinator = entry.runtime_data.coordinator

    created_devices = []  # list of devices we've already created entities for
    created_scanner_entities = []  # list of scanner addresses we've created config entities for

    @callback
    def device_new(address: str) -> None:
        """
        Create entities for newly-found device.

        Called from the data co-ordinator when it finds a new device that needs
        to have sensors created. Not called directly, but via the dispatch
        facility from HA.
        Make sure you have a full list of scanners ready before calling this.
        """
        if address not in created_devices:
            entities = []
            entities.append(BermudaNumber(coordinator, entry, address))
            # We set update before add to False because we are being
            # call(back(ed)) from the update, so causing it to call another would be... bad.
            async_add_devices(entities, False)
            created_devices.append(address)
        else:
            # _LOGGER.debug(
            #     "Ignoring create request for existing dev_tracker %s", address
            # )
            pass
        # tell the co-ord we've done it.
        coordinator.number_created(address)

    @callback
    def scanners_changed() -> None:
        """
        Create per-scanner configuration Number entities.

        Called when the list of scanners changes (new scanner added, etc).
        Creates RSSI offset, attenuation, and max_radius Number entities
        for each scanner device.
        """
        entities = []
        for address, device in coordinator.devices.items():
            if device.is_scanner and address not in created_scanner_entities:
                # Create the three configuration Number entities for this scanner
                entities.append(BermudaScannerRSSIOffset(coordinator, entry, address))
                entities.append(BermudaScannerAttenuation(coordinator, entry, address))
                entities.append(BermudaScannerMaxRadius(coordinator, entry, address))
                created_scanner_entities.append(address)

        if entities:
            async_add_devices(entities, False)

    # Connect device_new to a signal so the coordinator can call it
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_NEW, device_new))

    # Connect scanners_changed to handle new scanners
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_SCANNERS_CHANGED, scanners_changed))

    # Now we must tell the co-ord to do initial refresh, so that it will call our callback.
    # await coordinator.async_config_entry_first_refresh()


class BermudaNumber(BermudaEntity, RestoreNumber):
    """A Number entity for bermuda devices."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Calibration Ref Power at 1m. 0 for default."
    _attr_translation_key = "ref_power"
    _attr_device_class = NumberDeviceClass.SIGNAL_STRENGTH
    _attr_entity_category = EntityCategory.CONFIG
    # _attr_entity_registry_enabled_default = False
    _attr_native_min_value = -127
    _attr_native_max_value = 0
    _attr_native_step = 1
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: BermudaDataUpdateCoordinator,
        entry: BermudaConfigEntry,
        address: str,
    ) -> None:
        """Initialise the number entity."""
        self.restored_data: NumberExtraStoredData | None = None
        super().__init__(coordinator, entry, address)

    async def async_added_to_hass(self) -> None:
        """Restore values from HA storage on startup."""
        await super().async_added_to_hass()
        self.restored_data = await self.async_get_last_number_data()
        if self.restored_data is not None and self.restored_data.native_value is not None:
            self.coordinator.devices[self.address].set_ref_power(self.restored_data.native_value)

    @property
    def native_value(self) -> float | None:
        """Return value of number."""
        # if self.restored_data is not None and self.restored_data.native_value is not None:
        #     return self.restored_data.native_value
        return self.coordinator.devices[self.address].ref_power
        return 0

    async def async_set_native_value(self, value: float) -> None:
        """Set value."""
        self.coordinator.devices[self.address].set_ref_power(value)
        self.async_write_ha_state()
        # Beware that STATE_DUMP_INTERVAL for restore_state's dump_state
        # is 15 minutes, so if HA is killed instead of exiting cleanly,
        # updated values may not be restored. Tempting to schedule a dump
        # here, since updates to calib will be infrequent, but users are
        # moderately likely to restart HA after playing with them.

    @property
    def unique_id(self):
        """
        "Uniquely identify this sensor so that it gets stored in the entity_registry,
        and can be maintained / renamed etc by the user.
        """
        return f"{self._device.unique_id}_ref_power"

    # @property
    # def extra_state_attributes(self) -> Mapping[str, Any]:
    #     """Return extra state attributes for this device."""
    #     return {"scanner": self._device.area_scanner, "area": self._device.area_name}

    # @property
    # def state(self) -> str:
    #     """Return the state of the device."""
    #     return self._device.zone

    # @property
    # def source_type(self) -> SourceType:
    #     """Return the source type, eg gps or router, of the device."""
    #     return SourceType.BLUETOOTH_LE

    # @property
    # def icon(self) -> str:
    #     """Return device icon."""
    #     return "mdi:bluetooth-connect" if self._device.zone == STATE_HOME else "mdi:bluetooth-off"


class BermudaScannerRSSIOffset(BermudaEntity, RestoreNumber):
    """Number entity for per-scanner RSSI offset calibration."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "RSSI Offset"
    _attr_translation_key = "scanner_rssi_offset"
    _attr_device_class = NumberDeviceClass.SIGNAL_STRENGTH
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = -127
    _attr_native_max_value = 127
    _attr_native_step = 1
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: BermudaDataUpdateCoordinator,
        entry: BermudaConfigEntry,
        address: str,
    ) -> None:
        """Initialise the scanner RSSI offset number entity."""
        self.restored_data: NumberExtraStoredData | None = None
        super().__init__(coordinator, entry, address)

    async def async_added_to_hass(self) -> None:
        """Restore values from HA storage on startup."""
        await super().async_added_to_hass()
        self.restored_data = await self.async_get_last_number_data()
        # Trigger reload so BermudaAdvert picks up restored values
        if self.restored_data is not None and self.restored_data.native_value is not None:
            self.coordinator.reload_all_advert_configs()

    @property
    def native_value(self) -> float | None:
        """Return value of RSSI offset."""
        if self.restored_data is not None and self.restored_data.native_value is not None:
            return self.restored_data.native_value
        # Default to 0 (no offset)
        return 0.0

    async def async_set_native_value(self, value: float) -> None:
        """Set RSSI offset value."""
        # Store the value so it persists
        self.restored_data = NumberExtraStoredData(native_value=value, native_max_value=None, native_min_value=None, native_step=None, native_unit_of_measurement=None)
        self.async_write_ha_state()
        # Trigger BermudaAdvert configs to reload
        self.coordinator.reload_all_advert_configs()

    @property
    def unique_id(self):
        """Uniquely identify this entity."""
        return f"{self._device.unique_id}_scanner_rssi_offset"


class BermudaScannerAttenuation(BermudaEntity, RestoreNumber):
    """Number entity for per-scanner attenuation factor."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Attenuation"
    _attr_translation_key = "scanner_attenuation"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 1
    _attr_native_max_value = 10
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: BermudaDataUpdateCoordinator,
        entry: BermudaConfigEntry,
        address: str,
    ) -> None:
        """Initialise the scanner attenuation number entity."""
        self.restored_data: NumberExtraStoredData | None = None
        super().__init__(coordinator, entry, address)

    async def async_added_to_hass(self) -> None:
        """Restore values from HA storage on startup."""
        await super().async_added_to_hass()
        self.restored_data = await self.async_get_last_number_data()

    @property
    def native_value(self) -> float | None:
        """Return value of attenuation."""
        if self.restored_data is not None and self.restored_data.native_value is not None:
            return self.restored_data.native_value
        # Default to global config value
        return float(self.coordinator.options.get("attenuation", 3.0))

    async def async_set_native_value(self, value: float) -> None:
        """Set attenuation value."""
        self.restored_data = NumberExtraStoredData(native_value=value, native_max_value=None, native_min_value=None, native_step=None, native_unit_of_measurement=None)
        self.async_write_ha_state()
        # Trigger BermudaAdvert configs to reload
        self.coordinator.reload_all_advert_configs()

    @property
    def unique_id(self):
        """Uniquely identify this entity."""
        return f"{self._device.unique_id}_scanner_attenuation"


class BermudaScannerMaxRadius(BermudaEntity, RestoreNumber):
    """Number entity for per-scanner maximum detection radius."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Max Radius"
    _attr_translation_key = "scanner_max_radius"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "m"
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: BermudaDataUpdateCoordinator,
        entry: BermudaConfigEntry,
        address: str,
    ) -> None:
        """Initialise the scanner max radius number entity."""
        self.restored_data: NumberExtraStoredData | None = None
        super().__init__(coordinator, entry, address)

    async def async_added_to_hass(self) -> None:
        """Restore values from HA storage on startup."""
        await super().async_added_to_hass()
        self.restored_data = await self.async_get_last_number_data()

    @property
    def native_value(self) -> float | None:
        """Return value of max radius."""
        if self.restored_data is not None and self.restored_data.native_value is not None:
            return self.restored_data.native_value
        # Default to global config value
        return float(self.coordinator.options.get("max_area_radius", 20.0))

    async def async_set_native_value(self, value: float) -> None:
        """Set max radius value."""
        self.restored_data = NumberExtraStoredData(native_value=value, native_max_value=None, native_min_value=None, native_step=None, native_unit_of_measurement=None)
        self.async_write_ha_state()
        # Note: max_radius is not currently used by BermudaAdvert, so no reload needed yet

    @property
    def unique_id(self):
        """Uniquely identify this entity."""
        return f"{self._device.unique_id}_scanner_max_radius"
