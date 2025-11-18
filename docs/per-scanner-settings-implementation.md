# Implementation Plan: Per-Scanner Settings (ESPresense-style)

## Goal
Make Bermuda more like ESPresense by adding per-scanner configuration for:
1. **Absorption/Attenuation Factor** - adjusts for room characteristics (walls, furniture, etc.)
2. **Maximum Distance Cutoff** - filters out devices beyond a certain distance from each scanner

## Current State Analysis

### Existing Configuration Structure

**Global Settings** (apply to all scanners):
- `CONF_MAX_RADIUS` (default: 20m) - Global maximum tracking distance
- `CONF_ATTENUATION` (default: 3) - Environmental signal attenuation factor
- `CONF_REF_POWER` (default: -55.0 dBm) - Expected RSSI at 1 meter

**Per-Scanner Settings** (already partially implemented):
- `CONF_RSSI_OFFSETS` - Dictionary with scanner address as key, RSSI offset as value
  - Example: `{"aa:bb:cc:dd:ee:ff": 5, "11:22:33:44:55:66": -3}`
  - Applied in `bermuda_advert.py:283` during distance calculation

### Key Code Locations

1. **Distance Calculation** - `bermuda_advert.py:283`
   ```python
   distance = rssi_to_metres(self.rssi + self.conf_rssi_offset, ref_power, self.conf_attenuation)
   ```

2. **Configuration Access** - `bermuda_advert.py:97-100`
   ```python
   self.conf_rssi_offset = self.options.get(CONF_RSSI_OFFSETS, {}).get(self.scanner_address, 0)
   self.conf_ref_power = self.options.get(CONF_REF_POWER)
   self.conf_attenuation = self.options.get(CONF_ATTENUATION)
   self.conf_max_velocity = self.options.get(CONF_MAX_VELOCITY)
   ```

3. **Area Determination** - `coordinator.py:1310-1356`
   ```python
   _max_radius = self.options.get(CONF_MAX_RADIUS, DEFAULT_MAX_RADIUS)
   ...
   if challenger.rssi_distance > _max_radius:
       continue  # Scanner reading is too far away
   ```

4. **Config Flow UI** - `config_flow.py:463-539`
   - `async_step_calibration2_scanners()` handles per-scanner RSSI offset configuration

## Proposed Changes

### 1. New Configuration Constants (`const.py`)

Add new per-scanner configuration keys:

```python
# Per-scanner configuration dictionaries
CONF_SCANNER_ATTENUATION = "scanner_attenuation"
DOCS[CONF_SCANNER_ATTENUATION] = "Per-scanner attenuation factor for environmental effects"

CONF_SCANNER_MAX_RADIUS = "scanner_max_radius"
DOCS[CONF_SCANNER_MAX_RADIUS] = "Per-scanner maximum tracking distance in meters"

# Default values when not configured
DEFAULT_SCANNER_ATTENUATION = None  # None means use global default
DEFAULT_SCANNER_MAX_RADIUS = None   # None means use global default
```

### 2. Data Structure

Each per-scanner setting will be stored as a dictionary with scanner MAC address as the key:

```python
# Example options structure after implementation:
{
    # Global defaults (fallback values)
    "max_area_radius": 20,
    "attenuation": 3.0,
    "ref_power": -55.0,

    # Per-scanner overrides
    "scanner_attenuation": {
        "aa:bb:cc:dd:ee:ff": 2.5,  # Office scanner - less walls
        "11:22:33:44:55:66": 4.0,  # Garage scanner - concrete walls
    },
    "scanner_max_radius": {
        "aa:bb:cc:dd:ee:ff": 10.0,  # Office - smaller room
        "11:22:33:44:55:66": 25.0,  # Garage - larger space
    },

    # Existing per-scanner settings
    "rssi_offsets": {
        "aa:bb:cc:dd:ee:ff": 2,
        "11:22:33:44:55:66": -3,
    }
}
```

### 3. Update `BermudaAdvert` Class (`bermuda_advert.py`)

