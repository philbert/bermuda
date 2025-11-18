# Bermuda BLE Trilateration - Repository Structure and Functionality

## Overview

Bermuda BLE Trilateration is a custom integration for Home Assistant that enables room-level presence detection and tracking of Bluetooth Low Energy (BLE) devices. The integration uses multiple Bluetooth proxies (ESPHome devices or Shelly Gen2+ devices) to determine which area (room) a Bluetooth device is currently in, and can potentially triangulate device positions.

**Project Information:**
- **Domain:** `bermuda`
- **Version:** Managed via git tags (0.0.0 in repository)
- **Home Assistant Minimum Version:** 2025.3
- **Integration Type:** Device
- **IoT Class:** Calculated
- **Repository:** https://github.com/agittins/bermuda
- **Installation:** Available via HACS (Home Assistant Community Store)

## Core Functionality

### What Bermuda Does

1. **Area-Based Device Location**: Tracks Bluetooth devices and determines which room/area they are in
2. **Distance Calculation**: Calculates approximate distance from each Bluetooth receiver to tracked devices
3. **Device Tracking**: Creates `device_tracker` entities that can be linked to "Person" entities for Home/Away tracking
4. **iBeacon Support**: Handles iBeacon devices, including those with randomized MAC addresses
5. **Private BLE Device Support**: Works with iOS and Android devices using IRK (Identity Resolving Keys) via the `private_ble_device` core component
6. **Configurable Parameters**: Allows tuning of RSSI reference levels, environmental attenuation, and tracking radius
7. **Data Export**: Provides comprehensive device data via the `bermuda.dump_devices` service

### Key Features

- Room presence detection without requiring additional hardware beyond ESP32 Bluetooth proxies or Shelly Plus devices
- Support for multiple device types: phones, smart watches, beacon tiles, thermometers, etc.
- Configurable sensor creation for chosen devices
- Comprehensive debugging and diagnostic information
- Integration with Home Assistant's area and floor registries

## Repository Structure

```
bermuda/
├── .github/                      # GitHub workflows and configuration
│   ├── dependabot.yml           # Dependency update configuration
│   ├── FUNDING.yml              # Sponsorship information
│   ├── labels.yml               # Issue label definitions
│   └── release-drafter.yml      # Release automation configuration
│
├── custom_components/bermuda/    # Main integration code
│   ├── __init__.py              # Integration setup and entry point
│   ├── bermuda_advert.py        # Advertisement packet handling
│   ├── bermuda_device.py        # Device representation and tracking logic
│   ├── bermuda_irk.py           # IRK (Identity Resolving Key) handling
│   ├── binary_sensor.py         # Binary sensor platform (currently disabled)
│   ├── config_flow.py           # Configuration UI flow
│   ├── const.py                 # Constants and configuration defaults
│   ├── coordinator.py           # Data update coordinator
│   ├── device_tracker.py        # Device tracker platform
│   ├── diagnostics.py           # Diagnostic information provider
│   ├── entity.py                # Base entity class
│   ├── log_spam_less.py         # Logging rate limiter
│   ├── manifest.json            # Integration metadata
│   ├── number.py                # Number entity platform (for configuration)
│   ├── sensor.py                # Sensor platform (area, distance, etc.)
│   ├── strings.json             # UI strings and translations
│   ├── switch.py                # Switch platform (currently disabled)
│   ├── util.py                  # Utility functions
│   │
│   ├── manufacturer_identification/  # Bluetooth manufacturer data
│   │   ├── company_identifiers.yaml  # Company ID to name mapping
│   │   └── member_uuids.yaml         # Bluetooth member UUID mapping
│   │
│   └── translations/            # Localization files
│       └── en.json              # English translations
│
├── docs/                        # Documentation directory
├── img/                         # Images and screenshots
│   └── screenshots/             # UI screenshots
├── scripts/                     # Development and utility scripts
├── tests/                       # Test suite
├── .vscode/                     # VS Code configuration
│
├── .devcontainer.json          # Dev container configuration
├── .gitattributes              # Git attributes
├── .gitignore                  # Git ignore rules
├── .isort.cfg                  # Import sorting configuration
├── .pre-commit-config.yaml     # Pre-commit hooks
├── CONTRIBUTING.md             # Contribution guidelines
├── hacs.json                   # HACS integration metadata
├── info.md                     # HACS info display
├── LICENSE                     # MIT License
├── pyproject.toml              # Python project configuration
├── pytest.ini                  # Pytest configuration
├── README.md                   # Main documentation
├── requirements.txt            # Runtime dependencies
├── requirements_dev.txt        # Development dependencies
├── requirements_test.txt       # Testing dependencies
└── setup.cfg                   # Setup configuration
```

