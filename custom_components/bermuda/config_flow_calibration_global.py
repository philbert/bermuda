"""Global calibration flow handlers for Bermuda config flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.helpers.selector import (
    DeviceSelector,
    DeviceSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .config_flow_helpers import get_bermuda_device_from_registry
from .const import (
    CONF_ATTENUATION,
    CONF_DEVICES,
    CONF_REF_POWER,
    CONF_SAVE_AND_CLOSE,
    CONF_SCANNERS,
    DEFAULT_ATTENUATION,
    DEFAULT_REF_POWER,
    DOMAIN,
)
from .util import rssi_to_metres

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult


class BermudaCalibrationGlobalFlowMixin:
    """Mixin class for Bermuda global calibration flow."""

    async def async_step_calibration1_global(self, user_input=None) -> ConfigFlowResult:
        """Handle global calibration flow."""
        # FIXME: This is ridiculous. But I can't yet find a better way.
        _ugly_token_hack = {
            # These are work-arounds for (broken?) placeholder substitutions.
            # I've not been able to find out why, but just having <details> in the
            # en.json will cause placeholders to break, due to *something* treating
            # the html elements as placeholders.
            "details": "<details>",
            "details_end": "</details>",
            "summary": "<summary>",
            "summary_end": "</summary>",
        }

        if user_input is not None:
            if user_input[CONF_SAVE_AND_CLOSE]:
                # Update the running options (this propagates to coordinator etc)
                self.options.update(
                    {
                        CONF_ATTENUATION: user_input[CONF_ATTENUATION],
                        CONF_REF_POWER: user_input[CONF_REF_POWER],
                    }
                )
                # Ideally, we'd like to just save out the config entry and return to the main menu.
                # Unfortunately, doing so seems to break the chosen device (for at least 15 seconds or so)
                # until it gets re-invigorated. My guess is that the link between coordinator and the
                # sensor entity might be getting broken, but not entirely sure.
                # For now disabling the return-to-menu and instead we finish out the flow.

                # Previous block for returning to menu:
                # # Let's update the options - but we don't want to call create entry as that will close the flow.
                # # This will save out the config entry:
                # self.hass.config_entries.async_update_entry(self.config_entry, options=self.options)
                # Reset last device so that the next step doesn't think it exists.
                # self._last_device = None
                # return await self.async_step_init()

                # Current block for finishing the flow:
                return await self._update_options()

            self._last_ref_power = user_input[CONF_REF_POWER]
            self._last_attenuation = user_input[CONF_ATTENUATION]
            self._last_device = user_input[CONF_DEVICES]
            self._last_scanner = user_input[CONF_SCANNERS]

        # TODO: Switch this to be a device selector when devices are made for scanners
        scanner_options = [
            SelectOptionDict(
                value=scanner,
                label=self.coordinator.devices[scanner].name if scanner in self.coordinator.devices else scanner,
            )
            for scanner in self.coordinator.scanner_list
        ]
        data_schema = {
            vol.Required(
                CONF_DEVICES,
                default=self._last_device if self._last_device is not None else vol.UNDEFINED,
            ): DeviceSelector(DeviceSelectorConfig(integration=DOMAIN)),
            vol.Required(
                CONF_SCANNERS,
                default=self._last_scanner if self._last_scanner is not None else vol.UNDEFINED,
            ): SelectSelector(
                SelectSelectorConfig(
                    options=scanner_options,
                    multiple=False,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_REF_POWER,
                default=self._last_ref_power
                if self._last_ref_power is not None
                else self.options.get(CONF_REF_POWER, DEFAULT_REF_POWER),
            ): vol.Coerce(float),
            vol.Required(
                CONF_ATTENUATION,
                default=self._last_attenuation
                if self._last_attenuation is not None
                else self.options.get(CONF_ATTENUATION, DEFAULT_ATTENUATION),
            ): vol.Coerce(float),
            vol.Optional(CONF_SAVE_AND_CLOSE, default=False): vol.Coerce(bool),
        }
        if user_input is None:
            return self.async_show_form(
                step_id="calibration1_global",
                data_schema=vol.Schema(data_schema),
                description_placeholders=_ugly_token_hack
                | {"suffix": "After you click Submit, the new distances will be shown here."},
            )
        results_str = ""
        device = get_bermuda_device_from_registry(self.hass, self.coordinator, user_input[CONF_DEVICES])
        if device is not None:
            scanner = device.get_scanner(user_input[CONF_SCANNERS])
            if scanner is None:
                return self.async_show_form(
                    step_id="calibration1_global",
                    errors={"err_scanner_no_record": "The selected scanner hasn't (yet) seen this device."},
                    data_schema=vol.Schema(data_schema),
                    description_placeholders=_ugly_token_hack
                    | {"suffix": "After you click Submit, the new distances will be shown here."},
                )

            distances = [
                rssi_to_metres(historical_rssi, self._last_ref_power, self._last_attenuation)
                for historical_rssi in scanner.hist_rssi
            ]

            # Build a markdown table showing distance and rssi history for the
            # selected device / scanner combination
            results_str = f"| {device.name} |"
            # Limit the number of columns to what's available up to a max of 5.
            cols = min(5, len(distances), len(scanner.hist_rssi))
            for i in range(cols):
                results_str += f" {i} |"
            results_str += "\n|---|"
            for i in range(cols):  # noqa for unused var i
                results_str += "---:|"

            results_str += "\n| Estimate (m) |"
            for i in range(cols):
                results_str += f" `{distances[i]:>5.2f}`|"
            results_str += "\n| RSSI Actual |"
            for i in range(cols):
                results_str += f" `{scanner.hist_rssi[i]:>5}`|"
            results_str += "\n"

        return self.async_show_form(
            step_id="calibration1_global",
            data_schema=vol.Schema(data_schema),
            description_placeholders=_ugly_token_hack
            | {
                "suffix": (
                    f"Recent distances, calculated using `ref_power = {self._last_ref_power}` "
                    f"and `attenuation = {self._last_attenuation}` (values from new...old):\n\n{results_str}"
                ),
            },
        )