**Modify initialization** (around line 97-101):

```python
# Get scanner-specific settings with fallback to global defaults
scanner_attenuations = self.options.get(CONF_SCANNER_ATTENUATION, {})
self.conf_attenuation = scanner_attenuations.get(
    self.scanner_address,
    self.options.get(CONF_ATTENUATION, DEFAULT_ATTENUATION)
)

scanner_max_radii = self.options.get(CONF_SCANNER_MAX_RADIUS, {})
self.conf_max_radius = scanner_max_radii.get(
    self.scanner_address,
    self.options.get(CONF_MAX_RADIUS, DEFAULT_MAX_RADIUS)
)

# Keep existing RSSI offset
self.conf_rssi_offset = self.options.get(CONF_RSSI_OFFSETS, {}).get(self.scanner_address, 0)
self.conf_ref_power = self.options.get(CONF_REF_POWER, DEFAULT_REF_POWER)
self.conf_max_velocity = self.options.get(CONF_MAX_VELOCITY, DEFAULT_MAX_VELOCITY)
self.conf_smoothing_samples = self.options.get(CONF_SMOOTHING_SAMPLES, DEFAULT_SMOOTHING_SAMPLES)
```

**No changes needed to `_update_raw_distance()`** - it already uses `self.conf_attenuation` from instance.

### 4. Update Area Determination (`coordinator.py`)

**Modify `_refresh_area_by_min_distance()`** (around line 1310-1356):

```python
def _refresh_area_by_min_distance(self, device: BermudaDevice):
    """Very basic Area setting by finding closest proxy to a given device."""
    incumbent: BermudaAdvert | None = device.area_advert

    # Remove global max_radius lookup
    # _max_radius = self.options.get(CONF_MAX_RADIUS, DEFAULT_MAX_RADIUS)

    nowstamp = monotonic_time_coarse()
    tests = self.AreaTests()
    tests.device = device.name
    _superchatty = False

    for challenger in device.adverts.values():
        # ... existing checks ...

        # NEW: Use per-scanner max_radius instead of global
        # Each BermudaAdvert now has its own conf_max_radius
        if (
            challenger.rssi_distance is None
            or challenger.rssi_distance > challenger.conf_max_radius  # CHANGED
            or challenger.area_id is None
        ):
            continue

        # ... rest of the logic unchanged ...
```

### 5. Enhanced Config Flow UI (`config_flow.py`)

Create a new step `async_step_calibration3_advanced_scanners()`:

