"""Tests for coordinator trilateration decision path."""

from __future__ import annotations

import time
from types import SimpleNamespace

from custom_components.bermuda.const import DISTANCE_TIMEOUT
from custom_components.bermuda.coordinator import BermudaDataUpdateCoordinator


class _DummyDevice:
    def __init__(self, address: str, mobility_type: str = "moving"):
        self.address = address
        self.name = address
        self.prefname = address
        self.name_by_user = None
        self.name_devreg = None
        self.name_bt_local_name = None
        self.name_bt_serviceinfo = None
        self.mobility_type = mobility_type
        self.create_sensor = True
        self.adverts = {}
        self.trilat_status = "unknown"
        self.trilat_reason = "init"
        self.trilat_floor_id = None
        self.trilat_floor_name = None
        self.trilat_anchor_count = 0
        self.trilat_x_m = None
        self.trilat_y_m = None
        self.trilat_residual_m = None

    def get_mobility_type(self):
        return self.mobility_type

    def set_trilat_unknown(self, reason, floor_id=None, floor_name=None, anchor_count=0):
        self.trilat_status = "unknown"
        self.trilat_reason = reason
        self.trilat_floor_id = floor_id
        self.trilat_floor_name = floor_name
        self.trilat_anchor_count = anchor_count
        self.trilat_x_m = None
        self.trilat_y_m = None
        self.trilat_residual_m = None

    def set_trilat_solution(self, x_m, y_m, floor_id, floor_name, anchor_count, residual_m):
        self.trilat_status = "ok"
        self.trilat_reason = "ok"
        self.trilat_x_m = x_m
        self.trilat_y_m = y_m
        self.trilat_floor_id = floor_id
        self.trilat_floor_name = floor_name
        self.trilat_anchor_count = anchor_count
        self.trilat_residual_m = residual_m


def _make_advert(scanner, stamp, rssi, distance_raw):
    return SimpleNamespace(
        scanner_address=scanner.address,
        stamp=stamp,
        scanner_device=scanner,
        rssi_filtered=rssi,
        rssi=rssi,
        conf_rssi_offset=0.0,
        rssi_distance_raw=distance_raw,
        rssi_distance=distance_raw,
        trilat_range_ewma_m=None,
    )


def _make_coordinator():
    coordinator = object.__new__(BermudaDataUpdateCoordinator)
    coordinator.options = {}
    coordinator.devices = {}
    coordinator._scanners = set()
    coordinator._trilat_decision_state = {}
    coordinator.fr = SimpleNamespace(async_get_floor=lambda floor_id: SimpleNamespace(name=f"Floor {floor_id}"))
    coordinator.get_scanner_max_radius = lambda _scanner: 20.0
    coordinator.get_scanner_anchor_enabled = lambda scanner_addr: bool(
        getattr(coordinator.devices.get(scanner_addr), "anchor_enabled", False)
    )
    coordinator.get_scanner_anchor_x = lambda scanner_addr: getattr(coordinator.devices.get(scanner_addr), "anchor_x_m", None)
    coordinator.get_scanner_anchor_y = lambda scanner_addr: getattr(coordinator.devices.get(scanner_addr), "anchor_y_m", None)
    coordinator.trilat_cross_floor_penalty_db = lambda: 8.0
    return coordinator


def test_trilat_unknown_when_inputs_stale():
    """No fresh adverts should yield explicit stale_inputs."""
    coordinator = _make_coordinator()
    device = _DummyDevice("dev-a")
    scanner = SimpleNamespace(address="scanner-a", floor_id="f1", anchor_enabled=True, anchor_x_m=0.0, anchor_y_m=0.0)
    coordinator.devices[scanner.address] = scanner
    old_stamp = time.monotonic() - DISTANCE_TIMEOUT - 5
    advert = _make_advert(scanner, old_stamp, -70.0, 4.0)
    device.adverts = {("dev-a", scanner.address): advert}

    coordinator._refresh_trilateration_for_device(device)

    assert device.trilat_status == "unknown"
    assert device.trilat_reason == "stale_inputs"


def test_trilat_unknown_with_insufficient_anchors():
    """Fresh input with fewer than 3 same-floor anchors should be insufficient_anchors."""
    coordinator = _make_coordinator()
    device = _DummyDevice("dev-b")

    scanner = SimpleNamespace(
        address="scanner-a",
        floor_id="f1",
        anchor_enabled=True,
        anchor_x_m=0.0,
        anchor_y_m=0.0,
        name="Scanner A",
    )
    coordinator.devices[scanner.address] = scanner

    fresh_stamp = time.monotonic()
    advert = _make_advert(scanner, fresh_stamp, -72.0, 3.5)
    device.adverts = {("dev-b", scanner.address): advert}

    coordinator._refresh_trilateration_for_device(device)

    assert device.trilat_status == "unknown"
    assert device.trilat_reason == "insufficient_anchors"
    assert device.trilat_anchor_count == 1
