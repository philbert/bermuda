"""Per-floor Z height configuration store for Bermuda."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

STORAGE_VERSION = 1
STORAGE_KEY = "bermuda/floor_config"


@dataclass
class FloorZConfig:
    """Per-floor surface height configuration."""

    floor_id: str
    floor_z_m: float | None = None      # Fixed surface height in metres
    floor_z_max_m: float | None = None  # Upper bound for range-mode (e.g. street level)


class FloorConfigStore:
    """Persist per-floor Z height configuration outside config entry options."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise the store."""
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._configs: dict[str, FloorZConfig] = {}
        self._loaded = False

    async def async_load(self) -> None:
        """Load floor config from storage."""
        if self._loaded:
            return
        loaded = await self._store.async_load()
        if isinstance(loaded, dict):
            floors_raw = loaded.get("floors", {})
            if isinstance(floors_raw, dict):
                for floor_id, raw in floors_raw.items():
                    if not isinstance(raw, dict):
                        continue
                    self._configs[str(floor_id)] = FloorZConfig(
                        floor_id=str(floor_id),
                        floor_z_m=float(raw["floor_z_m"]) if raw.get("floor_z_m") is not None else None,
                        floor_z_max_m=float(raw["floor_z_max_m"]) if raw.get("floor_z_max_m") is not None else None,
                    )
        self._loaded = True

    async def async_save(self) -> None:
        """Persist current configuration to storage."""
        floors_data: dict[str, dict[str, Any]] = {}
        for floor_id, cfg in self._configs.items():
            entry: dict[str, Any] = {}
            if cfg.floor_z_m is not None:
                entry["floor_z_m"] = cfg.floor_z_m
            if cfg.floor_z_max_m is not None:
                entry["floor_z_max_m"] = cfg.floor_z_max_m
            floors_data[floor_id] = entry
        await self._store.async_save({"floors": floors_data})

    def get(self, floor_id: str | None) -> FloorZConfig | None:
        """Return the Z config for a floor, or None if unconfigured."""
        if floor_id is None:
            return None
        return self._configs.get(floor_id)

    async def async_set(
        self,
        floor_id: str,
        floor_z_m: float | None,
        floor_z_max_m: float | None = None,
    ) -> None:
        """Set Z config for a floor and persist."""
        self._configs[floor_id] = FloorZConfig(
            floor_id=floor_id,
            floor_z_m=floor_z_m,
            floor_z_max_m=floor_z_max_m,
        )
        await self.async_save()

    @property
    def all_configs(self) -> dict[str, FloorZConfig]:
        """Return a shallow copy of all floor configs."""
        return dict(self._configs)