```python
async def async_step_calibration3_advanced_scanners(self, user_input=None):
    """
    Per-scanner advanced configuration: attenuation and max distance.

    Similar to calibration2_scanners but for attenuation and max_radius
    instead of RSSI offsets. More user-friendly than RSSI adjustments.
    """
    if user_input is not None:
        if user_input.get(CONF_SAVE_AND_CLOSE):
            # Build per-scanner dicts
            scanner_attenuations = {}
            scanner_max_radii = {}

            for scanner_address in self.coordinator.scanner_list:
                scanner_name = self.coordinator.devices[scanner_address].name
                scanner_data = user_input[CONF_SCANNER_INFO].get(scanner_name, {})

                # Store attenuation if provided (not None)
                if (atten := scanner_data.get("attenuation")) is not None:
                    scanner_attenuations[scanner_address] = max(min(float(atten), 10.0), 1.0)

                # Store max_radius if provided (not None)
                if (max_rad := scanner_data.get("max_radius")) is not None:
                    scanner_max_radii[scanner_address] = max(min(float(max_rad), 100.0), 1.0)

            self.options.update({
                CONF_SCANNER_ATTENUATION: scanner_attenuations,
                CONF_SCANNER_MAX_RADIUS: scanner_max_radii,
            })
            return await self._update_options()

        # Store for refresh
        self._last_scanner_info = user_input[CONF_SCANNER_INFO]
        self._last_device = user_input.get(CONF_DEVICES)

    # Build default values from saved config
    saved_attenuations = self.options.get(CONF_SCANNER_ATTENUATION, {})
    saved_max_radii = self.options.get(CONF_SCANNER_MAX_RADIUS, {})
    global_attenuation = self.options.get(CONF_ATTENUATION, DEFAULT_ATTENUATION)
    global_max_radius = self.options.get(CONF_MAX_RADIUS, DEFAULT_MAX_RADIUS)

    scanner_config_dict = {}
    for scanner_address in self.coordinator.scanner_list:
        scanner_name = self.coordinator.devices[scanner_address].name
        scanner_config_dict[scanner_name] = {
            "attenuation": saved_attenuations.get(scanner_address, global_attenuation),
            "max_radius": saved_max_radii.get(scanner_address, global_max_radius),
        }

    data_schema = {
        vol.Optional(CONF_DEVICES): DeviceSelector(DeviceSelectorConfig(integration=DOMAIN)),
        vol.Required(
            CONF_SCANNER_INFO,
            default=scanner_config_dict if not self._last_scanner_info else self._last_scanner_info,
        ): ObjectSelector(),
        vol.Optional(CONF_SAVE_AND_CLOSE, default=False): vol.Coerce(bool),
    }

    # Build description with distance estimates if device selected
    description_suffix = "Configure per-scanner settings. Lower attenuation for open spaces, higher for rooms with thick walls."

    if self._last_device and isinstance(self._last_scanner_info, dict):
        device = self._get_bermuda_device_from_registry(self._last_device)
        if device is not None:
            results_str = "\n\n**Current Estimated Distances:**\n\n"
            results_str += "| Scanner | Distance | Attenuation | Max Radius |\n"
            results_str += "|---------|----------|-------------|------------|\n"

            for scanner_address in self.coordinator.scanner_list:
                scanner_name = self.coordinator.devices[scanner_address].name
                scanner_data = self._last_scanner_info.get(scanner_name, {})
                atten = scanner_data.get("attenuation", global_attenuation)
                max_rad = scanner_data.get("max_radius", global_max_radius)

                if (advert := device.get_scanner(scanner_address)) is not None:
                    # Recalculate with new settings
                    if advert.rssi is not None:
                        distance = rssi_to_metres(
                            advert.rssi + advert.conf_rssi_offset,
                            self.options.get(CONF_REF_POWER, DEFAULT_REF_POWER),
                            atten,
                        )
                        status = "✓" if distance <= max_rad else "✗ (too far)"
                        results_str += f"| {scanner_name} | {distance:.2f}m {status} | {atten} | {max_rad}m |\n"

            description_suffix = results_str

    return self.async_show_form(
        step_id="calibration3_advanced_scanners",
        data_schema=vol.Schema(data_schema),
        description_placeholders={"suffix": description_suffix},
    )
```

**Update the main calibration menu** (`async_step_init()`) to include the new option:

```python
# In the calibration menu options, add:
"calibration3_advanced_scanners": "Advanced Per-Scanner Settings (Attenuation, Max Distance)",
```

### 6. Backwards Compatibility

The implementation maintains full backwards compatibility:

1. **Existing configs** will continue to work - global settings are still used as defaults
2. **Migration not required** - per-scanner settings are optional and default to global values
3. **RSSI offsets preserved** - existing calibration2_scanners step remains unchanged
4. **Gradual adoption** - users can configure per-scanner settings for some scanners while others use defaults

### 7. User Experience Improvements

**Benefits over current RSSI offset approach:**

| Current (RSSI Offset) | Proposed (Per-Scanner Settings) |
|----------------------|--------------------------------|
| Obscure RSSI value adjustment (-127 to +127) | Clear attenuation factor (1.0 to 10.0) |
| Requires understanding of dBm | Intuitive: lower = open space, higher = thick walls |
| Global max radius for all scanners | Each scanner has appropriate range |
| No visual feedback on effect | Shows calculated distances in real-time |
| Single calibration step | Separate basic (RSSI) and advanced (attenuation) steps |