## Core Components

### 1. BermudaDevice (`bermuda_device.py`)

Internal representation of a Bluetooth device. Key characteristics:

- **Not an HA Entity**: Represents all discovered devices, not just tracked ones
- **Device Types**: Can represent both receivers (scanners/proxies) and transmitters (tracked devices)
- **Naming System**: Maintains multiple name sources (Bluetooth, device registry, user-defined)
- **Address Handling**: Supports various address types including MAC addresses, iBeacon UUIDs, and IRKs
- **Metadevice Support**: Creates "meta-devices" for beacons and private BLE devices to aggregate data from multiple source addresses

### 2. Data Update Coordinator (`coordinator.py`)

Manages the Bluetooth data processing cycle:

- **Update Interval**: Processes Bluetooth data every ~1 second (`UPDATE_INTERVAL = 1.05`)
- **Sensor Update Interval**: User-configurable, default 10 seconds
- **Device Management**: Maintains device list, prunes stale devices
- **Scanner Detection**: Automatically discovers and tracks Bluetooth proxy devices
- **Area Assignment**: Determines which area a device is in based on signal strength

### 3. Platform Implementations

#### Sensor Platform (`sensor.py`)
Creates sensor entities for tracked devices:
- Area sensor (which room the device is in)
- Distance sensor (approximate distance)
- Additional diagnostic sensors (disabled by default)

#### Device Tracker Platform (`device_tracker.py`)
Creates device tracker entities for home/away detection:
- Can be linked to Person entities
- Configurable timeout for "Not Home" status
- Default timeout: 30 seconds

#### Number Platform (`number.py`)
Provides number entities for per-device configuration:
- Reference power adjustment
- Other device-specific tuning parameters

### 4. Advertisement Handling (`bermuda_advert.py`)

Processes Bluetooth advertisement packets:
- Timestamp tracking
- RSSI (signal strength) measurements
- Distance calculations
- Historical data maintenance

### 5. IRK Support (`bermuda_irk.py`)

Handles Identity Resolving Keys for private BLE devices:
- Resolves randomized MAC addresses to known devices
- Integrates with Home Assistant's `private_ble_device` component
- Supports both iOS and Android devices

### 6. Configuration Flow (`config_flow.py`)

Provides the UI for:
- Initial integration setup
- Device selection and configuration
- Scanner configuration (area assignment, RSSI offsets)
- Global settings (attenuation, reference power, max radius, etc.)

## Data Flow

1. **Bluetooth Advertisement Reception**
   - ESPHome proxies or Shelly devices receive BLE advertisements
   - Home Assistant's Bluetooth backend distributes advertisements to integrations

2. **Advertisement Processing**
   - Coordinator receives advertisement data every ~1 second
   - Creates or updates `BermudaDevice` entries
   - Stores RSSI values and timestamps in advertisement history

3. **Distance Calculation**
   - Uses RSSI (signal strength) to estimate distance
   - Applies environmental attenuation factor
   - Maintains smoothed distance values

4. **Area Determination**
   - Compares signal strengths from all scanners
   - Selects the area with strongest, freshest signal
   - Applies maximum radius filtering

5. **Sensor Updates**
   - Updates sensor entities at user-configured intervals (default 10s)
   - Marks sensors as unavailable after timeout period
   - Updates device tracker entities with home/away status

## Key Constants and Configuration

### Timeouts and Intervals
- `UPDATE_INTERVAL`: 1.05 seconds (Bluetooth processing cycle)
- `DEFAULT_UPDATE_INTERVAL`: 10 seconds (sensor updates)
- `DISTANCE_TIMEOUT`: 30 seconds (mark distance as stale)
- `DEFAULT_DEVTRACK_TIMEOUT`: 30 seconds (mark device as not home)
- `AREA_MAX_AD_AGE`: Maximum age for area-winning advertisements

### Distance and Signal
- `DEFAULT_ATTENUATION`: 3 (environmental signal attenuation factor)
- `DEFAULT_REF_POWER`: -55.0 dBm (RSSI at 1 metre)
- `DEFAULT_MAX_RADIUS`: 20 metres (maximum tracking radius)
- `DISTANCE_INFINITE`: 999 (represents unknown/infinite distance)
- `DEFAULT_MAX_VELOCITY`: 3 m/s (ignore faster movements)