**Example user scenarios:**

1. **Office Scanner** (open plan, drywall):
   - Attenuation: 2.5 (lower than default 3.0)
   - Max Radius: 10m (smaller room)

2. **Garage Scanner** (concrete walls, metal doors):
   - Attenuation: 4.5 (higher than default)
   - Max Radius: 25m (larger space, but signals don't penetrate walls)

3. **Bedroom Scanner** (upstairs, wood/plaster):
   - Attenuation: 3.0 (use global default)
   - Max Radius: 15m

## Implementation Checklist

### Phase 1: Core Functionality
- [ ] Add new constants to `const.py`
- [ ] Update `BermudaAdvert.__init__()` to read per-scanner settings
- [ ] Update `coordinator.py` area determination to use per-scanner max_radius
- [ ] Add per-scanner settings to coordinator initialization defaults

### Phase 2: Configuration UI
- [ ] Create `async_step_calibration3_advanced_scanners()` in `config_flow.py`
- [ ] Add menu option in `async_step_init()`
- [ ] Add helper text and descriptions in `strings.json` / translations

### Phase 3: Testing
- [ ] Test with mixed configuration (some scanners with custom settings, some using defaults)
- [ ] Test backwards compatibility with existing configs
- [ ] Test extreme values (attenuation 1.0 vs 10.0, max_radius 1m vs 100m)
- [ ] Verify distance calculations update correctly in UI

### Phase 4: Documentation
- [ ] Update README.md with new per-scanner configuration options
- [ ] Add examples of typical attenuation values for different environments
- [ ] Update wiki documentation
- [ ] Create migration guide for users currently using RSSI offsets

## Testing Scenarios

### Test 1: New Installation
1. Install integration with defaults
2. Configure basic device tracking
3. Navigate to advanced scanner settings
4. Set different attenuation/max_radius for each scanner
5. Verify devices tracked correctly with per-scanner settings

### Test 2: Existing Installation Upgrade
1. Start with existing config using RSSI offsets
2. Upgrade to new version
3. Verify existing tracking continues to work
4. Add per-scanner settings for one scanner
5. Verify mixed global/per-scanner configuration works

### Test 3: Edge Cases
1. Set attenuation to 1.0 (minimum) - should give longer distance estimates
2. Set attenuation to 10.0 (maximum) - should give shorter distance estimates
3. Set max_radius to 1.0m - should only detect very close devices
4. Set max_radius to 100m - should detect all devices in range
5. Remove per-scanner setting - should fall back to global default

## Migration Path for Existing RSSI Offset Users

Users currently using RSSI offsets can:

1. **Keep using RSSI offsets** - they continue to work as before
2. **Switch to attenuation** - provides more intuitive control
3. **Use both** - RSSI offset applied first, then attenuation used in distance calculation

**Conversion guidance** (approximate):
- RSSI offset of +10 dBm ≈ Attenuation factor increase of 0.3-0.5
- RSSI offset of -10 dBm ≈ Attenuation factor decrease of 0.3-0.5

Users should recalibrate using the new per-scanner settings rather than trying to convert.

## Future Enhancements

1. **Auto-calibration**: Walk a device through the house and automatically determine scanner attenuation
2. **Templates**: Preset attenuation values for common environments (office, home, warehouse)
3. **Per-scanner ref_power**: Allow different reference power per scanner (different antenna gains)
4. **Visualization**: Show scanner ranges as circles on a floor plan
5. **Scanner profiles**: Save/load complete scanner configuration sets

## ESPresense Feature Comparison

After implementation, Bermuda will have feature parity with ESPresense for:
- ✅ Per-scanner absorption/attenuation factor
- ✅ Per-scanner maximum distance cutoff
- ✅ Flexible room-specific tuning
- ✅ Visual feedback during configuration

Additional advantages over ESPresense:
- Integrated with Home Assistant device registry
- No separate MQTT broker required
- Leverages existing ESPHome bluetooth proxy infrastructure
- Automatic iBeacon and Private BLE device support