### Device Management
- `PRUNE_MAX_COUNT`: 1000 (maximum device entries)
- `PRUNE_TIME_INTERVAL`: 180 seconds (pruning frequency)
- `PRUNE_TIME_DEFAULT`: 86400 seconds (1 day for regular devices)
- `PRUNE_TIME_UNKNOWN_IRK`: 240 seconds (resolvable private addresses)
- `PRUNE_TIME_KNOWN_IRK`: 16 minutes (known private BLE devices)

### Smoothing
- `DEFAULT_SMOOTHING_SAMPLES`: 20 (samples for distance averaging)
- `HIST_KEEP_COUNT`: 10 (historical measurements per scanner)

## Dependencies

### Home Assistant Core Components
- `bluetooth_adapters`: Bluetooth adapter management
- `device_tracker`: Device tracking functionality
- `private_ble_device`: IRK support for iOS/Android devices

### External Requirements
The integration has minimal external dependencies and primarily relies on Home Assistant's built-in Bluetooth capabilities.

## Device Types and Address Handling

### Address Types
- `BDADDR_TYPE_OTHER`: Standard 48-bit MAC addresses
- `BDADDR_TYPE_RANDOM_RESOLVABLE`: Resolvable private addresses (requires IRK)
- `BDADDR_TYPE_RANDOM_STATIC`: Static random addresses
- `BDADDR_TYPE_RANDOM_UNRESOLVABLE`: Non-resolvable random addresses
- `ADDR_TYPE_IBEACON`: iBeacon UUID identifiers
- `ADDR_TYPE_PRIVATE_BLE_DEVICE`: Private BLE device identifiers

### Metadevice Types
- `METADEVICE_TYPE_IBEACON_SOURCE`: Source MAC sending beacon packets
- `METADEVICE_IBEACON_DEVICE`: Aggregated iBeacon tracking device
- `METADEVICE_TYPE_PRIVATE_BLE_SOURCE`: Current random MAC of private BLE device
- `METADEVICE_PRIVATE_BLE_DEVICE`: Aggregated private BLE tracking device

## Services

### bermuda.dump_devices
Returns comprehensive internal state data:
- All tracked devices and their properties
- Distance measurements from each scanner
- Advertisement history
- Configuration data
- Can be filtered by device address/UUID
- Output format may change between versions

## Development Information

### Code Quality Tools
- **Black**: Code formatting
- **isort**: Import sorting
- **pre-commit**: Git hooks for quality checks
- **pytest**: Testing framework
- **ruff**: Modern Python linter

### Project Origin
Generated from the Home Assistant Custom Component Cookiecutter template by @oncleben31, based on @Ludeeus's integration_blueprint.

### Testing
Tests are located in the `tests/` directory. Run with pytest.

### Contributing
See `CONTRIBUTING.md` for guidelines on contributing to the project.

## Usage Notes

### Hardware Requirements
- **Bluetooth Proxies**: One or more of:
  - ESPHome devices with `bluetooth_proxy` component (e.g., D1-Mini32 boards)
  - Shelly Plus or later devices with Bluetooth proxying enabled
  - USB Bluetooth on HA host (limited functionality, no timestamps)

### Setup Process
1. Install via HACS or manually
2. Add integration in Settings > Devices & Services
3. Configure which Bluetooth devices to track
4. Assign areas to scanner devices
5. Optionally tune RSSI offsets and reference power per scanner

### Best Practices
- Place Bluetooth proxies in different rooms for accurate area detection
- Assign correct areas to each scanner in the configuration
- Use at least 3 scanners for potential trilateration
- Tune attenuation factor based on your home's construction
- Monitor the dump_devices service output for troubleshooting

## Future Goals

- Full trilateration with coordinate-based positioning
- Map-based device visualization
- Enhanced tracking algorithms

## License

MIT License - See LICENSE file for details

## Maintainer

@agittins (Ashley Gittins)

## Support and Community

- **Wiki**: Primary documentation source
- **GitHub Discussions**: User guides and Q&A
- **Home Assistant Community Forum**: User assistance and discussion
- **Discord**: Community chat
- **Sponsorship**: GitHub Sponsors, Buy Me a Coffee, Patreon
